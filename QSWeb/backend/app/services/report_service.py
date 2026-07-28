"""
报告中心服务

负责报告生成、存储、检索和注册。
"""

import datetime as dt
import json
import logging
import os
import uuid
from typing import Dict, List, Optional, Any

from app.models.report import (
    ReportScenario,
    ReportGenerateRequest,
    ReportInfo,
    REPORT_SCENARIO_REGISTRY,
)

logger = logging.getLogger(__name__)

QS_CONFIG_PATH = os.path.expanduser("~/QuantStudioConfig/QSWebConfig.json")
DEFAULT_REPORT_DIR = os.path.expanduser("~/QuantStudioConfig/reports")


def get_report_dir() -> str:
    """获取报告存储目录（从 QSWebConfig.json 读取，未配置时使用默认值）"""
    if os.path.exists(QS_CONFIG_PATH):
        try:
            with open(QS_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            report_cfg = cfg.get("report", {})
            if report_cfg.get("output_dir"):
                return os.path.expanduser(report_cfg["output_dir"])
        except Exception:
            pass
    return DEFAULT_REPORT_DIR


def set_report_dir(path: str):
    """设置报告存储目录（写入 QSWebConfig.json）"""
    cfg = {}
    if os.path.exists(QS_CONFIG_PATH):
        try:
            with open(QS_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    if "report" not in cfg:
        cfg["report"] = {}
    cfg["report"]["output_dir"] = path
    os.makedirs(os.path.dirname(QS_CONFIG_PATH), exist_ok=True)
    with open(QS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.makedirs(os.path.expanduser(path), exist_ok=True)


class ReportService:
    """报告中心服务"""

    def __init__(self, factor_service=None):
        self._factor_service = factor_service
        os.makedirs(get_report_dir(), exist_ok=True)

    # ─── 场景列表 ─────────────────────────────────────────────

    def list_scenarios(self) -> List[dict]:
        """列出所有可用的报告场景"""
        return [
            {
                "key": key,
                "name": info["name"],
                "description": info.get("description", ""),
                "output_formats": info.get("output_formats", ["html", "markdown"]),
                "module_options": info.get("module_options", []),
            }
            for key, info in REPORT_SCENARIO_REGISTRY.items()
        ]

    # ─── 报告生成 ─────────────────────────────────────────────

    async def generate(self, req: ReportGenerateRequest) -> str:
        """提交报告生成任务，返回 task_id。"""
        from app.tasks.manager import task_manager

        # 提前解析因子引用，避免在闭包中引用 req（Pydantic model 可能在 await 后失效）
        factor_refs = [ref.model_dump() for ref in req.factor_refs]
        price_ref = req.price_ref.model_dump() if req.price_ref else None
        mask_ref = req.mask_ref.model_dump() if req.mask_ref else None
        cat_data_ref = req.cat_data_ref.model_dump() if req.cat_data_ref else None
        weight_ref = req.weight_ref.model_dump() if req.weight_ref else None
        start_date = req.start_date
        end_date = req.end_date
        output_formats = list(req.output_formats)
        descriptor_ids = list(req.descriptor_ids) if req.descriptor_ids else None
        rebalance_dts = list(req.rebalance_dts) if req.rebalance_dts else None
        scenario = req.scenario
        modules_config = req.modules.model_dump() if req.modules else {}

        async def _run():
            import asyncio
            loop = asyncio.get_running_loop()

            await task_manager.update_progress(task_id, 5, "正在加载因子...")

            # 解析因子
            keep_factor_service(self)
            factors = []
            for ref_dict in factor_refs:
                f = await _resolve_factor(ref_dict)
                factors.append(f)

            price = None
            if price_ref:
                await task_manager.update_progress(task_id, 10, "正在加载价格因子...")
                price = await _resolve_factor(price_ref)

            mask = None
            if mask_ref:
                mask = await _resolve_factor(mask_ref)

            cat_data = None
            if cat_data_ref:
                cat_data = await _resolve_factor(cat_data_ref)

            weight = None
            if weight_ref:
                weight = await _resolve_factor(weight_ref)

            await task_manager.update_progress(task_id, 20, "正在获取时点和截面 ID...")

            ref_factor = factor_refs[0]
            dtruler, dts = await _get_dts(ref_factor, start_date, end_date)
            ids = descriptor_ids
            if not ids:
                ids = await _get_section_ids(ref_factor)

            parsed_rebalance = None
            if rebalance_dts:
                parsed_rebalance = [
                    dt.datetime.strptime(d, "%Y-%m-%d") for d in rebalance_dts
                ]

            await task_manager.update_progress(task_id, 30, "正在构造报告节点...")

            # 同步执行报告生成
            def _sync_generate():
                from QSExt.ReportGenerator.scenarios.single_factor.scenario import (
                    SingleFactorReport,
                )
                from QuantStudio.Core.CalcEngine import Engine
                from QuantStudio.Core.Node import DTInitData, DTLocalContext
                from QuantStudio.Factor.Factor import FactorContext

                data_nodes = SingleFactorReport.create_nodes(
                    factors,
                    price=price,
                    mask=mask,
                    cat_data=cat_data,
                    weight=weight,
                    descriptor_ids=ids,
                    rebalance_dts=parsed_rebalance,
                    config=modules_config,
                )

                factor_names = [f.Name for f in factors]

                report_node = SingleFactorReport(
                    data_nodes=data_nodes,
                    args={"OutputFormats": output_formats},
                    factor_names=factor_names,
                )

                start_dt = dts[0] if isinstance(dts[0], dt.datetime) else dt.datetime.combine(dts[0], dt.time.min) if hasattr(dts[0], 'date') else dts[0]
                end_dt = dts[-1] if isinstance(dts[-1], dt.datetime) else dt.datetime.combine(dts[-1], dt.time.min) if hasattr(dts[-1], 'date') else dts[-1]

                context = FactorContext(
                    PID="0",
                    PIDList=["0"],
                    DTRuler=dtruler,
                    SectionIDs=ids,
                )

                with Engine() as exec_engine:
                    output, = exec_engine.run(
                        [report_node],
                        context,
                        fwd_data_list=[DTLocalContext(DTs=dts)],
                        init_data_list=[DTInitData(DTRange=(start_dt, end_dt))],
                    )

                return output, factor_names

            await task_manager.update_progress(task_id, 40, "正在运行计算...")

            reports_dict, factor_names = await loop.run_in_executor(None, _sync_generate)

            await task_manager.update_progress(task_id, 80, "正在保存报告...")

            report_id = uuid.uuid4().hex[:12]
            saved_formats = []

            for fname, format_contents in reports_dict.items():
                for fmt, content in format_contents.items():
                    filename = f"{report_id}_{fname}.{fmt}"
                    filepath = os.path.join(get_report_dir(), filename)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                    if fmt not in saved_formats:
                        saved_formats.append(fmt)

            meta = {
                "id": report_id,
                "name": task_name,
                "scenario": scenario,
                "factor_names": factor_names,
                "formats": saved_formats,
                "output_dir": get_report_dir(),
                "registered": False,
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "start_date": start_date,
                "end_date": end_date,
            }
            _save_report_meta(report_id, meta)

            await task_manager.update_progress(task_id, 100, "完成")

            return {
                "report_id": report_id,
                "name": task_name,
                "factor_names": factor_names,
                "formats": saved_formats,
            }

        task_name = req.name or f"{scenario} 报告"
        task_id = await task_manager.submit(name=task_name, coro_or_func=_run())
        return task_id

    # ─── 报告列表 ─────────────────────────────────────────────

    def list_reports(
        self,
        scenario: Optional[str] = None,
        factor_name: Optional[str] = None,
    ) -> List[ReportInfo]:
        """列出已生成的报告，支持筛选"""
        all_meta = _load_all_report_meta()
        results = []
        for meta in all_meta:
            if scenario and meta.get("scenario") != scenario:
                continue
            if factor_name and factor_name not in meta.get("factor_names", []):
                continue
            results.append(ReportInfo(**meta))
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results

    def get_report(self, report_id: str) -> Optional[ReportInfo]:
        """获取单个报告元信息"""
        meta = _load_report_meta(report_id)
        if meta is None:
            return None
        return ReportInfo(**meta)

    def _get_report_dir(self, report_id: str) -> str:
        """获取报告的存储目录（优先使用生成时的目录，回退到当前配置）"""
        meta = _load_report_meta(report_id)
        if meta and meta.get("output_dir"):
            return meta["output_dir"]
        return get_report_dir()

    def get_report_content(self, report_id: str, fmt: str = "html") -> Optional[Dict[str, str]]:
        """获取报告内容。Returns {factor_name: content, ...} 或 None"""
        import glob as _glob
        output_dir = self._get_report_dir(report_id)
        pattern = os.path.join(output_dir, f"{report_id}_*.{fmt}")
        files = _glob.glob(pattern)
        if not files:
            return None

        contents = {}
        for fp in files:
            basename = os.path.basename(fp)
            name_part = basename[len(report_id) + 1: -len(f".{fmt}")]
            with open(fp, "r", encoding="utf-8") as f:
                contents[name_part] = f.read()

        return contents

    def delete_report(self, report_id: str) -> bool:
        """删除报告及其元数据"""
        import glob as _glob
        output_dir = self._get_report_dir(report_id)
        pattern = os.path.join(output_dir, f"{report_id}_*")
        files = _glob.glob(pattern)
        for fp in files:
            try:
                os.remove(fp)
            except OSError:
                pass

        _delete_report_meta(report_id)
        return True

    # ─── 报告注册 ────────────────────────────────────────────

    def register_report(
        self,
        report_id: str,
        factor_qsids: Optional[List[str]] = None,
        bt_qsid: Optional[str] = None,
    ) -> Dict[str, str]:
        """将报告注册到 QSRegistry（同步，在 executor 中运行时不阻塞 loop）"""
        from QSExt.QSRegistry.QSGraphDB import QSGraphDB

        meta = _load_report_meta(report_id)
        if meta is None:
            raise ValueError(f"报告不存在: {report_id}")

        import glob as _glob
        report_ids = {}

        try:
            gdb = QSGraphDB()
            gdb.connect()
        except Exception as e:
            logger.warning(f"无法连接图数据库: {e}")
            raise RuntimeError(f"无法连接图数据库: {e}")

        output_dir = self._get_report_dir(report_id)
        for fmt in meta.get("formats", []):
            pattern = os.path.join(output_dir, f"{report_id}_*.{fmt}")
            for fp in _glob.glob(pattern):
                try:
                    rid = gdb.storeReport(
                        report_path=fp,
                        factor_qsids=factor_qsids or [],
                        bt_qsid=bt_qsid,
                        scenario_name=meta.get("scenario", ""),
                        name=f"{meta.get('name', '')} - {fmt.upper()}",
                    )
                    report_ids[os.path.basename(fp)] = rid
                except Exception as e:
                    logger.warning(f"注册报告 {fp} 失败: {e}")

        meta["registered"] = True
        _save_report_meta(report_id, meta)

        return report_ids


# ─── 因子解析辅助函数 ───────────────────────────────────────

async def _resolve_factor(ref_dict: dict):
    """从 FactorDB 获取 Factor 对象"""
    from app.services.factor_service import factor_service
    import asyncio
    loop = asyncio.get_running_loop()
    db = await factor_service._get_factor_db(ref_dict["conn_id"])

    def _sync():
        ft = db.getTable(ref_dict["table_name"])
        return ft.getFactor(ref_dict["factor_name"])

    return await loop.run_in_executor(None, _sync)


async def _get_dts(ref_dict: dict, start_date: str, end_date: str):
    """获取时点标尺和计算时点"""
    from app.services.factor_service import factor_service
    import asyncio
    loop = asyncio.get_running_loop()
    db = await factor_service._get_factor_db(ref_dict["conn_id"])

    start_dt = dt.datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = dt.datetime.strptime(end_date, "%Y-%m-%d")
    ruler_start = start_dt - dt.timedelta(days=365 * 10 + 1)

    def _sync():
        ft = db.getTable(ref_dict["table_name"])
        dtruler = ft.getDateTime(
            ifactor_name=ref_dict["factor_name"], iid=None,
            start_dt=ruler_start, end_dt=end_dt,
        )
        dts = ft.getDateTime(
            ifactor_name=ref_dict["factor_name"], iid=None,
            start_dt=start_dt, end_dt=end_dt,
        )
        return dtruler, dts

    return await loop.run_in_executor(None, _sync)


async def _get_section_ids(ref_dict: dict):
    """获取截面 ID 列表"""
    from app.services.factor_service import factor_service
    import asyncio
    loop = asyncio.get_running_loop()
    db = await factor_service._get_factor_db(ref_dict["conn_id"])

    def _sync():
        ft = db.getTable(ref_dict["table_name"])
        return ft.getID(ifactor_name=ref_dict["factor_name"], idt=None)

    return await loop.run_in_executor(None, _sync)


def keep_factor_service(svc):
    """确保 factor_service 已设置（延迟绑定）"""
    from app.services.factor_service import factor_service as fs
    if svc._factor_service is None:
        svc._factor_service = fs


# ─── 报告元数据持久化（QSWebConfig.json） ────────────────────

def _load_qs_config() -> dict:
    """加载 QSWebConfig.json"""
    if os.path.exists(QS_CONFIG_PATH):
        try:
            with open(QS_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_qs_config(cfg: dict):
    """保存 QSWebConfig.json"""
    os.makedirs(os.path.dirname(QS_CONFIG_PATH), exist_ok=True)
    with open(QS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _load_all_report_meta() -> List[dict]:
    """加载所有报告元数据"""
    cfg = _load_qs_config()
    reports = cfg.get("reports", {})
    return list(reports.values())


def _load_report_meta(report_id: str) -> Optional[dict]:
    """加载单个报告元数据"""
    cfg = _load_qs_config()
    reports = cfg.get("reports", {})
    return reports.get(report_id)


def _save_report_meta(report_id: str, meta: dict):
    """保存报告元数据"""
    cfg = _load_qs_config()
    if "reports" not in cfg:
        cfg["reports"] = {}
    cfg["reports"][report_id] = meta
    _save_qs_config(cfg)


def _delete_report_meta(report_id: str):
    """删除报告元数据"""
    cfg = _load_qs_config()
    if "reports" in cfg and report_id in cfg["reports"]:
        del cfg["reports"][report_id]
        _save_qs_config(cfg)


# 全局单例
report_service = ReportService()
