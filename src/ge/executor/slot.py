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
from __future__ import annotations
import threading


class SlotManager:
    def __init__(self, total_slots: int):
        self._total = total_slots
        self._used = 0
        self._lock = threading.Lock()

    @property
    def total(self) -> int:
        return self._total

    @property
    def idle(self) -> int:
        with self._lock:
            return self._total - self._used

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    def acquire(self) -> bool:
        with self._lock:
            if self._used < self._total:
                self._used += 1
                return True
            return False

    def release(self):
        with self._lock:
            if self._used > 0:
                self._used -= 1
