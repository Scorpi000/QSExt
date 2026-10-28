"""公开操作白名单与原生标准读取适配。"""

import ast
import inspect
import operator
import re
from contextlib import nullcontext
from decimal import Decimal, InvalidOperation

import pandas as pd

from QuantStudio.Factor.Factor import Factor
from QuantStudio.Factor.FactorDB import WritableFactorDB
from QuantStudio.Factor.FactorTable import FactorTable
from QuantStudio.Core.Node import Node

from .protocol import RemoteFactorError

SQL_ARGUMENTS = {"FilterCondition", "TransformSQL", "QuerySQL", "DTSQL", "IDSQL", "TablePrefix", "DTFmt", "DateFmt", "UseIndex", "ForceIndex", "IgnoreIndex", "AdditionalCondition"}


def validate_table_args(db, name, values):
    """限制可进入原生 eval 和 SQL 拼接的参数，服务器预配置仍可使用。"""
    from .protocol import digest

    if "TableType" in values and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", str(values["TableType"])):
        raise RemoteFactorError("表类型必须为已注册类型名称", code="FORBIDDEN", status=403, effect="not_started")
    guarded = SQL_ARGUMENTS.intersection(values)
    if guarded:
        defaults = db.getTable(name).Args
        for key in guarded:
            if digest(values[key]) != digest(defaults.get(key)):
                raise RemoteFactorError("该 SQL 相关参数只能在服务器配置", code="FORBIDDEN", status=403, effect="not_started")


def protect_duckdb(db):
    """阻止原生 SQL 拼接把一次数据源查询变成多条 SQL 命令。"""
    if type(db).__module__ != "QSExt.Factor.DuckDB":
        return
    import duckdb

    fetchall, execute, delete_data = db.fetchall, db.execute, db.deleteData
    def check(sql, read):
        statements = duckdb.extract_statements(sql)
        if len(statements) != 1 or (read and statements[0].type != duckdb.StatementType.SELECT):
            raise RemoteFactorError("拒绝多语句或非查询 SQL", code="FORBIDDEN", status=403, effect="not_started")
    def safe_fetchall(sql, *args, **kwargs):
        check(sql, True)
        return fetchall(sql, *args, **kwargs)
    def safe_execute(sql):
        check(sql, False)
        return execute(sql)
    def safe_delete_data(table_name, ids=None, dts=None, dt_ids=None):
        ids = None if ids is None else [item.replace("'", "''") for item in ids]
        dt_ids = None if dt_ids is None else [(date, item.replace("'", "''")) for date, item in dt_ids]
        return delete_data(table_name, ids=ids, dts=dts, dt_ids=dt_ids)
    db.fetchall, db.execute = safe_fetchall, safe_execute
    db.deleteData = safe_delete_data


def sql_ids(table, values):
    """为旧 SQL 构造器转义字符串 ID，数值字段只接受实际数值。"""
    if values is None or not hasattr(table, "__QS_adjustID__"):
        return values
    if not all(isinstance(value, str) for value in values):
        raise RemoteFactorError("SQL 因子库 ID 必须为字符串", code="INVALID_ARGUMENT", status=422)
    if not getattr(table, "_IDFieldIsStr", True):
        try:
            if not all(Decimal(str(value)).is_finite() for value in table.__QS_adjustID__(values)):
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            raise RemoteFactorError("数值 ID 字段不接受 SQL 表达式", code="INVALID_ARGUMENT", status=422) from None
    return [value.replace("'", "''") for value in values]


def filter_ids(table, kwargs, max_cells):
    """解释受限筛选表达式，不调用原生实现中的 Python eval。"""
    ids = kwargs.get("ids")
    if ids is None:
        ids = table.getID(idt=kwargs["idt"])
    expression = kwargs.get("id_filter_str")
    if not expression:
        return pd.Series(True, index=ids)
    names = {"_qs_id": None}
    text = expression.replace("@_ID", "_qs_id")
    for index, name in enumerate(sorted(table.FactorNames, key=len, reverse=True)):
        variable = f"_qs_{index}"
        if "@" + name in text:
            text = text.replace("@" + name, variable)
            names[variable] = name
    binary = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Mod: operator.mod, ast.BitAnd: operator.and_, ast.BitOr: operator.or_, ast.BitXor: operator.xor}
    unary = {ast.Invert: operator.invert, ast.USub: operator.neg, ast.UAdd: operator.pos}
    compare = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}
    try:
        tree = ast.parse(text, mode="eval")
        allowed = {ast.Expression, ast.Load, ast.Constant, ast.Name, ast.List, ast.Tuple, ast.Set, ast.BinOp, ast.UnaryOp, ast.Compare, ast.Call, ast.Attribute} | set(binary) | set(unary) | set(compare)
        for node in ast.walk(tree):
            if type(node) not in allowed or (isinstance(node, ast.Name) and node.id not in names):
                raise ValueError("不支持的表达式")
            if isinstance(node, ast.Attribute) and not (isinstance(node.value, ast.Name) and node.value.id in names and node.attr in ("isin", "isna", "notna")):
                raise ValueError("不支持的属性")
            if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Attribute) or node.keywords):
                raise ValueError("不支持的调用")
    except (SyntaxError, ValueError, RecursionError):
        raise RemoteFactorError("筛选仅支持字段比较、算术、位逻辑及 isin/isna/notna", code="INVALID_FILTER", status=422) from None
    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    factors = [names[name] for name in names if name in used and names[name] is not None]
    if len(factors) * len(ids) > max_cells:
        raise RemoteFactorError("筛选超过单元格限制", code="TOO_LARGE", status=413)
    data = read_standard(table, {"factor_names": factors, "ids": ids, "dts": [kwargs["idt"]]}) if factors else None
    env = {"_qs_id": pd.Series(ids, index=ids)}
    env.update({variable: data.loc[name].iloc[0] for variable, name in names.items() if name in factors})
    def evaluate(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return env[node.id]
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return [evaluate(item) for item in node.elts]
        if isinstance(node, ast.BinOp):
            return binary[type(node.op)](evaluate(node.left), evaluate(node.right))
        if isinstance(node, ast.UnaryOp):
            return unary[type(node.op)](evaluate(node.operand))
        if isinstance(node, ast.Compare):
            left, result = evaluate(node.left), True
            for operation, right in zip(node.ops, node.comparators):
                right = evaluate(right)
                result = result & compare[type(operation)](left, right)
                left = right
            return result
        if isinstance(node, ast.Call):
            return getattr(env[node.func.value.id], node.func.attr)(*[evaluate(item) for item in node.args])
        raise RemoteFactorError("筛选表达式无效", code="INVALID_FILTER", status=422)
    return pd.Series(evaluate(tree.body), index=ids).astype(bool)

READS = {
    "database": {"TableNames"},
    "table": {"FactorNames", "getMetaData", "getFactorMetaData", "getID", "getDateTime", "getIDMask", "getFilteredID"},
    "factor": {"getMetaData", "getID", "getDateTime"},
}
WRITES = {"writeData", "renameTable", "deleteTable", "setTableMetaData", "renameFactor", "deleteFactor", "setFactorMetaData"}
EXTENSIONS = {
    "DuckDB": {"createTable": True, "addFactor": True, "deleteData": True, "deleteTableMetaData": True, "deleteFactorMetaData": True},
}
PROPERTY_NAMES = {"TableNames", "FactorNames"}


def supported_writes(db):
    """排除只继承了未实现基类方法的写能力。"""
    result = set()
    for name in WRITES:
        actual = getattr(type(db), name, None)
        base = getattr(WritableFactorDB, name, None)
        if actual is not None and actual is not base:
            result.add(name)
    return result


def backend_args(obj, base):
    """仅提取后端新增参数，不传输来源、执行器等本地资源。"""
    excluded = set(base.__QS_ArgClass__.model_fields)
    return {key: value for key, value in obj.Args.items() if key not in excluded}


def argument_schema(obj, base):
    """返回可见参数的简单描述，不传输 Python 类型或模型。"""
    return {name: {"title": field.title, "description": field.description, "type": str(field.annotation), "frozen": bool(field.frozen)}
            for name, field in type(obj.Args).model_fields.items() if name not in base.__QS_ArgClass__.model_fields}


def validate_call(obj, operation, kwargs):
    """在调用后端前验证命名参数，禁止任意反射入口。"""
    if operation in PROPERTY_NAMES:
        if kwargs:
            raise RemoteFactorError("属性查询不接受参数", code="INVALID_ARGUMENT", status=422)
        return
    try:
        inspect.signature(getattr(obj, operation)).bind(**kwargs)
    except (TypeError, ValueError):
        raise RemoteFactorError("操作参数与后端签名不匹配", code="INVALID_ARGUMENT", status=422) from None
    # 基类带 **kwargs 的接口不能成为任意参数的兜底通道。
    if operation in ("writeData", "readData"):
        allowed = {"data", "table_name", "if_exists", "data_type"} if operation == "writeData" else {"factor_names", "ids", "dts", "section_ids", "dt_ruler"}
        if set(kwargs).difference(allowed):
            raise RemoteFactorError("存在未声明的读取或写入参数", code="INVALID_ARGUMENT", status=422)


def read_standard(obj, kwargs):
    """读取原子数据源，显式绕过全局计算上下文。

    Args:
        obj: 已校验的真实因子表或原子因子。
        kwargs: 标准读取参数。

    Returns:
        原生标准 Panel 或 DataFrame。
    """
    factor = obj if isinstance(obj, Factor) else None
    table = factor.FactorTable if factor is not None else obj
    if factor is not None and (factor.Descriptors or table is None or type(factor).readData is not Factor.readData):
        raise RemoteFactorError("当前适配器仅允许原子数据源因子", code="UNSUPPORTED", status=422)
    validate_call(table, "readData", kwargs | ({"factor_names": [factor.Name]} if factor is not None else {}))
    values = dict(kwargs)
    if factor is not None:
        values["factor_names"] = [factor.Name]
    from QSExt.Factor._DuckDBCoordination import CoordinatedTable
    coordinated = isinstance(table, CoordinatedTable)
    if type(table).readData is not FactorTable.readData and not coordinated:
        raise RemoteFactorError("后端自定义 readData 需要显式适配器", code="UNSUPPORTED", status=422)
    with table.FactorDB.session() if coordinated else nullcontext():
        raw = table.__QS_prepareRawData__(factor_names=values["factor_names"], ids=sql_ids(table, values["ids"]), dts=values["dts"])
        result = table.__QS_calcData__(raw_data=raw, factor_names=values["factor_names"], ids=values["ids"], dts=values["dts"])
    return result.iloc[0] if factor is not None else result
