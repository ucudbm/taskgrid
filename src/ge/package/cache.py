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
import shutil
from pathlib import Path
from ..log import get_package_logger


class PackageCache:
    def __init__(self, cache_dir: str):
        self._root = Path(cache_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, package: str, version: int) -> Path:
        return self._root / package / str(version) / "package.tar"

    def get(self, package: str, version: int) -> Path | None:
        p = self._path(package, version)
        return p if p.exists() else None

    def put(self, package: str, version: int, data: bytes) -> Path:
        p = self._path(package, version)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        get_package_logger().info("Cached package %s v%s at %s", package, version, p)
        return p

    def clear(self):
        if self._root.exists():
            shutil.rmtree(self._root)
            self._root.mkdir(parents=True)
