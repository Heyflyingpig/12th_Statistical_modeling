import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon
from pathlib import Path
import matplotlib.pyplot as plt

# 配置路径
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INPUT_BOUNDARY = DATA_DIR / "shaoguan_districts_official.json"
OUTPUT_GRID = DATA_DIR / "analysis_grid_500m.geojson"

def generate_fishnet(boundary_path, step=0.0045):
    """
    核心逻辑：构建覆盖研究区域的渔网格网
    step=0.0045 约为 500米
    """
    print(f">>> [Step 1] 正在加载行政边界: {boundary_path.name}")
    city = gpd.read_file(boundary_path)
    
    # 获取外接矩形范围
    xmin, ymin, xmax, ymax = city.total_bounds
    
    # 生成经纬度序列
    cols = np.arange(xmin, xmax + step, step)
    rows = np.arange(ymin, ymax + step, step)
    
    print(f">>> [Step 2] 正在生成原始网格阵列...")
    polygons = []
    for x in cols:
        for y in rows:
            # 构建矩形四个顶点
            polygons.append(Polygon([(x, y), (x + step, y), (x + step, y + step), (x, y + step)]))
    
    grid = gpd.GeoDataFrame({'geometry': polygons}, crs=city.crs)
    
    print(f">>> [Step 3] 正在执行空间相交筛选 (只保留陆地格网)...")
    # 使用 inner join 只保留与城市边界相交的格子
    final_grid = gpd.sjoin(grid, city, how="inner", predicate='intersects')
    
    # 清理冗余字段，生成唯一ID
    final_grid = final_grid[['geometry', 'name']].copy()
    final_grid = final_grid.rename(columns={'name': 'district_name'})
    final_grid['grid_id'] = [f"G_{i:06d}" for i in range(len(final_grid))]
    
    # 可视化预览
    print(f">>> [Step 4] 正在生成预览图...")
    fig, ax = plt.subplots(figsize=(10, 10))
    final_grid.plot(ax=ax, facecolor='none', edgecolor='blue', linewidth=0.1)
    plt.title(f"Generated 500m Grid for {boundary_path.stem}\nTotal Units: {len(final_grid)}")
    plt.savefig(DATA_DIR / "grid_preview.png", dpi=300)
    
    return final_grid

if __name__ == "__main__":
    if not INPUT_BOUNDARY.exists():
        print(f"❌ 错误: 未找到输入文件 {INPUT_BOUNDARY}")
    else:
        grid_gdf = generate_fishnet(INPUT_BOUNDARY)
        grid_gdf.to_file(OUTPUT_GRID, driver='GeoJSON')
        print(f"✅ 空间底座构建成功！\n文件路径: {OUTPUT_GRID}\n格网总数: {len(grid_gdf)}")
        print("💡 提示：现在你可以将此文件上传至 AI Earth 提取遥感指标了。")