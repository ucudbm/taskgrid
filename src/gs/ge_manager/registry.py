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
import time
from typing import Optional

from ..db.repository import Repository
from ..redis_client.state_cache import StateCache


class GERegistry:
    def __init__(self, repo: Repository, cache: StateCache, offline_timeout: int = 30):
        self._repo = repo
        self._cache = cache
        self._offline_timeout = offline_timeout

    def register(self, ge_id: str, pool: Optional[str] = None,
                 os_tag: Optional[str] = None, total_slots: int = 1,
                 device_id: Optional[str] = None,
                 force: bool = False) -> dict:
        existing = self._repo.get_ge(ge_id)
        if existing:
            if not force:
                return {"ge_id": ge_id, "status": "conflict"}

            self._repo.update_ge(
                ge_id,
                state="online",
                total_slots=total_slots,
                idle_slots=total_slots,
                current_task_id=None,
                pool=pool,
                os_tag=os_tag,
                device_id=device_id,
            )
            self._cache.set_ge_online(ge_id, {
                "state": "idle",
                "total_slots": str(total_slots),
                "idle_slots": str(total_slots),
                "pool": pool or "",
                "os_tag": os_tag or "",
            }, ttl=self._offline_timeout + 30)
            return {"ge_id": ge_id, "status": "reconnected"}

        self._repo.register_ge(ge_id, pool, os_tag, total_slots, device_id)
        self._cache.set_ge_online(ge_id, {
            "state": "idle",
            "total_slots": str(total_slots),
            "idle_slots": str(total_slots),
            "pool": pool or "",
            "os_tag": os_tag or "",
        }, ttl=self._offline_timeout + 30)
        return {"ge_id": ge_id, "status": "registered"}

    def update(self, ge_id: str, **fields):
        self._repo.update_ge(ge_id, **fields)
        cache_fields = {}
        for k in ("pool", "os_tag"):
            if k in fields:
                cache_fields[k] = fields[k] or ""
        if cache_fields:
            data = self._cache.get_ge_state(ge_id)
            if data:
                data.update(cache_fields)
                self._cache.set_ge_online(
                    ge_id, data, ttl=self._offline_timeout + 30
                )
