# -*- coding: utf-8 -*-
from typing import Optional, List

import pandas as pd


def dataframe2html_with_histograms(df: pd.DataFrame, pos_color:str='red', neg_color:str='green', max_width:int=100, target_cols:Optional[List[str]]=None, number_format:str|dict='{:.2f}') -> str:
    """
    将 DataFrame 转换为 HTML 表格, 在数值列中显示直方图
    
    Args:
        df: pandas DataFrame
        pos_color: 正值直方图颜色
        neg_color: 负值直方图颜色
        max_width: 直方图最大宽度(像素)
        target_cols: 需要绘制直方图的列名列表, None 表示 df 中的所有数值列
        number_format: 数值格式化字符串，如果为 dict 表示每一列单独设置, 未指定的则默认为 '{:.2f}'
    
    Returns:
        生成的 HTML 字符串
    """
    # 创建HTML表格开头
    html = '<table border="1" style="border-collapse: collapse; width: 100%;">\n'
    
    # 添加表头
    html += '  <thead>\n    <tr>\n'
    for col in df.columns:
        html += f'      <th style="padding: 8px; text-align: center;">{col}</th>\n'
    html += '    </tr>\n  </thead>\n'
    
    # 添加表格主体
    html += '  <tbody>\n'
    
    if target_cols is None: target_cols = df.columns

    if isinstance(number_format, str): number_format = {iField: number_format for iField in df.columns}

    for _, row in df.iterrows():
        html += '    <tr>\n'
        
        for col in df.columns:
            cell_value = row[col]
            
            # 判断是否为数值类型
            if pd.api.types.is_numeric_dtype(df[col]) and not pd.isna(cell_value) and (col in target_cols):
                # 计算该列的最大绝对值用于比例计算
                col_abs_max = df[col].abs().max()
                
                if col_abs_max == 0:
                    # 如果该列全为0，则不显示直方图
                    formatted_value = number_format.get(col, "{:.2f}").format(cell_value) if isinstance(cell_value, (int, float)) else str(cell_value)
                    html += f'      <td style="padding: 4px; text-align: center; position: relative;">{formatted_value}</td>\n'
                else:
                    # 计算直方图宽度
                    ratio = abs(cell_value) / col_abs_max
                    hist_width = int(ratio * max_width)
                    
                    # 设置直方图颜色
                    color = pos_color if cell_value >= 0 else neg_color
                    
                    # 格式化数值
                    formatted_value = number_format.get(col, "{:.2f}").format(cell_value)
                    
                    # 创建直方图容器
                    if cell_value >= 0:
                        # 正值：直方图从中间向右延伸，数值居中
                        html += f'''      <td style="padding: 4px; text-align: center; position: relative; min-width: {max_width}px;">
        <div style="position: absolute; left: 50%; height: 20px; background-color: {color}; 
                   width: {hist_width}px; transform: translateX(0%); z-index: 1;"></div>
        <div style="position: relative; z-index: 2; display: flex; justify-content: center; align-items: center; height: 100%;">
          {formatted_value}
        </div>
      </td>\n'''
                    else:
                        # 负值：直方图从中间向左延伸，数值居中
                        html += f'''      <td style="padding: 4px; text-align: center; position: relative; min-width: {max_width}px;">
        <div style="position: absolute; right: 50%; height: 20px; background-color: {color}; 
                   width: {hist_width}px; transform: translateX(0%); z-index: 1;"></div>
        <div style="position: relative; z-index: 2; display: flex; justify-content: center; align-items: center; height: 100%;">
          {formatted_value}
        </div>
      </td>\n'''
            else:
                # 非数值类型直接显示
                html += f'      <td style="padding: 8px; text-align: center;">{cell_value}</td>\n'
        
        html += '    </tr>\n'
    
    html += '  </tbody>\n</table>'
    return html
