# ReportGenerator — 回测报告生成系统

## 1. 背景与动机

QuantStudio 的回测框架（`QuantStudio.BackTest`）提供了 IC 分析、分位数组合、因子换手率等回测模块。每个 `BTNode` 的 `backward_compute()` 产出包含 DataFrame 的 dict，其内置的 `genReport()` 可生成 HTML 报告，但存在以下局限：

- **样式与代码耦合**：报告样式硬编码在各 BTNode 的 `genReport()` 中，修改外观需要改动 QuantStudio 源码
- **多场景复用困难**：不同需求（单因子报告、多因子对比、策略回测报告）需要重复编写相似的组装和渲染代码
- **单一输出格式**：仅支持 HTML，无法生成 Markdown 或未来扩展 PDF 等格式
- **单因子效率低**：对多个因子逐个测试需要多次 `Engine.run()`，无法一次执行、按因子拆分

本模块建立一套**场景驱动的报告生成框架**，核心思想是：

> **回测逻辑**（Python） + **报告布局**（YAML） + **可视化组件**（组件库） = 报告

---

## 2. 模块结构

```
QSExt/ReportGenerator/
├── __init__.py                     # 包入口
├── core.py                         # Scenario 基类（纯渲染）, DataContext, ScenarioResult
├── layout.py                       # LayoutRenderer（YAML 布局 → 组件树 → 报告）
├── node.py                         # ReportGeneratorNode（DAG 内渲染节点）
│
├── components/                     # 可复用可视化组件库
│   ├── base.py                     # Component 抽象基类
│   ├── registry.py                 # ComponentRegistry 全局注册表
│   ├── chart.py                    # Chart 组件 + 7 种内置图表类型
│   ├── data_table.py               # DataTable 组件
│   ├── stat_grid.py                # StatGrid KPI 卡片组
│   ├── factor_summary.py           # FactorSummary 因子概况
│   └── section.py                  # Section 布局容器
│
├── themes/                         # 主题系统
│   ├── base.py                     # Theme 基类（颜色/字体/间距/CSS）
│   └── default.py                  # DefaultTheme 默认主题
│
├── renderers/                      # 输出格式渲染器
│   ├── base.py                     # ReportRenderer 抽象基类
│   ├── html_renderer.py            # HtmlRenderer（自包含 HTML，图表 base64 内嵌）
│   └── md_renderer.py              # MarkdownRenderer（复用 QSExt.Tools.Markdown）
│
└── scenarios/                      # 场景目录
    └── single_factor/              # 单因子全面测试场景
        ├── scenario.py             # SingleFactorScenario（纯渲染） + create_modules()
        └── config.yaml             # 参数 + 报告布局声明
```

---

## 3. 三大核心抽象

### 3.1 Scenario — 负责"从结果生成报告"

```python
from QSExt.ReportGenerator.core import Scenario, ScenarioResult

class Scenario:
    name: str                           # 场景标识
    config: dict                        # 从 config.yaml 加载的完整配置

    def prepare_data_context(self, output, factor_names) -> DataContext:
        """准备渲染上下文。基类默认实现，可覆盖以注入额外元数据。"""

    def render(self, output: dict, factor_names: List[str]) -> ScenarioResult:
        """从回测结果 dict 生成报告（纯渲染，不涉及回测编排）。
        
        这是 Scenario 的唯一主入口。输入是回测完成后产出的 output dict，
        输出是结构化报告。
        """
```

**Scenario 不再负责回测 DAG 构造**。回测编排由独立的 `create_modules()` 函数负责（或在计算图内由 `ReportGeneratorNode` 承担）。Scenario 专注于一件事：拿到结果 dict，渲染报告。

**子类职责**：只需覆盖 `prepare_data_context()`（约 10 行）以注入场景特定的元数据。

### 3.2 ReportGeneratorNode — 负责"在计算图内渲染"

```python
from QSExt.ReportGenerator.node import ReportGeneratorNode

class ReportGeneratorNode(Node):
    """DAG 节点：聚合 BTNodes 输出 + 渲染报告。
    
    DAG 拓扑: BTNodes → ReportGeneratorNode
    
    与 Scenario.render() 等效，但渲染发生在 Engine 执行流程内部，
    而非事后调用。适合需要统一生命周期的场景。
    """
```

**两种使用路径**：

| 路径 | 组件 | 适用场景 |
|------|------|----------|
| 事后渲染 | `Scenario.render(output, factor_names)` | 已有结果 dict，快速生成报告 |
| 图内渲染 | `ReportGeneratorNode(bt_nodes, ...)` | 需要渲染参与 DAG 生命周期 |

### 3.3 Component — 负责"怎么渲染一个视觉单元"

```python
from QSExt.ReportGenerator.components.base import Component

class Component(ABC):
    name: str  # 注册名

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

**内置图表类型**（Chart 组件的 `type` 参数）：

| type | 说明 |
|------|------|
| `ic_bar` | IC 柱状图 |
| `ic_decay_bar` | IC 衰减柱状图 |
| `nav_curve` | 净值曲线 |
| `turnover_area` | 换手率面积图 |
| `heatmap` | 相关性热力图 |
| `bar_chart` | 通用柱状图 |
| `line_chart` | 通用折线图 |

### 3.4 DataContext — 负责"数据从哪里来"

```python
from QSExt.ReportGenerator.core import DataContext

ctx = DataContext(output_dict, factor_names, config)

# 组件通过两级映射获取数据
df = ctx.get("0-Rank IC 分析", "IC")       # → DataFrame
meta = ctx.get("meta", "factor_names")      # → List[str]
info = ctx.get("meta", "factor_info")       # → dict（场景注入）
```

内部结构：`{source_name: {key: value}}`，其中 `source` 对应 `BTReport` 输出 dict 中的模块 key（如 `"0-Rank IC 分析"`），`key` 对应该模块 dict 中的数据键（如 `"IC"`、`"统计数据"`）。

---

## 4. 数据流

```
调用者                           回测编排（独立函数）                报告生成（Scenario）
───────                         ──────────────────                ──────────────────
  │                                                                       │
  ├── factors, price, mask, ...                                          │
  │        │                                                              │
  │        ▼                                                              │
  │  create_modules(factors, ...)   ← 构建 BTNode DAG                    │
  │        │                                                              │
  │        ├── CalcIC(...)(factors) → ICNode                              │
  │        ├── makeQuantilePortfolio(f) → PFNodes                         │
  │        ├── CalcFactorTurnover(...) → TurnoverNode                     │
  │        └── → [ICNode, PFNode_A, ..., TurnoverNode]                    │
  │        │                                                              │
  │        ▼                                                              │
  │  Engine.run([BTReport(nodes)], context)  ← 执行计算图                 │
  │        │   或: Engine.run([ReportGeneratorNode(nodes, ...)], context) │
  │        │                                                              │
  │        ▼                                                              │
  │  Unified output dict:                                                 │
  │    {                                                                  │
  │      "0-Rank IC 分析":  {"IC": DF(cols=[A,B,C]), ...},              │
  │      "2-分位数组合(A)":  {"净值": DF, ...},                          │
  │      "3-因子换手率":     {"换手率": DF(cols=[A,B,C])},              │
  │    }                                                                  │
  │        │                                                              │
  │        └──────────────────────────────────────┐                       │
  │                                               ▼                       │
  │                                      scenario.render(output,          │
  │                                                      factor_names)    │
  │                                               │                       │
  │                                     (1) split_output_for_factor       │
  │                                         → 按因子名列切片              │
  │                                               │                       │
  │                                     (2) LayoutRenderer.render(        │
  │                                           config.report,              │
  │                                           DataContext(output_A),      │
  │                                           theme, fmt)                 │
  │                                               │                       │
  │                                         ├── header（因子概况）        │
  │                                         ├── sections（IC/组合/...）   │
  │                                         └── assemble_page → 完整报告  │
  │                                               │                       │
  │                                               ▼                       │
  │  ScenarioResult:                                                     │
  │    {                                                                  │
  │      output:   <完整 raw dict>,                                       │
  │      reports:  {"Factor_A": {"html": "...", "md": "..."}, ...},       │
  │      combined: {"html": "...", "md": "..."}                           │
  │    }                                                                  │
```

**关键变化**（v2）：回测编排（`create_modules` + `Engine.run`）与报告生成（`Scenario.render`）已解耦。
调用者可选择：
- **事后渲染**：`Engine.run` → 拿到 output dict → `Scenario.render(output, names)`
- **图内渲染**：`Engine.run([ReportGeneratorNode(nodes, ...)])` → 直接产出带渲染产物的 dict

---

## 5. 配置文件格式（config.yaml）

每个场景的配置文件分为两部分：**回测参数**（传给 `create_modules`）和**报告布局**（驱动组件渲染）。

### 5.1 回测参数段（`modules`）

```yaml
modules:
  ic:
    lookback: 31
    period_lookback: 1
    corr_method: "spearman"       # spearman | pearson | kendall
    rolling_avg_period: 12

  ic_decay:
    periods: [1, 2, 3, 6, 12]    # 衰减分析的回看周期（月）

  quantile_portfolio:
    group_num: 5
    ascending: false
    long_short_pairs: [[0, -1]]  # 多空组合 ID 对

  factor_turnover:
    lookback: 31
    period_lookback: 1
```

模块启用/禁用通过 **存在性** 控制：删除某个模块的配置块即禁用。

### 5.2 报告布局段（`report`）

```yaml
report:
  theme: default                              # 主题名
  page_title: "{factor_name} — 单因子测试报告"  # 支持占位符
  combined_title: "多因子对比测试报告"

  # ═══ 页眉 ═══
  header:
    component: section
    params:
      layout: grid
      columns: 3
    children:
      - component: factor_summary
        data:
          source: meta                       # 元数据通道
          key: factor_info
      - component: stat_grid
        data:
          source: 0-Rank IC 分析             # 引用回测模块输出
          key: 统计数据
        params:
          metrics:
            - {label: "Rank IC 均值", field: "IC均值", format: ".4f"}
            - {label: "ICIR",        field: "ICIR",   format: ".2f"}

  # ═══ 章节 ═══
  sections:
    - id: ic_analysis
      title: "一、Rank IC 分析"
      params:
        layout: two_column                   # single | two_column | grid
      children:
        - component: chart
          data:
            source: 0-Rank IC 分析
            key: IC
          params:
            type: ic_bar                     # 图表类型
            title: "IC 序列"
        - component: data_table
          data:
            source: 0-Rank IC 分析
            key: 统计数据
          params:
            precision: 4
            sortable: true

    - id: appendix
      title: "附录：完整统计数据"
      params:
        collapsible: true                    # 可折叠
        layout: single
      children:
        - component: data_table
          data:
            source: 0-Rank IC 分析
            key: 截面宽度
```

### 5.3 输出配置段（`output`）

```yaml
output:
  formats: ["html", "markdown"]
  per_factor_reports: true       # 每个因子独立报告
  combined_report: true          # 多因子汇总对比报告
```

### 5.4 布局节点通用属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `component` | string | 组件注册名（`chart` / `data_table` / `stat_grid` / `factor_summary` / `section`） |
| `title` | string | 章节/图表/表格标题 |
| `params.layout` | string | 布局类型：`single` / `two_column` / `grid` |
| `params.columns` | int | grid 布局的列数 |
| `params.collapsible` | bool | 是否可折叠 |
| `children` | list | 子组件列表（仅 section 容器有效） |
| `data.source` | string | 数据来源：`meta` 或 BTReport output 中的模块 key |
| `data.key` | string | 数据键名：source 下的具体 DataFrame 键 |
| `params.metrics` | list | 仅 stat_grid：`[{label, field, format}]` |
| `params.precision` | int | 仅 data_table：数值精度 |
| `params.type` | string | 仅 chart：图表类型名 |

---

## 6. 使用方法

### 6.1 基本用法 — 事后渲染（推荐）

回测和报告分离，各司其职：

```python
from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.BackTest.BackTestModel import BTReport
from QuantStudio.Factor.Factor import FactorContext

from QSExt.ReportGenerator.scenarios.single_factor.scenario import (
    SingleFactorScenario, create_modules
)

# 1. 准备因子
#    factors = [factor1, factor2, factor3]
#    price, mask = ...

# 2. 准备 FactorContext
context = FactorContext(DTRuler=dt_ruler, SectionIDs=section_ids)

# 3. 回测：构建 BTNodes + Engine 执行
nodes = create_modules(factors, price=price, mask=mask)
report_node = BTReport(bt_node_list=nodes)
output = Engine().run([report_node], context)[0]

# 4. 报告：Scenario 纯渲染
scenario = SingleFactorScenario()
result = scenario.render(output, [f.Name for f in factors])

# 5. 获取结果
# result.reports["factor1"]["html"]     → HTML 报告
# result.reports["factor1"]["markdown"] → Markdown 报告
# result.combined["html"]               → 汇总对比报告

# 6. 保存报告
for name, report in result.reports.items():
    with open(f"report_{name}.html", "w", encoding="utf-8") as f:
        f.write(report["html"])
```

### 6.2 图内渲染 — 使用 ReportGeneratorNode

将报告渲染纳入计算图，一步到位：

```python
from QuantStudio.Core.CalcEngine import Engine
from QSExt.ReportGenerator.node import ReportGeneratorNode
from QSExt.ReportGenerator.scenarios.single_factor.scenario import create_modules

nodes = create_modules(factors, price=price, mask=mask)
factor_names = [f.Name for f in factors]

rg_node = ReportGeneratorNode(
    bt_nodes=nodes,
    factor_names=factor_names,
    report_config=scenario.config["report"],
    args={
        "OutputFormats": ["html", "markdown"],
        "PerFactorReports": True,
        "CombinedReport": True,
    }
)

result = Engine().run([rg_node], context)[0]
# result["_reports"]["factor1"]["html"]  → 完整 HTML 报告
# result["_combined"]["html"]            → 汇总对比报告
```

### 6.3 覆盖配置参数

```python
scenario = SingleFactorScenario(
    config_path="path/to/custom_config.yaml",
    output__formats=["html"],
)
```

### 6.4 自定义报告布局（不改代码）

只需编辑 `config.yaml` 的 `report` 段：

- **调整章节顺序**：重排 `sections` 列表
- **修改 KPI 指标**：编辑 `stat_grid` 的 `metrics` 列表
- **修改图表类型**：修改 `chart` 的 `params.type`
- **调整表格精度**：修改 `data_table` 的 `params.precision`

---

### 6.5 报告注册到图数据库

生成报告后可通过 `register_reports_to_db` 一键写入文件并注册到 QSGraphDB：

```python
from QSExt.ReportGenerator.core import register_reports_to_db

report_ids = register_reports_to_db(
    result=scenario_result,                # Scenario.render() 的返回值
    factor_qsids=["FACTOR_abc123", ...],   # 因子 QSID 列表
    output_dir="D:/reports/",              # 报告输出目录
    bt_qsid="d4e5f6a7...",                # 可选：关联的回测 QSID
    scenario_name="single_factor",         # 场景名称
)
# 返回: {"Factor_A_html": "rpt_001", "Factor_A_markdown": "rpt_002", ...,
#        "combined_html": "rpt_007", ...}
```

或直接使用 QSGraphDB 的手动方法：

```python
from QSExt.QSRegistry.QSGraphDB import QSGraphDB

gdb = QSGraphDB()
gdb.connect()
report_id = gdb.storeReport(
    report_path="D:/reports/momentum_report.html",
    factor_qsids=["FACTOR_abc123"],
    bt_qsid="d4e5f6a7...",
    scenario_name="single_factor",
)
```

## 7. 扩展指南

### 7.1 新增场景

1. 创建目录 `scenarios/<name>/`
2. 编写 `scenario.py`，包含两部分：

**回测编排**（独立函数）：

```python
def create_modules(factors, /, price=None, mask=None,
                   cat_data=None, weight=None, **kwargs) -> list:
    """构建该场景所需的 BTNode 列表。"""
    nodes = []
    # 在这里构建 CalcXX 算子和 BTNode
    return nodes
```

**报告场景**（可选子类，用于自定义数据准备）：

```python
from QSExt.ReportGenerator.core import Scenario, DataContext

class MyScenario(Scenario):
    name = "my_scenario"

    def prepare_data_context(self, output, factor_names):
        ctx = DataContext(output, factor_names, self.config)
        # 注入场景特定的元数据
        ctx.set("meta", "custom_info", {...})
        return ctx
```

3. 编写 `config.yaml`（参考 `single_factor/config.yaml`）

### 7.2 新增图表类型

```python
from QSExt.ReportGenerator.components.chart import Chart

# 1. 编写生成函数
def _render_my_chart(data, params, theme):
    fig = Figure(figsize=(14, 6))
    ax = fig.add_subplot(111)
    # ... matplotlib 绘图 ...
    return fig

# 2. 注册
Chart.register_chart_type("my_chart", _render_my_chart)

# 3. 在 YAML 中使用
# params:
#   type: my_chart
```

### 7.3 新增主题

1. 在 `themes/` 下新建文件，继承 `Theme`：

```python
from QSExt.ReportGenerator.themes.base import Theme

class DarkTheme(Theme):
    name = "dark"
    primary_color = "#6B9BD2"
    bg_color = "#1E1E1E"
    text_color = "#CCCCCC"
    # ... 覆盖更多属性 ...
```

2. 在 YAML 中切换：

```yaml
report:
  theme: dark
```

### 7.4 新增组件类型

```python
from QSExt.ReportGenerator.components.base import Component
from QSExt.ReportGenerator.components.registry import ComponentRegistry

class MyComponent(Component):
    name = "my_component"

    def render(self, data, params, theme, renderer):
        # 返回 HTML/Markdown 片段
        return f"<div>{data}</div>"

ComponentRegistry.register("my_component", MyComponent)
```

---

## 8. 主题系统

### 可配置属性

| 类别 | 属性 | 默认值 | 说明 |
|------|------|--------|------|
| 颜色 | `primary_color` | `#2B579A` | 主色调 |
| | `accent_color` | `#4472C4` | 强调色 |
| | `bg_color` | `#FFFFFF` | 页面背景 |
| | `text_color` | `#333333` | 正文颜色 |
| | `muted_text_color` | `#666666` | 次要文字 |
| | `border_color` | `#E0E0E0` | 边框颜色 |
| 图表 | `chart_colors` | 8 色调色板 | 图表系列配色（按序循环） |
| 排版 | `font_family` | `Microsoft YaHei, ...` | 字体栈 |
| | `base_font_size` | `14px` | 基准字号 |
| | `title_size` | `1.6em` | 页面标题大小 |
| | `section_size` | `1.25em` | 章节标题大小 |
| 间距 | `page_padding` | `24px` | 页面内边距 |
| | `section_margin` | `28px 0 16px 0` | 章节外边距 |
| | `card_padding` | `16px 20px` | KPI 卡片内边距 |
| 表格 | `table_header_bg` | `#F5F7FA` | 表头背景色 |
| | `table_stripe_bg` | `#FAFBFC` | 斑马纹背景 |
| | `table_hover_bg` | `#F0F4F8` | 悬停高亮 |

---

## 9. 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 样式管理 | YAML 声明式布局 + 组件库 | 非开发人员可调整；改样式不动 Python；组件跨场景复用 |
| 报告渲染 | 自定义渲染 raw dict，不复用 BTNode.genReport() | 需要统一风格和多格式输出；genReport() 是硬编码 HTML |
| 回测与报告分离 | 独立函数 + Scenario 纯渲染 | 报告生成不依赖 QuantStudio DAG，可被任何来源的 output dict 复用 |
| 图内渲染 | ReportGeneratorNode（DAG Node） | 需要统一生命周期或并行执行时，渲染可纳入计算图 |
| 场景表示 | 独立函数（create_modules）+ 可选 Scenario 子类 | 回测模块接线逻辑仍用 Python 代码保证灵活性；报告场景可定制元数据 |
| 配置职责 | YAML 只存参数和布局，不存接线 | 避免配置变成脚本语言 |
| 多因子执行 | 一次 Engine.run()，按因子名分列 | QuantStudio 原生支持多因子列式输出，避免 N 次重复执行 |
| 渲染器 | 策略模式（HtmlRenderer / MarkdownRenderer） | 输出格式可独立扩展，不影响组件和主题 |

---

## 10. 测试

测试文件位于 `tests/test_ReportGenerator.py`，40 个测试覆盖：

- `DataContext` — 数据存取、日期推断、元数据注入
- `split_output_for_factor` — 按因子名拆分 DataFrame、共享数据保留
- `Theme` — CSS 生成、single/two_column/grid 布局
- `HtmlRenderer` / `MarkdownRenderer` — 表格、图表、KPI 卡片、页面组装
- `Component` — Chart（7 种类型）、DataTable、StatGrid、FactorSummary、Section 容器
- `LayoutRenderer` — 端到端 HTML/Markdown 渲染
- `Config` — YAML 加载、source 名称一致性校验
- `End-to-End` — 完整流水线：3 因子 mock output → 拆分 → 逐因子渲染 → 汇总对比
- `ReportGeneratorNode` — 创建、聚合、逐因子渲染、汇总渲染、Markdown 格式、merge_result
- `ReportGeneratorNode Integration` — 与 ScenarioResult 格式兼容性

运行方式：

```bash
cd d:/HST/QSExt
python -m pytest tests/test_ReportGenerator.py -v
```
