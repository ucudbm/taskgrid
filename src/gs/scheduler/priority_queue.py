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

import redis


class PriorityQueue:
    _ROUTING_PREFIXES = {
        "ge": "ge:{}",
        "device": "device:{}",
        "pool": "pool:{}",
        "os_tag": "os:{}",
    }

    def __init__(self, client: redis.Redis):
        self._client = client
        self._prefix = "taskgrid:queue:"

    def _key(self, priority: str, ge_id: Optional[str] = None,
             pool: Optional[str] = None, os_tag: Optional[str] = None,
             device_id: Optional[str] = None) -> str:
        if ge_id:
            return f"{self._prefix}{priority}:ge:{ge_id}"
        if device_id:
            return f"{self._prefix}{priority}:device:{device_id}"
        if pool:
            return f"{self._prefix}{priority}:pool:{pool}"
        if os_tag:
            return f"{self._prefix}{priority}:os:{os_tag}"
        return f"{self._prefix}{priority}"

    def push(self, task_id: int, priority: str = "medium",
             ge_id: Optional[str] = None, pool: Optional[str] = None,
             os_tag: Optional[str] = None, device_id: Optional[str] = None):
        key = self._key(priority, ge_id, pool, os_tag, device_id)
        self._client.zadd(key, {str(task_id): time.time()})

    def pop(self, priority: str = "medium",
            ge_id: Optional[str] = None, pool: Optional[str] = None,
            os_tag: Optional[str] = None, device_id: Optional[str] = None) -> Optional[int]:
        key = self._key(priority, ge_id, pool, os_tag, device_id)
        result = self._client.zpopmin(key, count=1)
        if result:
            task_id_str = result[0][0]
            if isinstance(task_id_str, bytes):
                task_id_str = task_id_str.decode()
            return int(task_id_str)
        return None

    def remove(self, task_id: int, priority: str = "medium",
               ge_id: Optional[str] = None, pool: Optional[str] = None,
               os_tag: Optional[str] = None, device_id: Optional[str] = None) -> bool:
        key = self._key(priority, ge_id, pool, os_tag, device_id)
        return self._client.zrem(key, str(task_id)) > 0

    def peek(self, priority: str = "medium", ge_id: Optional[str] = None) -> Optional[int]:
        key = self._key(priority, ge_id)
        result = self._client.zrange(key, 0, 0)
        if result:
            task_id_str = result[0]
            if isinstance(task_id_str, bytes):
                task_id_str = task_id_str.decode()
            return int(task_id_str)
        return None

    def size(self, priority: str = "medium", ge_id: Optional[str] = None) -> int:
        key = self._key(priority, ge_id)
        return self._client.zcard(key)

    def pop_by_routing(self, ge_id: str, pool: Optional[str] = None,
                       os_tag: Optional[str] = None,
                       device_id: Optional[str] = None) -> Optional[int]:
        for priority in ("high", "medium", "low"):
            task_id = self.pop(priority, ge_id=ge_id)
            if task_id is not None:
                return task_id
        if device_id:
            for priority in ("high", "medium", "low"):
                task_id = self.pop(priority, device_id=device_id)
                if task_id is not None:
                    return task_id
        if pool:
            for priority in ("high", "medium", "low"):
                task_id = self.pop(priority, pool=pool)
                if task_id is not None:
                    return task_id
        if os_tag:
            for priority in ("high", "medium", "low"):
                task_id = self.pop(priority, os_tag=os_tag)
                if task_id is not None:
                    return task_id
        for priority in ("high", "medium", "low"):
            task_id = self.pop(priority)
            if task_id is not None:
                return task_id
        return None
