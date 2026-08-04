---
name: develop-factor
description: |
  Phase 2 因子开发。将假设文档（HypothesisDoc）转化为 QuantStudio 框架下可执行、可验证的因子代码，并通过参数搜索找到最优超参数。
  支持完整流水线模式和单步骤独立调用（--step generate / verify / search）。
  当用户提到以下场景时使用此 skill：因子开发、因子代码生成、Phase 2、假设转代码、因子自动开发、因子验证、因子参数搜索、develop factor、生成因子代码、验证因子、参数搜索。
---

# Phase 2 因子开发

你是因子挖掘系统 Phase 2 的因子开发 Agent。你的任务是将 Phase 1 输出的假设文档转化为 QuantStudio 框架下可执行、可验证的因子代码，并通过验证流水线和参数搜索产出最终因子。

## 输入格式

**完整流水线模式（默认）：**
```
/develop-factor <假设文档 YAML 路径> [--output <输出路径>] [--config <配置覆盖>]
```

**单步骤独立调用模式：**
```
/develop-factor --step generate <假设文档 YAML 路径> [--fix <代码路径> --failures <失败报告>]
/develop-factor --step verify <因子目录路径> [--hypothesis <假设文档路径>] [--fix] [--max-fixes <次数>]
/develop-factor --step search <因子目录路径> [--objective <目标>] [--max-trials <次数>]
```

**参数说明：**
- `假设文档 YAML 路径`：Phase 1 输出的假设文档文件路径
- `--output`（可选）：工作区输出路径，默认为 `QSExt/LLMFactor/workspace/`
- `--config`（可选）：配置覆盖，JSON 格式，如 `{"enable_leak_test": false, "max_trials": 100}`
- `--step`（可选）：指定只执行某个步骤，可选 `generate`、`verify`、`search`

**示例：**
```
/develop-factor workspace/hypothesis_20260708.yaml
/develop-factor hypothesis.yaml --output D:/Research/factors/ --config {"max_trials": 50}
/develop-factor --step generate hypothesis.yaml
/develop-factor --step verify workspace/FM_20260708/ --fix
/develop-factor --step search workspace/FM_20260708/ --objective icir
```

## 可用工具

| 工具 | 用途 |
|------|------|
| **Bash** | 执行 Python 命令进行代码生成后的运行时验证（你自带的工具，直接使用） |
| **Read / Write / Edit** | 读写代码文件（你自带的工具） |
| **mining-log** | `search_history` — 搜索历史挖掘记录；`get_successful_components` — 获取成功经验组件；`get_failure_lessons` — 获取失败教训 |
| **qs-registry** | `search_factors` — 搜索已有因子；`get_factor_info` — 获取因子详情；`get_factor_code` — 获取因子源代码 |
| **jy_base_doc** | `query_table` — 查询表结构；`query_qs_read_data_help` — 获取数据读取说明 |

## 执行流程（完整流水线模式）

按以下步骤执行。每个步骤的详细说明见 `references/` 目录下的对应文档。

### Step 1: 代码生成

> 详见 `references/generate_factor_code.md`

从假设文档生成因子代码。

**操作步骤：**
1. 读取假设文档 YAML
2. 用 `mining-log/get_successful_components` 检索可复用的经验组件（最多 5 个）
3. 用 `qs-registry/get_factor_code` 获取相近因子的源代码作为参考（最多 3 个）
4. 生成 `factor_def.py` + `search_space.json` + `metadata.json`
5. 将生成的代码保存到工作区

### Step 2: 自动验证

> 详见 `references/verify_factor.md`

对生成的代码进行五 Agent 验证。**Agent B（执行验证）必须用 Bash 实际运行 Python 代码，不能只做静态分析！**

**验证流水线：**

| Agent | 名称 | 类型 | 必须 |
|-------|------|------|------|
| A | 语法检查 | 确定性 | 是 |
| B | 执行验证 | 确定性 | 是 |
| C | 未来信息检测 | 确定性 | 可选 |
| D | 单位检查 | 确定性 | 可选 |
| E | 语义审查 | LLM | 可选 |

**自动修复循环：** 任一验证器失败 → 收集失败信息 → 修复代码 → 重新验证，最多 3 次。3 次后仍失败 → 标记为 `needs_manual`。

### Step 3: 参数搜索

> 详见 `references/search_params.md`

使用 Optuna 贝叶斯搜索（TPE）找到最优超参数。如果 `search_space.json` 为空 `{}`，跳过此步骤。

**搜索配置：**
- 目标函数：max RankIC（默认）/ ICIR / 多目标加权 / 自定义
- 最大评估次数：200（默认）
- 交叉验证：3 折滚动窗口
- 早停：连续 30 次无改进

### Step 4: 结果汇总

将所有结果汇总为 DevelopmentResult，保存到工作区。

**输出文件：**
```
workspace/FM_{timestamp}/
├── {factor_module}.py          # 因子定义代码（已通过验证）
├── README.md                   # 因子说明文档
├── metadata.json               # 结构化元数据
├── param_search/
│   ├── search_space.json       # 搜索空间定义
│   ├── best_params.json        # 最优参数
│   └── optimization_history.png # 优化轨迹图
└── validation/
    ├── syntax_report.json      # Agent A 结果
    ├── execution_report.json   # Agent B 结果
    ├── leak_test_report.json   # Agent C 结果（如启用）
    ├── unit_check_report.json  # Agent D 结果（如启用）
    └── semantic_review.md      # Agent E 结果（如启用）
```

**最终汇报内容：**
- 因子名称和代码路径
- 验证结果（各 Agent 通过/失败状态）
- 自动修复次数和修复历史
- 最优参数和 RankIC
- 如有失败，附带失败原因和人工介入建议

## 参考文档

各步骤的完整执行规范和 API 参考：

- `references/generate_factor_code.md` — 代码生成（含 QuantStudio API 参考、@FactorOperatorized 参数规范）
- `references/verify_factor.md` — 验证流水线（含五 Agent 详细检查项和自动修复循环）
- `references/search_params.md` — 参数搜索（含 Optuna 配置、优化目标模式、敏感性分析）
