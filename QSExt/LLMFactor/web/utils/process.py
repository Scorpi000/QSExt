# -*- coding: utf-8 -*-
"""挖掘进程管理器。

管理挖掘子进程的生命周期：启动、停止、状态查询。
子进程的 stdout/stderr 重定向到日志文件，支持实时查看。
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

__QS_Logger__ = logging.getLogger("QSR.web.process")


@dataclass
class MiningConfig:
    """挖掘配置参数。"""
    direction: str = ""
    mode: str = "skill"
    max_rounds: int = 5
    max_hours: float = 4.0
    workspace_dir: str = ""
    max_turns_hypothesis: int = 50
    max_turns_development: int = 80
    config_path: str = ""
    clear_cache: bool = True

    def to_args(self) -> list[str]:
        """转为命令行参数列表。"""
        args = [
            "--target", self.direction,
            "--mode", self.mode,
            "--max-rounds", str(self.max_rounds),
            "--max-hours", str(self.max_hours),
        ]
        # workspace_dir 已由配置文件的 resolve_workspace_dir() 推导，无需通过命令行传入
        if self.config_path:
            args.extend(["--config", self.config_path])
        args.extend([
            "--max-turns-hypothesis", str(self.max_turns_hypothesis),
            "--max-turns-development", str(self.max_turns_development),
        ])
        args.append("--clear-cache" if self.clear_cache else "--no-clear-cache")
        return args


def _find_workspace(workspace_base: Path) -> Optional[str]:
    """在工作区目录下查找最新的挖掘输出目录。

    所有运行模式统一输出到 FM_* 目录，直接在 workspace_base 下查找。

    Args:
        workspace_base: 工作区根目录

    Returns:
        找到的目录路径，未找到返回 None
    """
    if not workspace_base.exists():
        return None
    fm_dirs = sorted(workspace_base.glob("FM_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if fm_dirs:
        return str(workspace_base)
    return None


class MiningProcessManager:
    """管理挖掘子进程的生命周期。"""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._config: Optional[MiningConfig] = None
        self._workspace_dir: Optional[str] = None
        self._log_file: Optional[object] = None
        self._log_path: Optional[str] = None
        self._start_error: Optional[str] = None
        self._discovery_thread: Optional[threading.Thread] = None

    def start(self, config: MiningConfig) -> str:
        """启动挖掘进程，立即返回。

        子进程的 stdout/stderr 重定向到日志文件。
        工作目录发现在后台线程中进行，通过 workspace_dir 属性轮询结果。

        Args:
            config: 挖掘配置参数

        Returns:
            预期的工作区根目录路径（工作目录可能尚未创建）

        Raises:
            RuntimeError: 已有进程在运行
        """
        if self.is_running:
            raise RuntimeError("已有挖掘进程在运行，请先停止")

        self._start_error = None
        self._workspace_dir = None

        # 构建命令
        module_path = "QSExt.LLMFactor.scripts.run_pipeline"
        cmd = [sys.executable, "-m", module_path] + config.to_args()

        # QSExt 项目根目录
        qs_root = str(Path(__file__).parent.parent.parent.parent.parent)

        # 准备日志文件
        workspace_base = Path(config.workspace_dir) if config.workspace_dir else Path(qs_root) / "QSExt" / "LLMFactor" / "workspace"
        workspace_base.mkdir(parents=True, exist_ok=True)
        self._log_path = str(workspace_base / "mining_process.log")
        self._log_file = open(self._log_path, "w", encoding="utf-8", errors="replace")

        __QS_Logger__.info(f"启动挖掘进程: {' '.join(cmd)}")

        # 启动子进程，stdout/stderr 重定向到日志文件
        self._process = subprocess.Popen(
            cmd,
            stdout=self._log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            cwd=qs_root,
        )
        self._config = config

        # 后台线程等待工作目录创建
        def _discover():
            for _ in range(30):
                time.sleep(1)
                if self._process.poll() is not None:
                    # 进程已退出
                    self._start_error = f"挖掘进程已退出，退出码: {self._process.returncode}"
                    return
                result = _find_workspace(workspace_base)
                if result:
                    self._workspace_dir = result
                    return
            # 超时但进程仍在运行，使用 workspace_base 作为兜底
            self._workspace_dir = str(workspace_base)

        self._discovery_thread = threading.Thread(target=_discover, daemon=True)
        self._discovery_thread.start()

        __QS_Logger__.info(f"挖掘进程已启动, PID={self._process.pid}")
        return str(workspace_base)

    def stop(self, timeout: int = 10):
        """停止挖掘进程。

        Args:
            timeout: 等待进程退出的超时时间（秒）
        """
        if not self.is_running:
            return

        __QS_Logger__.info(f"停止挖掘进程, PID={self._process.pid}")
        try:
            if os.name == "nt":
                os.kill(self._process.pid, signal.CTRL_BREAK_EVENT)
            else:
                os.kill(self._process.pid, signal.SIGTERM)
            self._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            __QS_Logger__.warning(f"进程未在 {timeout}s 内退出，强制终止")
            self._process.kill()
            self._process.wait(timeout=5)
        except Exception as e:
            __QS_Logger__.error(f"停止进程时出错: {e}")
        finally:
            self._process = None
            self._close_log()

    def _close_log(self):
        """关闭日志文件。"""
        log_file = getattr(self, "_log_file", None)
        if log_file and not log_file.closed:
            try:
                log_file.close()
            except Exception:
                pass
        self._log_file = None

    @property
    def is_running(self) -> bool:
        """进程是否正在运行。"""
        return self._process is not None and self._process.poll() is None

    @property
    def pid(self) -> Optional[int]:
        """进程 PID。"""
        return self._process.pid if self._process else None

    @property
    def config(self) -> Optional[MiningConfig]:
        """当前配置。"""
        return self._config

    @property
    def workspace_dir(self) -> Optional[str]:
        """当前工作目录（后台发现，可能为 None）。"""
        return self._workspace_dir

    @property
    def log_path(self) -> Optional[str]:
        """日志文件路径。"""
        return getattr(self, "_log_path", None)

    @property
    def start_error(self) -> Optional[str]:
        """启动错误信息（后台发现线程设置）。"""
        return getattr(self, "_start_error", None)
