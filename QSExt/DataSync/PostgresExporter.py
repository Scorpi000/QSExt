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

import psycopg2


class PostgresExporter:
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
        return psycopg2.connect(
            host=self.server,
            port=int(self.port), 
            database=self.database,
            user=self.username,
            password=self.password
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
    
    def get_table_list(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
        SELECT 
            tablename AS table_name
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY schemaname, tablename
        """)
        rslt = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return rslt

    def get_table_info(self, table_name: str, max_id:Optional[int]=None, id_field:str="JSID", where_clause: str = None) -> Dict[str, Any]:
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
                    c.column_name,
                    c.data_type,
                    c.character_maximum_length,
                    c.numeric_precision,
                    c.numeric_scale,
                    c.is_nullable,
                    CASE 
                        WHEN pk.column_name IS NOT NULL THEN 'YES' 
                        ELSE 'NO' 
                    END AS is_primary_key
                FROM 
                    information_schema.columns c
                LEFT JOIN (
                    SELECT 
                        kcu.column_name,
                        kcu.table_name,
                        kcu.table_schema
                    FROM 
                        information_schema.table_constraints tc
                    JOIN 
                        information_schema.key_column_usage kcu 
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                    WHERE 
                        tc.constraint_type = 'PRIMARY KEY'
                ) pk ON c.table_name = pk.table_name 
                    AND c.column_name = pk.column_name 
                    AND c.table_schema = pk.table_schema
                WHERE 
                    c.table_schema = 'public'
                    AND c.table_name = '{table_name}'
            """)
            columns = cursor.fetchall()
            
            # 获取总行数
            sql = f"SELECT COUNT(*) FROM {table_name} "
            if where_clause:
                sql += f" WHERE {where_clause}"
            if max_id is not None:
                if where_clause:
                    sql += f" AND {id_field} > {max_id}"
                else:
                    sql += f" WHERE {id_field} > {max_id}"
            cursor.execute(sql)
            # if max_id is not None:
            #     cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {id_field} > {max_id}")
            # else:
            #     cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            total_rows = cursor.fetchone()[0]
            
            return {
                'columns': [{
                    'name': col[0], 
                    'type': merge_sqlserver_type(col[1], col[2], col[3], col[4]), 
                    'nullable': col[5], 
                    "is_pk": col[6]
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
                WITH index_info AS (
                    SELECT 
                        i.schemaname,
                        i.tablename,
                        i.indexname,
                        CASE WHEN pg_index.indisunique THEN 'UNIQUE INDEX' ELSE 'NONUNIQUE INDEX' END AS constraint_type,
                        pg_index.indisprimary AS is_primary,
                        pg_index.indkey,
                        pg_index.indoption,
                        pg_class.oid AS index_oid,
                        pg_index.indrelid AS table_oid
                    FROM pg_indexes i
                    JOIN pg_class ON pg_class.relname = i.indexname
                    JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace 
                        AND pg_namespace.nspname = i.schemaname
                    JOIN pg_index ON pg_index.indexrelid = pg_class.oid
                    WHERE i.schemaname = 'public'
                    AND i.tablename = '{table_name}'
                )
                SELECT 
                    ii.schemaname AS schema_name,
                    ii.tablename AS table_name,
                    ii.indexname AS index_name,
                    ii.constraint_type,
                    ii.is_primary,
                    a.attname AS column_name,
                    CASE 
                        WHEN (ii.indoption[array_position(ii.indkey, a.attnum) - 1] & 1) = 0 
                        THEN 'ASC' 
                        ELSE 'DESC' 
                    END AS sort_direction,
                    array_position(ii.indkey, a.attnum) AS column_position
                FROM index_info ii
                JOIN pg_attribute a ON a.attrelid = ii.table_oid
                    AND a.attnum = ANY(ii.indkey)
                ORDER BY ii.indexname, column_position;""")

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
            writer = csv.writer(f)
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
        table_info = self.get_table_info(table_name, max_id=max_id, id_field=id_field, where_clause=where_clause)
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
                writer = csv.writer(f)
                writer.writerow(column_names)
                writer.writerow([col['type'] for col in table_info['columns']])
                writer.writerow([col['nullable'] for col in table_info['columns']])
                writer.writerow([col['is_pk'] for col in table_info['columns']])
        
        # 写入索引信息
        index_info = self.get_index_info(table_name=table_name)
        index_file = os.path.join(export_dir, f"{token}-INDEX.csv")
        with open(index_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(index_info)
        
        conn = self.get_connection()
        cursor = conn.cursor()
        offset = 0# exported_rows
        total_exported = exported_rows
        try:
            while True:
                # 构建查询语句
                base_query = f"SELECT {', '.join([f'{col}' for col in column_names])} FROM {table_name}"
                if where_clause:
                    base_query += f" WHERE {where_clause}"
                
                # 如果有排序字段，用于断点续传
                if order_by:
                    if last_id is not None:
                        if where_clause:
                            base_query += f" AND [{order_by}] > {last_id}"
                        else:
                            base_query += f" WHERE [{order_by}] > {last_id}"
                    base_query += f" ORDER BY {order_by}"

                # 执行查询
                query = f"{base_query} LIMIT {self.batch_size}"
                if not order_by:  # 如果没有排序字段，使用简单的分页
                    query = f"""
                        SELECT * FROM (
                            SELECT {', '.join([f'[{col}]' for col in column_names])}, ROW_NUMBER() OVER (ORDER BY {column_names[0]}) as rn
                            FROM [{table_name}]
                        ) t WHERE rn > {offset} AND rn <= {offset + self.batch_size}
                    """
                
                cursor.execute(query)
                rows = cursor.fetchall()
                
                if not rows:
                    break
                
                # 写入CSV文件
                export_file = os.path.join(export_dir, f"{token}-{str(idx).zfill(6)}.csv")
                with open(export_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
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

if __name__ == "__main__":
    import pandas as pd

    main_dir = r'D:\Data\PosgresSync'
    config = {
        'server': 'localhost',
        'port': '5433',
        'database': 'JYDB',
        'username': 'shzq',
        'password': 'shzq#321',
        'export_dir': main_dir,
        'batch_size': 2000000
    }
    exporter = PostgresExporter(**config)
    # exporter.export_table(token="aha", table_name="secumain", where_clause="innercode IN (3, 11, 310976, 1679, 300284, 398635)", order_by="jsid", resume=True)

    table_list = sorted(exporter.get_table_list(), reverse=True)
    excluded_tables = ["qt_tradingdaynew", "c_ex_datastock", "lc_indexcomponent", "lc_indexcomponentsweight", "qt_indexquote", "qt_csiindexquote"]
    for table_name in table_list:
        if table_name in excluded_tables: continue
        print(table_name)
        table_info = exporter.get_table_info(table_name=table_name)
        col_info = pd.DataFrame(table_info["columns"])
        col_list = col_info["name"].tolist()
        if "companycode" in col_list:
            exporter.export_table(token="aha", table_name=table_name, where_clause="companycode IN (3, 9, 17136463, 1460, 76931, 194602)", order_by="jsid", resume=True)
        elif "innercode" in col_list:
            exporter.export_table(token="aha", table_name=table_name, where_clause="innercode IN (3, 11, 310976, 1679, 300284, 398635)", order_by="jsid", resume=True)
        else:
            exporter.export_table(token="aha", table_name=table_name, where_clause=None, order_by="jsid", resume=True)

    print("===")