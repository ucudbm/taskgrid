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
from ge.package.cache import PackageCache


class TestPackageCache:
    def test_put_and_get(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = PackageCache(tmp)
            p = cache.put("web_test", 1, b"hello package")
            assert p.exists()

            cached = cache.get("web_test", 1)
            assert cached is not None
            assert cached.read_bytes() == b"hello package"

    def test_cache_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = PackageCache(tmp)
            assert cache.get("unknown", 99) is None

    def test_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = PackageCache(tmp)
            cache.put("pkg", 1, b"data")
            cache.clear()
            assert cache.get("pkg", 1) is None
