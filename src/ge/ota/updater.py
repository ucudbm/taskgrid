import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

import httpx
from packaging.version import parse as parse_version

from .. import _utils
from ..log import get_sys_logger
from .._utils import get_version as get_current_ge_version


class OTAUpdater:
    def __init__(self, enabled: bool, update_url: str | None = None):
        self._enabled = enabled
        self._update_url = update_url
        self._checked_version: str | None = None
        self._slot_mgr = None

    def set_slot_manager(self, slot_mgr):
        self._slot_mgr = slot_mgr

    def check_and_update(self, heartbeat_response: dict | None = None):
        if not self._enabled:
            return
        log = get_sys_logger()

        url = None
        if heartbeat_response:
            url = heartbeat_response.get("update_url")
        if not url:
            url = self._update_url
        if not url:
            return

        target_version_str = self._resolve_version(url, heartbeat_response)
        if not target_version_str:
            return
        if target_version_str == self._checked_version:
            return

        current_version_str = get_current_ge_version()
        try:
            if parse_version(target_version_str) <= parse_version(current_version_str):
                log.info("GE already at %s, target %s, skipping", current_version_str, target_version_str)
                self._checked_version = target_version_str
                return
        except Exception:
            log.warning("Cannot parse versions: current=%s target=%s, falling back to string compare", current_version_str, target_version_str)
            if target_version_str == current_version_str:
                return

        if self._slot_mgr and self._slot_mgr.used > 0:
            log.info("OTA update deferred: %s slot(s) in use", self._slot_mgr.used)
            return

        self._checked_version = target_version_str

        log.info("OTA update: %s -> %s at %s", current_version_str, target_version_str, url)

        try:
            update_dir = Path(tempfile.mkdtemp(prefix="ge_ota_"))
            archive_path = update_dir / "update.tar.gz"

            log.info("Downloading update from %s", url)
            resp = httpx.get(url, follow_redirects=True, timeout=120)
            resp.raise_for_status()
            archive_path.write_bytes(resp.content)
            log.info("Downloaded %d bytes", len(resp.content))

            sha256_url = url + ".sha256"
            try:
                sha_resp = httpx.get(sha256_url, timeout=30)
                sha_resp.raise_for_status()
                expected_hash = sha_resp.text.strip().split()[0].lower()
                actual_hash = hashlib.sha256(resp.content).hexdigest().lower()
                if actual_hash != expected_hash:
                    log.error("SHA256 mismatch: expected %s, got %s", expected_hash, actual_hash)
                    return
                log.info("Checksum verified")
            except (httpx.HTTPError, OSError):
                log.warning("No SHA256 available at %s, skipping checksum", sha256_url)

            extract_dir = update_dir / "extracted"
            extract_dir.mkdir()
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(extract_dir)
            log.info("Extracted to %s", extract_dir)

            ge_root = Path(_utils.__file__).parent
            ge_root = ge_root.resolve()
            log.info("GE install root: %s", ge_root)

            candidate = extract_dir / "ge"
            if not candidate.exists():
                children = list(extract_dir.iterdir())
                if children:
                    candidate = children[0] / "ge"
            if not candidate.exists() or not (candidate / "_utils.py").exists():
                log.error("Update archive does not contain valid ge/ package")
                log.info("Contents: %s", list(extract_dir.rglob("*")))
                return

            backup_dir = ge_root.parent / f"ge.bak.{int(time.time())}"
            log.info("Backing up current GE to %s", backup_dir)
            shutil.copytree(ge_root, backup_dir)

            for item in ge_root.iterdir():
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink()
            for item in candidate.iterdir():
                dest = ge_root / item.name
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

            log.info("Update applied, restarting...")

            import ge.main
            main_path = Path(ge.main.__file__).resolve()
            python = sys.executable
            args = [python, str(main_path)]
            if "-c" in sys.argv:
                idx = sys.argv.index("-c")
                args.extend(sys.argv[idx:idx + 2])
            log.info("Exec: %s", " ".join(args))
            os.execv(python, args)

        except Exception as e:
            log.exception("OTA update failed: %s", e)

    @staticmethod
    def _resolve_version(url: str, heartbeat_response: dict | None = None) -> str | None:
        if heartbeat_response and heartbeat_response.get("update_version"):
            return str(heartbeat_response["update_version"])
        try:
            return url.rsplit("/", 1)[-1].replace(".tar.gz", "")
        except Exception:
            return None
