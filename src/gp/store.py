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
import json
import shutil
import tarfile
from pathlib import Path
from typing import Optional


class PackageStore:
    def __init__(self, store_dir: str):
        self._root = Path(store_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def _pkg_dir(self, name: str) -> Path:
        return self._root / name

    def _ver_dir(self, name: str, version: int) -> Path:
        return self._pkg_dir(name) / str(version)

    def _meta_path(self, name: str) -> Path:
        return self._pkg_dir(name) / "metadata.json"

    def _ver_meta_path(self, name: str, version: int) -> Path:
        return self._ver_dir(name, version) / "metadata.json"

    def _pkg_file(self, name: str, version: int) -> Path:
        return self._ver_dir(name, version) / "package.tar"

    def list_packages(self) -> list[dict]:
        if not self._root.exists():
            return []
        packages = []
        for p in sorted(self._root.iterdir()):
            if p.is_dir() and (p / "metadata.json").exists():
                meta = json.loads((p / "metadata.json").read_text())
                packages.append(meta)
        return packages

    def get_package_meta(self, name: str) -> Optional[dict]:
        path = self._meta_path(name)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def create_package(self, name: str, description: str = "") -> dict:
        pkg_dir = self._pkg_dir(name)
        if pkg_dir.exists():
            return self.get_package_meta(name)

        pkg_dir.mkdir(parents=True)
        meta = {
            "name": name,
            "description": description,
            "created_at": self._now(),
        }
        self._meta_path(name).write_text(json.dumps(meta, indent=2))
        return meta

    def list_versions(self, name: str) -> list[dict]:
        pkg_dir = self._pkg_dir(name)
        if not pkg_dir.exists():
            return []
        versions = []
        for p in sorted(pkg_dir.iterdir(), key=lambda x: int(x.name) if x.name.isdigit() else 0):
            if p.is_dir() and p.name.isdigit() and (p / "metadata.json").exists():
                meta = json.loads((p / "metadata.json").read_text())
                version = int(p.name)
                meta["version"] = version
                versions.append(meta)
        return versions

    def get_version_meta(self, name: str, version: int) -> Optional[dict]:
        path = self._ver_meta_path(name, version)
        if not path.exists():
            return None
        meta = json.loads(path.read_text())
        meta["version"] = version
        return meta

    def next_version(self, name: str) -> int:
        versions = self.list_versions(name)
        if not versions:
            return 1
        return max(v["version"] for v in versions) + 1

    def publish_version(self, name: str, version: int, tar_data: bytes, description: str = "", tasks: list = None) -> dict:
        ver_dir = self._ver_dir(name, version)
        ver_dir.mkdir(parents=True, exist_ok=True)

        pkg_file = self._pkg_file(name, version)
        pkg_file.write_bytes(tar_data)

        meta = {
            "version": version,
            "description": description,
            "created_at": self._now(),
        }
        if tasks:
            meta["tasks"] = tasks
        self._ver_meta_path(name, version).write_text(json.dumps(meta, indent=2))
        return meta

    def get_package_file(self, name: str, version: int) -> Optional[bytes]:
        pkg_file = self._pkg_file(name, version)
        if not pkg_file.exists():
            return None
        return pkg_file.read_bytes()

    def search(self, query: str) -> list[dict]:
        query = query.lower()
        packages = self.list_packages()
        return [p for p in packages if query in p["name"].lower() or query in p.get("description", "").lower()]

    def delete_package(self, name: str):
        pkg_dir = self._pkg_dir(name)
        if pkg_dir.exists():
            shutil.rmtree(pkg_dir)

    def save_result_file(self, task_id: int, filename: str, data: bytes):
        result_dir = self._root / "results" / str(task_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        (result_dir / filename).write_bytes(data)

    def get_result_file(self, task_id: int, filename: str) -> Optional[bytes]:
        path = self._root / "results" / str(task_id) / filename
        if not path.exists():
            return None
        return path.read_bytes()

    def delete_result_files(self, task_id: int):
        result_dir = self._root / "results" / str(task_id)
        if result_dir.exists():
            shutil.rmtree(result_dir)

    @staticmethod
    def _now() -> str:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
