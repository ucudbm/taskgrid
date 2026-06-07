import io
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from ge.package.downloader import PackageManager


class TestPackageManager:

    def _make_mock_cfg(self, cache_dir: str):
        cfg = MagicMock()
        cfg.gp_url = "http://localhost:9000"
        cfg.package_cache_dir = cache_dir
        cfg.auth_headers = {}
        return cfg

    def _make_tar(self, files: dict[str, str]) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            for name, content in files.items():
                info = tarfile.TarInfo(name=name)
                data = content.encode()
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    def test_fetch_cache_hit(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            with tempfile.TemporaryDirectory() as dest_dir:
                cfg = self._make_mock_cfg(cache_dir)
                mgr = PackageManager(cfg)
                mgr._client = MagicMock()

                content = self._make_tar({"hello.txt": "world"})
                cached_path = mgr._cache.put("mypkg", 1, content)

                mgr.fetch("mypkg", 1, Path(dest_dir))
                assert (Path(dest_dir) / "hello.txt").exists()
                assert (Path(dest_dir) / "hello.txt").read_text() == "world"
                mgr._client.stream.assert_not_called()

    def test_fetch_cache_miss(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            with tempfile.TemporaryDirectory() as dest_dir:
                cfg = self._make_mock_cfg(cache_dir)
                mgr = PackageManager(cfg)
                mgr._client = MagicMock()

                content = self._make_tar({"run.sh": "echo hello"})
                mock_resp = MagicMock()
                mock_resp.__enter__.return_value = mock_resp
                mock_resp.read.return_value = content
                mgr._client.stream.return_value = mock_resp

                mgr.fetch("newpkg", 1, Path(dest_dir))
                assert (Path(dest_dir) / "run.sh").exists()
                assert (Path(dest_dir) / "run.sh").read_text() == "echo hello"
                mgr._client.stream.assert_called_once_with("GET", "http://localhost:9000/api/packages/newpkg/versions/1")
                cached = mgr._cache.get("newpkg", 1)
                assert cached is not None

    def test_fetch_cache_miss_and_reuse(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            with tempfile.TemporaryDirectory() as dest1:
                with tempfile.TemporaryDirectory() as dest2:
                    cfg = self._make_mock_cfg(cache_dir)
                    mgr = PackageManager(cfg)
                    mgr._client = MagicMock()

                    content = self._make_tar({"data.txt": "cached-content"})
                    mock_resp = MagicMock()
                    mock_resp.__enter__.return_value = mock_resp
                    mock_resp.read.return_value = content
                    mgr._client.stream.return_value = mock_resp

                    mgr.fetch("cached-pkg", 2, Path(dest1))
                    assert (Path(dest1) / "data.txt").read_text() == "cached-content"
                    assert mgr._client.stream.call_count == 1

                    mgr.fetch("cached-pkg", 2, Path(dest2))
                    assert (Path(dest2) / "data.txt").read_text() == "cached-content"
                    assert mgr._client.stream.call_count == 1

    def test_latest_version(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            cfg = self._make_mock_cfg(cache_dir)
            mgr = PackageManager(cfg)
            mgr._client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.json.return_value = [{"version": 1}, {"version": 3}, {"version": 2}]
            mgr._client.get.return_value = mock_resp
            ver = mgr.latest_version("some-pkg")
            assert ver == 3
            mgr._client.get.assert_called_once_with(
                "http://localhost:9000/api/packages/some-pkg/versions",
            )

    def test_latest_version_no_versions(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            cfg = self._make_mock_cfg(cache_dir)
            mgr = PackageManager(cfg)
            mgr._client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.json.return_value = []
            mgr._client.get.return_value = mock_resp
            import pytest
            with pytest.raises(ValueError, match="No versions found"):
                mgr.latest_version("empty-pkg")

    def test_upload_result_file(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = self._make_mock_cfg(cache_dir)
                mgr = PackageManager(cfg)
                mgr._client = MagicMock()
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"url": "http://gp/results/42/files/report.html"}
                mgr._client.post.return_value = mock_resp

                filepath = Path(tmp) / "report.html"
                filepath.write_text("test report")
                url = mgr.upload_result_file(42, filepath)
                assert url == "http://gp/results/42/files/report.html"
                mgr._client.post.assert_called_once()
