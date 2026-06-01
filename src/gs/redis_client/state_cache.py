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
import json
import time
from typing import Optional

import redis


class StateCache:
    def __init__(self, client: redis.Redis):
        self._client = client
        self._ge_prefix = "taskgrid:ge:"
        self._online_set = "taskgrid:ge:online"

    def set_ge_online(self, ge_id: str, state: dict, ttl: int = 60):
        key = f"{self._ge_prefix}{ge_id}:state"
        self._client.hset(key, mapping=state)
        self._client.expire(key, ttl)
        self._client.sadd(self._online_set, ge_id)
        self._client.expire(self._online_set, ttl + 10)

    def get_ge_state(self, ge_id: str) -> Optional[dict]:
        key = f"{self._ge_prefix}{ge_id}:state"
        data = self._client.hgetall(key)
        if not data:
            return None
        return {k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in data.items()}

    def remove_ge_online(self, ge_id: str):
        self._client.srem(self._online_set, ge_id)
        self._client.delete(f"{self._ge_prefix}{ge_id}:state")

    def get_online_ges(self) -> list[str]:
        members = self._client.smembers(self._online_set)
        return [m.decode() if isinstance(m, bytes) else m for m in members]

    def is_online(self, ge_id: str) -> bool:
        return bool(self._client.sismember(self._online_set, ge_id))

    def set_cancel_flag(self, task_id: int):
        self._client.set(f"taskgrid:cancel:{task_id}", "1", ex=86400)

    def remove_cancel_flag(self, task_id: int):
        self._client.delete(f"taskgrid:cancel:{task_id}")

    def is_cancelled(self, task_id: int) -> bool:
        return bool(self._client.exists(f"taskgrid:cancel:{task_id}"))

    def get_cancelled_tasks_for_ge(self, ge_id: str, current_task_id: Optional[int] = None) -> list[int]:
        if current_task_id is not None and self.is_cancelled(current_task_id):
            return [current_task_id]
        return []
