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


class HeartbeatProcessor:
    def __init__(self, repo: Repository, cache: StateCache, offline_timeout: int = 30):
        self._repo = repo
        self._cache = cache
        self._offline_timeout = offline_timeout

    def process(self, ge_id: str, state: str, task_id: Optional[int] = None,
                progress: Optional[str] = None, slots: Optional[dict] = None) -> dict:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now_dt.microsecond // 1000:03d}Z"

        ge_row = self._repo.get_ge(ge_id)
        if ge_row is None:
            return {"status": "error", "message": "unknown ge"}

        total_slots = slots.get("total", 1) if slots else 1
        idle_slots = slots.get("idle", 0) if slots else 0

        self._repo.update_ge(
            ge_id,
            state="online",
            last_heartbeat=now,
            total_slots=total_slots,
            idle_slots=idle_slots,
            current_task_id=task_id,
        )

        self._cache.set_ge_online(ge_id, {
            "state": state,
            "total_slots": str(total_slots),
            "idle_slots": str(idle_slots),
            "last_heartbeat": now,
        }, ttl=self._offline_timeout + 30)

        cancelled_ids = self._cache.get_cancelled_tasks_for_ge(ge_id, current_task_id=task_id)
        response = {"status": "ok"}
        if cancelled_ids:
            response["cancelled_task_ids"] = cancelled_ids
        return response

    def mark_offline(self, ge_id: str):
        self._repo.update_ge(ge_id, state="offline", idle_slots=0, current_task_id=None)
        self._cache.remove_ge_online(ge_id)
