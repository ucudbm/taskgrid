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
from ge.executor.slot import SlotManager


class TestSlotManager:
    def test_acquire_release(self):
        sm = SlotManager(3)
        assert sm.total == 3
        assert sm.idle == 3

        assert sm.acquire() is True
        assert sm.idle == 2
        assert sm.used == 1

        assert sm.acquire() is True
        assert sm.idle == 1

        sm.release()
        assert sm.idle == 2

    def test_no_overflow(self):
        sm = SlotManager(1)
        assert sm.acquire() is True
        assert sm.acquire() is False
        assert sm.idle == 0

    def test_zero_slots(self):
        sm = SlotManager(0)
        assert sm.acquire() is False

    def test_release_below_zero(self):
        sm = SlotManager(2)
        sm.release()
        assert sm.idle == 2
