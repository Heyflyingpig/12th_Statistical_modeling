import pandas as pd
import geopandas as gpd
from rasterstats import zonal_stats
from pathlib import Path
import re
import warnings

warnings.filterwarnings('ignore')

# ==========================================
# 1. 路径配置 (请确保这里的路径与你实际存放位置一致)
# ==========================================
BASE_DIR = Path(__file__).resolve().parent if '__file__' in globals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"

# ⚠️ 请将你解压后的几个G的TIF文件放在这个文件夹下
# 假设你的TIF命名包含年份，例如 "NTL_2019.tif", "global_2020.tif" 等
TIF_DIR = DATA_DIR / "tif_sources"

GRID_PATH = DATA_DIR / "scientific_grid_500m.geojson"


def inject_satellite_data():
    print(">>> [启动] 正在加载空间网格并处理坐标系...")
    grid = gpd.read_file(GRID_PATH)
    # 强制将 ID 转为字符串，防止后续 Merge 报错
    grid['grid_id'] = grid['grid_id'].astype(str)

    # 【核心要点】你的网格是 EPSG:4511，开源 TIF 是 WGS84 (EPSG:4326)
    # 必须在内存中动态转换坐标系，否则提取出来的全是空值！
    grid_wgs84 = grid.to_crs("EPSG:4326")

    csv_files = list(DATA_DIR.glob("Shaoguan_RVRI_20*.csv"))
    print(f"   - 扫描到 {len(csv_files)} 个待升级的 CSV 面板文件。")

    for csv_file in csv_files:
        # 1. 智能提取年份 (兼容 "2022 (1).csv" 这种季度命名)
        match = re.search(r"20\d{2}", csv_file.name)
        if not match:
            continue
        year = int(match.group())

        # 2. 映射 TIF 文件 (2025年用2024年的数据做平替)
        tif_year = 2024 if year == 2025 else year

        # 寻找对应年份的 TIF 文件
        tif_matches = list(TIF_DIR.glob(f"*{tif_year}*.tif"))
        if not tif_matches:
            print(f"   ❌ [跳过] 找不到包含年份 {tif_year} 的 TIF 文件，请检查 {TIF_DIR.name} 目录。")
            continue
        tif_path = tif_matches[0]

        print(f"\n>>> [处理中] 正在将 {tif_path.name} 注入到 {csv_file.name} ...")

        # 3. 核心大招：直接从 TIF 中分区提取平均亮度 (Zonal Statistics)
        # 这步可能会消耗一点内存和时间，取决于 TIF 的大小
        stats = zonal_stats(
            vectors=grid_wgs84,
            raster=str(tif_path),
            stats="mean",
            nodata=0,  # 排除背景零值干扰
            geojson_out=False
        )

        # 提取结果并填补空值（水体或无灯光区域设为 0）
        mean_light = [s['mean'] if s['mean'] is not None else 0 for s in stats]

        # 4. 构建临时挂载表
        temp_df = pd.DataFrame({
            'grid_id': grid_wgs84['grid_id'],
            'new_light': mean_light
        })

        # 5. 读取原 CSV，替换旧的 light 字段
        df = pd.read_csv(csv_file)
        df['grid_id'] = df['grid_id'].astype(str)

        # 与新灯光数据 Merge
        df = df.merge(temp_df, on='grid_id', how='left')

        # 用新提取的高精度灯光覆盖旧灯光，然后删掉多余列
        df['light'] = df['new_light'].fillna(0)
        df.drop(columns=['new_light'], inplace=True)

        # 6. 原地保存（直接覆盖旧 CSV）
        df.to_csv(csv_file, index=False)
        print(f"   ✅ [成功] {csv_file.name} 灯光数据已升级完毕！")


if __name__ == "__main__":
    inject_satellite_data()
    print("\n🎉 所有卫星数据已成功注入！现在您可以直接运行 02_RVRI_Synthesis_V5.py 了！")