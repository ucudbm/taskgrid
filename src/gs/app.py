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
import gzip
import logging
import os
import sys
import time
import threading
from pathlib import Path

import redis
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from .config import GSConfig
from .db.repository import Repository
from .redis_client.lock import RedisLock
from .redis_client.state_cache import StateCache
from .scheduler.priority_queue import PriorityQueue
from .scheduler.lock_manager import LockManager
from .scheduler.router import TaskScheduler
from .ge_manager.registry import GERegistry
from .ge_manager.heartbeat import HeartbeatProcessor
from .ge_manager.state import GEStateManager
from .result.collector import ResultCollector
from .storage.file_store import FileStore
from .api.tasks import router as tasks_router
from .api.ge import router as ge_router
from .api.packages import router as packages_router
from .web.router import router as web_router


class GSFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        s = time.strftime("%Y-%m-%dT%H:%M:%S", ct)
        return f"{s}.{int(record.msecs):03d}"

    def format(self, record):
        record.component = "GS"
        return super().format(record)


_LOG_FMT = "%(asctime)s [%(component)s] [%(levelname)s] %(message)s"


def _setup_logging(level: str):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(GSFormatter(_LOG_FMT))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).addHandler(handler)
        logging.getLogger(name).propagate = False


app = FastAPI(title="TaskGrid GS")
app.add_middleware(GZipMiddleware, minimum_size=100)


@app.middleware("http")
async def gzip_decompress(request: Request, call_next):
    if request.headers.get("Content-Encoding") == "gzip":
        body = await request.body()
        request._body = gzip.decompress(body)
    return await call_next(request)

_cfg: GSConfig = None
_repo: Repository = None
_redis: redis.Redis = None
_queue: PriorityQueue = None
_lock: RedisLock = None
_lock_mgr: LockManager = None
_cache: StateCache = None
_registry: GERegistry = None
_heartbeat_proc: HeartbeatProcessor = None
_state_mgr: GEStateManager = None
_scheduler: TaskScheduler = None
_collector: ResultCollector = None
_store: FileStore = None
_log: logging.Logger = None


def get_cfg() -> GSConfig:
    global _cfg
    return _cfg


def get_repo() -> Repository:
    global _repo
    return _repo


def get_queue() -> PriorityQueue:
    global _queue
    return _queue


def get_lock_mgr() -> LockManager:
    global _lock_mgr
    return _lock_mgr


def get_cache() -> StateCache:
    global _cache
    return _cache


def get_registry() -> GERegistry:
    global _registry
    return _registry


def get_heartbeat_processor() -> HeartbeatProcessor:
    global _heartbeat_proc
    return _heartbeat_proc


def get_state_manager() -> GEStateManager:
    global _state_mgr
    return _state_mgr


def get_scheduler() -> TaskScheduler:
    global _scheduler
    return _scheduler


def get_collector() -> ResultCollector:
    global _collector
    return _collector


def get_store() -> FileStore:
    global _store
    return _store


def _periodic_cleanup(interval: int = 60):
    def _loop():
        while True:
            time.sleep(interval)
            try:
                _state_mgr.check_offline_ges()
            except Exception as e:
                _log.error("Offline check error: %s", e)
            try:
                _store.cleanup_old_files(_cfg.retention_days)
            except Exception as e:
                _log.error("Cleanup error: %s", e)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


def create_app(cfg: GSConfig) -> FastAPI:
    global _cfg, _repo, _redis, _queue, _lock, _lock_mgr, _cache
    global _registry, _heartbeat_proc, _state_mgr, _scheduler, _collector, _store, _log

    _cfg = cfg
    _setup_logging(cfg.log_level)
    _log = logging.getLogger("gs")

    db_dir = Path(cfg.db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    _repo = Repository(cfg.db_path)

    Path(cfg.store_dir).mkdir(parents=True, exist_ok=True)
    _store = FileStore(cfg.store_dir)

    _redis = redis.Redis.from_url(cfg.redis_url, decode_responses=False)
    _redis.ping()
    _log.info("Connected to Redis: %s", cfg.redis_url)

    _lock = RedisLock(_redis)
    _cache = StateCache(_redis)
    _queue = PriorityQueue(_redis)
    _lock_mgr = LockManager(_lock)
    _scheduler = TaskScheduler(_repo, _queue, _lock_mgr, _cache)
    _heartbeat_proc = HeartbeatProcessor(_repo, _cache, cfg.offline_timeout)
    _state_mgr = GEStateManager(_repo, _cache, _heartbeat_proc, cfg.offline_timeout)
    _registry = GERegistry(_repo, _cache, cfg.offline_timeout)
    _collector = ResultCollector(_scheduler, _repo)

    static_dir = Path(__file__).parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(web_router)
    app.include_router(tasks_router)
    app.include_router(ge_router)
    app.include_router(packages_router)

    _periodic_cleanup()

    _log.info("GS initialized (db=%s, store=%s)", cfg.db_path, cfg.store_dir)
    return app
