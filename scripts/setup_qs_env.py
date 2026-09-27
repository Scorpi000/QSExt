#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""QSExt 环境配置脚本。

在本仓库（QSExt）之外配置一份完整的 QS 开发环境。脚本分两步执行：

1. 先委托 QuantStudio 的同名脚本 `scripts/setup_qs_env.py` 完成 QS 侧配置
   （装依赖、生成 `.mcp.json`、拷 skill、写 `CLAUDE.md` / `CLAUDE.local.md`、
   拷 `docs/` 与 `examples/`、自检）；
2. 再在其上叠加 QSExt 侧内容：

       .mcp.json                     渲染 .mcp.example.json 后追加 qs_registry /
                                     tinysoft_doc / akshare_doc 三个服务
       .claude/skills/*              各 SKILL 的完整拷贝（非链接，可脱离本仓库使用）
       docs/QSExt/                   QSExt 文档（带命名空间，不与 QS 的 docs/ 冲突）
       CLAUDE.local.md               追加「QSExt 扩展」章节与 QSExt 因子库章节
       requirements.txt              追加本仓库依赖

QuantStudio 侧脚本不做任何改动——QSExt 依赖 QuantStudio，反向不成立，因此本脚本是
唯一入口，QuantStudio 单独使用时不感知 QSExt。

QuantStudio 仓库位置按 `--qs-repo` > `QS_REPO` 环境变量 > `QuantStudio.__file__`
派生 的顺序解析，后者最可靠：只要 QuantStudio 可导入，就能定位到其源码根。

配置完成后默认执行 QSExt 侧自检（三个 MCP 服务可启动）。与 QS 侧一致，自检失败只告警
不中断（--no-check 可跳过）。

使用方法:
    # 配置到本仓库自身（默认：--target-dir 为 QS 仓库根）
    python scripts/setup_qs_env.py

    # 配置到指定目录
    python scripts/setup_qs_env.py --target-dir D:/Project/MyProject

    # 指定 QuantStudio 仓库位置（默认由 QuantStudio.__file__ 派生）
    python scripts/setup_qs_env.py --qs-repo D:/Project/QuantStudio

    # 指定 MCP 文档缓存目录（默认 D:/Data/DocPortal，其下按数据源建子目录）
    python scripts/setup_qs_env.py --ext-cache-dir E:/Cache/QSExtDoc

    # 跳过依赖安装（两侧都跳过）
    python scripts/setup_qs_env.py --skip-pip

    # 覆盖已存在的 .mcp.json 条目 / skill / 生成产物
    python scripts/setup_qs_env.py --force

    # 仅预览将要执行的操作，不做任何改动
    python scripts/setup_qs_env.py --dry-run

    # 其余参数（--cache-dir / --factor-db / --risk-db / --pip-index-url 等）原样转发给 QS 脚本：
    python scripts/setup_qs_env.py --factor-db HDF5DB=D:/MyData/HDF5DBConfig.json
    python scripts/setup_qs_env.py --risk-db HDF5FRDB=D:/MyRisk/HDF5FRDBConfig.json

前置要求:
    - 建议使用 QS 环境的解释器执行本脚本（依赖安装的目标即该解释器）。
    - QuantStudio 必须可导入（用于定位其仓库根）；也可用 --qs-repo 显式指定。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# QSExt 侧的 MCP 服务入口
MCP_QS_REGISTRY = REPO_ROOT / "mcp" / "qs_registry.py"
MCP_TINYSOFT_DOC = REPO_ROOT / "mcp" / "tinysoft_doc.py"
MCP_AKSHARE_DOC = REPO_ROOT / "mcp" / "akshare_doc.py"
TEMPLATE_MCP = REPO_ROOT / ".mcp.example.json"

REQUIREMENTS = REPO_ROOT / "requirements.txt"
DOCS_SRC = REPO_ROOT / "docs"

# SKILL 源目录：各自向下查找含 SKILL.md 的子目录（递归拷贝，带 references/）
SKILL_SRC_DIRS = (
    REPO_ROOT / "skills",
    REPO_ROOT / "QSExt" / "DefModule" / "skills",
)

DEFAULT_EXT_CACHE_DIR = "D:/Data/DocPortal"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_API_KEY = "ollama"
DEFAULT_EMBEDDING_MODEL = "bge-m3"
DEFAULT_QS_TOOLS = "all"

# QSExt 侧的因子库类型 -> (默认配置文件名, 章节标题, 内容描述)
# 形状与 QS 脚本的 FACTOR_DB_TYPES 对齐；--factor-db 传入的类型若在此表中，
# 由本脚本消费，不会转发给 QS 脚本（否则 QS 的解析器会因未知类型报错）。
EXT_FACTOR_DB_TYPES = {
    "AKShareDB": ("AKShareDBConfig.json", "AKShareDB（AKShare 数据源）",
                  "AKShare 提供的行情、财务等公开数据"),
    "TinySoftDB": ("TinySoftDBConfig.json", "TinySoftDB（天软数据源）",
                   "天软 TSL 数据库的行情、财务等数据"),
    "DuckDB": ("DuckDBConfig.json", "DuckDB（本地 DuckDB 因子库）",
               "本地 DuckDB 文件 / Parquet 目录，读写均可"),
}

# 可检索表结构的 MCP 服务（渲染章节时附注）
EXT_FACTOR_DB_MCP = {
    "AKShareDB": "akshare_doc",
    "TinySoftDB": "tinysoft_doc",
}

# CLAUDE.local.md 中 QSExt 因子库章节的哨兵，独立于 EXT_SECTION_SENTINEL，
# 这样 --force 替换因子库章节时不会波及 QSExt 章节里的手改内容
EXT_FACTOR_DB_SENTINEL = "<!-- QSEXT:EXT-FACTOR-DB -->"

# 拷贝 docs/ 时排除的目录（与 QS 脚本一致）：data/ 是 notebook 运行产物，
# 检查点与字节码缓存属于编辑/运行残留，均非文档内容。
DOCS_EXCLUDE_DIRS = {"data", ".ipynb_checkpoints", "__pycache__"}

# CLAUDE.local.md 中 QSExt 章节的哨兵，用于 --force 时定位并替换旧章节
EXT_SECTION_SENTINEL = "<!-- QSEXT:EXT-SECTION -->"

_NEO4J_CONFIG_HINT = "DBName / IPAddr / Port / User / Pwd"

# 转发给 QuantStudio 脚本的参数名（值为 None/False 的不转发；--factor-db 可重复）
QS_FORWARD_FLAGS = ("--target-dir", "--cache-dir", "--pip-index-url")
QS_FORWARD_SWITCHES = ("--force", "--dry-run", "--no-check", "--skip-pip", "--skip-skeleton")


def _log(msg: str, *, level: str = "INFO") -> None:
    prefix = {"INFO": "[INFO]", "WARN": "[WARN]", "SKIP": "[SKIP]", "DRY": "[DRY-RUN]"}[level]
    print(f"{prefix} {msg}")


def _resolve_dir(raw: str) -> Path:
    return Path(raw).expanduser().resolve()


def resolve_qs_repo(raw: str | None) -> Path:
    """解析 QuantStudio 仓库根目录。

    优先级：显式参数 > `QS_REPO` 环境变量 > 由 `QuantStudio.__file__` 派生。
    导出即可定位到源码根的前提是 QuantStudio 以源码模式（仓库根在 sys.path 上）
    被导入，这是本框架的常规用法。

    Args:
        raw: `--qs-repo` 传入的路径；为 None 时走环境变量与自动派生

    Returns:
        QuantStudio 仓库根目录（已校验其中存在 scripts/setup_qs_env.py）

    Raises:
        FileNotFoundError: 三种途径均未能定位到有效的 QuantStudio 仓库
    """
    candidates: list[tuple[str, Path]] = []
    if raw:
        candidates.append(("--qs-repo", _resolve_dir(raw)))
    env_raw = os.getenv("QS_REPO")
    if env_raw:
        candidates.append(("QS_REPO 环境变量", _resolve_dir(env_raw)))
    try:
        import QuantStudio
        # QuantStudio/QuantStudio/__init__.py -> 仓库根是 parents[1]
        candidates.append(("QuantStudio.__file__", Path(QuantStudio.__file__).resolve().parents[1]))
    except ImportError:
        _log("无法导入 QuantStudio，跳过自动定位", level="WARN")

    for source, path in candidates:
        if (path / "scripts" / "setup_qs_env.py").is_file():
            _log(f"QuantStudio 仓库（来源：{source}）: {path}")
            return path
        _log(f"{source} 指向的 {path} 下没有 scripts/setup_qs_env.py，尝试下一途径", level="WARN")

    raise FileNotFoundError(
        "无法定位 QuantStudio 仓库。请确认 QuantStudio 可导入，"
        "或用 --qs-repo / QS_REPO 环境变量指定其仓库根目录"
    )


def load_qs_setup(qs_repo: Path):
    """导入 QuantStudio 的 setup_qs_env 模块。

    `qs_repo` 与 `qs_repo/scripts` 都插入 sys.path——前者用于解析 `QuantStudio`
    包（本脚本可能运行在未配置 PYTHONPATH 的环境中），后者用于导入脚本自身。

    Args:
        qs_repo: QuantStudio 仓库根目录

    Returns:
        已导入的 `setup_qs_env` 模块对象
    """
    for path in (qs_repo / "scripts", qs_repo):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
    import setup_qs_env as qs
    return qs


def forward_to_qs(qs, forwarded: list[str]) -> int:
    """把参数转发给 QuantStudio 的 main() 并执行。

    QuantStudio 的 main() 直接解析 sys.argv，因此临时改写 sys.argv 而非重新解析；
    它正常路径下只 return 不 sys.exit，此处仍捕获 SystemExit 以防万一。

    Args:
        qs: 已导入的 QuantStudio setup_qs_env 模块
        forwarded: 组装好的参数列表（不含 argv[0]）

    Returns:
        QuantStudio main() 的返回码
    """
    saved_argv = sys.argv
    try:
        sys.argv = ["setup_qs_env.py", *forwarded]
        try:
            return qs.main() or 0
        except SystemExit as e:
            return e.code if isinstance(e.code, int) else 0
    finally:
        sys.argv = saved_argv


def install_ext_requirements(python: str, dry_run: bool, index_url: str | None) -> None:
    """安装本仓库 requirements.txt 中的依赖。

    QS 与 QSExt 的依赖清单分别安装，不做合并：两份清单独立演进，合并需要读两份
    再改写其一，多一层耦合且无收益。

    Args:
        python: 目标解释器路径
        dry_run: 仅预览不执行
        index_url: pip 镜像源地址
    """
    if not REQUIREMENTS.exists():
        _log(f"未找到依赖清单: {REQUIREMENTS}，跳过", level="SKIP")
        return

    cmd = [python, "-m", "pip", "install", "-r", str(REQUIREMENTS)]
    if index_url:
        cmd += ["-i", index_url]

    if dry_run:
        _log(f"将执行: {' '.join(cmd)}", level="DRY")
        return

    _log(f"安装 QSExt 依赖: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def _mcp_pythonpath(qs_repo: Path) -> str:
    """QSExt 的 MCP 服务需要同时看到 QuantStudio 与 QSExt 两个包。"""
    return os.pathsep.join([qs_repo.as_posix(), REPO_ROOT.as_posix()])


def render_mcp_template(
    qs_repo: Path,
    target_dir: Path,
    ext_cache_dir: Path,
    ollama_base_url: str,
    embedding_model: str,
) -> dict:
    """渲染 .mcp.example.json，返回 QSExt 的三个 MCP 服务条目。

    与 QS 侧的做法一致：占位符全部替换后校验 JSON 合法性与无残留占位符。
    替换值中的反斜杠需转义，否则 Windows 路径会破坏 JSON 字符串。

    Args:
        qs_repo: QuantStudio 仓库根目录
        target_dir: 配置目标目录（作为 MCP 服务的工作目录）
        ext_cache_dir: MCP 文档缓存根目录（其下按数据源建子目录）
        ollama_base_url: Ollama 服务地址（qs_registry 语义检索用）
        embedding_model: 嵌入模型名（qs_registry 语义检索用）

    Returns:
        服务名 -> 服务配置 的字典

    Raises:
        FileNotFoundError: 未找到模板文件
        ValueError: 模板中存在未替换的占位符
    """
    if not TEMPLATE_MCP.is_file():
        raise FileNotFoundError(f"未找到 MCP 模板: {TEMPLATE_MCP}")

    text = TEMPLATE_MCP.read_text(encoding="utf-8")
    replacements = {
        "{{PYTHON}}": sys.executable,
        "{{PROJECT}}": target_dir.as_posix(),
        "{{PYTHONPATH}}": _mcp_pythonpath(qs_repo),
        "{{QS_REGISTRY_PY}}": MCP_QS_REGISTRY.as_posix(),
        "{{TINYSOFT_DOC_PY}}": MCP_TINYSOFT_DOC.as_posix(),
        "{{AKSHARE_DOC_PY}}": MCP_AKSHARE_DOC.as_posix(),
        "{{TINYSOFT_CACHE_DIR}}": (ext_cache_dir / "TinySoftDoc").as_posix(),
        "{{AKSHARE_CACHE_DIR}}": (ext_cache_dir / "AKShareDoc").as_posix(),
        "{{OLLAMA_BASE_URL}}": ollama_base_url,
        "{{OLLAMA_API_KEY}}": DEFAULT_OLLAMA_API_KEY,
        "{{EMBEDDING_MODEL}}": embedding_model,
        "{{QS_TOOLS}}": DEFAULT_QS_TOOLS,
    }
    for key, value in replacements.items():
        text = text.replace(key, value.replace("\\", "\\\\"))

    # 校验替换后仍是合法 JSON；残留占位符会让解析失败或漏改字段
    if "{{" in text:
        leftover = text[text.index("{{") : text.index("{{") + 40]
        raise ValueError(f"模板中存在未替换的占位符: {leftover}")

    return json.loads(text)["mcpServers"]


def merge_mcp_config(
    target_dir: Path,
    qs_repo: Path,
    ext_cache_dir: Path,
    ollama_base_url: str,
    embedding_model: str,
    force: bool,
    dry_run: bool,
) -> None:
    """把 QSExt 的 MCP 服务合并进目标目录的 .mcp.json。

    QS 脚本已写出自己的 .mcp.json（可能被 --skip-* 跳过），这里是读回后追加——
    已有条目一律保留，绝不覆盖 QS 的服务。单个 QSExt 服务已存在时，无 --force
    跳过该条目，有 --force 覆盖该条目。

    Args:
        target_dir: 配置目标目录
        qs_repo: QuantStudio 仓库根目录
        ext_cache_dir: MCP 文档缓存根目录
        ollama_base_url: Ollama 服务地址
        embedding_model: 嵌入模型名
        force: 是否覆盖已存在的同名单个服务条目
        dry_run: 仅预览不落盘
    """
    target = target_dir / ".mcp.json"
    entries = render_mcp_template(qs_repo, target_dir, ext_cache_dir, ollama_base_url, embedding_model)

    if target.is_file():
        try:
            config = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            _log(f"{target} 解析失败（{e}），跳过 QSExt 服务合并", level="WARN")
            return
    else:
        _log(f"未找到 {target}（可能被跳过），QSExt 将仅写入自身服务", level="WARN")
        config = {"mcpServers": {}}

    servers = config.setdefault("mcpServers", {})
    added, skipped = [], []
    for name, entry in entries.items():
        if name in servers and not force:
            skipped.append(name)
            continue
        servers[name] = entry
        added.append(name)

    for name in skipped:
        _log(f"{target} 中已存在服务 {name}，跳过（--force 可覆盖）", level="SKIP")
    if not added:
        return

    text = json.dumps(config, indent=2, ensure_ascii=False)
    if dry_run:
        _log(f"将写入 {target} 并追加服务: {', '.join(added)}", level="DRY")
        return

    target.write_text(text, encoding="utf-8")
    _log(f"已写入 {target}，追加服务: {', '.join(added)}")


def copy_ext_skills(target_dir: Path, force: bool, dry_run: bool) -> None:
    """把本仓库的 SKILL 拷到目标目录的 .claude/skills/。

    递归拷贝以带走 references/ 子树。源目录逐个扫描，含 SKILL.md 的子目录才算
    一个 SKILL——这样 QSExt/DefModule/skills 下的非 SKILL 文件不会被误拷。

    Args:
        target_dir: 配置目标目录
        force: 覆盖已存在的同名 SKILL
        dry_run: 仅预览不落盘
    """
    sources: list[Path] = []
    for src_dir in SKILL_SRC_DIRS:
        if not src_dir.is_dir():
            _log(f"未找到 skill 源目录 {src_dir}，跳过", level="SKIP")
            continue
        sources += sorted(p for p in src_dir.iterdir() if (p / "SKILL.md").is_file())

    if not sources:
        _log("没有找到含 SKILL.md 的目录", level="WARN")
        return

    dst_root = target_dir / ".claude" / "skills"
    if not dry_run:
        dst_root.mkdir(parents=True, exist_ok=True)

    for src in sources:
        dst = dst_root / src.name

        if dst.exists():
            if not force:
                _log(f"{dst} 已存在，跳过（--force 可覆盖）", level="SKIP")
                continue
            if dry_run:
                _log(f"将删除后重新拷贝: {dst}", level="DRY")
            else:
                shutil.rmtree(dst)

        if dry_run:
            _log(f"将拷贝 Skill: {src.name} -> {dst}", level="DRY")
            continue

        shutil.copytree(src, dst)
        _log(f"已拷贝 Skill: {src.name} -> {dst}")


def copy_ext_docs(target_dir: Path, force: bool, dry_run: bool) -> None:
    """把本仓库 docs/ 拷到目标目录的 docs/QSExt/。

    必须带 QSExt 命名空间：目标目录的 docs/ 已被 QS 脚本占据，直接平铺会冲突。

    Args:
        target_dir: 配置目标目录
        force: 覆盖已存在的 docs/QSExt
        dry_run: 仅预览不落盘
    """
    if not DOCS_SRC.is_dir():
        _log(f"未找到文档目录 {DOCS_SRC}，跳过", level="SKIP")
        return

    dst = target_dir / "docs" / "QSExt"
    if dst.exists() and not force:
        _log(f"{dst} 已存在，跳过（--force 可覆盖）", level="SKIP")
        return

    def ignore(directory, names):
        return [n for n in names if n in DOCS_EXCLUDE_DIRS]

    count = sum(1 for p in DOCS_SRC.rglob("*") if p.is_file() and not (DOCS_EXCLUDE_DIRS & set(p.parts)))
    if dry_run:
        _log(f"将拷贝 {count} 个文档文件到 {dst}", level="DRY")
        return

    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(DOCS_SRC, dst, ignore=ignore)
    _log(f"已拷贝 {count} 个文档文件到 {dst}")


def render_ext_section(qs_repo: Path, ext_cache_dir: Path) -> str:
    """渲染 CLAUDE.local.md 的「QSExt 扩展」章节。

    不硬编码 Neo4j 库名——实际库名以 ~/QuantStudioConfig/Neo4jDBConfig.json 为准。

    Args:
        qs_repo: QuantStudio 仓库根目录
        ext_cache_dir: MCP 文档缓存根目录

    Returns:
        章节文本（含开头哨兵，结尾带换行）
    """
    return f"""\
{EXT_SECTION_SENTINEL}
# QSExt 扩展

QSExt 是 QuantStudio 的扩展包，提供额外的因子库适配器、策略、报告生成与 MCP 服务。
本环境已同时配置 QuantStudio 与 QSExt，QSExt 通过 `from QuantStudio.xxx import yyy`
引用核心库。

* QSExt 项目地址：{REPO_ROOT.as_posix()}
* QuantStudio 项目地址：{qs_repo.as_posix()}
* 使用 QSExt 时，PYTHONPATH 需同时包含上述两个仓库根

## 可用的 MCP 服务（QSExt 提供）

| 服务 | 用途 |
|------|------|
| `qs_registry` | 检索已注册的因子、回测、风险表、优化器及其依赖关系（Neo4j 图数据库） |
| `tinysoft_doc` | 检索天软 TSDN 文档站的函数与数据表说明 |
| `akshare_doc` | 检索 AKShare 数据接口的参数与调用示例 |

* `qs_registry` 需要 `~/QuantStudioConfig/Neo4jDBConfig.json`（连接信息以该文件为准）
* `tinysoft_doc` / `akshare_doc` 的本地索引缓存在 {ext_cache_dir.as_posix()}
"""


def append_ext_claude_local(
    target_dir: Path, qs_repo: Path, ext_cache_dir: Path, force: bool, dry_run: bool
) -> None:
    """在目标目录的 CLAUDE.local.md 后追加「QSExt 扩展」章节。

    QS 脚本已写好该文件（本地约定 + 可用因子库），此处只做追加。章节用哨兵界定：
    已存在且无 --force 时跳过，有 --force 时替换旧章节，避免重复堆叠。

    Args:
        target_dir: 配置目标目录
        qs_repo: QuantStudio 仓库根目录
        ext_cache_dir: MCP 文档缓存根目录
        force: 覆盖已存在的 QSExt 章节
        dry_run: 仅预览不落盘
    """
    target = target_dir / "CLAUDE.local.md"
    section = render_ext_section(qs_repo, ext_cache_dir)

    if target.is_file():
        content = target.read_text(encoding="utf-8")
    else:
        _log(f"未找到 {target}（可能被跳过），将单独生成", level="WARN")
        content = ""

    if EXT_SECTION_SENTINEL in content:
        if not force:
            _log(f"{target} 中已有 QSExt 章节，跳过（--force 可覆盖）", level="SKIP")
            return
        content = content[: content.index(EXT_SECTION_SENTINEL)].rstrip("\n") + "\n"
        action = "替换"
    else:
        action = "追加"

    rendered = (content.rstrip("\n") + "\n\n" + section) if content else section

    if dry_run:
        _log(f"将{action} QSExt 章节到 {target}", level="DRY")
        print(rendered)
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    _log(f"已{action} QSExt 章节到 {target}")


def _ext_secret_fields(db_type: str) -> set:
    """返回该 QSExt 因子库的敏感字段名集合。

    与 QS 脚本的 _secret_fields 同款逻辑：优先读字段声明中
    json_schema_extra={"secret": True} 的标记。QSExt 各库已补上该标记，
    因此这里能直接过滤掉凭据，无需按名称兜底。

    Args:
        db_type: 因子库类型短名

    Returns:
        敏感字段名集合；无法导入该库时返回空集
    """
    import importlib

    try:
        module = importlib.import_module(f"QSExt.Factor.{db_type}")
    except ImportError as e:
        _log(f"无法导入 QSExt.Factor.{db_type}（{e}），跳过敏感字段过滤", level="WARN")
        return set()

    cls = getattr(module, db_type, None)
    arg_cls = getattr(cls, "__QS_ArgClass__", None)
    fields = getattr(arg_cls, "model_fields", None)
    if not fields:
        return set()
    return {
        name for name, field in fields.items()
        if (getattr(field, "json_schema_extra", None) or {}).get("secret")
    }


def _ext_ctor(db_type: str, config_path: Path) -> str:
    """构造该因子库的调用表达式。

    配置文件不是默认路径时必须显式传入，否则对象会按默认配置创建，连到别的库。
    """
    default = Path(os.path.expanduser("~")) / "QuantStudioConfig" / EXT_FACTOR_DB_TYPES[db_type][0]
    if config_path.resolve() == default.resolve():
        return f"{db_type}()"
    return f"{db_type}(config_file=r'{config_path}')"


def _ext_db_example(db_type: str, config_path: Path) -> str:
    """返回该 QSExt 因子库在指定配置文件下的读取示例代码块。"""
    ctor = _ext_ctor(db_type, config_path)
    if db_type == "AKShareDB":
        return f'''\
```python
import datetime as dt
from QSExt.Factor.AKShareDB import AKShareDB

db = {ctor}
db.connect()
db.TableNames                          # 可用表名列表
db.getTradeDay(start_date=dt.datetime(2024, 6, 24), end_date=dt.datetime(2024, 6, 28))
db.getStockID(exchange=("SSE", "SZSE"), date=dt.datetime(2024, 6, 28))   # 证券 ID

tbl = db.getTable("实时行情数据-东财")
tbl.FactorNames                        # 该表的因子名
tbl.readData(["最新价", "涨跌幅"], ids, dts)   # -> Panel（因子 x 时序 x 证券）
```
'''
    if db_type == "TinySoftDB":
        return f'''\
```python
import datetime as dt
from QSExt.Factor.TinySoftDB import TinySoftDB

db = {ctor}
db.connect()
db.TableNames                          # 可用表名列表
db.getTradeDay(start_date=dt.datetime(2024, 6, 24), end_date=dt.datetime(2024, 6, 28))
db.getStockID(date=dt.datetime(2024, 6, 28))    # 证券 ID

tbl = db.getTable("A股基本信息")
tbl.FactorNames                        # 该表的因子名
tbl.readData(factor_names, ids, dts)   # -> Panel（因子 x 时序 x 证券）
```
'''
    return f'''\
```python
from QSExt.Factor.DuckDB import DuckDB

db = {ctor}
db.connect()
db.TableNames                          # 可用表名列表

tbl = db.getTable("<表名>")
tbl.FactorNames                        # 该表的因子名
tbl.readData(factor_names, ids, dts)   # -> Panel（因子 x 时序 x 证券）
```
'''


def render_ext_factor_db_sections(ext_specs: list[tuple[str, Path]]) -> str:
    """渲染 CLAUDE.local.md 的「可用因子库（QSExt）」章节。

    只产出 `##` 子节，不含 `# 可用因子库` 标题——后者由 QS 脚本写出，重复会破结构。
    无可用 spec 时返回空串（不产出哨兵，不占位）。

    Args:
        ext_specs: QSExt 侧的 (类型, 配置文件路径) 列表

    Returns:
        章节文本（含开头哨兵，结尾带换行）；无内容时返回空串
    """
    if not ext_specs:
        return ""

    blocks = [EXT_FACTOR_DB_SENTINEL, "# 可用因子库（QSExt 扩展）"]
    for db_type, config_path in ext_specs:
        _, title, description = EXT_FACTOR_DB_TYPES[db_type]
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            _log(f"解析 {db_type} 配置失败 {config_path}: {e}，跳过该节", level="WARN")
            continue

        secret = _ext_secret_fields(db_type)
        info = {k: v for k, v in config.items() if k not in secret}

        blocks.append(f"\n## {title}\n")
        blocks.append(f"- 配置文件：{config_path}")
        if db_type == "TinySoftDB":
            blocks.append(f"- 服务器：{info.get('IPAddr', '')}:{info.get('Port', '')}")
        elif db_type == "DuckDB":
            if info.get("DBFile"):
                blocks.append(f"- 数据库文件：{info.get('DBFile')}")
            if info.get("ParquetDir"):
                blocks.append(f"- Parquet 目录：{info.get('ParquetDir')}")
        blocks.append(f"- 内容：{description}")
        if db_type in EXT_FACTOR_DB_MCP:
            blocks.append(f"- 表结构说明使用 `{EXT_FACTOR_DB_MCP[db_type]}` MCP 工具检索")
        blocks.append("\n" + _ext_db_example(db_type, config_path))

    if len(blocks) <= 2:
        return ""
    return "\n".join(blocks) + "\n"


def append_ext_factor_db(target_dir: Path, ext_specs: list[tuple[str, Path]], force: bool, dry_run: bool) -> None:
    """在目标目录的 CLAUDE.local.md 后追加 QSExt 因子库章节。

    用独立的哨兵界定，与「QSExt 扩展」章节互不干扰：--force 只替换本块，
    不会波及 QSExt 章节里的手改内容。

    Args:
        target_dir: 配置目标目录
        ext_specs: QSExt 侧的 (类型, 配置文件路径) 列表
        force: 覆盖已存在的因子库章节
        dry_run: 仅预览不落盘
    """
    section = render_ext_factor_db_sections(ext_specs)
    if not section:
        _log("没有可登记的 QSExt 因子库（无显式或默认配置），跳过", level="SKIP")
        return

    target = target_dir / "CLAUDE.local.md"
    if target.is_file():
        content = target.read_text(encoding="utf-8")
    else:
        _log(f"未找到 {target}（可能被跳过），将单独生成", level="WARN")
        content = ""

    if EXT_FACTOR_DB_SENTINEL in content:
        if not force:
            _log(f"{target} 中已有因子库章节，跳过（--force 可覆盖）", level="SKIP")
            return
        content = content[: content.index(EXT_FACTOR_DB_SENTINEL)].rstrip("\n") + "\n"
        action = "替换"
    else:
        action = "追加"

    rendered = (content.rstrip("\n") + "\n\n" + section) if content else section

    if dry_run:
        _log(f"将{action} QSExt 因子库章节到 {target}", level="DRY")
        print(rendered)
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    _log(f"已{action} QSExt 因子库章节到 {target}")


def check_ext_config(dry_run: bool) -> None:
    """检查 QSExt MCP 服务所需的配置文件，缺失时给出建立提示。

    Args:
        dry_run: 仅预览不执行
    """
    config_path = Path(os.path.expanduser("~")) / "QuantStudioConfig" / "Neo4jDBConfig.json"
    if config_path.is_file():
        _log(f"{config_path} 已就位", level="SKIP")
        return

    if dry_run:
        _log(f"将检查配置 {config_path}（当前缺失）", level="DRY")
        return

    _log(f"缺少 qs_registry 所需的 Neo4j 配置：", level="WARN")
    print(f"        {config_path}")
    print(f"            (需要字段：{_NEO4J_CONFIG_HINT})")
    print("        连接信息请向数据提供方索取后手动创建，脚本不会代写。")


def _start_mcp_server(server: dict, target_dir: Path) -> bool:
    """对单个 MCP 服务做一次 JSON-RPC initialize 握手。

    Args:
        server: .mcp.json 中的单个服务配置
        target_dir: 目标目录（作为兜底 cwd）

    Returns:
        握手成功返回 True
    """
    request = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "setup-check", "version": "1"}},
    })
    env = dict(os.environ, **server.get("env", {}))
    try:
        proc = subprocess.run(
            [server["command"], *server["args"]], input=request + "\n", capture_output=True,
            text=True, cwd=server.get("cwd", str(target_dir)), env=env, timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        _log(f"MCP 服务启动失败: {e}", level="WARN")
        return False
    return '"result"' in proc.stdout


def run_ext_self_check(target_dir: Path) -> None:
    """QSExt 侧自检：三个 MCP 服务能否启动。

    任一失败只告警不中断——Neo4j / Ollama 不可达是常见状态，不应阻断环境配置。

    Args:
        target_dir: 配置目标目录
    """
    print("-" * 60)
    _log("开始 QSExt 侧自检")

    mcp_config = target_dir / ".mcp.json"
    if not mcp_config.is_file():
        _log("未找到 .mcp.json，跳过 QSExt MCP 检查", level="SKIP")
        return

    try:
        servers = json.loads(mcp_config.read_text(encoding="utf-8"))["mcpServers"]
    except (KeyError, json.JSONDecodeError) as e:
        _log(f".mcp.json 解析失败: {e}", level="WARN")
        return

    for name in ("qs_registry", "tinysoft_doc", "akshare_doc"):
        server = servers.get(name)
        if server is None:
            _log(f".mcp.json 中未配置 {name}，跳过", level="SKIP")
            continue
        if _start_mcp_server(server, target_dir):
            _log(f"MCP 服务 ({name}) 启动正常")
        else:
            _log(f"MCP 服务 ({name}) 无有效响应", level="WARN")


def split_factor_db_specs(qs, raw_specs: list[str] | None) -> tuple[list[tuple[str, Path]], list[tuple[str, Path]]]:
    """把 --factor-db 拆成 QuantStudio 侧与 QSExt 侧两组。

    非 QSExt 类型的 spec 原样交给 QS 脚本，QSExt 类型由本脚本消费——QS 的
    resolve_factor_db_specs 遇到未知类型会直接抛错，必须先在这里拦下。

    与 QS 侧一致，每个 QSExt 类型在解析完显式传入的 spec 后，再查一次默认配置
    ~/QuantStudioConfig/<TYPE>Config.json，存在则作为兜底追加（同类型可出现多节）。

    Args:
        qs: 已导入的 QuantStudio setup_qs_env 模块（取它的类型注册表）
        raw_specs: --factor-db 传入的原始字符串列表

    Returns:
        (QS 侧 spec 列表, QSExt 侧 spec 列表)，元素均为 (类型, 配置文件路径)

    Raises:
        ValueError: 类型未知，或不是 TYPE=PATH 形式
    """
    qs_specs: list[tuple[str, Path]] = []
    ext_specs: list[tuple[str, Path]] = []

    for raw in raw_specs or []:
        if "=" not in raw:
            raise ValueError(f"--factor-db 需要 TYPE=PATH 形式，收到: {raw}")
        db_type, _, path = raw.partition("=")
        db_type = db_type.strip()

        # 先判 QSExt：将来若与 QS 的类型重名，由 QSExt 胜出，且不转发给 QS
        if db_type in EXT_FACTOR_DB_TYPES:
            config_path = _resolve_dir(path.strip())
            if not config_path.is_file():
                _log(f"未找到 {db_type} 的配置 {config_path}，跳过", level="SKIP")
                continue
            ext_specs.append((db_type, config_path))
        elif db_type in qs.FACTOR_DB_TYPES:
            config_path = _resolve_dir(path.strip())
            if not config_path.is_file():
                _log(f"未找到 {db_type} 的配置 {config_path}，跳过", level="SKIP")
                continue
            qs_specs.append((db_type, config_path))
        else:
            raise ValueError(
                f"未知因子库类型 '{db_type}'。"
                f"QuantStudio 已知: {', '.join(sorted(qs.FACTOR_DB_TYPES))}；"
                f"QSExt 已知: {', '.join(sorted(EXT_FACTOR_DB_TYPES))}"
            )

    config_dir = Path(os.path.expanduser("~")) / "QuantStudioConfig"
    for db_type, (filename, _, _) in EXT_FACTOR_DB_TYPES.items():
        default = config_dir / filename
        if default.is_file():
            ext_specs.append((db_type, default))
        else:
            _log(f"未找到 {db_type} 的默认配置 {default}，跳过", level="SKIP")
    return qs_specs, ext_specs


def check_ext_factor_db(qs_repo: Path, ext_specs: list[tuple[str, Path]]) -> None:
    """QSExt 因子库可用性探测：逐个构造连接并报告表数量。

    与 run_ext_self_check（MCP 启动）并列，二者互不相干。只对已登记的 spec 探测，
    与 CLAUDE.local.md 的内容保持一致。任一失败只告警不中断——网络或凭据不可用是
    常见状态，不应阻断环境配置。

    QSExt 没有聚合的 Factor.api，需按 `QSExt.Factor.<类型>` 逐模块导入。

    Args:
        qs_repo: QuantStudio 仓库根目录
        ext_specs: QSExt 侧的 (类型, 配置文件路径) 列表
    """
    if not ext_specs:
        return

    print("-" * 60)
    _log("开始 QSExt 因子库可用性探测")

    for db_type, config_path in ext_specs:
        probe = (
            "import sys; sys.path.insert(0, %r); sys.path.insert(0, %r); "
            "from QSExt.Factor.%s import %s as _Cls; "
            "db = _Cls(config_file=%r); db.connect(); print(len(db.TableNames))"
            % (qs_repo.as_posix(), REPO_ROOT.as_posix(), db_type, db_type, config_path.as_posix())
        )
        try:
            result = subprocess.run(
                [sys.executable, "-c", probe], capture_output=True, text=True, timeout=180
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            _log(f"{db_type} 探测失败: {e}", level="WARN")
            continue

        if result.returncode == 0:
            _log(f"{db_type} 连接成功，{result.stdout.strip().splitlines()[-1]} 张表")
        else:
            last = result.stderr.strip().splitlines()[-1] if result.stderr else "未知错误"
            _log(f"{db_type} 连接失败（{config_path}）: {last}", level="WARN")


def build_qs_argv(args: argparse.Namespace, qs_specs: list[tuple[str, Path]]) -> list[str]:
    """把 QSExt 侧的参数翻译成 QuantStudio 脚本的参数列表。

    Args:
        args: 本脚本解析出的参数
        qs_specs: 属于 QuantStudio 的因子库 spec（QSExt 类型已被拦截）

    Returns:
        转发给 QS 脚本的参数列表（不含 argv[0]）
    """
    argv: list[str] = []
    for flag in QS_FORWARD_FLAGS:
        value = getattr(args, flag.lstrip("-").replace("-", "_"), None)
        if value:
            argv += [flag, str(value)]
    for flag in QS_FORWARD_SWITCHES:
        if getattr(args, flag.lstrip("-").replace("-", "_"), False):
            argv.append(flag)
    for db_type, config_path in qs_specs:
        argv += ["--factor-db", f"{db_type}={config_path}"]
    # 风险库全部由 QuantStudio 处理（QSExt 暂无风险库实现），原样转发
    for spec in args.risk_db or []:
        argv += ["--risk-db", spec]
    return argv


def main() -> int:
    parser = argparse.ArgumentParser(
        description="配置一份同时包含 QuantStudio 与 QSExt 的开发环境"
                    "（先委托 QuantStudio 的 setup_qs_env.py，再叠加 QSExt 内容）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target-dir", default=None, help="配置写入的目标目录；未指定时由 QS 脚本决定")
    parser.add_argument("--qs-repo", default=None, help="QuantStudio 仓库根目录；未指定时自动定位")
    parser.add_argument("--ext-cache-dir", default=DEFAULT_EXT_CACHE_DIR,
                        help=f"QSExt MCP 文档缓存根目录 (默认: {DEFAULT_EXT_CACHE_DIR})")
    parser.add_argument("--ollama-base-url", default=DEFAULT_OLLAMA_BASE_URL,
                        help=f"Ollama 服务地址 (默认: {DEFAULT_OLLAMA_BASE_URL})")
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL,
                        help=f"嵌入模型名 (默认: {DEFAULT_EMBEDDING_MODEL})")
    parser.add_argument("--skip-pip", action="store_true", help="跳过依赖安装（QuantStudio 与 QSExt 两侧）")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的 .mcp.json 条目 / skill / 生成产物")
    parser.add_argument("--dry-run", action="store_true", help="仅预览操作，不做任何改动")
    parser.add_argument("--no-check", action="store_true", help="配置完成后跳过自检")
    # 以下参数仅用于转发给 QS 脚本
    parser.add_argument("--cache-dir", default=None, help="聚源文档缓存目录（转发给 QS 脚本）")
    parser.add_argument("--pip-index-url", default=None, help="pip 镜像源地址（转发给 QS 脚本）")
    parser.add_argument("--skip-skeleton", action="store_true", help="不生成 Python 工程骨架（转发给 QS 脚本）")
    parser.add_argument("--factor-db", action="append", default=None, metavar="TYPE=PATH",
                        help="因子库配置，可重复（转发给 QS 脚本）")
    parser.add_argument("--risk-db", action="append", default=None, metavar="TYPE=PATH",
                        help="风险库配置，可重复（转发给 QS 脚本）")
    args = parser.parse_args()

    python = sys.executable
    if not python:
        _log("无法获取当前解释器路径 (sys.executable 为空)", level="WARN")
        return 1
    # 不能对解释器路径做 resolve()：venv 的 bin/python 是指向基础解释器的符号链接，
    # 解析后会丢失虚拟环境身份，导致依赖装到基础解释器里
    python = str(Path(python).absolute())

    ext_cache_dir = _resolve_dir(args.ext_cache_dir)

    print(f"QSExt 仓库根目录: {REPO_ROOT}")
    print(f"QSExt MCP 缓存目录: {ext_cache_dir}")
    print(f"Python 解释器: {python}")
    print("-" * 60)

    try:
        qs_repo = resolve_qs_repo(args.qs_repo)
        qs = load_qs_setup(qs_repo)
    except (FileNotFoundError, ImportError) as e:
        _log(str(e), level="WARN")
        return 1

    # 目标目录：以 QS 脚本的最终决定为准，两边保持一致
    target_dir = _resolve_dir(args.target_dir) if args.target_dir else qs.REPO_ROOT
    if args.target_dir and not target_dir.is_dir():
        _log(f"--target-dir 指定的目录不存在: {target_dir}", level="WARN")
        return 1
    print(f"配置目标目录: {target_dir}")

    # 拦截不属于 QuantStudio 的因子库类型：QS 的解析器遇到未知类型会直接报错
    try:
        qs_specs, ext_specs = split_factor_db_specs(qs, args.factor_db)
    except ValueError as e:
        _log(str(e), level="WARN")
        return 1

    print("-" * 60)
    print(">>> 步骤 1/2：委托 QuantStudio 配置 QS 侧内容")
    rc = forward_to_qs(qs, build_qs_argv(args, qs_specs))
    if rc != 0:
        _log(f"QuantStudio 侧配置失败（返回码 {rc}），中止 QSExt 侧配置", level="WARN")
        return rc

    print("-" * 60)
    print(">>> 步骤 2/2：叠加 QSExt 侧内容")

    if args.skip_pip:
        _log("按参数跳过依赖安装（QuantStudio 与 QSExt）", level="SKIP")
    else:
        install_ext_requirements(python, args.dry_run, args.pip_index_url)

    merge_mcp_config(target_dir, qs_repo, ext_cache_dir, args.ollama_base_url,
                     args.embedding_model, args.force, args.dry_run)
    copy_ext_skills(target_dir, args.force, args.dry_run)
    copy_ext_docs(target_dir, args.force, args.dry_run)
    append_ext_claude_local(target_dir, qs_repo, ext_cache_dir, args.force, args.dry_run)
    append_ext_factor_db(target_dir, ext_specs, args.force, args.dry_run)
    check_ext_config(args.dry_run)

    print("-" * 60)
    if args.dry_run:
        print("配置完成。（dry-run，未做任何改动）")
    elif args.no_check:
        print("配置完成。（已跳过自检）")
    else:
        print("配置完成。")
        run_ext_self_check(target_dir)
        check_ext_factor_db(qs_repo, ext_specs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
