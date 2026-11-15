"""面向 MCP 的有限、类型稳定的因子发现和读取操作。"""

import datetime as dt
import json
import math

from .catalog import decode_cursor, encode_cursor, normalize


def parse_date(value):
    try:
        return dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("日期必须使用 ISO 8601 格式") from None


class FactorDataService:
    def __init__(self, catalog, client_factory, max_cells=2000, max_result_bytes=65536):
        self.catalog = catalog
        self.client_factory = client_factory
        self.max_cells = max_cells
        self.max_result_bytes = max_result_bytes

    def refresh_catalog(self):
        return self.catalog.refresh()

    def list_databases(self):
        return {"items": self.catalog.databases(), "refreshed_at": self.catalog.state("refreshed_at"),
                "catalog_stale": self.catalog.is_stale()}

    def list_tables(self, database=None, query="", cursor=None, page_size=20):
        return self.catalog.tables(database, query, cursor, page_size)

    def search_factors(self, query="", database=None, table=None, cursor=None, page_size=20):
        return self.catalog.search(query, database, table, cursor, page_size)

    def get_factor(self, identifier):
        return self.catalog.get(identifier)

    def get_coverage(self, identifier, id_query="", id_cursor=None, id_page_size=50,
                     start_date=None, end_date=None):
        if not 1 <= id_page_size <= 200:
            raise ValueError("id_page_size 必须在 1 到 200 之间")
        item = self.catalog.get(identifier)
        with self._factor(item) as (_, table, factor):
            ids = list(factor.getID())
            if id_query:
                ids = [value for value in ids if id_query.casefold() in str(value).casefold()]
            start = parse_date(start_date) if start_date else None
            end = parse_date(end_date) if end_date else None
            dates = list(factor.getDateTime(start_dt=start, end_dt=end))
        offset = decode_cursor(id_cursor)
        page = ids[offset:offset + id_page_size]
        return {"factor_id": identifier, "id_count": len(ids), "ids": page,
                "next_id_cursor": encode_cursor(offset + id_page_size) if offset + id_page_size < len(ids) else None,
                "date_count": len(dates), "start_date": normalize(min(dates)) if dates else None,
                "end_date": normalize(max(dates)) if dates else None}

    def read_data(self, factor_ids, ids, dates=None, start_date=None, end_date=None):
        if not factor_ids or len(factor_ids) > 20:
            raise ValueError("factor_ids 数量必须为 1 到 20")
        if not ids or len(ids) > self.max_cells:
            raise ValueError("ids 不能为空且不能超过读取上限")
        items = [self.catalog.get(identifier) for identifier in factor_ids]
        location = {(item["database_name"], item["table_name"]) for item in items}
        if len(location) != 1:
            raise ValueError("一次读取的因子必须属于同一数据库和因子表")
        if dates and (start_date or end_date):
            raise ValueError("dates 与日期区间不能同时使用")
        if not dates and not (start_date and end_date):
            raise ValueError("必须提供 dates，或同时提供 start_date 和 end_date")
        parsed_dates = [parse_date(value) for value in dates] if dates else None
        with self._table(items[0]) as (_, table):
            if parsed_dates is None:
                parsed_dates = list(table.getDateTime(ifactor_name=items[0]["factor_name"],
                    start_dt=parse_date(start_date), end_dt=parse_date(end_date)))
            cells = len(items) * len(ids) * len(parsed_dates)
            if cells > self.max_cells:
                raise ValueError(f"读取规模 {cells} 超过上限 {self.max_cells}，请缩小因子、ID 或日期范围")
            names = [item["factor_name"] for item in items]
            panel = table.readData(factor_names=names, ids=ids, dts=parsed_dates)
        rows = []
        for position, (identifier, name) in enumerate(zip(factor_ids, names)):
            frame = panel.iloc[position]
            for date_value in frame.index:
                for asset_id in frame.columns:
                    rows.append({"date": normalize(date_value), "asset_id": str(asset_id),
                                 "factor_id": identifier, "factor": name,
                                 "value": normalize(frame.at[date_value, asset_id])})
        result = {"database": items[0]["database_name"], "table": items[0]["table_name"],
                  "factor_ids": factor_ids, "cell_count": cells, "rows": rows}
        if len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > self.max_result_bytes:
            raise ValueError("读取结果超过 MCP 响应字节上限，请进一步缩小范围")
        return result

    def _client(self):
        client = self.client_factory()
        client.connect()
        return client

    class _RemoteContext:
        def __init__(self, service, item, factor=False):
            self.service, self.item, self.factor = service, item, factor

        def __enter__(self):
            self.client = self.service._client()
            self.database = self.client.getDatabase(self.item["database_name"]).connect()
            self.table = self.database.getTable(self.item["table_name"])
            if self.factor:
                return self.database, self.table, self.table.getFactor(self.item["factor_name"])
            return self.database, self.table

        def __exit__(self, *args):
            try:
                self.database.disconnect()
            finally:
                self.client.close()

    def _factor(self, item):
        return self._RemoteContext(self, item, True)

    def _table(self, item):
        return self._RemoteContext(self, item, False)
