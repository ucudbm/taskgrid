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
import threading
import httpx
from .config import GEConfig
from .log import get_heartbeat_logger
from .executor.slot import SlotManager
from ._utils import gzip_json, timestamp_now, get_version


class HeartbeatReporter:
    def __init__(self, cfg: GEConfig, slot_mgr: SlotManager, client: httpx.Client):
        self._cfg = cfg
        self._slots = slot_mgr
        self._client = client
        self._running_task_ids: set[int] = set()
        self._task_progress: dict[int, str] = {}
        self._task_lock = threading.Lock()

    @property
    def running_task_id(self) -> int | None:
        with self._task_lock:
            for tid in self._running_task_ids:
                return tid
            return None

    def add_task_id(self, task_id: int):
        with self._task_lock:
            self._running_task_ids.add(task_id)

    def remove_task_id(self, task_id: int):
        with self._task_lock:
            self._running_task_ids.discard(task_id)

    def set_progress(self, task_id: int, phase: str):
        with self._task_lock:
            self._task_progress[task_id] = phase

    def clear_progress(self, task_id: int):
        with self._task_lock:
            self._task_progress.pop(task_id, None)

    def _get_progress(self, task_id: int | None) -> str | None:
        if task_id is None:
            return None
        with self._task_lock:
            return self._task_progress.get(task_id)

    def send(self) -> dict | None:
        with self._task_lock:
            task_ids = sorted(self._running_task_ids)
            is_running = bool(self._running_task_ids)
            progress = self._get_progress(next(iter(self._running_task_ids), None))
        payload = {
            "ge_id": self._cfg.id,
            "state": "running" if is_running else "idle",
            "task_id": task_ids[0] if task_ids else None,
            "task_ids": task_ids,
            "progress": progress,
            "slots": {
                "total": self._slots.total,
                "idle": self._slots.idle,
            },
            "version": get_version(),
            "timestamp": timestamp_now(),
        }

        try:
            body, gzip_headers = gzip_json(payload)
            resp = self._client.post(
                self._cfg.heartbeat_url,
                content=body,
                headers=gzip_headers,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            get_heartbeat_logger().warning("Heartbeat failed: %s", e)
            return None
