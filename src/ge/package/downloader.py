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
import tarfile
import io
import httpx
from pathlib import Path
from ..config import GEConfig
from ..log import get_package_logger
from .cache import PackageCache


class PackageManager:
    def __init__(self, cfg: GEConfig):
        self._gp_url = cfg.gp_url.rstrip("/")
        self._cache = PackageCache(cfg.package_cache_dir)
        self._client = httpx.Client(timeout=30, headers=cfg.auth_headers)

    def close(self):
        self._client.close()

    def latest_version(self, package: str) -> int:
        url = f"{self._gp_url}/api/packages/{package}/versions"
        get_package_logger().info("Querying latest version for %s", package)
        resp = self._client.get(url)
        resp.raise_for_status()
        versions = resp.json()
        if not versions:
            raise ValueError(f"No versions found for package '{package}'")
        return max(v["version"] for v in versions)

    def fetch(self, package: str, version: int, dest_dir: Path):
        cached = self._cache.get(package, version)
        if cached:
            get_package_logger().info(
                "Package cache hit: %s v%s", package, version
            )
            with tarfile.open(cached, "r") as tf:
                tf.extractall(path=dest_dir)
            return

        get_package_logger().info(
            "Downloading package %s v%s from GP", package, version
        )
        url = f"{self._gp_url}/api/packages/{package}/versions/{version}"
        with self._client.stream("GET", url) as resp:
            resp.raise_for_status()
            content = resp.read()

        self._cache.put(package, version, content)

        with tarfile.open(fileobj=io.BytesIO(content)) as tf:
            tf.extractall(path=dest_dir)

    def upload_result_file(self, task_id: int, filepath: Path) -> str:
        url = f"{self._gp_url}/api/results/{task_id}/files"
        filename = filepath.name
        get_package_logger().info("Uploading result file %s for task %s", filename, task_id)
        with open(filepath, "rb") as f:
            resp = self._client.post(url, files={"file": (filename, f, "application/octet-stream")})
            resp.raise_for_status()
            data = resp.json()
        return data["url"]
