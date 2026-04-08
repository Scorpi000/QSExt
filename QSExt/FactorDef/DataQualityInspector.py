import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import base64
from io import BytesIO

# 设置绘图后端，防止内存泄漏并支持无头环境运行
plt.switch_backend('Agg') 
plt.style.use('seaborn-v0_8-whitegrid')
# 设置中文字体，防止中文乱码
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans'] 
plt.rcParams['axes.unicode_minus'] = False

class DataQualityInspector:
    def __init__(self, mask_df, threshold_zscore=2.5, min_missing_pct=0.05, max_abs_missing_rate=1.0):
        """
        初始化检测器
        :param mask_df: 掩码 DataFrame (index: 时间, columns: 证券代码, values: bool)
        :param threshold_zscore: 异常检测的 Z-Score 阈值 (默认 2.5 倍标准差)
        :param min_missing_pct: 触发异常检测的最小缺失率阈值 (防止在极低缺失率时误报)
        :param max_abs_missing_rate: 绝对缺失率上限 (默认 1.0 即 100%，若设为 0.05 则表示缺失率>5% 才可能被标记异常)
                                     注意：这里逻辑是，如果用户希望“只要低于某值就不算异常”，
                                     通常是指“绝对阈值”。这里将其作为异常判定的下界条件。
                                     即：只有 (缺失率 > max_abs_missing_rate) 且 (Z-Score 异常) 时才报警。
        """
        self.mask = mask_df
        self.threshold_zscore = threshold_zscore
        self.min_missing_pct = min_missing_pct
        self.max_abs_missing_rate = max_abs_missing_rate

    def _plot_to_base64(self, rate_series, anomalies, name):
        """
        绘制图表并转换为 Base64 字符串
        """
        try:
            plt.figure(figsize=(12, 5))
            
            # 绘制主曲线
            plt.plot(rate_series.index, rate_series.values, label='缺失率', color='#1f77b4', alpha=0.7, linewidth=1)
            
            # 标注异常点
            if len(anomalies) > 0:
                plt.scatter(anomalies.index, anomalies.values, color='red', zorder=5, label='异常点', s=80, marker='x')
            
            # 绘制平均线
            mean_rate = rate_series.mean()
            plt.axhline(y=mean_rate, color='g', linestyle='--', label=f'平均缺失率 ({mean_rate:.2%})')
            
            # 绘制绝对阈值线 (如果设置了且小于 1.0)
            if self.max_abs_missing_rate < 1.0:
                plt.axhline(y=self.max_abs_missing_rate, color='orange', linestyle=':', label=f'绝对阈值 ({self.max_abs_missing_rate:.2%})')

            plt.title(f'{name} - 缺失率时序检测')
            plt.xlabel('时间')
            plt.ylabel('缺失率')
            plt.legend(loc='upper right')
            
            # 格式化时间轴
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            plt.gcf().autofmt_xdate()
            plt.grid(True, linestyle=':', alpha=0.6)
            
            # 保存到内存缓冲区
            buf = BytesIO()
            plt.savefig(buf, format='png', dpi=80)
            plt.close()
            
            buf.seek(0)
            img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            return img_base64
        except Exception as e:
            return None

    def inspect(self, data_dict):
        report = "# 📊 数据质量检测报告\n\n"
        
        # --- 1. 基础信息统计 ---
        report += "## 1. 基础信息概览\n\n"
        report += "| 数据项名称 | 起始时间 | 结束时间 | 覆盖证券数 | 连续性状态 |\n"
        report += "| :--- | :--- | :--- | :--- | :--- |\n"
        
        # 预计算 Mask 的有效日期集合
        mask_valid_dates = self.mask.index[self.mask.any(axis=1)]

        for name, df in data_dict.items():
            # 1. 快速交集计算
            common_cols = df.columns.intersection(self.mask.columns)
            if len(common_cols) == 0:
                report += f"| {name} | - | - | 0 | ⚠️ 无重合证券 |\n"
                continue

            # 2. 连续性检查
            if df.empty:
                 is_continuous = False
                 start_d, end_d = None, None
            else:
                start_d, end_d = df.index.min(), df.index.max()
                # 找出该范围内 Mask 的有效日期
                target_dates_in_range = [d for d in mask_valid_dates if start_d <= d <= end_d]
                # 检查数据项是否包含所有这些日期
                df_index_set = set(df.index)
                missing_dates = [d for d in target_dates_in_range if d not in df_index_set]
                is_continuous = len(missing_dates) == 0

            status_html = "**🔴 不连续**" if not is_continuous else "✅ 正常"
            report += f"| {name} | {start_d} | {end_d} | {len(common_cols)} | {status_html} |\n"

        report += "\n"

        # --- 2. 缺失率异常检测 ---
        report += "## 2. 缺失率异常检测\n\n"
        
        for name, df in data_dict.items():
            report += f"### 📉 数据项: {name}\n\n"
            
            common_cols = df.columns.intersection(self.mask.columns)
            if len(common_cols) == 0:
                continue
                
            # === 向量化计算 ===
            
            # 1. 重索引：一次性将所有数据对齐到 Mask 的时间轴
            df_aligned = df.reindex(index=self.mask.index, columns=common_cols)
            mask_aligned = self.mask[common_cols]
            
            # 2. 计算缺失矩阵
            missing_matrix = df_aligned.isna() & mask_aligned
            
            # 3. 按行求和
            missing_count_series = missing_matrix.sum(axis=1)
            
            # 4. 计算每天的总有效数量
            total_count_series = mask_aligned.sum(axis=1)
            
            # 5. 过滤掉没有有效数据的行
            valid_rows = total_count_series > 0
            missing_count_series = missing_count_series[valid_rows]
            total_count_series = total_count_series[valid_rows]
            
            # 6. 计算缺失率
            rate_series = missing_count_series / total_count_series
            
            if rate_series.empty:
                report += "> ℹ️ 无有效数据点。\n\n"
                continue

            # === 异常检测 ===
            mean_rate = rate_series.mean()
            std_rate = rate_series.std()
            
            anomalies = pd.Series(dtype=float)
            
            if std_rate > 0:
                z_scores = (rate_series - mean_rate) / std_rate
                # 异常判定逻辑：
                # 1. Z-Score 超过阈值 (波动大)
                # 2. 缺失率 > min_missing_pct (防止极低值误报)
                # 3. 缺失率 > max_abs_missing_rate (新增：绝对缺失率必须超过此值才算异常)
                #    注意：如果 max_abs_missing_rate 设为 1.0 (默认)，则此条件恒成立，相当于不限制。
                #    如果用户设为 0.05，则缺失率必须大于 5% 才会被标记。
                anomaly_mask = (
                    (z_scores.abs() > self.threshold_zscore) & 
                    (rate_series > self.min_missing_pct) &
                    (rate_series > self.max_abs_missing_rate)
                )
                anomalies = rate_series[anomaly_mask]
            
            # 生成文本报告
            if len(anomalies) > 0:
                report += f"**🔴 发现 {len(anomalies)} 个异常时点**\n\n"
                report += "| 异常日期 | 缺失率 | 缺失数量/总数量 |\n"
                report += "| :--- | :--- | :--- |\n"
                for date, rate in anomalies.items():
                    n_miss = int(missing_count_series[date])
                    n_tot = int(total_count_series[date])
                    report += f"| **{date.date()}** | **{rate:.2%}** | {n_miss} / {n_tot} |\n"
                report += "\n"
            else:
                report += "✅ 未发现明显的缺失率异常波动。\n\n"

            # 绘图
            img_base64 = self._plot_to_base64(rate_series, anomalies, name)
            if img_base64:
                report += f"![{name} 缺失率曲线](data:image/png;base64,{img_base64})\n\n"

        return report

# ==========================================
# 模拟数据生成
# ==========================================
def generate_mock_data():
    dates = pd.date_range('2023-01-01', '2026-10-01', freq='B')
    stocks = [f'Stock_{i:03d}' for i in range(1, 201)]
    
    # Mask
    mask_data = np.random.choice([True, False], size=(len(dates), len(stocks)), p=[0.9, 0.1])
    mask_df = pd.DataFrame(mask_data, index=dates, columns=stocks)
    
    # Data A: 正常
    data_a = pd.DataFrame(np.random.randn(len(dates), len(stocks)), index=dates, columns=stocks)
    data_a.iloc[50, 5] = np.nan
    
    # Data B: 异常波动 (缺失率很高)
    data_b = pd.DataFrame(np.random.randn(len(dates), len(stocks)), index=dates, columns=stocks)
    data_b.iloc[500, 50:150] = np.nan 
    
    # Data C: 时间不连续
    data_c_dates = dates.drop(dates[100:110])
    data_c = pd.DataFrame(np.random.randn(len(data_c_dates), len(stocks)), index=data_c_dates, columns=stocks)

    return {
        "Mask": mask_df,
        "Data_A": data_a,
        "Data_B": data_b,
        "Data_C": data_c
    }

if __name__ == "__main__":
    mock_data = generate_mock_data()
    mask = mock_data.pop("Mask")
    
    # 初始化检测器
    # max_abs_missing_rate=0.02 表示：只有缺失率超过 2% 的波动才会被标记为异常
    inspector = DataQualityInspector(mask_df=mask, threshold_zscore=2.5, min_missing_pct=0.01, max_abs_missing_rate=0.02)
    
    markdown_report = inspector.inspect(mock_data)
    
    with open("data_quality_report.md", "w", encoding="utf-8") as f:
        f.write(markdown_report)
        
    print("✅ 检测完成，报告已生成。")