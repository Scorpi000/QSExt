# ReportGenerator — 报告生成系统

## 1. 背景与动机

QuantStudio 提供了 IC 分析、分位数组合、因子换手率等截面因子回测模块，以及 AccountStats 等策略回测模块，这些模块的 `backward_compute()` 产出包含 DataFrame 的 dict，但内置的报告功能存在局限：

- **样式与代码耦合**：报告样式硬编码在 QuantStudio 源码中
- **多场景复用困难**：不同需求（单因子报告、多因子对比、策略回测报告）需要重复编写组装和渲染代码
- **单一输出格式**：仅支持 HTML

本模块建立一套**场景驱动的报告生成框架**，核心思想是：

> **场景类（Python）定义数据来源** + **报告布局（YAML）声明组件排列** + **可视化组件（组件库）负责渲染**

---

## 2. 模块结构

```
QSExt/ReportGenerator/
├── __init__.py                     # ReportGenerator 抽象基类
├── core.py                         # DataContext、split_output_for_factor、register_reports_to_db
├── layout.py                       # LayoutRenderer（YAML 布局 → 组件树 → 报告）

├── components/                     # 可复用可视化组件库
│   ├── base.py                     # Component 抽象基类
│   ├── registry.py                 # ComponentRegistry 全局注册表
│   ├── chart.py                    # Chart 组件 + 10 种内置图表类型
│   ├── data_table.py               # DataTable 组件
│   ├── stat_grid.py                # StatGrid KPI 卡片组
│   ├── factor_summary.py           # FactorSummary 因子概况
│   └── section.py                  # Section 布局容器

├── themes/                         # 主题系统
│   └── base.py                     # Theme 基类（颜色/字体/间距/CSS）

├── renderers/                      # 输出格式渲染器
│   ├── base.py                     # ReportRenderer 抽象基类
│   ├── html_renderer.py            # HtmlRenderer（自包含 HTML，图表 base64 内嵌）
│   └── md_renderer.py              # MarkdownRenderer

├── scenarios/                      # 场景目录
│   ├── __init__.py                 # ScenarioRegistry 场景注册表
│   ├── single_factor/              # 单因子测试场景
│   │   ├── __init__.py
│   │   ├── scenario.py             # SingleFactorReport(ReportGenerator) 子类
│   │   └── config.yaml             # 参数 + 报告布局声明
│   └── single_strategy/            # 单策略回测场景
│       ├── __init__.py
│       ├── scenario.py             # SingleStrategyReport(ReportGenerator) 子类
│       └── config.yaml             # 参数 + 报告布局声明

└── scripts/                        # 执行脚本
    ├── run_report.py               # CLI 入口（profile 驱动）
    ├── run_factor_report_manual.py # 单因子报告手动测试
    └── run_strategy_report_manual.py # 单策略报告手动测试
```

---

## 3. 核心设计

### 3.1 ReportGenerator — 报告生成计算图节点

```python
from QSExt.ReportGenerator import ReportGenerator

class ReportGenerator(Node):
    """通用报告生成节点，子类通过两个方法定义场景。"""

    @classmethod
    def create_nodes(cls, *args, **kwargs) -> List[Node]:
        """定义场景所需的上游数据节点。"""

    def generate_report(self, output_list: List[Any]) -> Dict[str, str]:
        """将上游节点产出渲染为报告。"""
```

**唯一抽象**：`create_nodes()` 定义"数据从哪来"，`generate_report()` 定义"数据怎么变成报告"。不存在分离的 Scenario vs ReportGeneratorNode 二分——一切通过子类化实现。

### 3.2 Component — 可视化组件

```python
from QSExt.ReportGenerator.components.base import Component

class Component(ABC):
    name: str

    def render(self, data, params, theme, renderer) -> str:
        """data + params + theme → HTML/Markdown 片段"""
```

**内置组件**：

| 注册名 | 类 | 说明 |
|--------|-----|------|
| `chart` | `Chart` | `type` 参数分发到不同 matplotlib 生成函数 |
| `data_table` | `DataTable` | DataFrame → 表格（可排序、精度控制） |
| `stat_grid` | `StatGrid` | KPI 指标卡片组 |
| `factor_summary` | `FactorSummary` | 因子基本信息展示 |
| `section` | `Section` | 章节容器，支持 single / two_column / grid 布局 |

**内置图表类型**：

| type | 说明 |
|------|------|
| `ic_bar` | IC 柱状图 + 移动平均线 |
| `ic_decay_bar` | IC 衰减柱状图 |
| `nav_curve` | 净值曲线 |
| `long_excess_nav` | 多头超额净值 |
| `long_short_nav` | 多空净值（含填充区域） |
| `turnover_area` | 换手率面积图 |
| `heatmap` | 相关性热力图 |
| `bar_chart` | 通用柱状图 |
| `line_chart` | 通用折线图 |
| `drawdown_line` | 回撤曲线（水下曲线） |

### 3.3 DataContext — 数据上下文

```python
from QSExt.ReportGenerator.core import DataContext

ctx = DataContext(output_dict, factor_names, config)

df = ctx.get("0-Rank IC 分析", "IC")       # → DataFrame
meta = ctx.get("meta", "factor_info")      # → dict（因子元信息）
```

内部结构：`{source_name: {key: value}}`。`source` 由场景子类在 `generate_report()` 中自行组织，`key` 对应该模块 dict 中的数据键。

---

## 4. 数据流

### 4.1 单因子报告

```
调用者                                  场景子类                             渲染管线
───────                                 ────────                            ────────
  │                                                                               │
  ├── factors, price, mask, ...                                                  │
  │        │                                                                      │
  │        ▼                                                                      │
  │  SingleFactorReport.create_nodes(factors, ...)                                │
  │        │                                                                      │
  │        └── → [ICNode, ICDecayNode, PFNode..., TurnoverNode]                   │
  │                  │                                                            │
  │                  ▼                                                            │
  │  SingleFactorReport(nodes, args={...})                                        │
  │        │                                                                      │
  │        ▼                                                                      │
  │  Engine.run([report_node], context)                                           │
  │        │                                                                      │
  │        │   DAG 遍历: deps.backward_compute() 依次产出                          │
  │        │   output_list = [IC产出, Decay产出, PF产出, Turnover产出]              │
  │        │                                                                      │
  │        ▼                                                                      │
  │  report_node.backward_compute(path, output_list, context)                     │
  │        │                                                                      │
  │        └── generate_report(output_list)                                       │
  │              │                                                                │
  │              ├── (1) 按已知顺序从 output_list 取数据，组织为 output dict       │
  │              │       {"0-Rank IC 分析": {...}, "1-IC 衰减分析": {...}, ...}  │
  │              │                                                                │
  │              ├── (2) split_output_for_factor(output, fname)                   │
  │              │       → 按因子名列切片                                          │
  │              │                                                                │
  │              ├── (3) DataContext(single_output, [fname], config)              │
  │              │                                                                │
  │              └── (4) LayoutRenderer.render(config, ctx, theme, fmt)           │
  │                      ├── header（因子概况）                                    │
  │                      ├── sections（IC/衰减/组合/换手率）                       │
  │                      └── assemble_page → 完整报告                              │
  │              │                                                                │
  │              ▼                                                                │
  │  {"Report": "报告内容"}                                                       │
```

### 4.2 单策略报告

```
调用者                                  场景子类                             渲染管线
───────                                 ────────                            ────────
  │                                                                               │
  ├── strategy (MakeAccount 因子), bmk_nv (可选)                                  │
  │        │                                                                      │
  │        ▼                                                                      │
  │  SingleStrategyReport.create_nodes(strategy, bmk_nv=...)                      │
  │        │                                                                      │
  │        └── → [AccountStats]                                                   │
  │                  │                                                            │
  │                  ▼                                                            │
  │  SingleStrategyReport(nodes, args={...}, strategy_name="...")                 │
  │        │                                                                      │
  │        ▼                                                                      │
  │  Engine.run([report_node], context)                                           │
  │        │                                                                      │
  │        │   AccountStats.backward_compute() 产出                                │
  │        │   output_list = [{"时间序列": df, "统计数据": df, "交易记录": df, ...}]  │
  │        │                                                                      │
  │        ▼                                                                      │
  │  report_node.generate_report(output_list)                                     │
  │        │                                                                      │
  │        ├── (1) 从 AccountStats 输出提取数据                                    │
  │        ├── (2) 计算衍生数据（回撤序列、年度/月度收益、交易统计）                │
  │        ├── (3) 组织为 DataContext                                              │
  │        │       {"0-绩效统计": {...}, "1-净值走势": {...}, ...}               │
  │        │                                                                      │
  │        └── (4) LayoutRenderer.render(config, ctx, theme, fmt)                 │
  │                ├── header（策略概况）                                          │
  │                ├── sections（绩效/净值/回撤/分时段收益/交易统计）               │
  │                └── assemble_page → 完整报告                                    │
  │        │                                                                      │
  │        ▼                                                                      │
  │  {"Report": "报告内容"}                                                       │
```

---

## 5. 配置文件格式（config.yaml）

每个场景的配置文件分为两部分：**回测参数**（传给 `create_nodes`）和**报告布局**（驱动组件渲染）。

### 5.1 回测参数段（`modules`）

```yaml
modules:
  ic:
    lookback: 31
    period_lookback: 1
    corr_method: "spearman"
    rolling_avg_period: 12

  ic_decay:
    periods: [1, 2, 3, 6, 12]

  quantile_portfolio:
    group_num: 5
    ascending: false
    long_short_pairs: [[0, -1]]

  factor_turnover:
    lookback: 31
    period_lookback: 1
```

### 5.2 报告布局段（`report`）

```yaml
report:
  theme: default
  page_title: "{factor_name} — 单因子测试报告"

  header:
    component: section
    params:
      layout: grid
      columns: 3
    children:
      - component: factor_summary
        data:
          source: meta
          key: factor_info
      - component: stat_grid
        data:
          source: 0-Rank IC 分析
          key: 统计数据
        params:
          metrics:
            - {label: "Rank IC 均值", field: "平均值", format: ".4f"}
            - {label: "ICIR", field: "IC_IR", format: ".2f"}

  sections:
    - id: ic_analysis
      title: "一、Rank IC 分析"
      params:
        layout: two_column
      children:
        - component: chart
          data:
            source: 0-Rank IC 分析
            key: IC
          params:
            type: ic_bar
            title: "IC 序列"
        - component: data_table
          data:
            source: 0-Rank IC 分析
            key: 统计数据
          params:
            precision: 4
```

**注意**：`data.source` 引用的名称由场景子类在 `generate_report()` 中组织 output dict 时决定，不需要额外的 `data_sources` 配置段。

### 5.3 各场景数据源映射

**SingleFactorReport** 的 output dict：

| source | key | 说明 |
|--------|-----|------|
| `0-Rank IC 分析` | `IC`, `统计数据` | IC 分析结果 |
| `1-IC 衰减分析` | `统计数据` | 不同周期的 IC 均值 |
| `2-分位数组合` | `净值`, `超额净值`, `统计数据` | 分位数组合表现 |
| `3-因子换手率` | `换手率` | 因子换手率序列 |

**SingleStrategyReport** 的 output dict（从 AccountStats 输出加工而来）：

| source | key | 说明 |
|--------|-----|------|
| `0-绩效统计` | `绝对表现`, `统计全表` | 核心绩效指标（年化收益、夏普、最大回撤等） |
| `1-净值走势` | `净值`, `收益率` | 净值曲线和逐期收益率（含基准对比） |
| `2-回撤分析` | `回撤序列`, `回撤事件` | 水下曲线和主要回撤事件表 |
| `3-分时段收益` | `年度收益`, `月度收益` | 按年/月分组的收益率矩阵 |
| `4-交易统计` | `交易概要`, `交易记录` | 交易次数、持仓数等概要和交易明细 |

### 5.4 布局节点通用属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `component` | string | 组件注册名 |
| `title` | string | 章节/图表/表格标题 |
| `params.layout` | string | 布局类型：`single` / `two_column` / `grid` |
| `params.columns` | int | grid 布局的列数 |
| `params.collapsible` | bool | 是否可折叠 |
| `children` | list | 子组件列表（仅 section 容器有效） |
| `data.source` | string | 数据来源名称（由场景子类定义） |
| `data.key` | string | 数据键名 |
| `params.type` | string | 图表类型（仅 chart） |
| `params.metrics` | list | KPI 指标定义（仅 stat_grid） |

---

## 6. 使用方法

### 6.1 单因子报告

```python
from QuantStudio.Core.CalcEngine import Engine
from QSExt.ReportGenerator.scenarios.single_factor import SingleFactorReport

# 1. 创建上游节点（场景类方法）
nodes = SingleFactorReport.create_nodes(
    factors=[factor1],
    price=price_factor,
    mask=mask_factor,
    cat_data=industry_factor,
)

# 2. 创建报告节点并嵌入计算图
report_node = SingleFactorReport(
    deps=nodes,
    factor_names=["动量因子"],
    args={"OutputFormat": "html"},
)

# 3. 运行
result = Engine().run([report_node], context)[0]
html_content = result["Report"]
```

### 6.2 单策略报告

```python
from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.BackTest.Strategy.Strategy import MakeAccount
from QSExt.ReportGenerator.scenarios.single_strategy import SingleStrategyReport

# 1. 创建策略
account = MakeAccount(
    signal_type="目标权重", start_dt=start_dt, init_cash=1e6,
)(last_price=price, signal=signal)

# 2. 创建上游节点（AccountStats）
nodes = SingleStrategyReport.create_nodes(account, bmk_nv=benchmark_nv)

# 3. 创建报告节点
report_node = SingleStrategyReport(
    deps=nodes,
    args={"OutputFormat": "html"},
    strategy_name="动量策略",
)

# 4. 运行
result = Engine().run([report_node], context)[0]
html_content = result["Report"]
```

### 6.3 自定义报告布局

只需编辑 `config.yaml` 的 `report` 段，无需修改任何 Python 代码：

- **调整章节顺序**：重排 `sections` 列表
- **修改 KPI 指标**：编辑 `stat_grid` 的 `metrics` 列表
- **修改图表类型**：修改 `chart` 的 `params.type`
- **调整表格精度**：修改 `data_table` 的 `params.precision`

### 6.4 使用配置文件

```python
report_node = SingleFactorReport(
    deps=nodes,
    factor_names=["动量因子"],
    args={"OutputFormat": "html", "ReportConfig": "my_config.yaml"},
)
```

### 6.5 报告注册到图数据库

```python
from QSExt.ReportGenerator.core import register_reports_to_db

report_ids = register_reports_to_db(
    result=reports,               # generate_report() 的返回值
    factor_qsids=["FACTOR_abc"],  # 因子 QSID 列表
    output_dir="D:/reports/",
    bt_qsid="d4e5f6a7...",
    scenario_name="single_factor",
)
```

---

## 7. 扩展指南

### 7.1 新增场景

子类化 `ReportGenerator`，实现 `create_nodes()` 和 `generate_report()`：

```python
from QSExt.ReportGenerator import ReportGenerator
from QSExt.ReportGenerator.core import DataContext, split_output_for_factor
from QSExt.ReportGenerator.layout import LayoutRenderer
from QSExt.ReportGenerator.themes.base import Theme

class MyReport(ReportGenerator):
    @classmethod
    def create_nodes(cls, factors, **kwargs) -> list:
        """构建该场景所需的上游数据节点。"""
        nodes = []
        # 构建回测、风险分析、优化器等节点
        return nodes

    def generate_report(self, output_list):
        """按 create_nodes 返回的顺序组织数据并渲染。"""
        # 1. 按已知顺序从 output_list 取数据
        output = {
            "my_source": output_list[0],
            ...
        }

        # 2. 渲染
        theme = Theme()
        layout_renderer = LayoutRenderer()
        reports = {}
        for fname in self._factor_names:
            single = split_output_for_factor(output, fname)
            ctx = DataContext(single, [fname], self._QSArgs.OutputConfig)
            reports[fname] = {}
            for fmt in self._QSArgs.OutputFormats:
                reports[fname][fmt] = layout_renderer.render(
                    self._QSArgs.ReportConfig, ctx, theme, fmt
                )
        return reports
```

### 7.2 新增图表类型

```python
from QSExt.ReportGenerator.components.chart import Chart

# matplotlib 版本
def _render_my_chart(data, params, theme):
    fig = Figure(figsize=(14, 6))
    ax = fig.add_subplot(111)
    # ... matplotlib 绘图 ...
    return fig

# plotly 版本
def _render_my_chart_plotly(data, params, theme):
    import plotly.graph_objects as go
    fig = go.Figure()
    # ... plotly 绘图 ...
    return fig

Chart.register_chart_type("matplotlib", "my_chart", _render_my_chart)
Chart.register_chart_type("plotly", "my_chart", _render_my_chart_plotly)
# YAML: params.type: my_chart
```

### 7.3 新增主题

```python
from QSExt.ReportGenerator.themes.base import Theme

class DarkTheme(Theme):
    name = "dark"
    primary_color = "#6B9BD2"
    bg_color = "#1E1E1E"
    text_color = "#CCCCCC"
```

### 7.4 新增组件类型

```python
from QSExt.ReportGenerator.components.base import Component
from QSExt.ReportGenerator.components.registry import ComponentRegistry

class MyComponent(Component):
    name = "my_component"

    def render(self, data, params, theme, renderer):
        return f"<div>{data}</div>"

ComponentRegistry.register("my_component", MyComponent)
```

---

## 8. 主题系统

| 类别 | 属性 | 默认值 | 说明 |
|------|------|--------|------|
| 颜色 | `primary_color` | `#2B579A` | 主色调 |
| | `accent_color` | `#4472C4` | 强调色 |
| | `bg_color` | `#FFFFFF` | 页面背景 |
| | `text_color` | `#333333` | 正文颜色 |
| | `muted_text_color` | `#666666` | 次要文字 |
| | `border_color` | `#E0E0E0` | 边框颜色 |
| 图表 | `chart_colors` | 8 色调色板 | 图表系列配色 |
| 排版 | `font_family` | `Microsoft YaHei, ...` | 字体栈 |
| | `base_font_size` | `14px` | 基准字号 |
| 表格 | `table_header_bg` | `#F5F7FA` | 表头背景色 |
| | `table_stripe_bg` | `#FAFBFC` | 斑马纹背景 |

---

## 9. 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 抽象方式 | 唯一的 `ReportGenerator` 基类 | 子类化足以覆盖所有场景，不需要 Scene vs Node 的二分 |
| 数据映射 | 场景代码直接映射，无配置段 | `create_nodes` 创建了节点，场景天然知道它们的产出结构 |
| 样式管理 | YAML 声明式布局 + 组件库 | 非开发人员可调整；组件跨场景复用 |
| 配置职责 | YAML 只存参数和布局 | 避免配置变成脚本语言 |
| 渲染器 | 策略模式（HtmlRenderer / MarkdownRenderer） | 格式可独立扩展 |

---

## 10. 测试

测试文件位于 `tests/test_ReportGenerator.py`，覆盖：

- `DataContext` — 数据存取、日期推断
- `split_output_for_factor` — 按因子名拆分
- `Theme` — CSS 生成、布局
- `HtmlRenderer` / `MarkdownRenderer` — 表格、图表、KPI 卡片、页面组装
- `Component` — Chart、DataTable、StatGrid、FactorSummary、Section
- `LayoutRenderer` — 端到端 HTML/Markdown 渲染
- `Config` — YAML 加载
- `End-to-End` — 完整流水线
- `SingleFactorReport` — 创建、渲染、Markdown 格式
- `SingleStrategyReport` — 创建、数据加工、渲染、回撤分析、分时段收益

手动测试脚本：
- `scripts/run_factor_report_manual.py` — 单因子报告（BaoStockDB 数据源）
- `scripts/run_strategy_report_manual.py` — 单策略报告（模拟数据）
