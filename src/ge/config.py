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
import os
from pathlib import Path
from typing import Optional
import yaml


class GEConfig:
    def __init__(self, path: Path):
        with open(path) as f:
            raw = yaml.safe_load(f)

        ge = raw.get("ge", {})

        self.id: str = ge.get("id", "ge-unknown")
        self.server_url: str = ge.get("server_url", "http://localhost:8000")
        self.gp_url: str = ge.get("gp_url", "http://localhost:8001")
        self.polling_interval: int = ge.get("polling_interval", 10)
        self.heartbeat_interval: int = ge.get("heartbeat_interval", 10)
        self.offline_timeout: int = ge.get("offline_timeout", 30)
        self.task_timeout: int = ge.get("task_timeout", 3600)
        self.retry_enabled: bool = ge.get("retry_enabled", False)
        self.retry_count: int = ge.get("retry_count", 0)
        self.workdir_base: str = ge.get("workdir_base", "/opt/taskgrid/workspace")
        self.log_dir: str = ge.get("log_dir", "/var/log/taskgrid")
        self.log_level: str = ge.get("log_level", "INFO")
        self.package_cache_dir: str = ge.get(
            "package_cache_dir", "/var/cache/taskgrid/packages"
        )
        self.task_log_retention_days: int = ge.get("task_log_retention_days", 30)
        self.temp_data_retention_days: int = ge.get("temp_data_retention_days", 3)
        self.auth_token: str = os.environ.get("TASKGRID_TOKEN") or ge.get("auth_token", "")
        self.pool: Optional[str] = ge.get("pool") or None
        self.os_tag: Optional[str] = ge.get("os_tag") or None
        self.device_id: Optional[str] = ge.get("device_id") or None
        self.total_slots: int = ge.get("total_slots", 3)

        web = ge.get("web", {})
        self.web_port: int = int(web.get("port", 0))

        ota = ge.get("ota", {})
        self.ota_enabled: bool = ota.get("enabled", False)
        self.ota_update_url: Optional[str] = ota.get("update_url")

    @property
    def auth_headers(self) -> dict:
        if self.auth_token:
            return {"Authorization": f"Bearer {self.auth_token}"}
        return {}

    @property
    def register_url(self) -> str:
        return f"{self.server_url}/api/ge/register"

    @property
    def heartbeat_url(self) -> str:
        return f"{self.server_url}/api/ge/heartbeat"

    @property
    def poll_url(self) -> str:
        return f"{self.server_url}/api/tasks/poll"

    @property
    def result_url(self) -> str:
        return f"{self.server_url}/api/tasks/result"
