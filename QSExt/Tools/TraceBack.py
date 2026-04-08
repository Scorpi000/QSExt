# coding=utf-8
import os
import sys
import traceback
import signal
from functools import partial


# 捕获所有未处理异常
def handle_exception(exc_type, exc_value, exc_traceback, log_file):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"=== {os.getpid()}: 未捕获异常 ===")
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

# 捕获终止信号
def signal_handler(signum, frame, log_file):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"=== {os.getpid()}: 收到信号 {signum} ===")
        stack_lines = traceback.format_stack(frame)
        f.write(''.join(stack_lines))
    sys.exit(1)

def traceCrush(log_file:str):
    sys.excepthook = partial(handle_exception, log_file=log_file)
    signal.signal(signal.SIGTERM, partial(signal_handler, log_file=log_file))
    signal.signal(signal.SIGINT, partial(signal_handler, log_file=log_file))