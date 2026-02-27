import os
import gc
import csv
import json
import time
import shutil
import traceback
import datetime as dt
from typing import List, Dict, Any, Optional
from multiprocessing import Process, Queue, Pool

import pymssql


# 将整数n近似平均的分成m份
def distributeEqual(n, m):
    Quotient, Remainder = int(n/m), n%m
    return [Quotient + 1] * Remainder + [Quotient] * (m - Remainder)

# 将一个list或者tuple平均分成m段
def partitionList(data,m,n_head=0,n_tail=0):
    n = len(data)
    PartitionNode = distributeEqual(n, m)
    SubData = []
    for i in range(m):
        StartInd = sum(PartitionNode[:i])
        EndInd = StartInd + PartitionNode[i]
        StartInd = max((StartInd-n_head,0))
        EndInd = min((EndInd+n_tail,n+1))
        SubData.append(data[StartInd:EndInd])
    return SubData


class MockedConn:
    class MockedCursor:
        def __init__(self, *args, **kwargs):
            self.ColInfo =  [
                ("SecuCode", "VARCHAR(200)", "NO"),
                ("SecuMarket", "INT", "YES"),
                ("ListedDate", "DATETIME", "YES"),
                ("JSID", "BIGINT", "NO")
            ]
            self.Rows =  [
                ("000001", 90, None, 1000),
                ("600000", 83, dt.datetime.today(), 2000)
            ]
        
        def execute(self, sql: str):
            if "INFORMATION_SCHEMA.COLUMNS" in sql:
                # COLUMN_NAME, DATA_TYPE, IS_NULLABLE 
                self.SQLType = "col_info"
            else:
                self.SQLType = "rows"
        
        def fetchall(self):
            if self.SQLType == "col_info":
                return self.ColInfo
            elif self.SQLType == "rows":
                return self.Rows
            else:
                raise Exception(f"未知的 SQLType: {self.SQLType}")
        
        def fetchone(self):
            return (2, )
        
        def close(self):
            pass
    
    def __init__(self, *args, **kwargs):
        pass
    
    def cursor(self):
        return self.MockedCursor()
    
    def close(self):
        pass


class SQLServerExporter:
    def __init__(
        self,
        server: str,
        port: str, 
        database: str,
        username: str,
        password: str, 
        export_dir: str = "exports",
        batch_size: int = 10000
    ):
        self.server = server
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.export_dir = export_dir
        self.batch_size = batch_size
        self.checkpoint_file = "export_checkpoint.json"
        
        # 确保导出目录存在
        os.makedirs(export_dir, exist_ok=True)
    
    def get_connection(self):
        """获取数据库连接"""
        #return MockedConn(
            #server=self.server,
            #database=self.database,
            #port=str(self.port), 
            #user=self.username,
            #password=self.password,
            #charset='GB18030'
        #)
        return pymssql.connect(
            server=self.server,
            database=self.database,
            port=str(self.port), 
            user=self.username,
            password=self.password,
            charset='UTF-8'
        )
    
    def get_checkpoint(self, token, table_name: str) -> Dict[str, Any]:
        """获取断点信息"""
        checkpoint_file = self.export_dir + os.sep + table_name + os.sep + self.checkpoint_file
        if os.path.exists(checkpoint_file):
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint = json.load(f)
                if checkpoint["token"]==token:
                    return checkpoint
                else:
                    return {}
        return {}
    
    def save_checkpoint(self, table_name: str, checkpoint: Dict[str, Any]):
        """保存断点信息"""
        checkpoint_file = self.export_dir + os.sep + table_name + os.sep + self.checkpoint_file
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint, f, ensure_ascii=False, indent=2)
    
    def get_table_info(self, table_name: str, max_id:Optional[int]=None, id_field:str="JSID") -> Dict[str, Any]:
        """获取表信息，包括列信息和总行数"""
        def merge_sqlserver_type(col, max_length, precision, scale):
            if col.lower() in ("varchar", "nvarchar", "char", "nchar", "binary", "varbinary"):
                return f"{col}({max_length})"
            elif col.lower() in ("decimal", "numeric"):
                return f"{col}({precision},{scale})"
            else:
                return col
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 获取列信息
            cursor.execute(f"""
                SELECT
                    c.name AS column_name,
                    ty.name AS data_type,
                    c.max_length AS max_length,
                    c.precision AS precision,
                    c.scale AS scale,
                    c.is_nullable AS is_nullable,
                    CASE WHEN pk.column_id IS NOT NULL THEN 'YES' ELSE 'NO' END AS is_pk,
                    CASE WHEN c.is_identity = 1 THEN 'YES' ELSE 'NO' END AS is_identity
                FROM sys.columns c
                INNER JOIN sys.tables t ON c.object_id = t.object_id
                INNER JOIN sys.types ty ON c.user_type_id = ty.user_type_id
                LEFT JOIN (
                    SELECT ic.object_id, ic.column_id
                    FROM sys.indexes i
                    INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                    WHERE i.is_primary_key = 1
                ) pk ON c.object_id = pk.object_id AND c.column_id = pk.column_id
                WHERE t.name = '{table_name}'
                ORDER BY c.column_id
            """)
            columns = cursor.fetchall()
            
            # 获取总行数
            if max_id is not None:
                cursor.execute(f"SELECT COUNT(*) FROM [{table_name}] WHERE {id_field} > {max_id}")
            else:
                cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
            total_rows = cursor.fetchone()[0]
            
            return {
                'columns': [{
                    'name': col[0], 
                    'type': merge_sqlserver_type(col[1], col[2], col[3], col[4]), 
                    'nullable': col[5], 
                    "is_pk": col[6], 
                    'is_identity': col[7]
                } for col in columns],
                'total_rows': total_rows
            }
        finally:
            cursor.close()
            conn.close()
    
    def get_index_info(self, table_name: str):
        """获取索引信息"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 获取列信息
            cursor.execute(f"""
                SELECT 
                    -- 索引基本信息
                    i.name AS index_name,
                    i.type_desc AS index_type,
                    CASE 
                        WHEN i.is_primary_key = 1 THEN 'Primary Key'
                        WHEN i.is_unique_constraint = 1 THEN 'Unique Constraint'
                        WHEN i.is_unique = 1 THEN 'Unique Index'
                        ELSE 'Non-Unique Index'
                    END AS constraint_type,
    
                    -- 列详细信息
                    c.name AS column_name,
                    ty.name AS data_type,
                    -- c.is_nullable,
    
                    -- 索引列属性
                    CASE 
                        WHEN ic.key_ordinal > 0 AND ic.is_included_column = 0 THEN 'Key Column (' + CAST(ic.key_ordinal AS varchar) + ')'
                        WHEN ic.is_included_column = 1 THEN 'Included Column'
                        ELSE 'Other'
                    END AS column_role,
                    ic.key_ordinal AS key_order,
                    CASE WHEN ic.is_descending_key = 1 THEN 'DESC' ELSE 'ASC' END AS sort_direction,
    
                    -- 索引其他属性
                    i.fill_factor,
                    i.filter_definition AS filter_condition,
                    ds.name AS filegroup_name
    
                FROM sys.indexes i
                INNER JOIN sys.tables t ON i.object_id = t.object_id
                INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
                INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                INNER JOIN sys.types ty ON c.user_type_id = ty.user_type_id
                INNER JOIN sys.data_spaces ds ON i.data_space_id = ds.data_space_id
                WHERE s.name = 'dbo'
                AND t.name = '{table_name}'
                AND i.type > 0  -- 排除堆表(Heap)
                ORDER BY 
                i.is_primary_key DESC,  -- 主键排前面
                i.name, 
                CASE WHEN ic.is_included_column = 1 THEN 999 ELSE ic.key_ordinal END""")

            columns = [col[0] for col in cursor.description]
            index_info = cursor.fetchall()
            return [columns] + index_info
        finally:
            cursor.close()
            conn.close()

    def export_del_table(self, token: str, table_name: str, last_del_id: Optional[int]=None, del_table_name="JYDB_DeleteRec", id_field:str="JSID", cursor=None):
        imported_cursor = (cursor is not None)
        if not imported_cursor:
            conn = self.get_connection()
            cursor = conn.cursor()
        try:
            if last_del_id is not None:
                cursor.execute(f"""SELECT TABLENAME, RECID, XGRQ, ID, JSID FROM {del_table_name} WHERE TABLENAME = '{table_name}' AND {id_field} > {last_del_id} ORDER BY {id_field}""")
            else:
                cursor.execute(f"""SELECT TABLENAME, RECID, XGRQ, ID, JSID FROM {del_table_name} WHERE TABLENAME = '{table_name}' ORDER BY {id_field}""")
            rows = cursor.fetchall()
        finally:
            if not imported_cursor:
                cursor.close()
                conn.close()
        if not rows: return None
        max_id = rows[-1][-1]
        # 写入CSV文件
        export_file = os.path.join(os.path.join(self.export_dir, table_name), f"{token}-DEL.csv")
        with open(export_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, escapechar="\\")
            writer.writerows(rows)
        return max_id
    
    def export_table(self, token: str, table_name: str, order_by: str = None, where_clause: str = None, del_table_name="JYDB_DeleteRec", id_field:str="JSID", resume: bool = True) -> str:
        """导出单个表"""
        print(f"开始导出表 {table_name}...")
        export_dir = os.path.join(self.export_dir, table_name)
        os.makedirs(export_dir, exist_ok=True)

        # 获取断点信息
        checkpoint = self.get_checkpoint(token, table_name)
        max_id = checkpoint.get("max_id", None)
        last_id = checkpoint.get('last_id', None)
        last_id = (max_id if last_id is None else last_id)
        last_del_id = checkpoint.get('last_del_id', None)
        idx = int(checkpoint.get("idx", 0))
        exported_rows = checkpoint.get('exported_rows', 0)

        # 获取表信息
        table_info = self.get_table_info(table_name, max_id=max_id, id_field=id_field)
        column_names = [col['name'] for col in table_info['columns']]
        
        # 构建导出文件路径
        header_file = os.path.join(export_dir, f"{token}.csv")
        
        # 如果文件已存在且不是断点续传，则删除旧文件
        if os.path.exists(header_file) and (not resume):
            os.remove(header_file)
        
        # 写入表头（如果是新文件）
        write_header = not os.path.exists(header_file) or (exported_rows == 0)
        if write_header:
            with open(header_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, escapechar="\\")
                writer.writerow(column_names)
                writer.writerow([col['type'] for col in table_info['columns']])
                writer.writerow([col['nullable'] for col in table_info['columns']])
                writer.writerow([col['is_pk'] for col in table_info['columns']])
        
        # 写入索引信息
        index_info = self.get_index_info(table_name=table_name)
        index_file = os.path.join(export_dir, f"{token}-INDEX.csv")
        with open(index_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, escapechar="\\")
            writer.writerows(index_info)
        
        # 类型映射
        def _gen_data_type_mapping(d):
            d = d.lower()
            if d=="varchar(-1)":
                return "ntext"
            elif d.startswith("varchar") or d.startswith("text") or d.startswith("char"):
                return "n"+d
            else:
                return None
        data_type_mapping = {col["name"]: m for col in table_info["columns"] if (m:=_gen_data_type_mapping(col["type"])) is not None}
        print(f"表 {table_name} 执行数据类型映射: {data_type_mapping}")
        conn = self.get_connection()
        cursor = conn.cursor()
        offset = 0# exported_rows
        total_exported = exported_rows
        try:
            while True:
                # 构建查询语句
                base_query = f"SELECT {', '.join([(f'[{col}]' if col not in data_type_mapping else f'CONVERT({data_type_mapping[col]}, [{col}]) AS {col}') for col in column_names])} FROM [{table_name}]"
                if where_clause:
                    base_query += f" WHERE {where_clause}"
                
                # 如果有排序字段，用于断点续传
                if order_by:
                    if last_id is not None:
                        if where_clause:
                            base_query += f" AND [{order_by}] > {last_id}"
                        else:
                            base_query += f" WHERE [{order_by}] > {last_id}"
                    base_query += f" ORDER BY [{order_by}]"

                # 执行查询
                query = f"{base_query} OFFSET {offset} ROWS FETCH NEXT {self.batch_size} ROWS ONLY"
                if not order_by:  # 如果没有排序字段，使用简单的分页
                    query = f"""
                        SELECT * FROM (
                            SELECT {', '.join([f'[{col}]' for col in column_names])}, ROW_NUMBER() OVER (ORDER BY {column_names[0]}) as rn
                            FROM [{table_name}]
                        ) t WHERE rn > {offset} AND rn <= {offset + self.batch_size}
                    """
                print(table_name, query)# DEBUG
                cursor.execute(query)
                rows = cursor.fetchall()
                
                if not rows:
                    break
                
                # 写入CSV文件
                export_file = os.path.join(export_dir, f"{token}-{str(idx).zfill(6)}.csv")
                with open(export_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f, escapechar="\\")
                    writer.writerows(rows)
                
                total_exported += len(rows)
                idx += 1
                
                # 更新断点
                if order_by and rows:
                    last_id = rows[-1][column_names.index(order_by)]
                    checkpoint = checkpoint | {
                        'token': token,
                        'max_id': max_id,
                        'last_id': last_id,
                        'idx': idx,
                        'exported_rows': total_exported,
                        'total_rows': table_info["total_rows"],
                        'export_time': dt.datetime.now().isoformat()
                    }
                    self.save_checkpoint(table_name, checkpoint)
                if len(rows) < self.batch_size:
                    break
                # offset += self.batch_size
                del rows
                rows = None
                gc.collect()
            # 导出删除记录
            last_del_id = self.export_del_table(token=token, table_name=table_name, last_del_id=last_del_id, del_table_name=del_table_name, id_field=id_field, cursor=cursor)
        except Exception as e:
            ifok, msg = False, traceback.format_exc()
        else:
            checkpoint = checkpoint | {
                'token': token,
                'data_file_num': idx + 1 + int(last_del_id is not None),
                'max_id': max_id,
                'last_id': last_id,
                'last_del_id': last_del_id,
                'idx': idx,
                'exported_rows': total_exported,
                'total_rows': table_info["total_rows"],
                'export_time': dt.datetime.now().isoformat()
            }
            self.save_checkpoint(table_name, checkpoint)
            ifok, msg = True, f"表 {table_name} 导出完成，共 {total_exported} 行"
        finally:
            cursor.close()
            conn.close()
        return ifok, msg, checkpoint
