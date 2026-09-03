# coding=utf-8
"""
报告生成执行脚本 —— 根据配置文件为因子生成测试报告。

使用方式:
    python run_report.py --profile a_stock_full                     # 使用指定报告配置
    python run_report.py --profile a_stock_full --settings prod     # 指定 settings
    python run_report.py --profile a_stock_full --output-dir ./out  # 输出目录
    python run_report.py --profile a_stock_full --dry-run           # 仅分析不执行

配置说明:
    settings.py 中通过 REPORT_PROFILES 定义报告配置集，每个配置指定:
    - scenario: 场景类型（在 ScenarioRegistry 中注册的名称）
    - section_id_list: 截面名称（引用 SECTION_ID_SOURCES 的 key）
    - config: YAML 报告配置文件路径（空字符串使用内置默认）
    - factors: 目标因子列表 [{db, table, factor}]，factor 支持 "*" 通配符
    - ref_factors: 参考因子 {逻辑名: {db, table, factor}}
"""

import os
import logging
import argparse
import datetime as dt

import pandas as pd

from QuantStudio.Core import setDefaultLogLevel
from QuantStudio.Core import __QS_Logger__ as Logger
from QuantStudio.Core.CalcEngine import Engine
from QuantStudio.Core.ParallelEngine import ParallelEngine
from QuantStudio.Factor.Factor import FactorContext, FactorLocalContext, FactorInitData
from QuantStudio.Factor.FactorCache import FeatherFactorCache
from QuantStudio.Factor.BasicOperator import rename
from QSExt.FactorDef.FactorDefContent import FactorDefSettings, FactorDefInputBuilder
from QSExt.ReportGenerator.scenarios import ScenarioRegistry
from QSExt.Tools.TraceBack import filterWarnings
filterWarnings()


__NOW__ = dt.datetime.now()
__FILE_NAME__ = os.path.splitext(os.path.basename(__file__))[0]


def main(settings_path: str = "settings", profile_name: str = "",
         output_dir: str = "", **cmd_overrides):
    """根据配置生成因子测试报告

    Args:
        settings_path: settings 模块路径
        profile_name: REPORT_PROFILES 中的配置名
        output_dir: 报告输出目录（空字符串使用 settings 中的值）
        **cmd_overrides: 命令行覆盖参数
    """
    # 1. 加载配置
    settings = FactorDefSettings.from_module(settings_path, **cmd_overrides)
    setDefaultLogLevel(getattr(logging, settings.log_level))
    Logger.info(f"配置已加载: {settings_path}")
    Logger.info(f"报告生成流水线启动 — 进程: {os.getpid()}, 时间: {__NOW__}")

    # 2. 选择报告配置
    report_profiles = settings.report_profiles
    if not report_profiles:
        Logger.error("settings 中未配置 REPORT_PROFILES，终止执行")
        return

    if not profile_name:
        profile_name = next(iter(report_profiles))
        Logger.info(f"未指定 --profile，使用第一个配置: {profile_name}")

    if profile_name not in report_profiles:
        Logger.error(f"报告配置 '{profile_name}' 不存在，可用: {list(report_profiles.keys())}")
        return

    profile_cfg = report_profiles[profile_name]
    Logger.info(f"报告配置: {profile_name}")
    Logger.info(f"  场景: {profile_cfg.get('scenario', '未指定')}")

    if settings.dry_run:
        _dry_run(settings, profile_name, profile_cfg)
        return

    # 3. 获取场景类
    scenario_name = profile_cfg.get("scenario", "single_factor")
    try:
        scenario_cls = ScenarioRegistry.get(scenario_name)
    except KeyError as e:
        Logger.error(str(e))
        return

    # 4. 输出目录
    out_dir = output_dir or settings.report_output_dir or "./reports"
    out_dir = os.path.join(out_dir, profile_name)
    os.makedirs(out_dir, exist_ok=True)
    Logger.info(f"输出目录: {out_dir}")

    # 5. 初始化数据库
    with FactorDefInputBuilder(settings) as builder:
        pool = builder._pool

        # 6. 加载参考因子
        ref_factors = _load_ref_factors(pool, profile_cfg.get("ref_factors", {}))
        Logger.info(f"参考因子: {list(ref_factors.keys())}")

        # 7. 加载目标因子（支持 * 通配符）
        target_factors = _load_factors(pool, profile_cfg.get("factors", []))
        if not target_factors:
            Logger.warning("目标因子为空，终止执行")
            return
        Logger.info(f"目标因子: {len(target_factors)} 个")

        # 8. 解析截面
        section_key = profile_cfg.get("section_id_list", "")
        if not section_key:
            Logger.error(f"REPORT_PROFILES['{profile_name}'] 中未配置 section_id_list")
            return

        # 9. 解析时间范围和 ID
        dts, dtruler = builder.resolve_dts()
        if not dts:
            Logger.warning("计算时点为空，终止执行")
            return

        section_ids = builder.resolve_section_ids(section_key)
        ids = section_ids  # 报告的 IDs 与 SectionIDs 相同

        if not ids:
            Logger.warning(f"IDs 为空，终止执行")
            return

        Logger.info(f"时点: {dts[0]} ~ {dts[-1]}, 共 {len(dts)} 个")
        Logger.info(f"截面: {section_key}, IDs: {len(ids)}")

        # 10. 为每个因子生成报告
        report_config = profile_cfg.get("config", "")
        report_nodes = []
        report_factor_names = []

        for factor in target_factors:
            fname = factor._QSArgs.Name
            Logger.info(f"  创建报告节点: {fname}")

            try:
                nodes = scenario_cls.create_nodes(
                    [factor],
                    price=ref_factors.get("price"),
                    mask=ref_factors.get("mask"),
                    cat_data=ref_factors.get("cat_data"),
                    weight=ref_factors.get("weight"),
                    descriptor_ids=section_ids,
                    dtruler=dtruler,
                    config=report_config,
                )
            except Exception as e:
                Logger.warning(f"  跳过 {fname}: create_nodes 失败 — {e}")
                continue

            args = {"Name": f"报告-{fname}"}
            if report_config:
                args["ReportConfig"] = report_config

            report_node = scenario_cls(
                deps=nodes, args=args, factor_names=[fname],
            )
            report_nodes.append(report_node)
            report_factor_names.append(fname)

        if not report_nodes:
            Logger.warning("没有可生成报告的因子")
            return

        Logger.info(f"共 {len(report_nodes)} 个报告节点，开始执行...")

        # 13. 执行
        _execute(settings, report_nodes, dts, dtruler, section_ids)

        # 14. 保存报告
        _save_reports(report_nodes, report_factor_names, out_dir)

    Logger.info("报告生成流水线执行完成")


def _load_ref_factors(pool, factors_cfg: dict) -> dict:
    """从配置加载参考因子

    Args:
        pool: DBPool
        factors_cfg: {逻辑名: {db, table, factor}}

    Returns:
        {逻辑名: Factor}
    """
    result = {}
    for name, cfg in factors_cfg.items():
        db_name = cfg.get("db", "")
        table_name = cfg.get("table", "")
        factor_name = cfg.get("factor", "")
        if not all([db_name, table_name, factor_name]):
            Logger.warning(f"参考因子 '{name}' 配置不完整，跳过")
            continue
        try:
            fdb = pool[db_name]
            ft = fdb.getTable(table_name)
            result[name] = ft.getFactor(factor_name)
            Logger.info(f"  参考因子 '{name}': {db_name}/{table_name}/{factor_name}")
        except Exception as e:
            Logger.warning(f"  加载参考因子 '{name}' 失败: {e}")
    return result


def _load_factors(pool, factors_cfg: list) -> list:
    """从配置加载目标因子列表

    Args:
        pool: DBPool
        factors_cfg: [{db, table, factor}, ...]
            factor 支持三种格式:
              - "*"                                              — 加载该表全部因子
              - ["close", "volume"]                              — 加载指定的多个因子（无额外配置）
              - [{"Name": "close", "Alias": "收盘价", "Order": "升序"}, ...]  — 带配置的因子列表
                Alias: 可选，重命名后的因子名
                Order: 可选，"升序" 表示取负值（默认 "降序" 不处理）

    Returns:
        [Factor, ...]
    """
    result = []
    for cfg in factors_cfg:
        db_name = cfg.get("db", "")
        table_name = cfg.get("table", "")
        factor_spec = cfg.get("factor", "*")
        if not all([db_name, table_name]):
            Logger.warning(f"因子配置不完整（需 db, table），跳过: {cfg}")
            continue
        try:
            fdb = pool[db_name]
            ft = fdb.getTable(table_name)

            # 解析因子列表
            if factor_spec == "*":
                factor_items = [{"Name": fn} for fn in ft.FactorNames]
            else:
                factor_items = [item if isinstance(item, dict) else {"Name": item} for item in factor_spec]

            for item in factor_items:
                fn = item.get("Name", "")
                alias = item.get("Alias", "")
                order = item.get("Order", "降序")
                if not fn:
                    Logger.warning(f"因子配置缺少 Name，跳过: {item}")
                    continue
                f = ft.getFactor(fn)
                # 升序：取负值
                if order == "升序":
                    f = -f
                    Logger.debug(f"  因子 {fn} 设置为升序（取负值）")
                # 重命名
                if alias:
                    f = rename(f, alias)
                    Logger.debug(f"  因子 {fn} 重命名为 {alias}")
                result.append(f)
            Logger.info(f"  加载 {db_name}/{table_name}: {len(factor_items)} 个因子")
        except Exception as e:
            Logger.warning(f"  加载因子失败 {db_name}/{table_name}/{factor_spec}: {e}")
    return result


def _execute(settings, report_nodes, dts, dtruler, section_ids):
    """执行引擎"""
    cache_dir = settings.cache_dir
    if cache_dir:
        task_cache_dir = os.path.join(cache_dir, __FILE_NAME__)
        os.makedirs(task_cache_dir, exist_ok=True)
    else:
        task_cache_dir = None

    workers = settings.workers
    engine_cfg = settings.engine
    engine_type = engine_cfg.get("type", "Engine")
    engine_params = engine_cfg.get("params", {})
    is_parallel = (engine_type == "ParallelEngine")

    # 使用 Engine 时强制单进程
    if not is_parallel:
        workers = 0

    Logger.info(f"开始执行 — engine={engine_type}, workers={workers}, 报告节点数={len(report_nodes)}")

    PIDList = [f"0-{i}" for i in range(int(workers))] if workers > 0 else ["0"]

    cache_args = {
        "DTRuler": dtruler,
        "PIDs": PIDList,
        "CacheDir": task_cache_dir,
        "StartMode": "new",
        "Suffix": ".pkl",
    }

    with FeatherFactorCache(args=cache_args) as Cache:
        with FactorContext(
            Mode=("DEBUG" if settings.debug else "PRD"),
            PIDList=PIDList,
            DTRuler=dtruler,
            SectionIDs=section_ids,
            DataCache=Cache,
        ) as Context:
            fwd_data = [FactorLocalContext(DTs=dts, IDs=[], SectionIDs=section_ids)] * len(report_nodes)
            init_data = [FactorInitData(DTRange=(dts[0], dts[-1]), SectionIDs=section_ids)] * len(report_nodes)

            if is_parallel:
                ExecEngine = ParallelEngine(**engine_params)
            else:
                ExecEngine = Engine(**engine_params)
            with ExecEngine:
                results = ExecEngine.run(
                    report_nodes, Context,
                    fwd_data_list=fwd_data,
                    init_data_list=init_data,
                )

    # 将结果写回节点的 _report_result 属性
    for node, result in zip(report_nodes, results):
        node._report_result = result


def _save_reports(report_nodes, factor_names, output_dir):
    """保存报告到文件"""
    # 格式名到文件后缀的映射
    fmt_suffix = {"html": "html", "markdown": "md"}

    Logger.info(f"保存报告到: {output_dir}")
    for node, fname in zip(report_nodes, factor_names):
        result = getattr(node, "_report_result", {})
        reports = result.get("reports", {})
        if not reports:
            # 兜底：尝试从 ReportKey 获取合并 HTML
            report_key = node._QSArgs.ReportKey
            html = result.get(report_key, "")
            if html:
                filepath = os.path.join(output_dir, f"{fname}.html")
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(html)
                Logger.info(f"  ✓ {fname}.html")
            else:
                Logger.warning(f"  ✗ {fname}: 无报告内容")
            continue

        for factor_name, fmt_dict in reports.items():
            for fmt, content in fmt_dict.items():
                suffix = fmt_suffix.get(fmt, fmt)
                filename = f"{factor_name}.{suffix}"
                filepath = os.path.join(output_dir, filename)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                Logger.info(f"  ✓ {filename}")


def _dry_run(settings, profile_name, profile_cfg):
    """Dry-run 模式：打印配置摘要"""
    Logger.info("=" * 60)
    Logger.info("DRY RUN — 仅分析配置")
    Logger.info("=" * 60)
    Logger.info(f"报告配置: {profile_name}")
    Logger.info(f"  scenario: {profile_cfg.get('scenario', '未指定')}")
    Logger.info(f"  section_id_list: {profile_cfg.get('section_id_list', '未指定')}")
    Logger.info(f"  config: {profile_cfg.get('config', '内置默认')}")

    factors_cfg = profile_cfg.get("factors", [])
    Logger.info(f"  目标因子 ({len(factors_cfg)}):")
    for cfg in factors_cfg:
        Logger.info(f"    {cfg.get('db')}/{cfg.get('table')}/{cfg.get('factor', '*')}")

    ref_cfg = profile_cfg.get("ref_factors", {})
    Logger.info(f"  参考因子 ({len(ref_cfg)}):")
    for name, cfg in ref_cfg.items():
        Logger.info(f"    {name}: {cfg.get('db')}/{cfg.get('table')}/{cfg.get('factor')}")

    Logger.info(f"输出目录: {settings.report_output_dir}")
    Logger.info(f"可用场景: {ScenarioRegistry.list_all()}")

    Logger.info(f"\nSECTION_ID_SOURCES:")
    for key, src in settings.section_id_sources.items():
        Logger.info(f"  {key}: {src.get('type', '?')}")


def _parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="QSExt 报告生成执行脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_report.py --profile a_stock_full
  python run_report.py --profile a_stock_full --settings settings_prod
  python run_report.py --profile a_stock_full --start-dt 2024-01-01 --end-dt 2026-06-30
  python run_report.py --profile a_stock_full --output-dir ./reports
  python run_report.py --profile a_stock_full --dry-run
        """,
    )
    parser.add_argument("--profile", "-p", default="", help="REPORT_PROFILES 中的配置名")
    parser.add_argument("--settings", "-s", default="settings", help="配置模块名 (默认: settings)")
    parser.add_argument("--output-dir", "-o", default="", help="报告输出目录")
    parser.add_argument("--start-dt", default=None, help="回测起始日期 (如 2024-01-01)")
    parser.add_argument("--end-dt", default=None, help="回测截止日期 (如 2026-06-30)")
    parser.add_argument("--lookback", type=int, default=None, help="回溯天数")
    parser.add_argument("--debug", "-d", action="store_true", default=None, help="调试模式")
    parser.add_argument("--dry-run", "-n", action="store_true", default=None, help="仅分析不执行")
    parser.add_argument("--workers", "-w", type=int, default=None, help="并发 worker 数")

    args = parser.parse_args()

    cmd_overrides = {}
    if args.debug is not None:
        cmd_overrides["debug"] = args.debug
    if args.dry_run is not None:
        cmd_overrides["dry_run"] = args.dry_run
    if args.workers is not None:
        cmd_overrides["workers"] = args.workers
    if args.start_dt is not None:
        cmd_overrides["start_dt"] = args.start_dt
    if args.end_dt is not None:
        cmd_overrides["end_dt"] = args.end_dt
    if args.lookback is not None:
        cmd_overrides["lookback"] = args.lookback

    return args, cmd_overrides


if __name__ == "__main__":
    args, cmd_overrides = _parse_args()
    main(
        settings_path=args.settings,
        profile_name=args.profile,
        output_dir=args.output_dir,
        **cmd_overrides,
    )
