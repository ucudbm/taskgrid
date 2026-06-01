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
"""
OTA Updater — Phase 2

In Phase 2, GE will:
1. Receive version update command from GS (via heartbeat response)
2. Download new package from update_url
3. Replace current executable
4. Restart service
"""

from ..log import get_sys_logger


class OTAUpdater:
    def __init__(self, enabled: bool, update_url: str | None = None):
        self._enabled = enabled
        self._update_url = update_url

    def check_and_update(self):
        if not self._enabled:
            return
        get_sys_logger().info("OTA update check skipped (Phase 2)")
