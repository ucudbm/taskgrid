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
from typing import Optional

from ..redis_client.lock import RedisLock


class LockManager:
    def __init__(self, lock: RedisLock):
        self._lock = lock

    def lock_task(self, task_id: int) -> Optional[str]:
        return self._lock.acquire(f"task:{task_id}", ttl=60, retry_timeout=5)

    def unlock_task(self, task_id: int, lock_value: str) -> bool:
        return self._lock.release(f"task:{task_id}", lock_value)

    def is_locked(self, task_id: int) -> bool:
        return self._lock.exists(f"task:{task_id}")
