# Copyright 2026 Shuo Huang
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import logging
import sys
import time
from pathlib import Path
from ..config import GEConfig

_sys_logger: logging.Logger = None
_heartbeat_logger: logging.Logger = None
_package_logger: logging.Logger = None


class UnifiedFormatter(logging.Formatter):
    def __init__(self, component: str, fmt: str = None):
        super().__init__(fmt)
        self._component = component

    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        s = time.strftime("%Y-%m-%dT%H:%M:%S", ct)
        return f"{s}.{int(record.msecs):03d}"

    def format(self, record):
        record.component = self._component
        return super().format(record)


_LOG_FMT = "%(asctime)s [%(component)s] [%(levelname)s] %(message)s"


def setup_logging(cfg: GEConfig):
    log_dir = Path(cfg.log_dir)
    sys_dir = log_dir / "sys"
    tasks_dir = log_dir / "tasks"
    sys_dir.mkdir(parents=True, exist_ok=True)
    tasks_dir.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, cfg.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(UnifiedFormatter("GE", _LOG_FMT))
    root.addHandler(console)

    global _sys_logger, _heartbeat_logger, _package_logger

    _sys_logger = logging.getLogger("ge.sys")
    _sys_logger.setLevel(level)
    sys_handler = logging.FileHandler(sys_dir / "ge.log", encoding="utf-8")
    sys_handler.setFormatter(UnifiedFormatter("GE", _LOG_FMT))
    _sys_logger.addHandler(sys_handler)

    _heartbeat_logger = logging.getLogger("ge.heartbeat")
    _heartbeat_logger.setLevel(level)
    hb_handler = logging.FileHandler(sys_dir / "heartbeat.log", encoding="utf-8")
    hb_handler.setFormatter(UnifiedFormatter("HB", _LOG_FMT))
    _heartbeat_logger.addHandler(hb_handler)

    _package_logger = logging.getLogger("ge.package")
    _package_logger.setLevel(level)
    pkg_handler = logging.FileHandler(sys_dir / "package.log", encoding="utf-8")
    pkg_handler.setFormatter(UnifiedFormatter("PKG", _LOG_FMT))
    _package_logger.addHandler(pkg_handler)

    _sys_logger.info("System logging initialized (log_dir=%s)", log_dir)


def get_sys_logger() -> logging.Logger:
    return _sys_logger or logging.getLogger("ge.sys")


def get_heartbeat_logger() -> logging.Logger:
    return _heartbeat_logger or logging.getLogger("ge.heartbeat")


def get_package_logger() -> logging.Logger:
    return _package_logger or logging.getLogger("ge.package")


def get_task_logger(task_id: int, log_dir: str) -> logging.Logger:
    task_dir = Path(log_dir) / "tasks" / str(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(f"ge.task.{task_id}")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    handler = logging.FileHandler(task_dir / "output.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    return logger
