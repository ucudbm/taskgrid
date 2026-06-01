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
import uuid
from typing import Optional

import redis


class RedisLock:
    def __init__(self, client: redis.Redis, key_prefix: str = "taskgrid:lock:"):
        self._client = client
        self._prefix = key_prefix

    def acquire(self, name: str, ttl: int = 60, retry_interval: float = 0.1,
                retry_timeout: float = 10) -> Optional[str]:
        lock_key = self._prefix + name
        lock_value = str(uuid.uuid4())
        deadline = time.time() + retry_timeout
        while time.time() < deadline:
            acquired = self._client.set(lock_key, lock_value, nx=True, ex=ttl)
            if acquired:
                return lock_value
            time.sleep(retry_interval)
        return None

    def release(self, name: str, lock_value: str) -> bool:
        lock_key = self._prefix + name
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        result = self._client.eval(script, 1, lock_key, lock_value)
        return result == 1

    def exists(self, name: str) -> bool:
        return bool(self._client.exists(self._prefix + name))
