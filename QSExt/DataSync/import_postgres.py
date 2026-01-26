import os
import csv
import json
import uuid
import time
import traceback
from datetime import datetime
from multiprocessing import Process, Queue
from typing import List, Dict, Any, Optional

import numpy as np
import psycopg2


class PostgresImporter:
    def __init__(self, host: str, port: str, database: str, username: str, password: str, import_dir: str = "exports"):
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.import_dir = import_dir
        self.checkpoint_file = "import_checkpoint.json"
    
    def get_connection(self):
        """获取数据库连接"""
        return psycopg2.connect(
            host=self.host,
            port=int(self.port), 
            database=self.database,
            user=self.username,
            password=self.password
        )
    
    def get_checkpoint(self, table_name: str) -> Dict[str, Any]:
        """获取断点信息"""
        checkpoint_file = self.import_dir + os.sep + table_name + os.sep + self.checkpoint_file
        if os.path.exists(checkpoint_file):
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint = json.load(f)
                return checkpoint
        return {}
    
    def save_checkpoint(self, table_name: str, checkpoint: Dict[str, Any]):
        """保存断点信息"""
        checkpoint_file = self.import_dir + os.sep + table_name + os.sep + self.checkpoint_file
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint, f, ensure_ascii=False, indent=2)
    
    def create_table_if_not_exists(self, table_name: str, columns_info: List[Dict[str, Any]]):
        """如果表不存在则创建表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 检查表是否存在
            cursor.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = '{table_name.lower()}'
                )
            """)
            
            exists = cursor.fetchone()[0]
            
            if not exists:
                # 构建建表语句
                column_defs = []
                for col in columns_info:
                    pg_type = self.map_sqlserver_type_to_postgres(col['type'])
                    nullable = 'NULL' if col['nullable'] == 'YES' else 'NOT NULL'
                    column_defs.append(f'{col["name"]} {pg_type} {nullable}')
                
                create_sql = f'CREATE TABLE {table_name} ({", ".join(column_defs)})'
                
                cursor.execute(create_sql)
                conn.commit()
                print(f"表 {table_name} 已创建")
            
        finally:
            cursor.close()
            conn.close()
    
    def map_sqlserver_type_to_postgres(self, sqlserver_type: str) -> str:
        """SQL Server 类型映射到 PostgreSQL 类型"""
        type_mapping = {
            'int': 'INTEGER',
            'bigint': 'BIGINT',
            'smallint': 'SMALLINT',
            'tinyint': 'SMALLINT',
            'bit': 'BOOLEAN',
            'decimal': 'DECIMAL',
            'numeric': 'NUMERIC',
            'float': 'DOUBLE PRECISION',
            'real': 'REAL',
            'money': 'DECIMAL(19,4)',
            'smallmoney': 'DECIMAL(10,4)',
            'char': 'CHAR',
            'varchar': 'VARCHAR',
            'text': 'TEXT',
            'nchar': 'CHAR',
            'nvarchar': 'VARCHAR',
            'ntext': 'TEXT',
            'datetime': 'TIMESTAMP',
            'datetime2': 'TIMESTAMP',
            'smalldatetime': 'TIMESTAMP',
            'date': 'DATE',
            'time': 'TIME',
            'datetimeoffset': 'TIMESTAMPTZ',
            'uniqueidentifier': 'UUID',
            'binary': 'BYTEA',
            'varbinary': 'BYTEA',
            'image': 'BYTEA',
            'xml': 'XML'
        }
        
        # 处理带长度的类型
        import re
        match = re.match(r'(\w+)(?:\((\d+)(?:,(\d+))?\))?', sqlserver_type.lower())
        if match:
            base_type = match.group(1)
            if base_type in type_mapping:
                pg_type = type_mapping[base_type]
                if match.group(2):
                    if match.group(3):  # 有精度和小数位数
                        pg_type += f"({match.group(2)},{match.group(3)})"
                    else:  # 只有长度
                        pg_type += f"({match.group(2)})"
                return pg_type
        
        return 'TEXT'  # 默认类型
    
    def get_max_id(self, table_name, id_field):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(f"""SELECT MAX({id_field}) FROM {table_name}""")
        max_id = cursor.fetchone()
        if max_id: return max_id[0]
        else: return None
    
    def import_table(self, token: str, table_name: str, resume: bool = True) -> int:
        """导入单个表"""
        print(f"开始导入表 {table_name}...")
        
        header_file =  self.import_dir + os.sep + table_name + os.sep + f"{token}.csv"
        if not os.path.exists(header_file):
            raise FileNotFoundError(f"表头文件不存在: {header_file}")
        with open(header_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)# 读取表头
            data_type = next(reader)# 数据类型
            nullable = next(reader)# 是否可空
        # 创建表结构信息
        columns_info = [{'name': col, 'type': data_type[i], 'nullable': nullable[i]} for i, col in enumerate(headers)]
        # 创建表（如果不存在）
        self.create_table_if_not_exists(table_name, columns_info)            
        
        # 获取断点信息
        checkpoint = self.get_checkpoint(table_name) if resume else {}
        imported_rows = checkpoint.get('imported_rows', 0)
        idx = int(checkpoint.get("idx", 0))
        
        # 读取CSV文件
        file_list = sorted((ifile for ifile in os.listdir(self.import_dir + os.sep + table_name) if ifile.startswith(token+"-") and ifile.endswith(".csv") and int(ifile.split(".")[0].split("-")[-1]) >= idx), key=lambda s: int(s.split(".")[0].split("-")[-1]))
        
        # 构建插入语句
        columns_str = ', '.join(headers)
        placeholders = ', '.join(['%s'] * len(headers))
        insert_sql = f'INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})'
        
        datetime_col_idx = [i for i, col in enumerate(columns_info) if col["type"].lower().startswith("date")]
        total_imported = imported_rows
        try:
            # 获取数据库连接
            conn = self.get_connection()
            cursor = conn.cursor()
            
            for ifile in file_list:
                with open(self.import_dir + os.sep + table_name + os.sep + ifile, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    batch = [row for row in reader]
                
                # 处理 datetime 字段
                if datetime_col_idx:
                    batch = np.array(batch, dtype="O")
                    for i in datetime_col_idx:
                        batch[:, i] = np.where(batch[:, i]!="", batch[:, i], None)
                    batch = batch.tolist()
                
                cursor.executemany(insert_sql, batch)
                conn.commit()
                total_imported += len(batch)
                idx += 1
                
                # 保存断点
                if resume:
                    self.save_checkpoint(table_name, {
                        'imported_rows': total_imported,
                        'import_time': datetime.now().isoformat(),
                        'idx': idx,
                    })
                    
        finally:
            cursor.close()
            conn.close()
        return total_imported


def execute_task(task):
    importer = task["importer"]
    try:
        imported_rows = importer.import_table(task["token"], task["table_name"])
        ifok, msg = True, f"共 {imported_rows} 行"
    except Exception as e:
        ifok, msg = False, traceback.format_exc()
    task["queue"].put((task["table_name"], ifok, msg))

def main( 
    main_dir: str,
    token: Optional[str] = None,
    batch_size: int = 10,
    interval_seconds: int = 60, 
    default_id_field: str = "JSID",
    specific_task_list: list = [],
    concurrent: bool = True
):
    # 配置信息
    config = {
        'host': 'localhost',
        'port': '15432',
        'database': 'JYDB',
        'username': 'hst',
        'password': 'shuntai11',
        'import_dir': 'sqlserver_exports'
    }
    importer = PostgresImporter(**config)
    
    import_status_file = main_dir + os.sep + "import_status.json"
    export_status_file = main_dir + os.sep + "export_status.json"
    
    with open(import_status_file, mode="r") as fp:
        import_status = json.load(fp)
    
    if not token: token = uuid.uuid4().hex
    if token != import_status.get("token", ""):
        task_list = specific_task_list
        table_list_file = main_dir + os.sep + "table_list.txt"
        if os.path.isfile(table_list_file):
            tables_to_import = []
            with open(table_list_file, mode="r") as file:
                for itable in file:
                    itable = itable.split(":")
                    itable, id_field = itable[0].strip(), (default_id_field if len(itable) == 1 else itable[1].strip())
                    tables_to_import.append({"table_name": itable, "id_field": id_field, "max_id": importer.get_max_id(itable, id_field)})
                task_list += [tables_to_import[i:i+batch_size] for i in range(0, len(tables_to_import), batch_size)]
        import_status = {"token": token, "task_list": task_list, "imported_table_list": [], "status": "running"}
    else:
        import_status["status"] = "running"
    with open(import_status_file, mode="w") as fp:
        json.dump(import_status, fp, ensure_ascii=False, indent=2)
    
    if not import_status["task_list"]:
        print("任务列表为空!")
        return
    
    task_idx = 0
    table_done_set = set()
    table_proc = {}# {table_name: process}
    queue = Queue()
    while task_idx < len(import_status["task_list"]):
        time.sleep(interval_seconds)
        
        while not queue.empty():
            table, ifok, msg = queue.get()
            table_done_set.add(table)
            if ifok:
                print(f"表 {table} 导入成功：{msg}")
            else:
                print(f"表 {table} 导入失败：{msg}")
            if concurrent: table_proc[table].terminate()
        
        if len(table_done_set) == len(import_status["task_list"][task_idx]):
            task_idx += 1
            table_done_set = set()
            table_proc = {}
            continue
        
        for task in import_status["task_list"][task_idx]:
            if task["table_name"] in table_done_set: continue
            task_dir = main_dir + os.sep + task["table_name"]
            if not os.path.isdir(task_dir): continue
            if not os.path.isfile(task_dir + os.sep + "export_checkpoint.json"): continue
            try:
                with open(task_dir + os.sep + "export_checkpoint.json", mode="r") as fp:
                    task_export_checkpoint = json.load(fp)
            except Exception as e:
                print(f'读取：{task_dir + os.sep + "export_checkpoint.json"} 失败：{e}')
                continue
            if task_export_checkpoint.get("token", None) != token: continue
            data_file_list = [ifile for ifile in os.listdir(task_dir) if ifile.startswith(token+"-")]
            if len(data_file_list) != task_export_checkpoint["data_file_num"]: continue
            if task["table_name"] in table_proc: continue
            # 启动导入任务
            if concurrent:
                table_proc[task["table_name"]] = Process(target=execute_task, args=(task | {"importer": importer, "queue": queue, "token": token}, ))
                table_proc[task["table_name"]].start()
            else:
                table_proc[task["table_name"]] = execute_task(task | {"importer": importer, "queue": queue, "token": token})
    
    with open(import_status_file, mode="w") as fp:
        json.dump(import_status | {"status": "finished"}, fp, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main(main_dir=r".\sqlserver_exports", token="606c8969b8914c2b8b1b0714f8fd828a", concurrent=False, interval_seconds=3)
    