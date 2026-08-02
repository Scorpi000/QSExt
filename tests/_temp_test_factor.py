# -*- coding: utf-8 -*-
__FACTOR_META__ = {
    "TargetTable": "test_table",
    "IDType": "A股",
    "Author": "Test",
}

def defFactor(fdi):
    from QuantStudio.Factor.Factor import DataFactor
    import QuantStudio.Factor.BasicOperator as fo
    close = fdi.FDB["JYDB"].getTable("日行情表").getFactor("close")
    open_ = fdi.FDB["JYDB"].getTable("日行情表").getFactor("open")
    factor = fo.div(close, open_)
    return [factor]
