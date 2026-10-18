"""工作台构图上下文、日期选择和运行期脚本执行工具。"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile


@dataclass(frozen=True)
class ConstructionContext:
    """本次构图的日期及截面快照，不包含活动数据库连接。"""

    dates: tuple[datetime, ...]
    section_ids: tuple[str, ...]
    module_directory: str | None = None


_construction = ContextVar("graph_construction", default=None)


@contextmanager
def construction_scope(dates, section_ids, module_directory=None):
    """在执行线程中限定构图维度的生命周期。"""
    token = _construction.set(ConstructionContext(tuple(dates), tuple(section_ids), module_directory))
    try:
        yield
    finally:
        _construction.reset(token)


def get_construction_context():
    """读取当前执行线程的构图维度快照，静态目录加载时返回 None。"""
    return _construction.get()


def calculation_dates(dates, rule):
    """按实际时点取每个周期的最后一个时点。"""
    if not rule:
        return list(dates)
    import pandas as pd
    count, unit = int(rule[:-1]), rule[-1]
    if count < 1:
        raise ValueError("计算频率必须大于零")
    index = pd.DatetimeIndex(dates)
    if unit == "d":
        return list(index[::count].to_pydatetime())
    period = {"w": "W", "m": "M", "y": "Y"}[unit]
    ends = pd.Series(index, index=index).groupby(index.to_period(period)).last().iloc[::count]
    return list(pd.DatetimeIndex(ends).to_pydatetime())


def build_script(block, args, inputs):
    """在任务构图阶段执行固定代码，返回完整账户因子。"""
    names = args["factor_names"]
    if len(names) != len(inputs["factors"]) or len(set(names)) != len(names) or any(not name for name in names):
        raise ValueError("策略别名必须唯一且与因子输入数量一致")
    code = args["code"]
    runtime = _construction.get()
    directory = Path(runtime.module_directory if runtime and runtime.module_directory else Path(tempfile.gettempdir()) / "qs_graph_scripts")
    name = "qs_strategy_" + hashlib.sha256((str(directory) + "\n" + code).encode()).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name + ".py")
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(code)
    except FileExistsError:
        pass
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            exec(compile(code, str(path), "exec"), module.__dict__)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return module.build_strategy(args["model_args"], dict(zip(names, inputs["factors"])), inputs["price"])
