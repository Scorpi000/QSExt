import os
import csv
import json
import uuid
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

# 获取文件夹的大小
def get_folder_size(folder_path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for file in filenames:
            file_path = os.path.join(dirpath, file)
            total_size += os.path.getsize(file_path)
    return total_size


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
            ifok, msg, checkpoint = exporter.export_table(task["token"], table_name, order_by=task["id_field"], del_table_name=task["del_table"], id_field=task["id_field"])
        except:
            ifok, msg = False, traceback.format_exc()
        if ifok: break
    #task["queue"].put((task["table_name"], ifok, msg))
    return task["table_name"], ifok, msg

def transfer_data(sdir, tdir, task):
    table_name = task["table_name"]
    tdir = tdir + os.sep + table_name
    sdir = sdir + os.sep + table_name
    if not os.path.isdir(tdir): os.mkdir(tdir)
    token = task["token"]
    file_list = sorted(ifile for ifile in os.listdir(sdir) if ifile.startswith(token) and ifile.endswith(".csv"))
    start_idx, cum_size, max_size = task.get("start_idx", 0), task["cum_size"], task["max_size"]
    file_size = {}
    salt = uuid.uuid4().hex# 防止文件跟之前的完全一样导致上传失败
    for i in range(start_idx, len(file_list)):
        ifile = file_list[i]
        # if os.path.isfile(tdir + os.sep + ifile):
        #     isize = os.path.getsize(ifile_path)
        #    file_size[ifile] = isize
        #     cum_size += isize
        #     start_idx += 1
        #     if cum_size + isize >= max_size:
        #         break
        #     else:
        #         continue
        ifile_path = os.path.join(sdir, ifile)
        isize = os.path.getsize(ifile_path)
        if cum_size + isize >= max_size:
            start_idx = i
            break
        shutil.copy(sdir + os.sep + ifile, tdir + os.sep + ifile)
        with open(tdir + os.sep + ifile, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(("salt", salt))
        isize = os.path.getsize(tdir + os.sep + ifile)
        file_size[ifile] = isize
        cum_size += isize
        start_idx += 1
    exporter = task["exporter"]
    checkpoint = exporter.get_checkpoint(token, table_name)
    checkpoint = checkpoint | {"data_file_num": len(file_list), "file_size": file_size,}
    checkpoint_file = tdir + os.sep + "export_checkpoint.json"
    with open(checkpoint_file, 'w', encoding='utf-8') as f:
        json.dump(checkpoint | {"salt": uuid.uuid4().hex}, f, ensure_ascii=False, indent=2)
    return {"start_idx": start_idx, "if_all": start_idx>=len(file_list), "cum_size": cum_size}

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
        concurrent_num: int = 1,
        max_size: float = 4.5# 单词最大传送的数据量，单位 G
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
        self.max_size = max_size * 1024 * 1024 * 1024# 转成单位为字节
        
        self.cmd = {}
        self.export_status = {}
        self.task_rslt = {}
        self.task_start_idx = 0# 任务执行和数据传输的开始位置，随着传输的进行，该值会逐渐增大
        self.task_file_start_idx = 0
        self.lock = Lock()
        self.observation_list = {
            self.cmd_file: dt.datetime.fromtimestamp(os.path.getmtime(os.path.join(self.main_dir, self.cmd_file))),
            self.import_status_file: dt.datetime.fromtimestamp(os.path.getmtime(os.path.join(self.main_dir, self.import_status_file)))
        }
        return super().__init__()
    
    def clear_data(self, table_name):
        table_path = os.path.join(self.main_dir, table_name)
        try:
            shutil.rmtree(table_path)
        except:
            print(f"清除表 {table_name} 数据失败: {traceback.format_exc()}")
            return get_folder_size(table_path)
        return 0

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
                    json.dump(self.export_status | {"salt": uuid.uuid4().hex}, fp, ensure_ascii=False, indent=2)
                print(f"任务 {self.cmd['token']} 终止!")
                return
            elif istatus == "task_group_finished":
                # 如果所有任务均以传输完，发送导出完成信号
                if self.task_start_idx >= len(self.cmd["task_list"]):
                    with open(export_status_file, mode="w") as fp:
                        self.export_status = self.export_status | {"token": token, "status": "finished"}
                        json.dump(self.export_status | {"salt": uuid.uuid4().hex}, fp, ensure_ascii=False, indent=2)
                    self.task_rslt = {}
                    self.task_start_idx = 0
                    self.task_file_start_idx = 0
                    print(f"任务 {self.cmd['token']} 完成")
                    print("\n\n\n\n等待接受新的导出任务中...")
                    return
                # 继续传输剩余任务数据
                task_group_idx = max(0, import_status.get("task_group_idx", self.export_status.get("task_group_idx", -1)) + 1)
                if task_group_idx <= self.export_status.get("task_group_idx", -1):
                    print(f"任务 {token} 的序号 {task_group_idx} 小于等于当前的序号 {self.export_status.get('task_group_idx', -1)}")
                    return
                cum_size, task_file_start_idx = 0, self.task_file_start_idx
                table_list = []
                for task in self.cmd["task_list"][self.task_start_idx:]:
                    ifok, msg = self.task_rslt[task["table_name"]]
                    if not ifok: 
                        self.task_start_idx += 1
                        task_file_start_idx = 0
                        continue
                    try:
                        transfer_rslt = transfer_data(self.source_dir, self.main_dir, task | {"token": token, "exporter": self.exporter, "cum_size": cum_size, "max_size": self.max_size, "start_idx": task_file_start_idx})
                    except:
                        print(f"任务 {token} 的表 {task['table_name']} 表的数据迁移 ({self.source_dir} -> {self.main_dir}) 失败: {traceback.format_exc()}")
                        cum_size += self.clear_data(task["table_name"])
                        self.task_start_idx += 1
                        task_file_start_idx = 0
                        continue
                    cum_size = transfer_rslt["cum_size"]
                    if transfer_rslt["if_all"]:
                        print(f"任务 {token} 的表 {task['table_name']} 表的数据迁移完成")
                        self.task_start_idx += 1
                        table_list.append(task["table_name"])
                    else:
                        print(f"任务 {token} 的表 {task['table_name']} 表的数据部分迁移完成")
                        self.task_file_start_idx = transfer_rslt["start_idx"]
                        table_list.append(task["table_name"])
                        break
                    task_file_start_idx = 0
                # 发送导出完成信号
                with open(export_status_file, mode="w") as fp:
                    self.export_status = self.export_status | {"token": token, "status": "task_group_finished", "task_group_idx": task_group_idx, "table_list": table_list}
                    json.dump(self.export_status | {"salt": uuid.uuid4().hex}, fp, ensure_ascii=False, indent=2)
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
            if self.cmd.get("status", None)=="accepted":
                print(f"当前任务正在执行或已经执行过，忽略接收到的 {self.cmd_file} 变更!")
                return
            else:
                self.cmd["status"] = "accepted"
                with open(cmd_file, mode="w") as fp:
                    json.dump(self.cmd, fp, ensure_ascii=False, indent=2)
            token = self.cmd["token"]

            print(f"接到新的导出任务: {token}")
            if not self.cmd.get("task_list", []):
                print(f"{token}: 任务列表为空!")
                with open(export_status_file, mode="w") as fp:
                    self.export_status = self.export_status | {"token": token, "status": "finished"}
                    json.dump(self.export_status | {"salt": uuid.uuid4().hex}, fp, ensure_ascii=False, indent=2)
                return
            
            # 任务列表非空
            self.export_status = self.export_status | {"token": token, "status": "running"}
            # with open(export_status_file, mode="w") as fp:
            #     json.dump(self.export_status | {"salt": uuid.uuid4().hex}, fp, ensure_ascii=False, indent=2)
            
            # 提取数据
            self.task_rslt = {}
            self.task_start_idx = max(0, self.cmd.get("task_start_idx", 0))
            # 执行导出任务
            with Pool(processes=self.concurrent_num) as pool:
                for task in self.cmd["task_list"][self.task_start_idx:]:
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
            
            # 同步数据
            task_group_idx, cum_size = 0, 0
            table_list = []
            for task in self.cmd["task_list"][self.task_start_idx:]:
                ifok, msg = self.task_rslt[task["table_name"]]
                if not ifok:
                    self.task_start_idx += 1
                    continue
                try:
                    transfer_rslt = transfer_data(self.source_dir, self.main_dir, task | {"token": token, "exporter": self.exporter, "cum_size": cum_size, "max_size": self.max_size, "start_idx": 0})
                except:
                    print(f"任务 {token} 的表 {task['table_name']} 表的数据迁移 ({self.source_dir} -> {self.main_dir}) 失败: {traceback.format_exc()}")
                    cum_size += self.clear_data(task["table_name"])
                    self.task_start_idx += 1
                    continue
                cum_size = transfer_rslt["cum_size"]
                if transfer_rslt["if_all"]:
                    print(f"任务 {token} 的表 {task['table_name']} 表的数据迁移完成")
                    self.task_start_idx += 1
                    table_list.append(task["table_name"])
                else:
                    print(f"任务 {token} 的表 {task['table_name']} 表的数据部分迁移完成")
                    self.task_file_start_idx = transfer_rslt["start_idx"]
                    table_list.append(task["table_name"])
                    break
            
            # 发送导出完成信号
            with open(export_status_file, mode="w") as fp:
                self.export_status = self.export_status | {"token": token, "status": "task_group_finished", "task_group_idx": task_group_idx, "table_list": table_list}
                json.dump(self.export_status | {"salt": uuid.uuid4().hex}, fp, ensure_ascii=False, indent=2)

    def on_any_event(self, event):
        if event.is_directory: return
        if event.event_type not in ("created", "modified"):return
        file_path = event.src_path
        task_dir, file_name = os.path.split(file_path)
        if file_name not in self.observation_list: return
        modified_time = dt.datetime.fromtimestamp(os.path.getmtime(event.src_path))
        if modified_time==self.observation_list[file_name]:
            print(f"文件 {file_name} 的修改时间({modified_time}) 没有发生变化，忽略此次变更!")
            return
        else:
            self.observation_list[file_name] = modified_time
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
        'batch_size': 2000000
    }
    exporter = SQLServerExporter(**config)

    event_handler = DataSender(
        main_dir=main_dir,
        source_dir=source_dir,
        exporter=exporter,
        interval_seconds=interval_seconds,
        max_size=4.5,
    )
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
