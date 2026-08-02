# FactorScriptWriter — 因子定义脚本生成器

> 实现位于 `QSExt/FactorDef/FactorScriptWriter.py`

将 ``Factor`` 对象列表生成为可执行的 FactorDef 脚本（`.py` 文件），用于因子定义的导出、持久化和共享。

## 与 FactorScriptWriter 的关系

- **FactorDefContent.py**: 定义 `defFactor(fdi) -> List[Factor]` 的标准接口，脚本**由用户手写**
- **FactorScriptWriter.py**: **自动生成**符合上述接口的脚本，输入是已有的 `Factor` 对象

## 用法

```python
from QSExt.FactorDef.FactorScriptWriter import generate_script

generate_script(
    factors=[factor1, factor2],
    meta={
        "TargetTable": "stock_cn_factor_mining",
        "IDType": "A股",
        "Author": "MiningStudio",
        "Description": "GP 挖掘产出因子",
        "Tags": ["gp", "mining"],
    },
    output_path="~/FactorDef/Scripts/my_factors.py",
    factor_names=["factor_a", "factor_b"],
)
```

参数说明：

| 参数 | 类型 | 说明 |
|------|------|------|
| ``factors`` | ``List[Factor]`` | 要导出的因子对象列表 |
| ``meta`` | ``dict`` | ``__FACTOR_META__`` 字典，会自动填充 ``DefScriptPath`` |
| ``output_path`` | ``str`` | 输出文件路径 |
| ``factor_names`` | ``List[str]\|None`` | 因子名称列表，None 则使用因子自带 Name |

## 生成的脚本

生成的脚本采用"重建"模式：不内联展开表达式，而是逐步重建算子调用链。脚本结构：

```python
from typing import List

from QuantStudio.Factor.Factor import Factor, DataFactor
from QuantStudio.Factor.BasicOperator import rename
from QuantStudio.Factor.FactorOperation import FactorOperator
from QSExt.FactorDef.FactorDefContent import FactorDefInput

_deserialize_op = FactorOperator.deserialize

__FACTOR_META__ = { ... }

def defFactor(fdi: FactorDefInput) -> List[Factor]:
    """自动生成的因子定义"""
    Factors = []

    # 因子 1: factor_a
    _t_1 = fdi.FDB["JYDB"].getTable("日行情表").getFactor("Close")
    _t_2 = fdi.FDB["JYDB"].getTable("日行情表").getFactor("Open")
    _op_3 = _deserialize_op({"__class__": "QuantStudio.Factor.BasicOperator.Div", ...})
    _factor_4 = _op_3(_t_1, _t_2)
    Factors.append(rename(_factor_4, factor_name="factor_a", ...))

    return Factors
```

## 实现细节

1. **因子树展平**：将每个 Factor 的嵌套 Descriptors 树展平为波兰表示法（PN）序列
2. **算子序列化**：算子节点调用 ``op.serialize()``（即 ``FactorOperator.serialize()``），包含全路径类名、完整参数和 ``calculate_ref``
3. **终端因子**：从 ``_FactorTable`` 提取来源信息（FactorDB 名称和表名），在脚本中通过 ``fdi.FDB[...].getTable(...).getFactor(...)`` 获取
4. **常数节点**：``_DataContent == "Value"`` 的 DataFactor 作为直接赋值处理

## 依赖

- **QuantStudio** — ``Factor``、``FactorOperator`` 的 ``serialize()/deserialize()``
- **dill** — 自定义算子 ``calculate`` 函数的序列化（仅自定义算子时）