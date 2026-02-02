import os
import json
import time
import traceback
import datetime as dt
from multiprocessing import Process, Queue

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


def execute_task(task):
    table_name = task["table_name"]
    # 等待数据到齐
    pre_msg = None
    task_dir = os.path.join(task["importer"].import_dir, table_name)
    while True:
        time.sleep(3)
        checkpoint_path = os.path.join(task_dir, "export_checkpoint.json")
        if not os.path.isfile(checkpoint_path):
            msg = f"任务 {task['token']} 的表 {table_name} 目录中没有 export_checkpoint.json 文件"
            if pre_msg != msg:
                print(msg)
                pre_msg = msg
            continue
        try:
            with open(checkpoint_path, mode="r") as fp:
                task_export_checkpoint = json.load(fp)
        except:
            msg = f'尝试读取 {checkpoint_path} 失败：{traceback.format_exc()}'
            if pre_msg != msg:
                print(msg)
                pre_msg = msg
            continue
        if task_export_checkpoint.get("token", None) != task["token"]:
            msg = f"""{checkpoint_path} 文件中的 token({task_export_checkpoint.get("token", None)}) 不等于任务 token"""
            if pre_msg != msg:
                print(msg)
                pre_msg = msg
            continue
        data_file_list = [ifile for ifile in os.listdir(task_dir) if ifile.startswith(task["token"])]
        if len(data_file_list) != task_export_checkpoint.get("data_file_num", None):
            msg = f"""{task_dir} 中的文件数量({len(data_file_list)}) 不等于 checkpoint 中的文件数量({task_export_checkpoint.get("data_file_num", None)})"""
            if pre_msg != msg:
                print(msg)
                pre_msg = msg
            continue
        break
    
    try:
        imported_rows = task["importer"].import_table(task["token"], task["table_name"], del_table_name=task["del_table"], resume=task.get("resume", True))
    except:
        ifok, msg = False, traceback.format_exc()
    else:
        ifok, msg = True, f"共 {imported_rows} 行"
    if "queue" in task:
        task["queue"].put((task["token"], task["table_name"], ifok, msg))
    else:
        return (task["token"], task["table_name"], ifok, msg)

class DataImporter(FileSystemEventHandler):
    def __init__(self,
        target_dir: str,
        importer,
        cmd_file: str = "cmd.json", 
        interval_seconds: int = 3,
        retry_num: int=3,
        concurrent_num: int=0
    ):
        self.target_dir = target_dir
        self.importer = importer
        self.cmd_file = cmd_file
        self.interval_seconds = interval_seconds
        self.retry_num = retry_num
        self.concurrent_num = concurrent_num

        self.proc_list = {}# {(token, table_name): Process}
        self.queue = Queue()
        self.observation_list = {
            self.cmd_file: dt.datetime.fromtimestamp(os.path.getmtime(os.path.join(self.target_dir, self.cmd_file)))
        }
        return super().__init__()
    
    def clear_data(self, task_dir):
        ifok = True
        for ifile in os.listdir(task_dir):
            if ifile.startswith(self.token):
                ifile_path = os.path.join(task_dir, ifile)
                for i in range(self.retry_num):
                    try:
                        os.remove(ifile_path)
                    except:
                        msg = traceback.format_exc()
                    else:
                        break
                else:
                    print(f"清理文件 {ifile_path} 失败: {msg}")
                    ifok = False
        if not ifok:
            print(f"清理任务目录 {task_dir} 失败")
        else:
            print(f"清理任务目录 {task_dir} 完成")
        return ifok
    
    def check_proc(self):
        has_proc = bool(self.proc_list)
        if self.concurrent_num > 0:
            while not self.queue.empty():
                token, table_name, ifok, msg = self.queue.get()
                if ifok:
                    print(f"任务 {token} 的表 {table_name} 导入完成: {msg}")
                else:
                    print(f"任务 {token} 的表 {table_name} 导入失败: {msg}")
                self.proc_list.pop((token, table_name), None)
            for token, table_name in list(self.proc_list.keys()):
                if (not self.proc_list[(token, table_name)].is_alive()) and self.queue.empty():
                    print(f"任务 {token} 的表 {table_name} 导入失败: 工作进程错误")
                    self.proc_list.pop((token, table_name), None)
        else:
            for token, table_name in list(self.proc_list.keys()):
                if self.proc_list[(token, table_name)] is not None:
                    token, table_name, ifok, msg = self.proc_list[(token, table_name)]
                    if ifok:
                        print(f"任务 {token} 的表 {table_name} 导入完成: {msg}")
                    else:
                        print(f"任务 {token} 的表 {table_name} 导入失败: {msg}")
                    self.proc_list.pop((token, table_name), None)
        if has_proc and (not self.proc_list):
            print("等待新的任务中...")

    def handle_cmd(self):
        cmd_file_path = os.path.join(self.target_dir, self.cmd_file)
        for i in range(self.retry_num):
            try:
                with open(cmd_file_path, mode="r") as fp:
                    cmd = json.load(fp)
            except:
                msg = traceback.format_exc()
                time.sleep(self.interval_seconds)
                continue
            else:
                break
        else:
            print(f'读取 {cmd_file_path} 失败：{msg}')
            return
        token = cmd["token"]
        table_list = cmd.get("table_list", [])
        del_table_list = cmd.get("del_table_list", [])
        resume = cmd.get("resume", True)

        if not table_list:
            print(f"{token} 任务列表为空!")
            return
        print(f"执行任务: {token}")
        
        # 启动导入任务
        for i, itable in enumerate(table_list):
            if (token, itable) in self.proc_list:
                print(f"任务 {token} 的表 {itable} 已经在导入，无需重复执行!")
                continue
            if self.concurrent_num <= 0:
                self.proc_list[(token, itable)] = None
                self.proc_list[(token, itable)] = execute_task({"importer": self.importer, "token": token, "table_name": itable, "del_table": del_table_list[i], "resume": resume})
            else:
                self.proc_list[(token, itable)] = Process(target=execute_task, args=({"importer": self.importer, "token": token, "table_name": itable, "del_table": del_table_list[i], "queue": self.queue, "resume": resume},))
                self.proc_list[(token, itable)].start()

    def on_any_event(self, event):
        if event.is_directory: 
            return
        if event.event_type not in ("created", "modified"):
            return
        file_path = event.src_path
        _, file_name = os.path.split(file_path)
        if file_name not in self.observation_list: return
        modified_time = dt.datetime.fromtimestamp(os.path.getmtime(event.src_path))
        if modified_time==self.observation_list[file_name]:
            print(f"文件 {file_name} 的修改时间({modified_time}) 没有发生变化，忽略此次变更信号！")
            return
        else:
            self.observation_list[file_name] = modified_time

        if file_name == self.cmd_file:
            return self.handle_cmd()

if __name__ == "__main__":
    from QSExt.DataSync.PostgresImporter import PostgresImporter

    target_dir = r'D:\Data\JYDBSync'
    config = {
        'host': 'localhost',
        'port': '5433',
        'database': 'JYDB',
        'username': 'shzq',
        'password': 'shzq#321',
        'import_dir': target_dir
    }
    importer = PostgresImporter(**config)
    interval_seconds = 3
    concurrent_num = 1

    event_handler = DataImporter(target_dir=target_dir, importer=importer, interval_seconds=interval_seconds, concurrent_num=concurrent_num)
    observer = Observer()
    observer.schedule(event_handler, path=target_dir, recursive=True)
    observer.start()
    print("等待新的任务中...")

    try:
        while True:
            time.sleep(interval_seconds)
            event_handler.check_proc()
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
