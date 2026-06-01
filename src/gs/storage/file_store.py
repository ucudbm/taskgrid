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
import shutil
from pathlib import Path
from typing import Optional


class FileStore:
    def __init__(self, store_dir: str):
        self._store_dir = Path(store_dir)
        self._store_dir.mkdir(parents=True, exist_ok=True)

    def save(self, task_id: int, filename: str, data: bytes) -> str:
        task_dir = self._store_dir / str(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        file_path = task_dir / filename
        file_path.write_bytes(data)
        return str(file_path)

    def get(self, task_id: int, filename: str) -> Optional[bytes]:
        file_path = self._store_dir / str(task_id) / filename
        if not file_path.exists():
            return None
        return file_path.read_bytes()

    def list_files(self, task_id: int) -> list[str]:
        task_dir = self._store_dir / str(task_id)
        if not task_dir.exists():
            return []
        return [f.name for f in task_dir.iterdir() if f.is_file()]

    def delete_task_files(self, task_id: int):
        task_dir = self._store_dir / str(task_id)
        if task_dir.exists():
            shutil.rmtree(task_dir)

    def cleanup_old_files(self, retention_days: int):
        now = __import__("time").time()
        cutoff = now - retention_days * 86400
        for item in self._store_dir.iterdir():
            if item.is_dir():
                try:
                    if item.stat().st_mtime < cutoff:
                        shutil.rmtree(item, ignore_errors=True)
                except OSError:
                    pass
