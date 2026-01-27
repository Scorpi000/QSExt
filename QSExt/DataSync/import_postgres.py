import os
import csv
import json
import uuid
import time
import traceback
from datetime import datetime
from multiprocessing import Process, Queue, Pool
from typing import List, Dict, Any, Optional

import numpy as np
import pandas as pd
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
    
    def check_table_exists(self, table_name: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        # 检查表是否存在
        try:
            cursor.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = '{table_name.lower()}'
                )
            """)
            
            exists = cursor.fetchone()[0]
        finally:
            cursor.close()
            conn.close()
        return exists

    def create_table_if_not_exists(self, table_name: str, columns_info: List[Dict[str, Any]]):
        """如果表不存在则创建表"""
        # 检查表是否存在
        if self.check_table_exists(table_name): return True

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
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
        return False
    
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
    
    def create_del_table(self, table_name:str="JYDB_DeleteRec"):
        # 检查表是否存在
        if self.check_table_exists(table_name): return True
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            create_sql = f"""
                CREATE TABLE {table_name} (
                TABLENAME varchar(100) NOT NULL,
                RECID bigint NOT NULL,
                XGRQ timestamp(6) NOT NULL,
                ID bigint NOT NULL,
                JSID bigint NOT NULL
                )
            """
            cursor.execute(create_sql)
            conn.commit()
            print(f"删除表 {table_name} 已创建")
        finally:
            cursor.close()
            conn.close()
        return False

    # 删除表，同时清空 del_table 中的删除记录
    def delete_table(self, table_name:str, del_table_name:str="JYDB_DeleteRec"):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            sql = f"""DROP TABLE IF EXISTS {table_name}"""
            cursor.execute(sql)
            sql = f"""DELETE FROM {del_table_name} WHERE TABLENAME='{table_name}'"""
            conn.commit()
            print(f"删除表: {table_name}")
        finally:
            cursor.close()
            conn.close()

    def get_max_id(self, table_name:str, id_field:str="JSID"):
        exists = self.check_table_exists(table_name)
        if not exists: return None
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"""SELECT MAX({id_field}) FROM {table_name}""")
            max_id = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
        if max_id: return max_id[0]
        else: return None
    
    def get_del_max_id(self, table_name:str, del_table_name:str="JYDB_DeleteRec", id_field:str="JSID"):
        exists = self.check_table_exists(table_name)
        if not exists: return None
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"""SELECT MAX({id_field}) FROM {del_table_name} WHERE TABLENAME = '{table_name}'""")
            max_id = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
        if max_id: return max_id[0]
        else: return None

    def import_del_table(self, token:str, table_name:str, exec_del:bool=True, del_table_name:str="JYDB_DeleteRec", cursor=None):
        del_file = self.import_dir + os.sep + table_name + os.sep + f"{token}-DEL.csv"
        if not os.path.isfile(del_file): return
        db_table_name = table_name.split("-")[0]
        insert_sql = f'INSERT INTO {del_table_name} (TABLENAME, RECID, XGRQ, ID, JSID) VALUES (%s, %s, %s, %s, %s)'
        with open(del_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            batch = [row for row in reader]
        imported_cursor = (cursor is not None)
        if not imported_cursor:
            conn = self.get_connection()
            cursor = conn.cursor()
        try:
            # 先删除目标表中的数据
            if exec_del:
                del_sql = f"""DELETE FROM {db_table_name} WHERE ID IN ('{"','".join(row[1] for row in batch)}')"""
                cursor.execute(del_sql)
            # 再执行删除表数据插入
            cursor.executemany(insert_sql, batch)
            conn.commit()
        finally:
            if not imported_cursor:
                cursor.close()
                conn.close()

    def clear_redundant_data(self, db_table_name: str, columns_info:list, data_file_path:str, id_field:str="JSID", cursor=None):
        id_col_idx = [i for i, col in enumerate(columns_info) if col["name"].lower()==id_field.lower()][0]
        with open(data_file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            first_row = next(reader)
        first_idx = first_row[id_col_idx]
        imported_cursor = (cursor is not None)
        if not imported_cursor:
            conn = self.get_connection()
            cursor = conn.cursor()
        try:
            sql = f"""DELETE FROM {db_table_name} WHERE {id_field} >= {first_idx}"""
            cursor.execute(sql)
            conn.commit()
        finally:
            if not imported_cursor:
                cursor.close()
                conn.close()

    def import_table(self, token: str, table_name: str, resume: bool = True, id_field="JSID") -> int:
        """导入单个表"""
        print(f"开始导入表 {table_name}...")
        db_table_name = table_name.split("-")[0]
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
        table_exists = self.create_table_if_not_exists(db_table_name, columns_info)
        self.create_del_table()
        
        # 获取断点信息
        checkpoint = self.get_checkpoint(table_name) if resume else {}
        imported_rows = checkpoint.get('imported_rows', 0)
        idx = int(checkpoint.get("idx", 0))
        
        # 读取CSV文件列表，并清理表里多余的数据
        file_list = sorted(ifile for ifile in os.listdir(self.import_dir + os.sep + table_name) if ifile.startswith(token+"-") and ifile.endswith(".csv") and (ifile.split(".")[0].split("-")[-1].lower()!="del") and int(ifile.split(".")[0].split("-")[-1]) >= idx)
        if table_exists:
            data_file_path = os.path.join(self.import_dir, table_name, file_list[0])
            self.clear_redundant_data(db_table_name=db_table_name, columns_info=columns_info, data_file_path=data_file_path, id_field=id_field)

        # 构建插入语句
        columns_str = ', '.join(headers)
        placeholders = ', '.join(['%s'] * len(headers))
        insert_sql = f'INSERT INTO {db_table_name} ({columns_str}) VALUES ({placeholders})'
        
        datetime_col_idx = [i for i, col in enumerate(columns_info) if col["type"].lower().startswith("date")]
        float_col_idx = [i for i, col in enumerate(columns_info) if col["type"].lower().startswith("float")]
        int_col_idx = [i for i, col in enumerate(columns_info) if "int" in col["type"].lower()]
        
        total_imported = imported_rows
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # 导入表数据
            for ifile in file_list:
                with open(self.import_dir + os.sep + table_name + os.sep + ifile, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    batch = [row for row in reader]
                
                # 处理特殊类型的字段
                batch = np.array(batch, dtype="O")
                batch = np.where(batch!="", batch, None)
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
                batch = batch.tolist()

                cursor.executemany(insert_sql, batch)
                conn.commit()
                total_imported += len(batch)
                idx += 1
                
                # 保存断点
                print(f"表 {table_name} 文件 {ifile} 导入完成!")
                if resume:
                    self.save_checkpoint(table_name, {
                        'imported_rows': total_imported,
                        'import_time': datetime.now().isoformat(),
                        'idx': idx,
                    })
            
            # 导入删除表数据
            self.import_del_table(token=token, table_name=table_name, exec_del=table_exists, cursor=cursor)
            print(f"表 {table_name} 的删除文件导入完成!")

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
    
    # 清空导入的文件
    if ifok:
        for ifile in os.listdir(importer.import_dir + os.sep + task["table_name"]):
            if ifile.startswith(task["token"]):
                ifile = importer.import_dir + os.sep + task["table_name"] + os.sep + ifile
                try:
                    os.remove(ifile)
                except:
                    print(f"清理文件失败: {ifile}")
    
    #task["queue"].put((task["table_name"], ifok, msg))
    return (task["table_name"], ifok, msg)
    

def main( 
    main_dir: str,
    token: Optional[str] = None,
    interval_seconds: int = 60, 
    default_id_field: str = "JSID",
    table_list_file: Optional[str] = None,
    specific_task_list: list = [],
    concurrent_num: int = 1
):
    # 配置信息
    config = {
        'host': 'localhost',
        'port': '5432',
        'database': 'JYDB',
        'username': 'shzq',
        'password': 'shzq#321',
        'import_dir': main_dir
    }
    importer = PostgresImporter(**config)
    
    import_status_file = main_dir + os.sep + "import_status.json"
    export_status_file = main_dir + os.sep + "export_status.json"
    
    if os.path.isfile(import_status_file):
        with open(import_status_file, mode="r") as fp:
            import_status = json.load(fp)
    else:
        import_status = {}
    
    if specific_task_list or (table_list_file and os.path.isfile(table_list_file)):
        task_list = specific_task_list
        if table_list_file and os.path.isfile(table_list_file):
            tables_to_import = []
            with open(table_list_file, mode="r") as file:
                for itable in file:
                    if itable.strip() == "---":
                        if tables_to_import: task_list.append(tables_to_import)
                        tables_to_import = []
                    else:
                        itable = itable.split(":")
                        itable, id_field = itable[0].strip(), (default_id_field if len(itable) == 1 else itable[1].strip())
                        tables_to_import.append({"table_name": itable, "id_field": id_field, "max_id": importer.get_max_id(itable, id_field), "del_max_id": importer.get_del_max_id(itable)})
                if tables_to_import: task_list.append(tables_to_import)
    else:
        task_list = []
    
    if not token: token = uuid.uuid4().hex
    if token != import_status.get("token", ""):
        import_status = {"token": token, "task_list": task_list, "imported_table_list": [], "status": "running", "task_group_idx": 0}
    else:# 重新运行已经存在的任务
        if import_status.get("status", None)=="task_group_finished":
            import_status["task_group_idx"] = import_status.get("task_group_idx", 0) + 1
        else:
            import_status.setdefault("task_group_idx", 0)
        import_status["status"] = "restart"
        if task_list: import_status["task_list"] = task_list

    print(f"执行任务: {token}")
    if not import_status["task_list"][import_status["task_group_idx"]:]:
        print("任务列表为空!")
        return
    
    with open(export_status_file, mode="w") as fp:
        json.dump({"token": token, "status": "running", "task_group_idx": -1}, fp, ensure_ascii=False, indent=2)

    with open(import_status_file, mode="w") as fp:
        json.dump(import_status, fp, ensure_ascii=False, indent=2)

    # 等待导出任务完成
    task_group_idx = -1
    i = 0
    while True:
        time.sleep(interval_seconds)
        try:
            with open(export_status_file, mode="r") as fp:
                export_status = json.load(fp)
        except:
            print(f"文件 {export_status_file} 打开失败: {traceback.format_exc()}")
            i += 1
            continue
        istatus = export_status.get("status", None)
        if (istatus in ("finished", "task_group_finished")) and (export_status["task_group_idx"] != task_group_idx):
            task_group_idx = export_status["task_group_idx"]
            print(f"导出任务 {task_group_idx} 完成，执行导入")
        elif (istatus == "finished"):
            print("导出任务已经全部完成!")
            break
        else:
            i += 1
            print(f"已经等待{i * interval_seconds}秒，继续等待导出任务 {task_group_idx+1} 完成...")
            continue
        
    
        # 执行导入任务
        task_group_list = import_status["task_list"][task_group_idx].copy()
        task_rslt = []
        with Pool(processes=concurrent_num) as pool:
            while task_group_list:
                time.sleep(interval_seconds)
                task = task_group_list.pop(0)
                task_dir = main_dir + os.sep + task["table_name"]
                if (not os.path.isdir(task_dir)) or (not os.path.isfile(task_dir + os.sep + "export_checkpoint.json")):
                    task_group_list.append(task)
                    print(f"""{task["table_name"]}/export_checkpoint.json 文件尚未收到!""")
                    continue
                try:
                    with open(task_dir + os.sep + "export_checkpoint.json", mode="r") as fp:
                        task_export_checkpoint = json.load(fp)
                except Exception as e:
                    print(f'读取：{task_dir + os.sep + "export_checkpoint.json"} 失败：{e}')
                    task_group_list.append(task)
                    continue
                if task_export_checkpoint.get("token", None) != token:
                    print(f"""{task["table_name"]}/export_checkpoint.json 文件中的 token({task_export_checkpoint.get("token", None)}) 不等于任务 token""")
                    task_group_list.append(task)
                    continue
                data_file_list = [ifile for ifile in os.listdir(task_dir) if ifile.startswith(token)]
                if len(data_file_list) != task_export_checkpoint.get("data_file_num", None):
                    print(f"""{task["table_name"]} 中的文件数量({len(data_file_list)}) 不等于 checkpoint 中的文件数量({task_export_checkpoint.get("data_file_num", None)})""")
                    task_group_list.append(task)
                    continue
                # 启动导入任务
                task_rslt.append((task["table_name"], pool.apply_async(execute_task, args=(task | {"importer": importer, "token": token}, ))))
            # 等待导入结束
            while task_rslt:
                table_name, rslt = task_rslt.pop(0)
                try:
                    _, ifok, msg = rslt.get()
                except:
                    print(f"{table_name} 表导入失败: {traceback.format_exc()}")
                else:
                    if ifok:
                        print(f"{table_name} 表导入成功: {msg}")
                    else:
                        print(f"{table_name} 表导入失败: {msg}")
        # 发送导入结束信号
        with open(import_status_file, mode="w") as fp:
            import_status = import_status | {"status": "task_group_finished", "task_group_idx": task_group_idx}
            json.dump(import_status, fp, ensure_ascii=False, indent=2)
    
    with open(import_status_file, mode="w") as fp:
        json.dump(import_status | {"status": "finished"}, fp, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # 执行未完成的任务
    # main(
    #     main_dir=r"D:\NXG Cloud\My Cloud\sqlserver_exports", 
    #     token="4ac3a2b2320a41eda319d99ca8e94f80", 
    #     concurrent=False, 
    #     interval_seconds=3
    # )

    # 执行指定的任务
    main(
        main_dir=r"D:\NXG Cloud\My Cloud\sqlserver_exports", 
        token="a8757f80c04343aa883da5432885b968", 
        concurrent_num=1, 
        interval_seconds=3,
        specific_task_list=[
            [
                {"table_name": "QT_DailyQuote-10-2", "id_field": "JSID", "max_id": None, "del_max_id": None}
            ],
            [
                {"table_name": "QT_DailyQuote-10-3", "id_field": "JSID", "max_id": None, "del_max_id": None}
            ]
        ]
    )

    # 执行默认任务
    # main(
    #     main_dir=r"D:\NXG Cloud\My Cloud\sqlserver_exports", 
    #     token=None, 
    #     concurrent=False, 
    #     interval_seconds=3, 
    #     table_list_file=r"D:\NXG Cloud\My Cloud\table_list.txt"
    # )
    