# -*- coding: utf-8 -*-
"""
生成示例报告

用 mock 数据通过 ReportGenerator 完整管线生成单因子测试报告，
用于展示报告的实际输出效果。

用法:
    python scripts/generate_sample_report.py

输出:
    - sample_report.html (在浏览器中自动打开)
    - sample_report.md
"""

import os
import sys
import webbrowser

import numpy as np
import pandas as pd

# 确保项目在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from QSExt.ReportGenerator.core import DataContext
from QSExt.ReportGenerator.themes.base import Theme
from QSExt.ReportGenerator.layout import LayoutRenderer
from QSExt.ReportGenerator.scenarios.single_factor import SingleFactorReport


def _make_mock_output():
    """构造模拟 BTReport output，模拟较真实的回测数据"""
    np.random.seed(42)
    dates = pd.date_range("2018-01-31", "2025-12-31", freq="ME")
    n = len(dates)  # 96 months
    factor_name = "动量因子_1M"

    # === IC 数据 ===
    ic_series = np.random.randn(n) * 0.06 + 0.025  # 均值 ~0.025, std ~0.06
    ic_df = pd.DataFrame({factor_name: ic_series}, index=dates)
    ic_ma = ic_df.rolling(12).mean()

    # === 统计数据 ===
    ic_series_pd = pd.Series(ic_series)
    ic_mean = ic_series_pd.mean()
    ic_std = ic_series_pd.std()
    icir = ic_mean / ic_std if ic_std > 0 else 0
    win_rate = (ic_series > 0).sum() / n
    t_stat = ic_mean / (ic_std / np.sqrt(n))
    stat_df = pd.DataFrame(
        {
            factor_name: [
                ic_mean, ic_std, icir, t_stat, win_rate,
                ic_series_pd.skew(), ic_series_pd.kurtosis()
            ]
        },
        index=[
            "IC均值", "IC标准差", "ICIR", "t统计量",
            "胜率", "偏度", "峰度"
        ]
    )

    # === 截面宽度 ===
    breadth = pd.DataFrame(
        {"宽度": np.random.randint(250, 500, n)},
        index=dates
    )

    # === IC 衰减 ===
    decay_periods = [1, 2, 3, 6, 12]
    base_ic = 0.022
    decay_values = [base_ic * (1 - 0.05 * i) + np.random.randn() * 0.003
                    for i in range(len(decay_periods))]
    decay_df = pd.DataFrame(
        {factor_name: decay_values},
        index=decay_periods
    )
    decay_stat = pd.DataFrame(
        {
            factor_name: [
                np.mean(decay_values), 0.005,
                (np.array(decay_values) > 0).sum() / len(decay_periods)
            ]
        },
        index=["IC均值", "IC标准差", "胜率"]
    )

    # === 分位数组合净值 ===
    n_groups = 5
    annual_returns = np.linspace(0.18, 0.02, n_groups)  # Q1: 18%, Q5: 2%
    monthly_returns = (1 + annual_returns) ** (1 / 12) - 1
    nav_data = {}
    for i in range(n_groups):
        rets = np.random.randn(n) * 0.04 + monthly_returns[i]
        nav_data[f"Q{i + 1}"] = np.cumprod(1 + rets)
    nav_df = pd.DataFrame(nav_data, index=dates)

    # === 分位数组合统计 ===
    pf_stats = {
        "年化收益率": [f"{r:.2%}" for r in annual_returns],
        "夏普比率": [f"{r / 0.15:.2f}" for r in annual_returns],
        "最大回撤": [f"{-0.08 - i * 0.02:.2%}" for i in range(n_groups)],
        "月胜率": [f"{0.62 - i * 0.03:.1%}" for i in range(n_groups)],
        "年化波动率": [f"{0.20 + i * 0.01:.2%}" for i in range(n_groups)],
    }
    pf_stat_df = pd.DataFrame(pf_stats, index=[f"Q{i + 1}" for i in range(n_groups)]).T

    # === 换手率 ===
    turnover_series = 0.15 + np.random.rand(n) * 0.25  # 15%~40%
    turnover_df = pd.DataFrame({factor_name: turnover_series}, index=dates)

    # === 组装 output dict（键名与 config.yaml 中 source 引用一致） ===
    output = {
        "0-Rank IC 分析": {
            "IC": ic_df,
            "IC的移动平均": ic_ma,
            "统计数据": stat_df,
            "截面宽度": breadth,
        },
        "1-IC 衰减分析": {
            "IC衰减": decay_df,
            "统计数据": decay_stat,
        },
        "2-分位数组合": {
            "净值": nav_df,
            "统计数据": pf_stat_df,
        },
        "3-因子换手率": {
            "换手率": turnover_df,
        },
    }
    return output, factor_name


def main():
    print("=" * 60)
    print("  ReportGenerator 示例报告生成")
    print("=" * 60)

    # 1. 构造 mock 数据
    print("\n[1/4] 构造模拟回测数据...")
    output, factor_name = _make_mock_output()

    # 2. 加载 config.yaml
    import yaml
    config_path = os.path.join(
        os.path.dirname(__file__),
        "..", "QSExt", "ReportGenerator", "scenarios",
        "single_factor", "config.yaml"
    )
    config_path = os.path.abspath(config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    print(f"  配置文件: {config_path}")
    print(f"  场景: {config['scenario']['name']} v{config['scenario']['version']}")

    # 3. 渲染
    print("\n[2/4] 构建 DataContext...")
    ctx = DataContext(output, [factor_name], config)
    ctx.set("meta", "factor_info", {
        "name": factor_name,
        "count": 1,
        "dt_start": ctx.get("meta", "dt_start") or "2018-01-31",
        "dt_end": ctx.get("meta", "dt_end") or "2025-12-31",
        "description": "过去1个月收益率排名（Spearman秩相关）",
        "tags": ["动量", "截面因子", "JYDB"],
    })

    print("[3/4] 渲染报告...")
    theme = Theme()
    layout_renderer = LayoutRenderer()
    report_config = config["report"]

    html = layout_renderer.render(report_config, ctx, theme, "html")
    md = layout_renderer.render(report_config, ctx, theme, "markdown")

    # 4. 写入文件
    print("[4/4] 写入输出文件...")
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    html_path = os.path.join(output_dir, "sample_report.html")
    md_path = os.path.join(output_dir, "sample_report.md")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  HTML 报告: {html_path} ({len(html):,} 字符)")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"  MD  报告:  {md_path} ({len(md):,} 字符)")

    # 5. 在浏览器中打开
    print(f"\n正在打开 HTML 报告...")
    webbrowser.open(f"file:///{html_path.replace(os.sep, '/')}")

    print("\n" + "=" * 60)
    print("  完成！")
    print(f"  HTML: {html_path}")
    print(f"  MD:   {md_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
