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
from ge.executor.venv import create_venv, destroy_venv


class TestVenv:
    def test_create_and_destroy(self):
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp) / "task_venv_test"
            workdir.mkdir()

            venv_path = create_venv(workdir)
            assert (venv_path / "bin" / "python").exists() or \
                   (venv_path / "Scripts" / "python.exe").exists()

            destroy_venv(workdir)
            assert not (workdir / ".venv").exists()
