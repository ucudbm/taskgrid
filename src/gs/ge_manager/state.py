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
from datetime import datetime, timezone
from typing import Optional

from ..db.repository import Repository
from ..redis_client.state_cache import StateCache
from .heartbeat import HeartbeatProcessor


class GEStateManager:
    def __init__(self, repo: Repository, cache: StateCache,
                 heartbeat_proc: HeartbeatProcessor, offline_timeout: int = 30):
        self._repo = repo
        self._cache = cache
        self._heartbeat = heartbeat_proc
        self._offline_timeout = offline_timeout

    def check_offline_ges(self):
        now = datetime.now(timezone.utc)
        online_ges = self._repo.list_online_ge()

        for ge in online_ges:
            hb_str = ge.get("last_heartbeat")
            if not hb_str:
                continue
            try:
                hb_time = datetime.fromisoformat(hb_str)
                if (now - hb_time).total_seconds() > self._offline_timeout:
                    self._heartbeat.mark_offline(ge["ge_id"])
            except (ValueError, TypeError):
                continue

    def get_ge_list(self) -> list[dict]:
        rows = self._repo.list_ge()
        result = []
        for r in rows:
            result.append({
                "ge_id": r["ge_id"],
                "state": r["state"],
                "last_heartbeat": r.get("last_heartbeat"),
                "total_slots": r["total_slots"],
                "idle_slots": r["idle_slots"],
                "current_task_id": r.get("current_task_id"),
                "pool": r.get("pool"),
                "os_tag": r.get("os_tag"),
                "device_id": r.get("device_id"),
                "registered_at": r.get("created_at"),
            })
        return result

    def get_ge_detail(self, ge_id: str) -> Optional[dict]:
        r = self._repo.get_ge(ge_id)
        if r is None:
            return None
        return {
            "ge_id": r["ge_id"],
            "state": r["state"],
            "last_heartbeat": r.get("last_heartbeat"),
            "total_slots": r["total_slots"],
            "idle_slots": r["idle_slots"],
            "current_task_id": r.get("current_task_id"),
            "pool": r.get("pool"),
            "os_tag": r.get("os_tag"),
            "device_id": r.get("device_id"),
            "registered_at": r.get("created_at"),
        }
