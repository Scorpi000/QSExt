# coding=utf-8
"""比较因子库中数据的差异"""
import datetime as dt

import numpy as np
import pandas as pd

from QuantStudio.Factor.HDF5DB import HDF5DB


def compare_dataframes(df1: pd.DataFrame, df2: pd.DataFrame, verbose: bool = True, if_float: bool=False, float_err=1e-6) -> dict:
    """
    全面比较两个 DataFrame 是否完全一致
    
    即使 index 或 columns 不一致，也会比较重合部分的数据
    
    Parameters:
    -----------
    df1, df2 : pd.DataFrame
        要比较的两个 DataFrame
    verbose : bool
        是否打印详细的比较结果
    
    Returns:
    --------
    dict : 包含各个维度的比较结果
    """
    
    results = {
        'is_identical': True,
        'shape_match': False,
        'index_match': False,
        'columns_match': False,
        'dtypes_match': False,
        'null_match': False,
        'values_match': False,
        'overlap_analysis': {},  # 新增：重合部分的分析
        'details': {}
    }
    
    # 1. 比较 shape
    results['shape_match'] = df1.shape == df2.shape
    if not results['shape_match']:
        results['is_identical'] = False
        results['details']['shape'] = {
            'df1_shape': df1.shape,
            'df2_shape': df2.shape
        }
        if verbose:
            print(f"❌ Shape 不一致: df1{df1.shape} vs df2{df2.shape}")
    else:
        if verbose:
            print(f"✅ Shape 一致: {df1.shape}")
    
    # 2. 比较 index
    try:
        results['index_match'] = df1.index.equals(df2.index)
        if not results['index_match']:
            results['is_identical'] = False
            # 找出差异
            common_index = df1.index.intersection(df2.index)
            only_in_df1 = df1.index.difference(df2.index)
            only_in_df2 = df2.index.difference(df1.index)
            
            results['details']['index'] = {
                'common': common_index.tolist(),
                'common_count': len(common_index),
                'only_in_df1': only_in_df1.tolist(),
                'only_in_df2': only_in_df2.tolist()
            }
            if verbose:
                print(f"❌ Index 不一致")
                print(f"   重合的 index ({len(common_index)} 个): {common_index.tolist()}")
                if len(only_in_df1) > 0:
                    print(f"   仅在 df1 中的 index ({len(only_in_df1)} 个): {only_in_df1.tolist()}")
                if len(only_in_df2) > 0:
                    print(f"   仅在 df2 中的 index ({len(only_in_df2)} 个): {only_in_df2.tolist()}")
        else:
            common_index = df1.index
            if verbose:
                print(f"✅ Index 一致 ({len(df1.index)} 个元素)")
    except Exception as e:
        results['index_match'] = False
        results['is_identical'] = False
        results['details']['index_error'] = str(e)
        common_index = pd.Index([])
    
    # 3. 比较 columns
    try:
        results['columns_match'] = df1.columns.equals(df2.columns)
        if not results['columns_match']:
            results['is_identical'] = False
            common_columns = df1.columns.intersection(df2.columns)
            only_in_df1 = df1.columns.difference(df2.columns)
            only_in_df2 = df2.columns.difference(df1.columns)
            order_diff = set(df1.columns) == set(df2.columns) and list(df1.columns) != list(df2.columns)
            
            results['details']['columns'] = {
                'common': common_columns.tolist(),
                'common_count': len(common_columns),
                'only_in_df1': only_in_df1.tolist(),
                'only_in_df2': only_in_df2.tolist(),
                'order_different': order_diff
            }
            if verbose:
                print(f"❌ Columns 不一致")
                print(f"   重合的 columns ({len(common_columns)} 个): {common_columns.tolist()}")
                if len(only_in_df1) > 0:
                    print(f"   仅在 df1 中的 columns ({len(only_in_df1)} 个): {only_in_df1.tolist()}")
                if len(only_in_df2) > 0:
                    print(f"   仅在 df2 中的 columns ({len(only_in_df2)} 个): {only_in_df2.tolist()}")
                if order_diff:
                    print(f"   列名相同但顺序不同")
        else:
            common_columns = df1.columns
            if verbose:
                print(f"✅ Columns 一致 ({len(df1.columns)} 个)")
    except Exception as e:
        results['columns_match'] = False
        results['is_identical'] = False
        results['details']['columns_error'] = str(e)
        common_columns = pd.Index([])
    
    # 4. 比较数据类型 (dtypes) - 只在重合的列上比较
    try:
        if len(common_columns) > 0:
            dtypes1 = df1[common_columns].dtypes
            dtypes2 = df2[common_columns].dtypes
            results['dtypes_match'] = dtypes1.equals(dtypes2)
            
            if not results['dtypes_match']:
                results['is_identical'] = False
                dtype_diff = dtypes1.compare(dtypes2)
                results['details']['dtypes'] = dtype_diff.to_dict()
                if verbose:
                    print(f"❌ 数据类型不一致 (在重合列中):")
                    print(f"   {dtype_diff}")
            else:
                if verbose:
                    print(f"✅ 数据类型一致 (在重合列中)")
        else:
            results['dtypes_match'] = False
            if verbose:
                print(f"⚠️  无法比较数据类型 (无重合列)")
    except Exception as e:
        results['dtypes_match'] = False
        results['is_identical'] = False
        results['details']['dtypes_error'] = str(e)
    
    # 5. 比较重合部分的 null 值分布
    try:
        if len(common_index) > 0 and len(common_columns) > 0:
            # 提取重合部分
            df1_overlap = df1.loc[common_index, common_columns]
            df2_overlap = df2.loc[common_index, common_columns]
            
            null_match = df1_overlap.isnull().equals(df2_overlap.isnull())
            results['null_match'] = null_match
            
            # 统计 null 值情况
            null_count1 = df1_overlap.isnull().sum().sum()
            null_count2 = df2_overlap.isnull().sum().sum()
            
            results['overlap_analysis']['null'] = {
                'df1_null_count': int(null_count1),
                'df2_null_count': int(null_count2),
                'overlap_shape': df1_overlap.shape
            }
            
            if not null_match:
                results['is_identical'] = False
                # 找出 null 值不同的位置
                null_diff = (df1_overlap.isnull() != df2_overlap.isnull())
                diff_locations = null_diff.any(axis=1)
                diff_rows = null_diff[diff_locations]
                
                # 详细记录差异
                diff_details = []
                for row_idx in diff_rows.index:
                    for col_idx in diff_rows.columns:
                        if null_diff.loc[row_idx, col_idx]:
                            diff_details.append({
                                'row': row_idx,
                                'column': col_idx,
                                'df1_is_null': pd.isna(df1.loc[row_idx, col_idx]),
                                'df2_is_null': pd.isna(df2.loc[row_idx, col_idx])
                            })
                
                results['details']['null'] = {
                    'different_cells_count': int(null_diff.sum().sum()),
                    'different_rows_count': int(diff_locations.sum()),
                    'sample_differences': diff_details[:5]
                }
                
                if verbose:
                    print(f"❌ Null 值分布在重合部分不一致")
                    print(f"   重合区域: {df1_overlap.shape[0]} 行 x {df1_overlap.shape[1]} 列")
                    print(f"   df1 有 {null_count1} 个 null, df2 有 {null_count2} 个 null")
                    print(f"   有 {diff_locations.sum()} 行的 null 分布不同")
                    if len(diff_details) > 0:
                        print(f"   示例差异:")
                        for diff in diff_details[:3]:
                            print(f"     [{diff['row']}, {diff['column']}] "
                                  f"df1_null={diff['df1_is_null']} vs df2_null={diff['df2_is_null']}")
            else:
                if verbose:
                    print(f"✅ Null 值分布在重合部分一致 (共 {null_count1} 个 null)")
                    print(f"   重合区域: {df1_overlap.shape[0]} 行 x {df1_overlap.shape[1]} 列")
        else:
            results['null_match'] = False
            if verbose:
                print(f"⚠️  无法比较 null 分布 (无重合的 index 或 columns)")
                
    except Exception as e:
        results['null_match'] = False
        results['is_identical'] = False
        results['details']['null_error'] = str(e)
        if verbose:
            print(f"❌ Null 比较时出错: {e}")
    
    # 6. 比较重合部分的 values
    try:
        if len(common_index) > 0 and len(common_columns) > 0:
            # 提取重合部分
            df1_overlap = df1.loc[common_index, common_columns]
            df2_overlap = df2.loc[common_index, common_columns]
            
            # 使用 equals 方法比较（正确处理 NaN）
            results['values_match'] = df1_overlap.equals(df2_overlap)
            
            if not results['values_match']:
                results['is_identical'] = False
                
                # 详细比较：找出具体哪些值不同
                if if_float:
                    comparison = ((df1_overlap - df2_overlap).abs() < float_err)
                else:
                    comparison = df1_overlap == df2_overlap
                both_nan = df1_overlap.isnull() & df2_overlap.isnull()
                match_mask = comparison | both_nan
                
                if not match_mask.all().all():
                    diff_mask = ~match_mask
                    diff_count = diff_mask.sum().sum()
                    
                    # 获取差异位置
                    diff_locations = []
                    diff_positions = np.argwhere(diff_mask.values)
                    
                    for i, (row_idx, col_idx) in enumerate(diff_positions[:10]):
                        row_label = df1_overlap.index[row_idx]
                        col_label = df1_overlap.columns[col_idx]
                        val1 = df1_overlap.iloc[row_idx, col_idx]
                        val2 = df2_overlap.iloc[row_idx, col_idx]
                        diff_locations.append({
                            'row': row_label,
                            'column': col_label,
                            'df1_value': val1,
                            'df2_value': val2,
                            'df1_type': type(val1).__name__,
                            'df2_type': type(val2).__name__
                        })
                    
                    results['details']['values'] = {
                        'total_differences': int(diff_count),
                        'sample_differences': diff_locations
                    }
                    
                    if verbose:
                        print(f"❌ Values 在重合部分不一致")
                        print(f"   重合区域: {df1_overlap.shape[0]} 行 x {df1_overlap.shape[1]} 列")
                        print(f"   共有 {diff_count} 个不同的值")
                        print(f"   前 {min(5, len(diff_locations))} 个差异示例:")
                        for diff in diff_locations[:5]:
                            print(f"     [{diff['row']}, {diff['column']}] "
                                  f"df1={diff['df1_value']!r} ({diff['df1_type']}) vs "
                                  f"df2={diff['df2_value']!r} ({diff['df2_type']})")
            else:
                if verbose:
                    print(f"✅ Values 在重合部分完全一致")
                    print(f"   重合区域: {df1_overlap.shape[0]} 行 x {df1_overlap.shape[1]} 列")
        else:
            results['values_match'] = False
            if verbose:
                print(f"⚠️  无法比较 values (无重合的 index 或 columns)")
                
    except Exception as e:
        results['values_match'] = False
        results['is_identical'] = False
        results['details']['values_error'] = str(e)
        if verbose:
            print(f"❌ Values 比较时出错: {e}")
    
    # 最终总结
    if verbose:
        if results['is_identical']:
            print("🎉 两个 DataFrame 完全一致！")
        else:
            print("⚠️  两个 DataFrame 存在差异")
            # 打印总结
            if not results['index_match'] or not results['columns_match']:
                print(f"\n📊 重合部分分析:")
                if len(common_index) > 0 and len(common_columns) > 0:
                    print(f"   - 重合区域: {len(common_index)} 行 x {len(common_columns)} 列")
                    print(f"   - Null 匹配: {'✅' if results['null_match'] else '❌'}")
                    print(f"   - Values 匹配: {'✅' if results['values_match'] else '❌'}")
                else:
                    print(f"   - 无重合区域可比较")
    return results


BmkFDB = HDF5DB(args={"MainDir": r"D:\Data\HDF5DB"}).connect()
BmkFT = BmkFDB.getTable("stock_cn_factor_value")
BmkFactorList = BmkFT.FactorNames

TgtFDB = HDF5DB(args={"MainDir": r"D:\Data\TestHDF5DB"}).connect()
TgtFT = TgtFDB.getTable("stock_cn_factor_value")
TgtFactorList = TgtFT.FactorNames

if BmkFactorList!=TgtFactorList:
    print("因子列表不相等")
    print("BMK: ", BmkFactorList)
    print("TGT: ", TgtFactorList)
else:
    print("因子列表相同")

for iFactor in sorted(set(BmkFactorList).intersection(TgtFactorList)):
    print("="*25 + f"比较 {iFactor}" + "="*25)
    iBmkData = BmkFT.readData(factor_names=[iFactor], dts=None, ids=None).iloc[0]
    iTgtData = TgtFT.readData(factor_names=[iFactor], dts=None, ids=None).iloc[0]
    iResult = compare_dataframes(iBmkData, iTgtData, verbose=True)
    print("="*50)

print("===")