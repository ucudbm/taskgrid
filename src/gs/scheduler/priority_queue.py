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
    def __init__(self, client: redis.Redis):
        self._client = client
        self._prefix = "taskgrid:queue:"

    def _key(self, priority: str, ge_id: Optional[str] = None) -> str:
        if ge_id:
            return f"{self._prefix}{priority}:ge:{ge_id}"
        return f"{self._prefix}{priority}"

    def _pool_key(self, priority: str, pool: str) -> str:
        return f"{self._prefix}{priority}:pool:{pool}"

    def _os_tag_key(self, priority: str, os_tag: str) -> str:
        return f"{self._prefix}{priority}:os:{os_tag}"

    def _device_key(self, priority: str, device_id: str) -> str:
        return f"{self._prefix}{priority}:device:{device_id}"

    def push(self, task_id: int, priority: str = "medium", ge_id: Optional[str] = None):
        key = self._key(priority, ge_id)
        self._client.zadd(key, {str(task_id): time.time()})

    def push_with_pool(self, task_id: int, priority: str, pool: str):
        key = self._pool_key(priority, pool)
        self._client.zadd(key, {str(task_id): time.time()})

    def push_with_os_tag(self, task_id: int, priority: str, os_tag: str):
        key = self._os_tag_key(priority, os_tag)
        self._client.zadd(key, {str(task_id): time.time()})

    def push_with_device(self, task_id: int, priority: str, device_id: str):
        key = self._device_key(priority, device_id)
        self._client.zadd(key, {str(task_id): time.time()})

    def pop(self, priority: str = "medium", ge_id: Optional[str] = None) -> Optional[int]:
        key = self._key(priority, ge_id)
        result = self._client.zpopmin(key, count=1)
        if result:
            task_id_str = result[0][0]
            if isinstance(task_id_str, bytes):
                task_id_str = task_id_str.decode()
            return int(task_id_str)
        return None

    def pop_from_pool(self, priority: str, pool: str) -> Optional[int]:
        key = self._pool_key(priority, pool)
        result = self._client.zpopmin(key, count=1)
        if result:
            task_id_str = result[0][0]
            if isinstance(task_id_str, bytes):
                task_id_str = task_id_str.decode()
            return int(task_id_str)
        return None

    def pop_from_os_tag(self, priority: str, os_tag: str) -> Optional[int]:
        key = self._os_tag_key(priority, os_tag)
        result = self._client.zpopmin(key, count=1)
        if result:
            task_id_str = result[0][0]
            if isinstance(task_id_str, bytes):
                task_id_str = task_id_str.decode()
            return int(task_id_str)
        return None

    def pop_from_device(self, priority: str, device_id: str) -> Optional[int]:
        key = self._device_key(priority, device_id)
        result = self._client.zpopmin(key, count=1)
        if result:
            task_id_str = result[0][0]
            if isinstance(task_id_str, bytes):
                task_id_str = task_id_str.decode()
            return int(task_id_str)
        return None

    def peek(self, priority: str = "medium", ge_id: Optional[str] = None) -> Optional[int]:
        key = self._key(priority, ge_id)
        result = self._client.zrange(key, 0, 0)
        if result:
            task_id_str = result[0]
            if isinstance(task_id_str, bytes):
                task_id_str = task_id_str.decode()
            return int(task_id_str)
        return None

    def remove(self, task_id: int, priority: str = "medium", ge_id: Optional[str] = None) -> bool:
        key = self._key(priority, ge_id)
        return self._client.zrem(key, str(task_id)) > 0

    def remove_from_pool(self, task_id: int, priority: str, pool: str) -> bool:
        key = self._pool_key(priority, pool)
        return self._client.zrem(key, str(task_id)) > 0

    def remove_from_os_tag(self, task_id: int, priority: str, os_tag: str) -> bool:
        key = self._os_tag_key(priority, os_tag)
        return self._client.zrem(key, str(task_id)) > 0

    def remove_from_device(self, task_id: int, priority: str, device_id: str) -> bool:
        key = self._device_key(priority, device_id)
        return self._client.zrem(key, str(task_id)) > 0

    def size(self, priority: str = "medium", ge_id: Optional[str] = None) -> int:
        key = self._key(priority, ge_id)
        return self._client.zcard(key)

    def _pop_any_from_key(self, key: str) -> Optional[int]:
        result = self._client.zpopmin(key, count=1)
        if result:
            task_id_str = result[0][0]
            if isinstance(task_id_str, bytes):
                task_id_str = task_id_str.decode()
            return int(task_id_str)
        return None

    def pop_by_routing(self, ge_id: str, pool: Optional[str] = None,
                       os_tag: Optional[str] = None,
                       device_id: Optional[str] = None) -> Optional[int]:
        for priority in ("high", "medium", "low"):
            task_id = self.pop(priority, ge_id)
            if task_id is not None:
                return task_id
        if device_id:
            for priority in ("high", "medium", "low"):
                task_id = self.pop_from_device(priority, device_id)
                if task_id is not None:
                    return task_id
        if pool:
            for priority in ("high", "medium", "low"):
                task_id = self.pop_from_pool(priority, pool)
                if task_id is not None:
                    return task_id
        if os_tag:
            for priority in ("high", "medium", "low"):
                task_id = self.pop_from_os_tag(priority, os_tag)
                if task_id is not None:
                    return task_id
        for priority in ("high", "medium", "low"):
            task_id = self._pop_any_from_key(self._key(priority))
            if task_id is not None:
                return task_id
        return None
