# -*- coding: utf-8 -*-
"""
测试 FactorScriptWriter: Factor 对象 → FactorDef 脚本

测试内容:
1. generate_script: 标准 BasicOperator 因子 → 可编译脚本
2. generate_script: 自定义算子 @FactorOperatorized

使用方法：
    C:/Users/hst/Project/PythonEnv/QS/Scripts/python.exe tests/test_factor_script_writer.py
"""

import datetime as dt
import os
import sys
import tempfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from QSExt.FactorDef.FactorScriptWriter import generate_script

nDT, nID = 20, 10
SectionIDs = [str(i).zfill(6) + ".SZ" for i in range(1, nID + 1)]
DTRuler = [dt.datetime(2025, 1, 1) + dt.timedelta(i) for i in range(nDT)]

Open = pd.DataFrame(np.random.rand(nDT, nID) * 10, index=DTRuler, columns=SectionIDs)
Close = pd.DataFrame(np.random.rand(nDT, nID) * 10, index=DTRuler, columns=SectionIDs)
Volume = pd.DataFrame(np.random.rand(nDT, nID) * 10000, index=DTRuler, columns=SectionIDs)


def test_generate_script_basic_ops():
    """测试 1: 标准算子因子 → 可编译脚本"""
    from QuantStudio.Factor.Factor import DataFactor
    import QuantStudio.Factor.BasicOperator as fo

    OpenF = DataFactor(data=Open, args={"Name": "Open"})
    CloseF = DataFactor(data=Close, args={"Name": "Close"})
    VolumeF = DataFactor(data=Volume, args={"Name": "Volume"})

    f1 = fo.mul(fo.add(OpenF, CloseF), VolumeF)
    f2 = fo.div(CloseF, OpenF)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test_factors.py")
        out = generate_script(
            factors=[f1, f2],
            meta={
                "TargetTable": "stock_cn_factor_test",
                "IDType": "A股",
                "Author": "Test",
                "Description": "测试因子",
                "Tags": ["test"],
            },
            output_path=path,
            factor_names=["test_momentum", "test_ratio"],
        )

        with open(out, "r", encoding="utf-8") as f:
            code = f.read()

        compile(code, out, "exec")
        print("[PASS] test_generate_script_basic_ops")
        print("  生成的脚本 (前15行):")
        for line in code.split("\n")[:15]:
            print(f"  {line}")
        print("  ...")
    return True


def test_generate_script_with_custom_op():
    """测试 2: 含自定义算子的因子 → 可编译脚本"""
    from QuantStudio.Factor.Factor import DataFactor
    from QuantStudio.Factor.FactorOperation import FactorOperatorized

    OpenF = DataFactor(data=Open, args={"Name": "Open"})

    @FactorOperatorized(
        operator_type="Point",
        args={"Arity": 1, "DataType": "double"},
    )
    def myCustomOp(f, idt, iid, x, args):
        return x[0] ** 2 + 1

    factor = myCustomOp(OpenF)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test_custom.py")
        out = generate_script(
            factors=[factor],
            meta={
                "TargetTable": "stock_cn_factor_test",
                "IDType": "A股",
                "Author": "Test",
            },
            output_path=path,
            factor_names=["custom_test"],
        )

        with open(out, "r", encoding="utf-8") as f:
            code = f.read()

        compile(code, out, "exec")
        print("[PASS] test_generate_script_with_custom_op")
        print("  生成的脚本 (前15行):")
        for line in code.split("\n")[:15]:
            print(f"  {line}")
        print("  ...")

    return True


# ─── 运行 ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("测试 FactorScriptWriter")
    print("=" * 60)

    test_generate_script_basic_ops()
    test_generate_script_with_custom_op()

    print()
    print("=" * 60)
    print("全部测试通过!")
    print("=" * 60)
