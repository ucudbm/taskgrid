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
import yaml


class GSConfig:
    def __init__(self, path: Path):
        with open(path) as f:
            raw = yaml.safe_load(f)

        gs = raw.get("gs", {})

        self.host: str = gs.get("host", "0.0.0.0")
        self.port: int = gs.get("port", 8000)
        self.db_path: str = gs.get("db_path", "/var/lib/taskgrid/gs.db")
        self.redis_url: str = gs.get("redis_url", "redis://localhost:6379/0")
        self.store_dir: str = gs.get("store_dir", "/var/lib/taskgrid/artifacts")
        self.gp_url: str = gs.get("gp_url", "http://localhost:8001")
        self.auth_token: str = os.environ.get("TASKGRID_TOKEN", gs.get("auth_token", ""))
        self.log_level: str = gs.get("log_level", "INFO")
        self.offline_timeout: int = gs.get("offline_timeout", 30)
        self.retention_days: int = gs.get("retention_days", 30)

    @property
    def auth_headers(self) -> dict:
        if self.auth_token:
            return {"Authorization": f"Bearer {self.auth_token}"}
        return {}
