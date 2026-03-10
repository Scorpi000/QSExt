import os
import csv
import traceback

import numpy as np
import pandas as pd

from QSExt.DataSync.PostgresImporter import PostgresImporter


csv.field_size_limit(2048 * 2048)

def read_table_info(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, escapechar="\\")
        headers = next(reader)# 读取表头
        data_type = next(reader)# 数据类型
        nullable = next(reader)# 是否可空
        pk = next(reader)# 是否为主键
    # 创建表结构信息
    columns_info = [{'name': col, 'type': data_type[i], 'nullable': nullable[i], 'pk': pk[i]} for i, col in enumerate(headers)]
    return columns_info

def read_data(table_name, file_path, header_file_path):
    columns_info = read_table_info(header_file_path)
    id_col_idx, datetime_col_idx, float_col_idx, int_col_idx = None, [], [], []
    for i, col in enumerate(columns_info):
        if col["name"].lower()=="id": id_col_idx = i
        if col["type"].lower().startswith("date"): datetime_col_idx.append(i)
        elif col["type"].lower().startswith("float"): float_col_idx.append(i)
        elif "int" in col["type"].lower(): int_col_idx.append(i)
    if id_col_idx is None: raise Exception(f"没有找到 ID 字段: {columns_info}")

    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, escapechar="\\")
        batch = list(reader)
        if batch and (batch[-1][0]=="salt"): batch = batch[:-1]# 去掉最后一行的 salt

    batch = np.array(batch, dtype="O")
    batch = np.where(batch!="", batch, None)
    # 处理特殊类型的字段
    # if datetime_col_idx:
    #     for i in datetime_col_idx:
    #         batch[:, i] = np.where(batch[:, i]!="", batch[:, i], None)
    if float_col_idx:
        for i in float_col_idx:
            batch[:, i] = batch[:, i].astype(float)
    if int_col_idx:
        for i in int_col_idx:
            mask = pd.isnull(batch[:, i])
            batch[:, i] = np.where(mask, batch[:, i], np.where(mask, 0, batch[:, i]).astype(int))
    
    headers = [col["name"] for col in columns_info]
    columns_str = ', '.join(headers)
    placeholders = ', '.join(['%s'] * len(headers))
    update_str = ", ".join(f"{col}=EXCLUDED.{col}" for col in headers if col.lower() != "id")
    insert_sql = f'INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders}) ON CONFLICT (id) DO UPDATE SET {update_str}'

    return batch.tolist(), insert_sql

def bifind_error_row(conn, sql, batch):
    cursor = conn.cursor()

    left, right = 0, len(batch) - 1
    # left, right = 15947, 15948# DEBUG
    while left < right:
        print(left, right)
        mid = left + (right - left) // 2
        ibatch = batch[left:mid+1]
        try:
            cursor.executemany(sql, ibatch)
            conn.commit()
        except:# 目标在左半部分
            right = mid
        else:# 目标在右半部分
            left = mid + 1
        if left == right:
            try:
                cursor.executemany(sql, batch[left:left+1])
                conn.commit()
            except:
                print(traceback.format_exc())
            return left
    return -1  # 未找到


if __name__=="__main__":
    config = {
        'host': 'localhost',
        'port': '5433',
        'database': 'JYDB',
        'username': 'shzq',
        'password': 'shzq#321',
        'import_dir': r'D:\Data\JYDBSync'
    }
    importer = PostgresImporter(**config)

    table_name = "LC_OperatingStatus"
    target_file_path = r"D:\Data\JYDBSync\LC_OperatingStatus\bf94af163d894dc78e6fd6d86f89c2b0-000001.csv"
    header_file_path = r"D:\Data\JYDBSync\LC_OperatingStatus\bf94af163d894dc78e6fd6d86f89c2b0.csv"

    batch, sql = read_data(table_name, target_file_path, header_file_path=header_file_path)
    conn = importer.get_connection()
    err_row_idx = bifind_error_row(conn=conn, sql=sql, batch=batch)
    print(err_row_idx)
    print("===")