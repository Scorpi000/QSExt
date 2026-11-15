"""SQLite 因子目录；搜索不在请求热路径遍历远程数据库。"""

import base64
import datetime as dt
import hashlib
import json
import math
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from QSExt.FactorService.protocol import RemoteFactorError


def normalize(value):
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    return str(value)


def factor_id(service_id, resource_id, table_name, factor_name):
    raw = json.dumps([service_id, resource_id, table_name, factor_name], ensure_ascii=False,
                     separators=(",", ":")).encode("utf-8")
    return "fac_" + hashlib.sha256(raw).hexdigest()[:32]


def encode_cursor(offset):
    return base64.urlsafe_b64encode(json.dumps({"offset": offset}, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_cursor(cursor):
    if cursor is None:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        value = json.loads(raw)
        if set(value) != {"offset"} or not isinstance(value["offset"], int) or value["offset"] < 0:
            raise ValueError
        return value["offset"]
    except (ValueError, TypeError, json.JSONDecodeError):
        raise ValueError("无效的分页游标") from None


class FactorCatalog:
    def __init__(self, path: Path, client_factory, ttl_seconds=300, databases=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.client_factory = client_factory
        self.ttl_seconds = ttl_seconds
        self.databases_filter = frozenset(databases) if databases else None
        self._lock = threading.Lock()
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self):
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS factors (
                    factor_id TEXT PRIMARY KEY,
                    service_id TEXT NOT NULL,
                    database_name TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    config_revision TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    factor_name TEXT NOT NULL,
                    data_type TEXT,
                    description TEXT,
                    metadata_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS factors_search
                    ON factors(database_name, table_name, factor_name);
                CREATE TABLE IF NOT EXISTS catalog_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)

    def state(self, key, default=None):
        with self._connect() as db:
            row = db.execute("SELECT value FROM catalog_state WHERE key = ?", (key,)).fetchone()
        return default if row is None else row["value"]

    def ensure_fresh(self):
        if not self.count():
            raise ValueError("因子目录正在后台初始化，请稍后重试；大库首次同步可能需要较长时间")

    def is_stale(self):
        refreshed_at = float(self.state("refreshed_at", "0"))
        return dt.datetime.now().timestamp() - refreshed_at > self.ttl_seconds

    def refresh(self):
        with self._lock:
            rows, skipped = [], []
            client = self.client_factory()
            try:
                client.connect()
                service_id = client.info["service_id"]
                directories = client.listDatabases()
                if self.databases_filter:
                    missing = self.databases_filter.difference(item["name"] for item in directories)
                    if missing:
                        raise ValueError("FactorService 未导出数据库：" + ", ".join(sorted(missing)))
                    directories = [item for item in directories if item["name"] in self.databases_filter]
                for directory in directories:
                    try:
                        snapshot = client.getCatalog(directory["name"])
                        table_items = snapshot["tables"]
                        skipped.extend({"database": directory["name"], "table": item["table_name"],
                                        "code": item["code"]} for item in snapshot.get("skipped_tables", []))
                    except RemoteFactorError as error:
                        if error.status != 404:
                            raise
                        table_items, fallback = self._legacy_catalog(client, directory["name"])
                        skipped.extend(fallback)
                    for table_item in table_items:
                        table_name = table_item["table_name"]
                        names = table_item["factor_names"]
                        metadata = self._metadata_dict(table_item.get("factor_metadata"), names)
                        now = dt.datetime.now().timestamp()
                        for name in names:
                            item = metadata.get(name, {})
                            rows.append((factor_id(service_id, directory["resource_id"], table_name, name),
                                service_id, directory["name"], directory["resource_id"],
                                directory["config_revision"], table_name, name,
                                str(item.get("DataType", "")), str(item.get("Description", "")),
                                json.dumps(normalize(item), ensure_ascii=False, separators=(",", ":")), now))
            finally:
                client.close()
            with self._connect() as db:
                db.execute("DELETE FROM factors")
                db.executemany("INSERT INTO factors VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
                db.execute("INSERT OR REPLACE INTO catalog_state(key, value) VALUES ('refreshed_at', ?)",
                           (str(dt.datetime.now().timestamp()),))
                db.execute("INSERT OR REPLACE INTO catalog_state(key, value) VALUES ('service_id', ?)",
                           (service_id,))
                db.execute("INSERT OR REPLACE INTO catalog_state(key, value) VALUES ('skipped_tables', ?)",
                           (json.dumps(skipped, ensure_ascii=False, separators=(",", ":")),))
            return {"service_id": service_id, "factor_count": len(rows),
                    "skipped_table_count": len(skipped), "skipped_tables": skipped[:100],
                    "refreshed_at": self.state("refreshed_at")}

    @staticmethod
    def _metadata(table, names):
        if not names:
            return {}
        try:
            frame = table.getFactorMetaData(factor_names=names)
            if hasattr(frame, "to_dict"):
                return {str(key): normalize(value) for key, value in frame.to_dict(orient="index").items()}
        except (TypeError, ValueError, RemoteFactorError):
            pass
        values = table.getFactorMetaData(factor_names=names, key="DataType")
        return {name: {"DataType": values.loc[name] if hasattr(values, "loc") else values[name]}
                for name in names}

    @staticmethod
    def _metadata_dict(value, names):
        if hasattr(value, "to_dict"):
            value = value.to_dict(orient="index")
        if not isinstance(value, dict):
            return {name: {} for name in names}
        return {name: normalize(value.get(name, {})) for name in names}

    def _legacy_catalog(self, client, database_name):
        database = client.getDatabase(database_name).connect()
        tables, skipped = [], []
        try:
            for table_name in database.TableNames:
                try:
                    table = database.getTable(table_name)
                    names = list(table.FactorNames)
                    tables.append({"table_name": table_name, "factor_names": names,
                                   "factor_metadata": self._metadata(table, names)})
                except RemoteFactorError as error:
                    skipped.append({"database": database_name, "table": table_name, "code": error.code})
        finally:
            database.disconnect()
        return tables, skipped

    def count(self):
        with self._connect() as db:
            return db.execute("SELECT COUNT(*) FROM factors").fetchone()[0]

    def databases(self):
        self.ensure_fresh()
        with self._connect() as db:
            rows = db.execute("""SELECT database_name, resource_id, config_revision,
                COUNT(DISTINCT table_name) AS table_count, COUNT(*) AS factor_count
                FROM factors GROUP BY database_name, resource_id, config_revision ORDER BY database_name""").fetchall()
        return [dict(row) for row in rows]

    def tables(self, database=None, query="", cursor=None, page_size=20):
        self.ensure_fresh()
        if not 1 <= page_size <= 100:
            raise ValueError("page_size 必须在 1 到 100 之间")
        where, values = [], []
        if database:
            where.append("database_name = ?")
            values.append(database)
        if query:
            where.append("table_name LIKE ? ESCAPE '\\'")
            values.append("%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
        clause = " WHERE " + " AND ".join(where) if where else ""
        offset = decode_cursor(cursor)
        sql = ("SELECT database_name, table_name, COUNT(*) AS factor_count FROM factors" + clause
               + " GROUP BY database_name, table_name ORDER BY database_name, table_name LIMIT ? OFFSET ?")
        with self._connect() as db:
            rows = db.execute(sql, (*values, page_size + 1, offset)).fetchall()
        return self._page(rows, offset, page_size)

    def search(self, query="", database=None, table=None, cursor=None, page_size=20):
        self.ensure_fresh()
        if not 1 <= page_size <= 100:
            raise ValueError("page_size 必须在 1 到 100 之间")
        where, values = [], []
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append("(factor_name LIKE ? ESCAPE '\\' OR table_name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')")
            values.extend(["%" + escaped + "%"] * 3)
        if database:
            where.append("database_name = ?")
            values.append(database)
        if table:
            where.append("table_name = ?")
            values.append(table)
        clause = " WHERE " + " AND ".join(where) if where else ""
        offset = decode_cursor(cursor)
        sql = ("SELECT factor_id, database_name, table_name, factor_name, data_type, description "
               "FROM factors" + clause + " ORDER BY database_name, table_name, factor_name, factor_id LIMIT ? OFFSET ?")
        with self._connect() as db:
            rows = db.execute(sql, (*values, page_size + 1, offset)).fetchall()
        return self._page(rows, offset, page_size)

    @staticmethod
    def _page(rows, offset, page_size):
        more = len(rows) > page_size
        items = [dict(row) for row in rows[:page_size]]
        return {"items": items, "next_cursor": encode_cursor(offset + page_size) if more else None}

    def get(self, identifier):
        self.ensure_fresh()
        with self._connect() as db:
            row = db.execute("SELECT * FROM factors WHERE factor_id = ?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("因子不存在或目录需要刷新")
        result = dict(row)
        result["metadata"] = json.loads(result.pop("metadata_json"))
        result.pop("updated_at")
        return result
