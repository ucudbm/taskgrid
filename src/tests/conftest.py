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
import tempfile
from pathlib import Path
import pytest
from ge.config import GEConfig


@pytest.fixture
def sample_config():
    content = """
ge:
  id: "ge-test"
  server_url: "http://localhost:8000"
  polling_interval: 5
  heartbeat_interval: 10
  offline_timeout: 30
  task_timeout: 3600
  retry_enabled: false
  retry_count: 0
  workdir_base: "/tmp/taskgrid-test/workspace"
  log_dir: "/tmp/taskgrid-test/logs"
  log_level: "DEBUG"
  package_cache_dir: "/tmp/taskgrid-test/cache"
  task_log_retention_days: 30
  temp_data_retention_days: 3
  ota:
    enabled: false
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(content)
        path = f.name
    yield GEConfig(Path(path))
    Path(path).unlink(missing_ok=True)
