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
from ge.config import GEConfig


class TestGEConfig:
    def test_load(self, sample_config):
        assert sample_config.id == "ge-test"
        assert sample_config.server_url == "http://localhost:8000"
        assert sample_config.polling_interval == 5
        assert sample_config.heartbeat_interval == 10
        assert sample_config.offline_timeout == 30
        assert sample_config.task_timeout == 3600
        assert sample_config.retry_enabled is False
        assert sample_config.retry_count == 0

    def test_url_properties(self, sample_config):
        assert sample_config.register_url == "http://localhost:8000/api/ge/register"
        assert sample_config.heartbeat_url == "http://localhost:8000/api/ge/heartbeat"
        assert sample_config.poll_url == "http://localhost:8000/api/tasks/poll"
        assert sample_config.result_url == "http://localhost:8000/api/tasks/result"

    def test_ota_defaults(self, sample_config):
        assert sample_config.ota_enabled is False
        assert sample_config.ota_update_url is None

    def test_retention_defaults(self, sample_config):
        assert sample_config.task_log_retention_days == 30
        assert sample_config.temp_data_retention_days == 3
