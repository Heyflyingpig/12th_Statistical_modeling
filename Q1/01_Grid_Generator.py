import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon
from pathlib import Path
import matplotlib.pyplot as plt

# ==========================================
# 1. 路径设置
# ==========================================
BASE_DIR = Path(__file__).resolve().parent.parent
Q1_DIR = BASE_DIR / "Q1"
DATA_DIR = Q1_DIR / "data"
OUTPUT_DIR = Q1_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INPUT_PATH = DATA_DIR / "shaoguan_districts_official.json"
OUTPUT_PATH = DATA_DIR / "scientific_grid_500m.geojson"
PREVIEW_PATH = OUTPUT_DIR / "grid_preview_final.png"

def create_ultimate_grid():
    print(f"\n{'='*60}")
    print(f"🥇 正在执行：2026 统计建模大赛 Q1 终极科学底座")
    print(f"{'='*60}")

    # 1. 加载并强制“溶解”边界
    print("1. [读取] 正在加载并清理行政边界数据...")
    raw_city = gpd.read_file(INPUT_PATH)
    # 强制投影为 CGCS2000 3度带 CM=114E (EPSG:4511 比 4479 在本地环境更稳)
    city = raw_city.to_crs("EPSG:4511")
    
    # 计算总面积，自证科学性
    total_area_km2 = city.geometry.area.sum() / 10**6
    print(f"   - 行政边界载入成功，区县数量: {len(city)}")
    print(f"   - 该文件覆盖的总面积: {total_area_km2:.2f} km²")
    
    # 关键整改：将所有区县合并为一个完整的“韶关掩模”
    city_mask = city.dissolve()
    city_mask['geometry'] = city_mask.geometry.buffer(0.1) # 增加0.1米缓冲，消除微小缝隙

    # 2. 计算渔网
    xmin, ymin, xmax, ymax = city_mask.total_bounds
    step = 500 # 500米
    
    # 确定经纬网格点，稍微外扩一格
    cols = np.arange(xmin - step, xmax + step, step)
    rows = np.arange(ymin - step, ymax + step, step)

    print(f"2. [生成] 正在物理构建 {len(cols)*len(rows)} 个矩形采样单元...")
    polygons = []
    for x in cols:
        for y in rows:
            polygons.append(Polygon([(x, y), (x+step, y), (x+step, y+step), (x, y+step)]))
    
    grid = gpd.GeoDataFrame({'geometry': polygons}, crs="EPSG:4511")

    # 3. 执行“全境保留”筛选
    print("3. [筛选] 正在执行 100% 物理相交检测 (这步确保不漏掉任何土地)...")
    # 只要格子和韶关的大掩模有任何接触，就保留
    final_grid = gpd.sjoin(grid, city_mask, how="inner", predicate='intersects')
    
    # 4. 回挂行政区划属性 (解决 district 丢失问题)
    print("4. [属性] 正在重新挂载区县行政属性...")
    # 这次用重心点对齐区县名，防止一个格子跨两个区产生多条记录
    final_grid['centroid'] = final_grid.geometry.centroid
    # 创建一个只包含点的数据框
    points = gpd.GeoDataFrame(final_grid[['centroid']], geometry='centroid', crs="EPSG:4511")
    # 把点的区县名拉回来
    point_with_dist = gpd.sjoin(points, city[['geometry', 'name']], how="left", predicate='within')
    
    # 5. 整理最终数据
    final_grid['district'] = point_with_dist['name']
    final_grid['grid_id'] = [f"G_{i:06d}" for i in range(len(final_grid))]
    final_grid = final_grid[['grid_id', 'district', 'geometry']]
    # 填充可能落在边缘外一丁点的残余空值
    final_grid['district'] = final_grid['district'].fillna("边缘争议区")

    grid_count = len(final_grid)
    print(f"✅ [校验] 最终格网总数: {grid_count}")
    
    if grid_count < 70000:
        print("⚠️ 警告：格网数依然偏低，请检查输入的 JSON 是否包含韶关全部县市！")

    # 6. 绘图预览
    print("5. [可视化] 正在生成 100% 覆盖预览图...")
    fig, ax = plt.subplots(figsize=(12, 12))
    city.plot(ax=ax, color='#f2f2f2', edgecolor='#333333', linewidth=0.5)
    final_grid.plot(ax=ax, facecolor='none', edgecolor='blue', linewidth=0.02, alpha=0.3)
    plt.title(f"Shaoguan 500m Scientific Grid\nTotal Units: {grid_count} (Check for full coverage)")
    plt.savefig(PREVIEW_PATH, dpi=300, bbox_inches='tight')

    # 7. 导出
    print("6. [导出] 正在转回 WGS84 并导出...")
    final_grid.to_crs("EPSG:4326").to_file(OUTPUT_PATH, driver='GeoJSON')
    print(f"{'='*60}\n🌟 Q1 底座构建完美完成！数据已存入: {OUTPUT_PATH}\n{'='*60}")

if __name__ == "__main__":
    create_ultimate_grid()
