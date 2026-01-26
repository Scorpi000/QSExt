# -*- coding: utf-8 -*-
"""估值表解析特殊处理"""

# 对 detail 进行特殊处理，在解析 detail 之前进行
def merge_rows(detail):
    detail[detail.columns[0]] = detail.iloc[:, 0].fillna(method="bfill")
    def _merge_rows(df):
        return df.fillna(method="bfill").iloc[0]
    detail = detail.groupby(by=[detail.columns[0]], as_index=False).apply(_merge_rows)
    return detail