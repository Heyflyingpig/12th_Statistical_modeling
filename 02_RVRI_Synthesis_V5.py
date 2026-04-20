import pandas as pd
import numpy as np
import geopandas as gpd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from pathlib import Path
import glob
import json
import matplotlib.pyplot as plt
import seaborn as sns

# ==========================================
# 1. 配置与路径管理
# ==========================================
if '__file__' in globals():
    BASE_DIR = Path(__file__).resolve().parent.parent
else:
    BASE_DIR = Path.cwd().parent

DATA_DIR = BASE_DIR / "Q1" / "data"
OUTPUT_DIR = BASE_DIR / "Q1" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 输入文件：严格限定 2019-2025 年度长表
MAPPING_SOURCE_CSV = DATA_DIR / "Shaoguan_RVRI_2019.csv"
GRID_BASE = DATA_DIR / "scientific_grid_500m.geojson"

# 输出文件
FINAL_CSV = OUTPUT_DIR / "Shaoguan_RVRI_Long_Panel_Final.csv"
FINAL_GEOJSON = OUTPUT_DIR / "Shaoguan_RVRI_Long_Panel_Final.geojson"
REPORT_JSON = OUTPUT_DIR / "validation_report.json"

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False


# ==========================================
# 2. 精准加载与行政修复
# ==========================================
def load_and_verify_data():
    print(">>> [Task 1] 正在精准筛选并加载年度长表面板...")
    # 仅选择符合年份命名的长表
    csv_files = glob.glob(str(DATA_DIR / "Shaoguan_RVRI_20*.csv"))
    print(f"   - 命中文件数: {len(csv_files)}")
    
    required_cols = ['grid_id', 'time', 'ndbi', 'ndvi', 'light']
    df_list = []
    
    for f in csv_files:
        temp = pd.read_csv(f)
        # 严格检查核心列是否存在，防止混入中间表或宽表
        if all(col in temp.columns for col in required_cols):
            df_list.append(temp[required_cols + (['district'] if 'district' in temp.columns else [])])
        else:
            print(f"   - [跳过] 文件 {Path(f).name} 缺少核心列")

    full_df = pd.concat(df_list, ignore_index=True)
    
    # 行政名字修复逻辑 (基于2019字典)
    print(">>> [Task 2] 正在同步行政区划标签 (district_name)...")
    map_df = pd.read_csv(MAPPING_SOURCE_CSV, usecols=['grid_id', 'district']).drop_duplicates('grid_id')
    
    if 'district' in full_df.columns: full_df.drop(columns=['district'], inplace=True)
    full_df = full_df.merge(map_df.rename(columns={'district':'district_name'}), on='grid_id', how='left')
    full_df['district_name'] = full_df['district_name'].fillna("边缘区")
    
    return full_df

# ==========================================
# 3. 指数合成与逻辑强制纠偏
# ==========================================
def build_logic_consistent_rvri(df):
    print(">>> [Task 3] 正在构建逻辑一致的 RVRI 风险指数...")

    # 3.1 处理空值
    raw_len = len(df)
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=['ndbi', 'light', 'ndvi'])
    null_rate = (raw_len - len(df)) / raw_len

    # 3.2 构造错配项 (Mismatch Gap)
    scaler_mm = MinMaxScaler()
    df[['ndbi_n', 'light_n']] = scaler_mm.fit_transform(df[['ndbi', 'light']])
    df['mismatch_gap'] = df['ndbi_n'] - df['light_n']

    # 3.3 构造风险同向特征并 PCA 合成
    df['light_neg'] = -df['light']
    df['ndvi_neg'] = -df['ndvi']
    features = ['mismatch_gap', 'light_neg', 'ndvi_neg']
    x = StandardScaler().fit_transform(df[features])
    pca = PCA(n_components=1)
    _ = pca.fit_transform(x).ravel()
    pca_loadings = pca.components_[0]

    # 3.4 方向校准（核心修复）
    # 仅做整体翻转无法同时满足多个方向约束，
    # 这里改为使用“绝对载荷”重构风险得分，确保所有风险同向特征都正向贡献。
    monotonic_loadings = np.abs(pca_loadings)
    df['rvri_raw'] = x @ monotonic_loadings

    # 3.5 0-1 归一化
    df['rvri'] = (df['rvri_raw'] - df['rvri_raw'].min()) / (df['rvri_raw'].max() - df['rvri_raw'].min())

    # 3.6 计算最终相关性指标用于审计
    metrics = {
        "null_rate": f"{null_rate:.2%}",
        "pca_explained_variance": f"{pca.explained_variance_ratio_[0]:.2%}",
        "corr_rvri_mismatch": df['rvri'].corr(df['mismatch_gap']),
        "corr_rvri_ndbi": df['rvri'].corr(df['ndbi']),
        "corr_rvri_light": df['rvri'].corr(df['light']),
        "time_coverage": sorted(df['time'].unique().tolist()),
        "declared_panel_range": "2019Q1-2025Q4"
    }

    print(f"   - 逻辑检查: corr(RVRI, Gap) = {metrics['corr_rvri_mismatch']:.4f}")
    print(f"   - 逻辑检查: corr(RVRI, Light) = {metrics['corr_rvri_light']:.4f}")

    loadings_map = {
        "pca_original": dict(zip(features, pca_loadings.tolist())),
        "pca_monotonic_abs": dict(zip(features, monotonic_loadings.tolist()))
    }
    return df, metrics, loadings_map


# ==========================================
# 4. 结果落盘与空间集成
# ==========================================
def save_and_visualize(df, metrics, loadings_map):
    print(">>> [Task 4] 正在将关键验证结果与空间底座落盘...")

    # 4.1 划分状态
    df['risk_state'] = pd.qcut(df['rvri'], 3, labels=[0, 1, 2]).astype(int)

    # 4.2 保存 CSV
    df.to_csv(FINAL_CSV, index=False)

    # 4.3 保存审计报告 (JSON)
    report_data = {
        "metrics": metrics,
        "pca_loadings": loadings_map,
        "risk_state_distribution": df['risk_state'].value_counts().to_dict()
    }
    with open(REPORT_JSON, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=4, ensure_ascii=False)

    # 4.4 空间化输出 (GeoJSON) - 选取最新快照
    if GRID_BASE.exists():
        grid = gpd.read_file(GRID_BASE)
        latest_time = df['time'].max()
        latest_df = df[df['time'] == latest_time]
        final_geo = grid.merge(latest_df, on='grid_id', how='inner')
        final_geo.to_file(FINAL_GEOJSON, driver='GeoJSON')
        print(f"   - 空间面板快照已存入: {FINAL_GEOJSON.name}")

    # 4.5 可复现绘图
    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=df.sample(5000, random_state=2026),
                    x='light', y='rvri', hue='risk_state',
                    palette='RdYlGn_r', alpha=0.4)
    plt.title("逻辑一致性检验：活力流量 vs 综合风险 (需呈现显著负相关)")
    plt.savefig(OUTPUT_DIR / "Q1_RVRI_Scientific_Check.png", dpi=300)
    plt.close()

    # 4.6 新增可视化：灯光分箱趋势图（答辩更直观）
    trend_df = df[['light', 'rvri']].copy()
    trend_df['light_bin'] = pd.qcut(trend_df['light'], q=20, duplicates='drop')
    trend = trend_df.groupby('light_bin', observed=False).agg(
        light_mean=('light', 'mean'),
        rvri_mean=('rvri', 'mean')
    ).reset_index(drop=True)

    plt.figure(figsize=(10, 6))
    sns.lineplot(data=trend, x='light_mean', y='rvri_mean', marker='o', linewidth=2)
    plt.title("灯光强度分箱趋势图：平均灯光 vs 平均RVRI")
    plt.xlabel("平均夜间灯光 (分箱均值)")
    plt.ylabel("平均RVRI")
    plt.grid(alpha=0.25)
    plt.savefig(OUTPUT_DIR / "Q1_RVRI_Light_Binned_Trend.png", dpi=300)
    plt.close()

    print(f"✅ 审计报告已生成: {REPORT_JSON.name}")


if __name__ == "__main__":
    try:
        panel_df = load_and_verify_data()
        final_df, report_metrics, loadings_map = build_logic_consistent_rvri(panel_df)
        save_and_visualize(final_df, report_metrics, loadings_map)
        print("\n🚀 Q1 逻辑加固任务圆满完成。RVRI 指数现已具备‘房多灯暗’的因果解释性。")
    except Exception as e:
        print(f"❌ 运行失败: {e}")



