import os
import json
import time
import shutil
import traceback
import datetime as dt
from multiprocessing import Pool
from threading import Lock
from typing import List, Dict, Any, Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


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

def execute_task(task):
    table_name = task["table_name"].split("-")
    if len(table_name) > 1:
        table_name, split_num, idx = table_name
        split_num, idx = int(split_num), int(idx)
    else:
        table_name, split_num, idx = table_name[0], 1, 0
    if idx > 0: return task["table_name"], True, "当前不是表导出的第一个分片，无需执行!"
    task_dir = task["export_dir"] + os.sep + table_name
    if not os.path.isdir(task_dir): os.mkdir(task_dir)
    exporter = task["exporter"]
    checkpoint = exporter.get_checkpoint(task["token"], table_name)
    if checkpoint.get("token", None) != task["token"]:
        exporter.save_checkpoint(table_name, {'token': task["token"], "last_id": task["max_id"], "last_del_id": task["del_max_id"]})
    for i in range(task["retry_num"]):
        try:
            ifok, msg, checkpoint = exporter.export_table(task["token"], table_name, order_by=task["id_field"])
        except:
            ifok, msg = False, traceback.format_exc()
        if ifok: break
    #task["queue"].put((task["table_name"], ifok, msg))
    return task["table_name"], ifok, msg


def transfer_data(sdir, tdir, task):
    table_name = task["table_name"].split("-")
    if len(table_name) > 1:
        table_name, split_num, idx = table_name
        split_num, idx = int(split_num), int(idx)
        tdir = tdir + os.sep + table_name + f"-{split_num}-{idx}"
    else:
        table_name, split_num, idx = table_name[0], 1, 0
        tdir = tdir + os.sep + table_name
    sdir = sdir + os.sep + table_name
    if not os.path.isdir(tdir): os.mkdir(tdir)
    token = task["token"]
    file_list = sorted(ifile for ifile in os.listdir(sdir) if ifile.startswith(token) and ifile.endswith(".csv"))
    file_list = partitionList(file_list, split_num)[idx]
    header_file = token + ".csv"
    if header_file not in file_list:
        file_list.append(header_file)
    index_file = token + "-INDEX.csv"
    if (idx == 0) and (index_file not in file_list):
        file_list.append(index_file)
    elif (idx != 0) and (index_file in file_list):
        file_list.remove(index_file)
    file_size = {}
    for ifile in file_list:
        file_size[ifile] = os.path.getsize(sdir + os.sep + ifile)
        if os.path.isfile(tdir + os.sep + ifile): continue
        shutil.copy(sdir + os.sep + ifile, tdir + os.sep + ifile)
    exporter = task["exporter"]
    checkpoint = exporter.get_checkpoint(token, table_name)
    checkpoint = checkpoint | {"data_file_num": len(file_list), "file_size": file_size,}
    checkpoint_file = tdir + os.sep + "export_checkpoint.json"
    with open(checkpoint_file, 'w', encoding='utf-8') as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)


class DataSender(FileSystemEventHandler):
    def __init__(self,
        main_dir: str,
        source_dir: str,
        exporter,
        cmd_file: str = "export_cmd.json",
        import_status_file: str = "import_status.json",
        export_status_file: str = "export_status.json", 
        interval_seconds: int = 3,
        retry_num: int = 3,
        concurrent_num: int = 1
    ):
        self.main_dir = main_dir
        self.source_dir = source_dir
        self.exporter = exporter
        self.cmd_file = cmd_file
        self.import_status_file = import_status_file
        self.export_status_file = export_status_file
        self.interval_seconds = interval_seconds
        self.retry_num = retry_num
        self.concurrent_num = concurrent_num
        
        self.cmd = {}
        self.export_status = {}
        self.task_rslt = {}
        self.lock = Lock()
        return super().__init__()
    
    def handle_import_status(self):
        with self.lock:
            if self.export_status.get("status", "finished") in ("finished", "terminated"):
                print(f"当前没有任务在执行，忽略接收到的 import_status 变更!")
                return
        
            import_status_file = os.path.join(self.main_dir, self.import_status_file)
            export_status_file = os.path.join(self.main_dir, self.export_status_file)
            for i in range(self.retry_num):
                try:
                    with open(import_status_file, mode="r") as fp:
                        import_status = json.load(fp)
                except:
                    msg = traceback.format_exc()
                    time.sleep(self.interval_seconds)
                else:
                    break
            else:
                print(f"打开文件 {import_status_file} 失败: {msg}")
                return
            token = import_status.get("token", None)
            if token != self.cmd["token"]:
                print(f"收到的任务 token({token}) 和当前执行的 token({self.cmd['token']}) 不一致!")
                return
            
            istatus = import_status.get("status", None)
            if istatus == "terminated":
                with open(export_status_file, mode="w") as fp:
                    self.export_status = self.export_status | {"token": token, "status": "terminated"}
                    json.dump(self.export_status, fp, ensure_ascii=False, indent=2)
                print(f"任务 {self.cmd['token']} 终止!")
                return
            elif istatus == "task_group_finished":
                # 按任务集同步数据
                task_group_idx = max(0, import_status.get("task_group_idx", self.export_status.get("task_group_idx", -1)) + 1)
                if task_group_idx >= len(self.cmd["task_list"]):
                    # 发送导出完成信号
                    with open(export_status_file, mode="w") as fp:
                        self.export_status = self.export_status | {"token": token, "status": "finished"}
                        json.dump(self.export_status, fp, ensure_ascii=False, indent=2)
                    print(f"任务 {self.cmd['token']} 完成")
                    print("\n\n\n\n等待接受新的导出任务中...")
                    return
                if task_group_idx <= self.export_status.get("task_group_idx", -1):
                    print(f"任务 {token} 的序号 {task_group_idx} 小于等于当前的序号 {self.export_status.get('task_group_idx', -1)}")
                    return
                for task in self.cmd["task_list"][task_group_idx]:
                    ifok, msg = self.task_rslt[task["table_name"]]
                    if not ifok: continue
                    try:
                        transfer_data(self.source_dir, self.main_dir, task | {"token": token, "exporter": self.exporter})
                    except:
                        print(f"任务 {token} 的表 {task['table_name']} 表的数据迁移 ({self.source_dir} -> {self.main_dir}) 失败: {traceback.format_exc()}")
                    else:
                        print(f"任务 {token} 的表 {task['table_name']} 表的数据迁移完成")
                # 发送导出完成信号
                with open(export_status_file, mode="w") as fp:
                    self.export_status = self.export_status | {"token": token, "status": "task_group_finished", "task_group_idx": task_group_idx,}
                    json.dump(self.export_status, fp, ensure_ascii=False, indent=2)
                return
            elif istatus not in ("starting", "running", "finished"):
                print(f"无法识别的任务状态: {istatus}")
                return

    def handle_cmd(self):
        with self.lock:
            if self.export_status.get("status", "finished") not in ("finished", "terminated"):
                print(f"正在运行任务 {self.cmd['token']}, 无法接受新任务!")
                return
            self.export_status["status"] = "starting"

            cmd_file = os.path.join(self.main_dir, self.cmd_file)
            export_status_file = os.path.join(self.main_dir, self.export_status_file)
            for i in range(self.retry_num):
                try:
                    with open(cmd_file, mode="r") as fp:
                        self.cmd = json.load(fp)
                except:
                    msg = traceback.format_exc()
                    time.sleep(self.interval_seconds)
                else:
                    break
            else:
                print(f"打开文件 {cmd_file} 失败: {msg}")
                return
            token = self.cmd["token"]

            print(f"接到新的导出任务: {token}")
            if not self.cmd.get("task_list", []):
                print(f"{token}: 任务列表为空!")
                with open(export_status_file, mode="w") as fp:
                    self.export_status = self.export_status | {"token": token, "status": "finished"}
                    json.dump(self.export_status, fp, ensure_ascii=False, indent=2)
                return
            
            # 任务列表非空
            with open(export_status_file, mode="w") as fp:
                self.export_status = self.export_status | {"token": token, "status": "running"}
                json.dump(self.export_status, fp, ensure_ascii=False, indent=2)
            
            # 提取数据
            self.task_rslt = {}
            task_group_start_idx = max(0, self.cmd.get("task_group_idx", 0))
            # 执行导出任务
            with Pool(processes=self.concurrent_num) as pool:
                for task_group in self.cmd["task_list"][task_group_start_idx:]:
                    for task in task_group:
                        print(f"任务 {token} 的表 {task['table_name']} 开始导出...")
                        self.task_rslt[task["table_name"]] = pool.apply_async(execute_task, args=(task | {"export_dir": self.source_dir, "exporter": self.exporter, "token": token, "retry_num": self.retry_num}, ))
                for table_name, proc in self.task_rslt.items():
                    try:
                        _, ifok, msg = proc.get()
                    except:
                        ifok, msg = False, traceback.format_exc()
                    if ifok:
                        print(f"任务 {token} 的表 {table_name} 表导出成功: {msg}")
                    else:
                        print(f"任务 {token} 的表 {table_name} 表导出失败: {msg}")
                    self.task_rslt[table_name] = (ifok, msg)

            # 按任务集同步数据
            task_group_idx = task_group_start_idx
            for task in self.cmd["task_list"][task_group_idx]:
                ifok, msg = self.task_rslt[task["table_name"]]
                if ifok:
                    try:
                        transfer_data(self.source_dir, self.main_dir, task | {"token": token, "exporter": self.exporter})
                    except:
                        print(f"任务 {token} 的表 {task['table_name']} 表的数据迁移 ({self.source_dir} -> {self.main_dir}) 失败: {traceback.format_exc()}")
                    else:
                        print(f"任务 {token} 的表 {task['table_name']} 表的数据迁移完成")
            
            # 发送导出完成信号
            with open(export_status_file, mode="w") as fp:
                self.export_status = self.export_status | {"token": token, "status": "task_group_finished", "task_group_idx": task_group_idx,}
                json.dump(self.export_status, fp, ensure_ascii=False, indent=2)

    def on_any_event(self, event):
        if event.is_directory: return
        if event.event_type not in ("created", "modified"):
            return
        file_path = event.src_path
        task_dir, file_name = os.path.split(file_path)
        if file_name == self.cmd_file:
            return self.handle_cmd()
        elif file_name == self.import_status_file:
            return self.handle_import_status()

if __name__ == "__main__":
    from SQLServerExporter import SQLServerExporter
    main_dir = r'C:\NXG Cloud\My Cloud\sqlserver_exports'
    source_dir = r'C:\Users\04122\Desktop\ExportedData'
    interval_seconds = 3
    config = {
        'server': '10.102.3.21',
        'port': '1333',
        'database': 'FundExt',
        'username': 'cwyspzb_04122',
        'password': 'Shzq@04122',
        'export_dir': source_dir,
        'batch_size': 1000000
    }
    exporter = SQLServerExporter(**config)

    event_handler = DataSender(main_dir=main_dir, source_dir=source_dir, exporter=exporter, interval_seconds=interval_seconds)
    observer = Observer()
    observer.schedule(event_handler, path=main_dir, recursive=True)
    observer.start()
    print("等待接受新的导出任务中...")
    
    try:
        while True:
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
