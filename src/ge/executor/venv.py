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
import subprocess
import shutil
import sys
from pathlib import Path
from ..log import get_sys_logger


def create_venv(workdir: Path) -> Path:
    venv_path = workdir / ".venv"
    log = get_sys_logger()
    log.info("Creating venv at %s", venv_path)
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_path)],
        check=True,
        capture_output=True,
    )
    return venv_path


def destroy_venv(workdir: Path):
    venv_path = workdir / ".venv"
    if venv_path.exists():
        shutil.rmtree(venv_path, ignore_errors=True)
        get_sys_logger().info("Destroyed venv at %s", venv_path)
