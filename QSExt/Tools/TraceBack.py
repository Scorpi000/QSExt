# coding=utf-8
import os
import sys
import signal
import warnings
import traceback
from functools import partial


def filterWarnings():
    """过滤常见的警告"""
    warnings.filterwarnings('ignore', category=FutureWarning)
    warnings.filterwarnings('ignore', 'All-NaN slice encountered')
    warnings.filterwarnings('ignore', 'All-NaN axis encountered')
    warnings.filterwarnings('ignore', 'invalid value encountered in power')
    warnings.filterwarnings('ignore', 'invalid value encountered in log')
    warnings.filterwarnings('ignore', 'invalid value encountered in divide')
    warnings.filterwarnings('ignore', 'invalid value encountered in scalar divide')
    warnings.filterwarnings('ignore', 'divide by zero encountered in log')
    warnings.filterwarnings('ignore', 'divide by zero encountered in divide')
    warnings.filterwarnings('ignore', 'Degrees of freedom <= 0 for slice')
    warnings.filterwarnings('ignore', 'Mean of empty slice')
    warnings.filterwarnings('ignore', 'An input array is constant; the correlation coefficient is not defined.')
    warnings.filterwarnings('ignore', 'An input array is nearly constant; the computed correlation coefficient may be inaccurate.')
    warnings.filterwarnings('ignore', 'divide by zero encountered in scalar divide')

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