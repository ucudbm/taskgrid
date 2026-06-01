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
from ._utils import gzip_json, timestamp_now


class HeartbeatReporter:
    def __init__(self, cfg: GEConfig, slot_mgr: SlotManager, client: httpx.Client):
        self._cfg = cfg
        self._slots = slot_mgr
        self._client = client
        self._running_task_id: int | None = None
        self._task_progress: dict[int, str] = {}
        self._progress_lock = threading.Lock()

    @property
    def running_task_id(self) -> int | None:
        return self._running_task_id

    @running_task_id.setter
    def running_task_id(self, value: int | None):
        self._running_task_id = value

    def set_progress(self, task_id: int, phase: str):
        with self._progress_lock:
            self._task_progress[task_id] = phase

    def clear_progress(self, task_id: int):
        with self._progress_lock:
            self._task_progress.pop(task_id, None)

    def _get_progress(self, task_id: int | None) -> str | None:
        if task_id is None:
            return None
        with self._progress_lock:
            return self._task_progress.get(task_id)

    def send(self) -> dict | None:
        payload = {
            "ge_id": self._cfg.id,
            "state": "running" if self._running_task_id else "idle",
            "task_id": self._running_task_id,
            "progress": self._get_progress(self._running_task_id),
            "slots": {
                "total": self._slots.total,
                "idle": self._slots.idle,
            },
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
