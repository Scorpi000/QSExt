import os
import json
import uuid
import time
import traceback
import subprocess
import datetime as dt
from multiprocessing import Process
from threading import Lock
from contextlib import redirect_stdout, redirect_stderr

from watchdog.events import FileSystemEventHandler


def execute_cmd(args):
    cmd, main_dir = args["cmd"], args["main_dir"]
    token = cmd.get("token", None)
    respond_file = os.path.join(main_dir, f"{token}-rsp.log")
    # 同时捕获标准输出和标准错误
    with open(respond_file, 'w', encoding='utf-8') as f:
        with redirect_stdout(f), redirect_stderr(f):
            try:
                if "type" not in cmd:
                    print("命令中没有包含 type 字段，无法解析命令")
                elif cmd["type"] == "ping":
                    print("在!")
                elif cmd["type"] == "os":
                    result = subprocess.run(cmd.get("cmd", None), shell=True, capture_output=True, text=True)
                    print(result.stdout)
                    print("返回码: ", result.returncode)
                    if result.returncode != 0:
                        print(result.stderr)
                elif cmd["type"] == "powershell":
                    result = subprocess.run(['powershell', '-Command', cmd.get("cmd", None)], shell=True, capture_output=True, text=True)
                    print(result.stdout)
                    print("返回码: ", result.returncode)
                    if result.returncode != 0:
                        print(result.stderr)
                else:
                    print(f"不支持的命令类型: {cmd['type']}")
            except:
                print(traceback.format_exc())
            finally:
                print(f"salt: {uuid.uuid4().hex}")
                print("$$END$$")


class CmdExecutor(FileSystemEventHandler):
    def __init__(self,
        main_dir: str,
        cmd_file: str = "cmd.json",
        log_file: str = "cmd.log", 
        interval_seconds: int = 3,
        retry_num: int = 3
    ):
        self.main_dir = main_dir
        self.cmd_file = cmd_file
        self.log_file = log_file
        self.interval_seconds = interval_seconds
        self.retry_num = retry_num
        
        self.proc_list = {}
        self.lock = Lock()
        self.observation_list = {
            self.cmd_file: dt.datetime.fromtimestamp(os.path.getmtime(os.path.join(self.main_dir, self.cmd_file)))
        }
        return super().__init__()
    
    def check_proc(self):
        for token in list(self.proc_list.keys()):
            if (not self.proc_list[token].is_alive()):
                self.proc_list.pop(token, None)
    
    def handle_cmd(self):
        with self.lock:
            cmd_file = os.path.join(self.main_dir, self.cmd_file)
            for i in range(self.retry_num):
                try:
                    with open(cmd_file, mode="r") as fp:
                        cmd = json.load(fp)
                except:
                    msg = traceback.format_exc()
                    time.sleep(self.interval_seconds)
                else:
                    break
            else:
                print(f"打开文件 {cmd_file} 失败: {msg}")
                return
            
            token = cmd.get("token", None)
            if token in self.proc_list: return
            print(f"接到命令: {cmd}")
            self.proc_list[token] = Process(target=execute_cmd, args=({"cmd": cmd, "main_dir": self.main_dir,}, ))
            self.proc_list[token].start()

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

if __name__ == "__main__":
    from watchdog.observers import Observer
    main_dir = r'C:\Users\hst\Desktop\Tmp'
    interval_seconds = 3
    
    event_handler = CmdExecutor(
        main_dir=main_dir,
        interval_seconds=interval_seconds
    )
    observer = Observer()
    observer.schedule(event_handler, path=main_dir, recursive=True)
    observer.start()
    print("等待接受新的命令...")
    
    try:
        while True:
            time.sleep(interval_seconds)
            event_handler.check_proc()
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
