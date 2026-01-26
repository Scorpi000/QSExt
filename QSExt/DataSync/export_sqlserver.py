import os
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
def distributeEqual(n,m,remainder_pos="left"):
    Quotient, Remainder = int(n/m), n%m
    Rslt = np.full(shape=(m,), fill_value=Quotient, dtype=np.int64)
    if remainder_pos=='left':
        Rslt[:Remainder] += 1
    elif remainder_pos=='right':
        Rslt[-Remainder:] += 1
    else:
        StartPos = int((m-Remainder)/2)
        Rslt[StartPos:StartPos+Remainder] += 1
    return Rslt.tolist()

# 将一个list或者tuple平均分成m段
def partitionList(data,m,n_head=0,n_tail=0):
    n = len(data)
    PartitionNode = distributeEqual(n,m)
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
            #charset='cp936'
        #)
        return pymssql.connect(
            server=self.server,
            database=self.database,
            port=str(self.port), 
            user=self.username,
            password=self.password,
            charset='cp936'
        )
    
    def get_checkpoint(self, table_name: str) -> Dict[str, Any]:
        """获取断点信息"""
        checkpoint_file = self.export_dir + os.sep + table_name + os.sep + self.checkpoint_file
        if os.path.exists(checkpoint_file):
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint = json.load(f)
                return checkpoint
        return {}
    
    def save_checkpoint(self, table_name: str, checkpoint: Dict[str, Any]):
        """保存断点信息"""
        checkpoint_file = self.export_dir + os.sep + table_name + os.sep + self.checkpoint_file
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint, f, ensure_ascii=False, indent=2)
    
    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """获取表信息，包括列信息和总行数"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 获取列信息
            cursor.execute(f"""
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = '{table_name}'
                ORDER BY ORDINAL_POSITION
            """)
            columns = cursor.fetchall()
            
            # 获取总行数
            cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
            total_rows = cursor.fetchone()[0]
            
            return {
                'columns': [{'name': col[0], 'type': col[1], 'nullable': col[2]} for col in columns],
                'total_rows': total_rows
            }
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
            rows = cursor.fetchone()
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
    
    def export_table(self, token: str, table_name: str, order_by: str = None, where_clause: str = None, resume: bool = True) -> str:
        """导出单个表"""
        print(f"开始导出表 {table_name}...")
        export_dir = os.path.join(self.export_dir, table_name)
        os.makedirs(export_dir, exist_ok=True)
        
        # 获取表信息
        table_info = self.get_table_info(table_name)
        column_names = [col['name'] for col in table_info['columns']]
        
        # 获取断点信息
        checkpoint = self.get_checkpoint(table_name)
        last_id = checkpoint.get('last_id', None)
        last_del_id = checkpoint.get('last_del_id', None)
        idx = int(checkpoint.get("idx", 0))
        exported_rows = checkpoint.get('exported_rows', 0)
        
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
        
        # 构建查询语句
        base_query = f"SELECT {', '.join([f'[{col}]' for col in column_names])} FROM [{table_name}]"
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
        
        conn = self.get_connection()
        cursor = conn.cursor()
        offset = exported_rows
        total_exported = exported_rows
        try:
            while True:
                # 执行查询
                query = f"{base_query} OFFSET {offset} ROWS FETCH NEXT {self.batch_size} ROWS ONLY"
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
                        'last_id': last_id,
                        'idx': idx,
                        'exported_rows': total_exported,
                        'total_rows': table_info["total_rows"],
                        'export_time': dt.datetime.now().isoformat()
                    }
                    self.save_checkpoint(table_name, checkpoint)
                if len(rows) < self.batch_size:
                    break
                offset += self.batch_size
            # 导出删除记录
            last_del_id = self.export_del_table(token=token, table_name=table_name, last_del_id=last_del_id, cursor=cursor)
        except Exception as e:
            ifok, msg = False, traceback.format_exc()
        else:
            checkpoint = checkpoint | {
                'data_file_num': idx + int(last_del_id is not None),
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


def execute_task(task):
    table_name = task["table_name"].split("-")
    if len(table_name) > 1:
        table_name, idx = table_name[0], table_name[1]
    else:
        table_name, idx = table_name[0], 0
    if idx > 0: return task["table_name"], True, "空执行!"
    task_dir = task["export_dir"] + os.sep + task["table_name"]
    if not os.path.isdir(task_dir): os.mkdir(task_dir)
    exporter = task["exporter"]
    exporter.save_checkpoint(table_name, {'token': task["token"], "last_id": task["max_id"], "last_del_id": task["del_max_id"]})
    for i in range(task["retry_num"]):
        try:
            ifok, msg, checkpoint = exporter.export_table(task["token"], table_name, order_by=task["id_field"])
        except:
            ifok, msg = False, traceback.format_exc()
        if ifok: break
    #task["queue"].put((task["table_name"], ifok, msg))
    return task["table_name"], ifok, msg

def transfer_data(sdir, tdir, task, split_num=1):
    table_name = task["table_name"].split("-")
    if len(table_name) > 1:
        table_name, idx = table_name[0], table_name[1]
    else:
        table_name, idx = table_name[0], 0
    sdir = sdir + os.sep + table_name
    tdir = tdir + os.sep + table_name
    if not os.path.isdir(tdir): os.mkdir(tdir)
    token = task["token"]
    file_list = sorted(ifile for ifile in os.listdir(sdir) if ifile.startswith(token) and ifile.endswith(".csv"))
    for ifile in partitionList(file_list, split_num)[idx]:
        shutil.copy(sdir + os.sep + ifile, tdir + os.sep + ifile)
    shutil.copy(sdir + os.sep + "export_checkpoint.json", tdir + os.sep + "export_checkpoint.json")

def main(
    main_dir: str,
    cache_dir: str, 
    interval_seconds: int = 60,
    retry_num: int = 3,
    concurrent_num: int = 1
):
    # 配置信息
    config = {
        'server': '10.102.3.21',
        'port': '1333',
        'database': 'FundExt',
        'username': 'cwyspzb_04122',
        'password': 'Shzq@04122',
        'export_dir': cache_dir,
        'batch_size': 200000
    }
    exporter = SQLServerExporter(**config)
    
    import_status_file = main_dir + os.sep + "import_status.json"
    export_status_file = main_dir + os.sep + "export_status.json"

    if os.path.isfile(export_status_file):
        with open(export_status_file, mode="r") as fp:
            export_status = json.load(fp)
        token = export_status.get("token", None)
    else:
        token, export_status = None, {}
    
    while True:
        # 等待新的导出任务，import_status_file 中的 token 和当前的 token 不相等表示产生了新任务
        wait_printed = False
        while token == export_status.get("token", None):
            if os.path.isfile(import_status_file):
                try:
                    with open(import_status_file, mode="r") as fp:
                        import_status = json.load(fp)
                    token = import_status["token"]
                except:
                    print(f"{import_status_file}读取失败: {traceback.format_exec()}")
            if not wait_printed:
                print("等待新的导出任务...")
                wait_printed = True
            time.sleep(interval_seconds)
        
        # 任务列表为空
        print(f"接到新的导出任务: {token}")
        if not import_status.get("task_list", []):
            print(f"{token}: 任务列表为空!")
            with open(export_status_file, mode="w") as fp:
                export_status = export_status | {"token": token, "status": "finished"}
                json.dump(export_status, fp, ensure_ascii=False, indent=2)
            continue
        
        # 任务列表非空
        with open(export_status_file, mode="w") as fp:
            export_status = export_status | {"token": token, "status": "running"}
            json.dump(export_status, fp, ensure_ascii=False, indent=2)
        
        # 提取数据
        task_rslt = {}
        with Pool(processes=concurrent_num) as pool:
            # 执行导出任务
            for task_group in import_status["task_list"]:
                for task in task_group:
                    print(f"{task['table_name']} 表开始导出")
                    task_rslt[task["table_name"]] = pool.apply_async(execute_task, args=(task | {"export_dir": cache_dir, "exporter": exporter, "token": token, "retry_num": retry_num}, ))
            # 按任务集同步数据
            for task_group_idx, task_group in enumerate(import_status["task_list"]):
                for task in task_group:
                    try:
                        ifok, msg, checkpoint = task_rslt[task["table_name"]].get()
                    except:
                        print(f"{task['table_name']} 表导出失败: {traceback.format_exc()}")
                    else:
                        if ifok:
                            transfer_data(cache_dir, main_dir, task, checkpoint)
                            print(f"{task['table_name']} 表导出成功: {msg}")
                        else:
                            print(f"{task['table_name']} 表导出失败: {msg}")
                # 发送导出完成信号
                with open(export_status_file, mode="w") as fp:
                    export_status = export_status | {"token": token, "status": "task_group_finished", "task_group_idx": task_group_idx,}
                    json.dump(export_status, fp, ensure_ascii=False, indent=2)
                # 等待导入完成
                while True:
                    time.sleep(interval_seconds)
                    with open(import_status_file, mode="r") as fp:
                        import_status = json.load(fp)
                    istatus = import_status.get("status", None)
                    if istatus == "terminated":
                        with open(export_status_file, mode="w") as fp:
                            token = import_status["token"]
                            export_status = export_status | {"token": token, "status": "terminated"}
                            json.dump(export_status, fp, ensure_ascii=False, indent=2)
                        break
                    elif istatus == "task_group_finished":
                        break
                if istatus == "terminated": break
        
        with open(export_status_file, mode="w") as fp:
            export_status = export_status | {"token": token, "status": "finished"}
            json.dump(export_status, fp, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main(main_dir=r".\sqlserver_exports", interval_seconds=3, concurrent=False)
