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
import httpx
from .config import GEConfig
from .log import get_sys_logger
from ._utils import gzip_json


class TaskPoller:
    def __init__(self, cfg: GEConfig, client: httpx.Client = None):
        self._cfg = cfg
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=10, headers=self._cfg.auth_headers)

    def close(self):
        if self._owns_client:
            self._client.close()

    def poll(self, idle_slots: int) -> list[dict]:
        if idle_slots <= 0:
            return []

        try:
            body, gzip_headers = gzip_json({"ge_id": self._cfg.id, "idle_slots": idle_slots})
            resp = self._client.post(
                self._cfg.poll_url,
                content=body,
                headers=gzip_headers,
            )
            resp.raise_for_status()
            tasks = resp.json()
            if tasks:
                get_sys_logger().info(
                    "Polled %s new task(s)", len(tasks)
                )
            return tasks if isinstance(tasks, list) else [tasks]
        except Exception as e:
            get_sys_logger().warning("Task poll failed: %s", e)
            return []
