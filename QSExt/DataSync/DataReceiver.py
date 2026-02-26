import os
import json
import uuid
import time
import shutil
import traceback
import datetime as dt
from threading import Lock
from typing import List, Dict, Any, Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class DataReceiver(FileSystemEventHandler):
    def __init__(self,
        main_dir: str,
        target_dir: str,
        importer,
        cmd_file: str = "cmd.json", 
        export_cmd_file: str = "export_cmd.json",
        target_cmd_file: str = "cmd.json",
        import_status_file: str = "import_status.json",
        export_status_file: str = "export_status.json", 
        interval_seconds: int = 3,
        retry_num=3
    ):
        self.main_dir = main_dir
        self.target_dir = target_dir
        self.importer = importer
        self.cmd_file = cmd_file
        self.export_cmd_file = export_cmd_file
        self.target_cmd_file = target_cmd_file
        self.import_status_file = import_status_file
        self.export_status_file = export_status_file
        self.interval_seconds = interval_seconds
        self.retry_num = retry_num
        
        self.token = None
        self.cmd = {}
        self.task_info = {}
        self.import_status = {}
        self.lock = Lock()
        self.observation_list = {
            self.cmd_file: dt.datetime.fromtimestamp(os.path.getmtime(os.path.join(self.main_dir, self.cmd_file))),
            self.export_status_file: dt.datetime.fromtimestamp(os.path.getmtime(os.path.join(self.main_dir, self.export_status_file)))
        }
        return super().__init__()
    
    def exec_data_transfer(self, table_list):
        table_list = table_list.copy()
        pre_msg = None
        while table_list:
            time.sleep(self.interval_seconds)
            table_name = table_list.pop(0)
            task_dir = os.path.join(self.main_dir, table_name)
            checkpoint_path = os.path.join(task_dir, "export_checkpoint.json")
            if not os.path.isfile(checkpoint_path):
                table_list.append(table_name)
                continue
            try:
                with open(checkpoint_path, mode="r") as fp:
                    task_export_checkpoint = json.load(fp)
            except:
                msg = f'尝试读取 {checkpoint_path} 失败：{traceback.format_exc()}'
                if pre_msg != msg:
                    print(msg)
                    pre_msg = msg
                table_list.append(table_name)
                continue
            if task_export_checkpoint.get("token", None) != self.token:
                msg = f"""{checkpoint_path} 文件中的 token({task_export_checkpoint.get("token", None)}) 不等于任务 token"""
                if pre_msg != msg:
                    print(msg)
                    pre_msg = msg
                table_list.append(table_name)
                continue
            data_file_list = [ifile for ifile in os.listdir(task_dir) if ifile.startswith(self.token)]
            file_size = task_export_checkpoint.get("file_size", {})
            if len(data_file_list) != len(file_size):
                msg = f"""{task_dir} 中的文件数量({len(data_file_list)}) 不等于 checkpoint 中的文件数量({len(file_size)})"""
                if pre_msg != msg:
                    print(msg)
                    pre_msg = msg
                table_list.append(table_name)
                continue
            for ifile in data_file_list:
                ifile_size = os.path.getsize(os.path.join(task_dir, ifile))
                if ifile_size != file_size[ifile]:
                    msg = f"""{task_dir} 中的文件({ifile}) 大小({ifile_size})不等于 checkpoint 中标记的文件大小({file_size[ifile]})"""
                    if pre_msg != msg:
                        print(msg)
                        pre_msg = msg
                    table_list.append(table_name)
                    break
            else:
                ifok = self.transfer_data(task_dir)
                if ifok: self.clear_data(task_dir)
    
    def transfer_data(self, task_dir):
        task_name = os.path.split(task_dir)[-1]
        tdir = os.path.join(self.target_dir, task_name)
        if not os.path.isdir(tdir): os.mkdir(tdir)
        sdir = task_dir
        for i in range(self.retry_num):
            try:
                shutil.copytree(sdir, tdir, dirs_exist_ok=True)
            except:
                msg = traceback.format_exc()
                time.sleep(self.interval_seconds)
            else:
                print(f"复制目录 {sdir} -> {tdir} 完成")
                return True
        else:
            print(f"复制目录 {sdir} -> {tdir} 失败: {msg}")
        return False
    
    def clear_data(self, task_dir):
        ifok = True
        for ifile in os.listdir(task_dir):
            #if ifile.startswith(self.token):
            ifile_path = os.path.join(task_dir, ifile)
            for i in range(self.retry_num):
                try:
                    os.remove(ifile_path)
                except:
                    msg = traceback.format_exc()
                    time.sleep(self.interval_seconds)
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
    
    def handle_cmd(self):
        with self.lock:
            if self.import_status.get("status", "finished") not in ("finished", "terminated"):
                print(f"正在运行任务 {self.cmd['token']}, 无法接受新任务!")
                return
            self.import_status["status"] = "starting"

        cmd_file_path = os.path.join(self.main_dir, self.cmd_file)
        for i in range(self.retry_num):
            try:
                with open(cmd_file_path, mode="r") as fp:
                    self.cmd = json.load(fp)
            except:
                msg = traceback.format_exc()
                time.sleep(self.interval_seconds)
                continue
            else:
                break
        else:
            print(f'读取 {cmd_file_path} 失败：{msg}')
            return
        self.token = self.cmd.get("token", None)
        if not self.token: self.token = uuid.uuid4().hex
        
        task_list = self.cmd.get("specific_task_list", [])
        table_list = self.cmd.get("table_list", [])
        table_list_file = self.cmd.get("table_list_file", None)
        if table_list_file and os.path.isfile(table_list_file):
            with open(table_list_file, mode="r") as file:
                table_list += list(file)
        elif table_list_file:
            print(f"table_list_file {table_list_file} 不存在!")
        for itable in table_list:
            if not itable.strip(): continue
            itable = itable.split(":")
            itable_name = itable[0].strip()
            if len(itable)>=2: id_field = itable[1].strip()
            else: id_field = "JSID"
            if len(itable)>=3: del_table = itable[2].strip()
            else: del_table = "JYDB_DeleteRec"
            task_list.append({
                "table_name": itable_name, 
                "id_field": id_field, 
                "del_table": del_table, 
                "max_id": self.importer.get_max_id(table_name=itable_name, id_field=id_field), 
                "del_max_id": self.importer.get_del_max_id(table_name=itable_name, del_table_name=del_table)
            })
        
        # 校验任务
        self.task_info = {}
        for task in task_list:
            if task["table_name"] in self.task_info:
                print(f"任务 {self.token} 的表 {task['table_name']} 有重复!")
                return
            else:
                self.task_info[task["table_name"]] = task

        print(f"执行任务: {self.token}")
        if not task_list:
            print("任务列表为空!")
            return
        self.import_status = {
            "token": self.token,
            "status": "starting",
            "task_list": task_list,
            "start_time": dt.datetime.now().isoformat(),
            "task_group_idx": self.cmd.get("task_group_idx", -1),
            "task_start_time": dt.datetime.now().isoformat(),
        }
        with open(os.path.join(self.main_dir, self.export_cmd_file), mode="w") as fp:
            salt = uuid.uuid4().hex# 防止生成的 cmd 文件完全一样导致不发生同步
            json.dump({"token": self.token, "task_list": task_list, "task_group_idx": self.cmd.get("task_group_idx", -1), "salt": salt}, fp, ensure_ascii=False, indent=2)
    
    def handle_export_status(self):
        with self.lock:
            export_status_file = os.path.join(self.main_dir, self.export_status_file)
            for i in range(self.retry_num):
                try:
                    with open(export_status_file, mode="r") as fp:
                        export_status = json.load(fp)
                except:
                    msg = traceback.format_exc()
                    time.sleep(self.interval_seconds)
                else:
                    break
            else:
                print(f"打开文件 {export_status_file} 失败: {msg}")
                return
            token = export_status.get("token", None)
            if token != self.token:
                print(f"收到的 export_status token({token}) 和当前执行的 token({self.token}) 不一致, 忽略接收到的 export_status 变更")
                return
            istatus, task_group_idx = export_status.get("status", None), export_status["task_group_idx"]
            if (istatus in ("finished", "task_group_finished")) and (task_group_idx > self.import_status["task_group_idx"]):
                self.import_status["task_group_idx"] = task_group_idx
                self.import_status["status"] = "running"
                running_time = (dt.datetime.now() - dt.datetime.fromisoformat(self.import_status["task_start_time"])).seconds
                self.import_status["task_start_time"] = dt.datetime.now().isoformat()
                with open(os.path.join(self.main_dir, self.import_status_file), mode="w") as fp:
                    json.dump(self.import_status | {"salt": uuid.uuid4().hex}, fp, ensure_ascii=False, indent=2)
                
                print(f"导出任务 {task_group_idx} 完成，用时 {running_time} 秒，执行数据迁移！")
                self.exec_data_transfer(export_status["table_list"])
                running_time = (dt.datetime.now() - dt.datetime.fromisoformat(self.import_status["task_start_time"])).seconds
                self.import_status["task_start_time"] = dt.datetime.now().isoformat()
                self.import_status["status"] = "task_group_finished"
                with open(os.path.join(self.main_dir, self.import_status_file), mode="w") as fp:
                    json.dump(self.import_status | {"salt": uuid.uuid4().hex}, fp, ensure_ascii=False, indent=2)
                with open(os.path.join(self.target_dir, self.target_cmd_file), mode="w") as fp:
                    salt = uuid.uuid4().hex# 防止生成的 cmd 文件完全一样导致不发生同步
                    del_table_list = [self.task_info[itable]["del_table"] for itable in export_status["table_list"]]
                    json.dump({"token": self.token, "table_list": export_status["table_list"], "del_table_list": del_table_list, "salt": salt}, fp, ensure_ascii=False, indent=2)
                print(f"数据迁移任务 {task_group_idx} 完成，用时 {running_time} 秒！")
            elif (istatus == "finished"):
                running_time = (dt.datetime.now() - dt.datetime.fromisoformat(self.import_status["start_time"])).seconds
                print(f"任务已经全部完成，用时 {running_time} 秒!")
                self.import_status["status"] = "finished"
                with open(os.path.join(self.main_dir, self.import_status_file), mode="w") as fp:
                    json.dump(self.import_status | {"salt": uuid.uuid4().hex}, fp, ensure_ascii=False, indent=2)
                print("\n\n\n\n等待新的任务中...")
            else:
                running_time = (dt.datetime.now() - dt.datetime.fromisoformat(self.import_status["task_start_time"])).seconds
                print(f"无效的导出文件变更: {export_status}，已经等待{running_time}秒，继续等待导出任务 {self.import_status['task_group_idx']+1} 完成...")
                return
        
    def on_any_event(self, event):
        if event.is_directory: return
        if event.event_type not in ("created", "modified"): return
        file_path = event.src_path
        task_dir, file_name = os.path.split(file_path)
        if file_name not in self.observation_list: return
        modified_time = dt.datetime.fromtimestamp(os.path.getmtime(event.src_path))
        if modified_time==self.observation_list[file_name]:
            print(f"文件 {file_name} 的修改时间({modified_time}) 没有发生变化，忽略此次变更信号！")
            return
        else:
            self.observation_list[file_name] = modified_time
        
        if file_name == self.cmd_file:
            return self.handle_cmd()
        if file_name == self.export_status_file:
            return self.handle_export_status()


if __name__ == "__main__":
    from QSExt.DataSync.PostgresImporter import PostgresImporter
    main_dir = r'D:\NXG Cloud\My Cloud\sqlserver_exports'
    target_dir = r'D:\Data\JYDBSync'
    interval_seconds = 3
    config = {
        'host': '172.25.109.134',
        'port': '5433',
        'database': 'JYDB',
        'username': 'shzq',
        'password': 'shzq#321',
        'import_dir': target_dir
    }
    importer = PostgresImporter(**config)
    
    event_handler = DataReceiver(main_dir=main_dir, target_dir=target_dir, importer=importer, interval_seconds=interval_seconds)
    observer = Observer()
    observer.schedule(event_handler, path=main_dir, recursive=True)
    observer.start()
    print("等待新的任务中...")

    try:
        while True:
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
