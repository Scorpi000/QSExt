"""
QSWeb 连接配置迁移脚本

将 QSWebConfig.yaml 中的 ``factor_dbs`` 节迁移到 QSGraphDB 图数据库。

用法:
    # 预览迁移（dry-run）
    python -m QSWeb.scripts.migrate_connections --dry-run

    # 执行实际迁移
    python -m QSWeb.scripts.migrate_connections

    # 指定配置文件路径
    python -m QSWeb.scripts.migrate_connections --config /path/to/QSWebConfig.json

流程:
    1. 读取 QSWebConfig.yaml 的 factor_dbs 节
    2. 为每条连接创建 FactorDB 实例并 connect
    3. 通过 QSGraphDB.registerFactorDB 写入 Neo4j
    4. 备份原 QSWebConfig.yaml（后缀 .bak）
    5. 删除 factor_dbs 节并写回

回滚:
    将备份文件恢复即可:
        cp QSWebConfig.yaml.bak QSWebConfig.yaml
"""

import json
import os
import sys
import shutil
import argparse
from pathlib import Path

import yaml


def get_config_path(custom_path: str = None) -> Path:
    """获取 QSWebConfig.yaml 路径"""
    if custom_path:
        return Path(custom_path)
    return Path(os.path.expanduser("~/QuantStudioConfig/QSWebConfig.yaml"))


def load_config(config_path: Path) -> dict:
    """加载配置文件"""
    if not config_path.exists():
        print(f"[错误] 配置文件不存在: {config_path}")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def backup_config(config_path: Path) -> Path:
    """备份配置文件"""
    backup_path = Path(str(config_path) + ".bak")
    shutil.copy2(config_path, backup_path)
    print(f"[备份] 已备份到: {backup_path}")
    return backup_path


def create_fdb(name: str, db_type: str, args: dict):
    """根据 db_type 创建 FactorDB 实例并 connect"""
    if db_type == "HDF5DB":
        from QuantStudio.Factor.HDF5DB import HDF5DB
        db = HDF5DB(args={"Name": name, **args})
    elif db_type in ("SQLDB", "JYDB"):
        from QuantStudio.Factor import JYDB
        db = JYDB(args={"Name": name, **args})
    elif db_type == "ClickHouseDB":
        from QSExt.Factor.ClickHouseDB import ClickHouseDB
        db = ClickHouseDB(args={"Name": name, **args})
    elif db_type == "MongoDB":
        from QSExt.Factor.MongoDB import MongoDB
        db = MongoDB(args={"Name": name, **args})
    elif db_type == "Neo4jDB":
        from QSExt.Factor.Neo4jDB import Neo4jDB
        db = Neo4jDB(args={"Name": name, **args})
    elif db_type == "DuckDB":
        from QSExt.Factor.DuckDB import DuckDB
        db = DuckDB(args={"Name": name, **args})
    elif db_type == "SQLite3DB":
        from QSExt.Factor.SQLite3DB import SQLite3DB
        db = SQLite3DB(args={"Name": name, **args})
    else:
        raise ValueError(f"不支持的数据库类型: {db_type}")
    db.connect()
    return db


def run_migration(config_path: Path, dry_run: bool = False):
    """执行迁移"""
    config = load_config(config_path)
    factor_dbs = config.get("factor_dbs", {})

    if not factor_dbs:
        print("[信息] QSWebConfig.yaml 中无 factor_dbs 节，无需迁移")
        return

    print(f"[信息] 发现 {len(factor_dbs)} 条连接配置\n")

    if dry_run:
        print("=" * 60)
        print("  DRY RUN 模式 — 仅预览，不执行实际迁移")
        print("=" * 60)

    # 连接 QSGraphDB
    from QSExt.QSRegistry.QSGraphDB import QSGraphDB
    gdb = QSGraphDB()
    gdb.connect()

    success_count = 0
    error_count = 0

    for conn_id, conn_info in factor_dbs.items():
        name = conn_info.get("name", conn_id)
        db_type = conn_info.get("db_type", "")
        description = conn_info.get("description", "")
        args = conn_info.get("args", {})

        print(f"\n--- 连接: {name} (ID: {conn_id}) ---")
        print(f"    类型: {db_type}")
        print(f"    参数: {json.dumps(args, ensure_ascii=False, default=str)}")

        if dry_run:
            try:
                fdb = create_fdb(name, db_type, args)
                qsid = fdb._QSArgs.QSID
                print(f"    QSID: {qsid} [预览]")
                fdb.disconnect()
                success_count += 1
            except Exception as e:
                print(f"    [错误] 无法创建 FactorDB: {e}")
                error_count += 1
        else:
            try:
                fdb = create_fdb(name, db_type, args)
                qsid = gdb.registerFactorDB(fdb)
                print(f"    [成功] 已注册到 QSGraphDB, QSID: {qsid}")
                success_count += 1
            except Exception as e:
                print(f"    [错误] 注册失败: {e}")
                error_count += 1

    print(f"\n{'=' * 60}")
    print(f"迁移完成: 成功 {success_count}, 失败 {error_count}")

    if dry_run:
        print("\n[提示] 预览完成。执行 python -m QSWeb.scripts.migrate_connections 进行实际迁移")
        return

    # 执行实际写入后的清理
    if success_count > 0:
        backup_config(config_path)
        del config["factor_dbs"]
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
        print(f"\n[完成] 已从 QSWebConfig.yaml 移除 factor_dbs 节")


def main():
    parser = argparse.ArgumentParser(
        description="将 QSWebConfig.yaml 的 factor_dbs 节迁移到 QSGraphDB"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="预览模式：仅显示将要迁移的连接和 QSID，不执行写入"
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="自定义 QSWebConfig.yaml 路径"
    )
    args = parser.parse_args()

    config_path = get_config_path(args.config)
    print(f"[配置路径] {config_path}\n")

    run_migration(config_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
