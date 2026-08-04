# Web 管理界面

> 因子挖掘系统的 Streamlit Web 管理界面：配置编辑、进程控制、实时监控、评测结果查看。
>
> 最后更新：2026-07-13

---

## 一、概述

Web 管理界面基于 Streamlit 构建，提供四个功能页面：

| 页面 | 功能 |
|------|------|
| **配置** | 编辑 4 个 YAML 配置文件，修改后直接写回磁盘 |
| **控制** | 启动/停止挖掘子进程，查看运行状态 |
| **监控** | 实时查看日志流和各轮次进度 |
| **结果** | 浏览评测结果：IC 曲线、分组收益、五维雷达图 |

---

## 二、快速启动

### 2.1 安装依赖

```bash
pip install streamlit plotly pyyaml streamlit-autorefresh
```

### 2.2 启动服务

```bash
# 从项目根目录
streamlit run QSExt/LLMFactor/web/app.py --server.port 8501
```

启动后访问 `http://localhost:8501`，左侧导航栏切换页面。

---

## 三、目录结构

```
QSExt/LLMFactor/web/
├── app.py                    # 主入口（页面标题、session_state 初始化）
├── pages/
│   ├── 1_配置.py             # 配置编辑页面
│   ├── 2_控制.py             # 进程控制页面
│   ├── 3_监控.py             # 实时监控页面
│   └── 4_结果.py             # 评测结果页面
├── components/
│   ├── charts.py             # 图表组件（IC 曲线、分组收益、雷达图）
│   ├── log_viewer.py         # 日志查看器（自动刷新、错误统计）
│   └── status_card.py        # 状态卡片（运行状态、轮次信息）
└── utils/
    ├── config_io.py          # 配置文件读写工具
    ├── process.py            # 挖掘进程管理器（启动/停止/状态查询）
    └── workspace.py          # 工作目录扫描（解析 FM_ 目录结构）
```

---

## 四、页面详解

### 4.1 配置页面（⚙️）

配置页面从指定目录加载 4 个 YAML 文件，以 Tab + 表单的形式展示所有字段，修改后点击「💾 保存」按钮写回 YAML。

#### 4.1.1 配置目录

页面顶部有一个「📁 配置目录」输入框，用于指定 YAML 配置文件所在目录：

- **默认值**：自动查找 `LLMFactor/config/` 目录
- **修改目录**：输入新的路径后，点击「🔄 重新加载」按钮从新目录读取配置
- **保存行为**：点击各 Tab 的「💾 保存」按钮时，配置会写入当前显示的目录；若目录不存在则自动创建

这允许将配置保存到不同位置（如工作区备份、实验性配置目录等）。

#### 4.1.2 四个配置 Tab

**🌐 全局流水线**（`pipeline.yaml`）

| 字段 | 类型 | 说明 |
|------|------|------|
| 项目根目录 | 文本 | `"auto"` 自动查找，或绝对路径 |
| Claude CLI 路径 | 文本 | `"auto"` 自动查找，或绝对路径 |
| 产出物输出目录 | 文本 | 绝对路径或相对路径，自动追加 `FM_<时间戳>` |
| 假设生成阶段最大轮次 | 整数 | Agent 最大对话轮次 |
| 因子开发阶段最大轮次 | 整数 | Agent 最大对话轮次 |
| 交易日起始/截止 | 日期文本 | 格式 `YYYY-MM-DD` |
| 股票截面日期 | 日期文本 | 格式 `YYYY-MM-DD` |
| 最大股票数量 | 整数 | 截面股票上限 |

**🔬 假设生成**（`hypothesis_research.yaml`）

| 字段 | 类型 | 说明 |
|------|------|------|
| 目标市场 | 下拉选择 | A股 / 港股 / 美股 |
| 数据频率 | 下拉选择 | 日频 / 周频 / 月频 |
| 最大方向数 | 整数 | 单次探索的研究方向上限 |
| 每方向最大 Wiki 页面数 | 整数 | 知识检索页面数上限 |
| 每方向最大因子代码数 | 整数 | 参考因子代码数上限 |
| 连续失败冻结阈值 | 整数 | 连续失败 N 次后冻结该方向 |

**🛠️ 因子开发**（`development.yaml`）

| 字段 | 类型 | 说明 |
|------|------|------|
| LLM 模型 | 文本 | 代码生成使用的模型名 |
| LLM 温度 | 浮点数 | 低温度确保生成一致性 |
| 最大自动修复次数 | 整数 | 代码验证失败后的自动修复上限 |
| 未来信息泄漏检测 | 开关 | 时序截断测试 |
| 单位检查 | 开关 | 检查因子值的量纲 |
| 语义审查 (LLM) | 开关 | 使用 LLM 审查代码逻辑 |
| 启用参数搜索 | 开关 | 关闭则跳过 Optuna 参数搜索 |
| 最大评估次数 | 整数 | Optuna 试验次数上限 |
| 交叉验证折数 | 整数 | 时序交叉验证折数 |
| 早停轮数 | 整数 | 连续无改进则停止搜索 |
| 优化目标 | 下拉选择 | rankic / icir / multi / custom |

**📊 因子评测**（`evaluation.yaml`）

| 字段 | 类型 | 说明 |
|------|------|------|
| 样本内起始/截止 | 月度文本 | 格式 `YYYY-MM` |
| 样本外起始/截止 | 月度文本 | 格式 `YYYY-MM` |
| 剔除 ST 股票 | 开关 | 股票池筛选 |
| 最小上市天数 | 整数 | 新股过滤 |
| 相关性方法 | 下拉选择 | spearman / pearson / kendall |
| IC 回溯期数 | 整数 | IC 计算的回溯窗口 |
| 因子回溯期数 | 整数 | 因子值的回溯窗口 |
| IC 衰减周期 | 逗号分隔文本 | 如 `1, 2, 3, 6, 12` |
| 分组数 | 整数 | 分组回测的组数 |
| 再平衡频率 | 下拉选择 | daily / weekly / monthly |
| Alpha t 统计量 | 浮点数 | 入库决策阈值 |
| 综合评分 | 浮点数 | 入库决策阈值 |
| 增量 IC t | 浮点数 | 多样性主关卡阈值 |
| OOS RankIC | 浮点数 | 样本外 RankIC 阈值 |
| 相关性预警阈值 | 浮点数 | 软约束，非硬门槛 |
| 五维评分权重 | 5 个浮点数 | effectiveness / stability / turnover / diversity / overfitting_risk |
| 写入挖掘日志库 | 开关 | 是否写入 PostgreSQL |
| 启用缓存 | 开关 | 因子数据缓存 |
| 缓存启动模式 | 下拉选择 | `continue` 复用 / `new` 清空 |
| 缓存目录 | 文本 | 留空使用系统临时目录 |

#### 4.1.2 配置预览

页面底部有可展开的「📋 当前配置预览」区域，以 JSON 格式展示 4 个配置文件的当前值，便于快速核对。

#### 4.1.3 工作流程

```
页面加载 → 自动查找配置目录 → 从 YAML 读取配置 → 填充表单控件
                                                        ↓
（可选）修改配置目录 → 点击「🔄 重新加载」→ 从新目录读取
                                                        ↓
                                              用户修改字段值
                                                        ↓
                                    点击「💾 保存」→ 写回当前目录的 YAML 文件
```

**注意事项**：
- 每个 Tab 有独立的保存按钮，只保存当前 Tab 对应的配置文件
- 修改配置目录后需点击「🔄 重新加载」才会从新目录读取；保存按钮始终写入当前显示的目录
- 目录不存在时，保存会自动创建目录及父目录
- YAML 文件中的注释在首次保存后会丢失（`yaml.safe_load` 不保留注释）
- `ic_decay_periods` 输入格式为逗号分隔的整数，如 `1, 2, 3, 6, 12`，格式有误时自动恢复默认值

---

### 4.2 控制页面（🎮）

控制页面管理挖掘子进程的生命周期。

#### 功能

- **状态卡片**：显示进程 PID、研究方向、运行模式、进度、已运行时间、工作目录
- **启动挖掘**：基于配置页面的参数，通过 `subprocess.Popen` 启动 `run_pipeline.py` 子进程
- **停止挖掘**：向子进程发送终止信号（Windows: `CTRL_BREAK_EVENT`，Linux: `SIGTERM`）
- **运行日志**：显示最近 30 行日志

#### 启动参数

控制页面从 `session_state.mining_config` 读取以下参数传递给子进程：

| 参数 | 命令行标志 | 默认值 |
|------|-----------|--------|
| 研究方向 | `--target` | 全部 |
| 运行模式 | `--mode` | skill |
| 最大轮次 | `--max-rounds` | 5 |
| 最大运行时间 | `--max-hours` | 4.0 |

#### 工作目录发现

启动后，进程管理器会等待子进程创建输出目录：
1. 在 `workspace_dir` 下查找 `loop_` 开头的目录（持续挖掘循环）
2. 在 `loop_` 目录下查找最新的 `FM_*` 子目录
3. 最长等待 30 秒，超时则报错

---

### 4.3 监控页面（📊）

监控页面提供实时日志查看和轮次进度概览。

#### 功能

- **工作目录输入**：自动填充控制页面启动时的工作目录，也支持手动输入
- **进度概览**：统计总轮次、入库数、拒绝数、精炼数
- **最近轮次**：展示最近 5 轮的因子名称、决策、评分、关键指标
- **日志查看**：
  - 自动扫描工作目录下的 `mining_loop.log`、`pipeline.log` 等日志文件
  - 支持选择不同日志文件
  - 可调整显示行数（50-500）
  - 安装 `streamlit-autorefresh` 后每 3 秒自动刷新
  - 显示日志总行数、错误数、警告数统计

#### 工作目录结构

监控页面支持两种目录结构：

```
# 单次运行
workspace/
└── FM_20260710_143000/
    ├── metadata.json
    ├── factor_def.py
    └── ...

# 持续挖掘循环
workspace/
└── loop_动量因子_20260710/
    ├── FM_20260710_143000/
    ├── FM_20260710_150000/
    └── mining_loop.log
```

---

### 4.4 结果页面（📈）

结果页面展示因子评测的详细结果。

#### 功能

- **因子汇总表格**：列出所有轮次的因子名称、类别、决策、评分、关键指标
  - 支持按决策（accepted / refining / rejected）筛选
  - 支持按类别筛选
  - 综合评分列使用进度条可视化
- **因子详情**（选择单个因子后展示）：
  - 指标卡片：综合评分、RankIC、ICIR
  - **五维雷达图**：有效性、稳定性、换手率、多样性、过拟合风险
  - **RankIC 曲线**：IC 时间序列 + 累计 IC 双轴图
  - **分组收益柱状图**：各分组的年化收益率
  - 元数据详情（JSON）
  - 因子代码（Python 源码）
  - README（因子说明文档）

#### 数据来源

结果页面从工作目录的 `metadata.json` 文件读取数据：

```
FM_xxx/
├── metadata.json        ← 主要数据来源
│   ├── factor_name
│   ├── category
│   ├── status
│   ├── decision.verdict
│   ├── evaluation.rankic_mean / rankicir / oos_rankic / composite_score
│   ├── evaluation.scores (五维评分)
│   ├── evaluation.ic_curve (IC 曲线数据)
│   └── evaluation.group_returns (分组收益数据)
├── factor_def.py        ← 因子代码
├── README.md            ← 因子说明
├── validation/          ← 验证结果
└── param_search/        ← 参数搜索结果
```

---

## 五、配置体系

### 5.1 配置文件关系

```
LLMFactor/config/
├── pipeline.yaml              → PipelineConfig（全局）
├── hypothesis_research.yaml   → ResearchConfig（假设生成）
├── development.yaml           → DevelopmentConfig（因子开发）
└── evaluation.yaml            → EvalConfig（因子评测）
```

配置加载链：

```
PipelineConfig.from_yaml("pipeline.yaml")
    ├── .load_hypothesis_config()  → ResearchConfig.from_yaml("hypothesis_research.yaml")
    ├── .load_development_config() → DevelopmentConfig.from_yaml("development.yaml")
    └── .load_evaluation_config()  → EvalConfig.from_yaml("evaluation.yaml")
```

### 5.2 Web 配置读写

Web 页面使用 `config_io.py` 工具模块直接读写 YAML 文件，不经过 `PipelineConfig` 等 dataclass：

```
页面加载 → config_io.load_all_configs() → 4 个 dict → 填充表单控件
保存按钮 → 从控件收集值 → config_io.save_config() → YAML 文件
```

这种设计的优点是 Web 页面可以独立于 pipeline 代码运行，不需要导入 `QuantStudio` 等重量级依赖。

### 5.3 命令行覆盖

Web 页面修改的配置文件会被命令行脚本自动加载。命令行参数（如 `--max-rounds`）会覆盖 YAML 中的对应值，优先级为：

```
命令行参数 > YAML 配置文件 > 代码默认值
```

---

## 六、常见操作

### 6.1 修改 Agent 轮次限制

1. 打开 **配置** 页面 → **🌐 全局流水线** Tab
2. 修改「假设生成阶段最大轮次」或「因子开发阶段最大轮次」
3. 点击「💾 保存全局配置」
4. 后续启动的挖掘任务自动使用新值

### 6.2 调整入库阈值

1. 打开 **配置** 页面 → **📊 因子评测** Tab
2. 在「入库决策阈值」区域修改 `min_alpha_t`、`min_composite_score` 等值
3. 点击「💾 保存因子评测配置」

### 6.3 切换 LLM 模型

1. 打开 **配置** 页面 → **🛠️ 因子开发** Tab
2. 修改「LLM 模型」字段（如改为 `claude-sonnet-5`）
3. 点击「💾 保存因子开发配置」

### 6.4 查看历史挖掘结果

1. 打开 **结果** 页面
2. 输入工作目录路径（如 `D:/HST/QSExt/local/workspace/loop_动量因子_20260710`）
3. 在汇总表格中浏览所有轮次
4. 选择单个因子查看详细图表

### 6.5 监控正在进行的挖掘

1. 通过 **控制** 页面启动挖掘后，工作目录自动填入 **监控** 页面
2. 日志每 3 秒自动刷新（需安装 `streamlit-autorefresh`）
3. 观察错误数和警告数统计，及时发现问题
