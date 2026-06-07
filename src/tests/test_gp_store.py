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
from gp.store import PackageStore


class TestPackageStore:
    def test_create_and_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PackageStore(tmp)
            store.create_package("web_test", "Web testing package")
            pkgs = store.list_packages()
            assert len(pkgs) == 1
            assert pkgs[0]["name"] == "web_test"

    def test_duplicate_create_returns_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PackageStore(tmp)
            store.create_package("pkg1", "first")
            store.create_package("pkg1", "second")
            pkgs = store.list_packages()
            assert len(pkgs) == 1

    def test_next_version_starts_at_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PackageStore(tmp)
            store.create_package("pkg1")
            assert store.next_version("pkg1") == 1

    def test_publish_and_list_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PackageStore(tmp)
            store.create_package("pkg1")
            store.publish_version("pkg1", 1, b"tar data v1", "initial")
            store.publish_version("pkg1", 2, b"tar data v2", "update")
            versions = store.list_versions("pkg1")
            assert len(versions) == 2
            assert versions[0]["version"] == 1
            assert versions[1]["version"] == 2

    def test_get_package_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PackageStore(tmp)
            store.create_package("pkg1")
            store.publish_version("pkg1", 1, b"hello-package")
            data = store.get_package_file("pkg1", 1)
            assert data == b"hello-package"

    def test_get_package_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PackageStore(tmp)
            assert store.get_package_file("nonexistent", 1) is None

    def test_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PackageStore(tmp)
            store.create_package("web_autotest", "Web UI testing")
            store.create_package("api_test", "API testing")
            results = store.search("web")
            assert len(results) == 1
            assert results[0]["name"] == "web_autotest"

    def test_search_all_on_empty_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PackageStore(tmp)
            store.create_package("a")
            store.create_package("b")
            assert len(store.search("")) == 2

    def test_get_version_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PackageStore(tmp)
            store.create_package("pkg1")
            store.publish_version("pkg1", 1, b"data", "first release")
            meta = store.get_version_meta("pkg1", 1)
            assert meta["version"] == 1
            assert meta["description"] == "first release"

    def test_get_version_meta_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PackageStore(tmp)
            assert store.get_version_meta("pkg1", 1) is None

    def test_get_package_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PackageStore(tmp)
            store.create_package("pkg1", "desc")
            meta = store.get_package_meta("pkg1")
            assert meta["name"] == "pkg1"
            assert meta["description"] == "desc"

    def test_get_package_meta_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PackageStore(tmp)
            assert store.get_package_meta("nonexistent") is None

    def test_delete_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PackageStore(tmp)
            store.create_package("pkg1")
            store.publish_version("pkg1", 1, b"data")
            store.delete_package("pkg1")
            assert store.get_package_meta("pkg1") is None

    def test_next_version_increments(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PackageStore(tmp)
            store.create_package("pkg1")
            assert store.next_version("pkg1") == 1
            store.publish_version("pkg1", 1, b"data")
            assert store.next_version("pkg1") == 2
            store.publish_version("pkg1", 2, b"data")
            assert store.next_version("pkg1") == 3

    def test_publish_with_tasks_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PackageStore(tmp)
            store.create_package("pkg-task")
            tasks = [{"name": "preprocess", "entrypoint": "pre.sh"},
                     {"name": "train", "entrypoint": "train.py"}]
            store.publish_version("pkg-task", 1, b"tarball", description="with tasks", tasks=tasks)
            meta = store.get_version_meta("pkg-task", 1)
            assert meta is not None
            assert meta["tasks"] == tasks
            assert meta["description"] == "with tasks"
            versions = store.list_versions("pkg-task")
            assert len(versions) == 1
            assert versions[0]["tasks"] == tasks
