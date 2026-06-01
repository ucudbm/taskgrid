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
import time
import threading
from pathlib import Path
from .config import GEConfig
from .log import get_sys_logger, setup_logging
from .heartbeat import HeartbeatReporter
from .poller import TaskPoller
from .executor.slot import SlotManager
from .executor.runner import TaskRunner
from .package.downloader import PackageManager
from .ota.updater import OTAUpdater
from ._utils import gzip_json
from ._client import DNSResilientClient


class Engine:
    def __init__(self, cfg: GEConfig):
        self._cfg = cfg
        setup_logging(cfg)
        self._log = get_sys_logger()

        self._slots = SlotManager(self._cfg.total_slots)
        self._pkg_mgr = PackageManager(cfg)
        self._client = DNSResilientClient(timeout=10, headers=self._cfg.auth_headers)
        self._heartbeat = HeartbeatReporter(cfg, self._slots, self._client)
        self._poller = TaskPoller(cfg, client=self._client)
        self._runner = TaskRunner(cfg, self._slots, self._pkg_mgr, heartbeat=self._heartbeat)
        self._updater = OTAUpdater(cfg.ota_enabled, cfg.ota_update_url)
        self._running = False

    def start(self):
        self._running = True
        self._register()
        self._log.info("GE %s started (poll=%ss, heartbeat=%ss)",
                       self._cfg.id, self._cfg.polling_interval,
                       self._cfg.heartbeat_interval)

        if self._cfg.task_log_retention_days > 0 or self._cfg.temp_data_retention_days > 0:
            self._start_retention_cleanup()

        last_hb = 0.0
        while self._running:
            try:
                now = time.time()
                if now - last_hb >= self._cfg.heartbeat_interval:
                    cancelled = self._heartbeat.send()
                    last_hb = now
                    self._updater.check_and_update()

                    cancelled_tasks = (cancelled or {}).get("cancelled_task_ids", [])
                    for ctid in cancelled_tasks:
                        self._log.info("Cancelling task %s per GS request", ctid)
                        self._runner.cancel(ctid)

                if self._slots.idle > 0:
                    tasks = self._poller.poll(self._slots.idle)
                    for task in tasks:
                        self._dispatch(task)

                time.sleep(self._cfg.polling_interval)

            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                self._log.exception("Engine loop error: %s", e)
                time.sleep(5)

    def stop(self):
        self._log.info("GE %s shutting down", self._cfg.id)
        self._running = False
        self._poller.close()
        self._pkg_mgr.close()
        self._client.close()

    def _start_retention_cleanup(self):
        def _cleanup_loop():
            while self._running:
                time.sleep(86400)
                self._cleanup_old_files()

        t = threading.Thread(target=_cleanup_loop, daemon=True)
        t.start()
        self._log.info("Retention cleanup started (interval=24h)")

    def _cleanup_old_files(self):
        now = time.time()

        log_days = self._cfg.task_log_retention_days
        if log_days > 0:
            log_cutoff = now - log_days * 86400
            for root, dirs, files in os.walk(self._cfg.log_dir):
                for name in files:
                    path = Path(root) / name
                    try:
                        if path.stat().st_mtime < log_cutoff:
                            path.unlink()
                    except OSError:
                        pass
                for name in dirs:
                    path = Path(root) / name
                    try:
                        if path.stat().st_mtime < log_cutoff:
                            shutil.rmtree(path, ignore_errors=True)
                    except OSError:
                        pass

        temp_days = self._cfg.temp_data_retention_days
        if temp_days > 0:
            temp_cutoff = now - temp_days * 86400
            cache_dir = Path(self._cfg.package_cache_dir)
            if cache_dir.exists():
                for item in cache_dir.iterdir():
                    if item.is_dir():
                        try:
                            if item.stat().st_mtime < temp_cutoff:
                                shutil.rmtree(item, ignore_errors=True)
                        except OSError:
                            pass

        self._log.info("Retention cleanup done")

    def _register(self):
        try:
            payload = {
                "ge_id": self._cfg.id,
                "total_slots": self._slots.total,
                "pool": self._cfg.pool,
                "os_tag": self._cfg.os_tag,
                "device_id": self._cfg.device_id,
            }
            body, gzip_headers = gzip_json(payload)
            resp = self._client.post(
                self._cfg.register_url,
                content=body,
                headers=gzip_headers,
                timeout=5,
            )
            if resp.status_code == 409:
                self._log.warning("GE ID conflict, re-registering...")
                payload["force"] = True
                body, _ = gzip_json(payload)
                resp = self._client.post(
                    self._cfg.register_url,
                    content=body,
                    headers=gzip_headers,
                    timeout=5,
                )
                resp.raise_for_status()
                data = resp.json()
                new_id = data.get("ge_id")
                if new_id and new_id != self._cfg.id:
                    self._log.info("GS renamed GE to %s", new_id)
                    self._cfg.id = new_id
            else:
                resp.raise_for_status()
            self._log.info("Registered with GS as %s", self._cfg.id)
        except Exception as e:
            self._log.error("Registration failed: %s", e)
            raise

    def _dispatch(self, task: dict):
        task_id = task["task_id"]
        self._log.info("Dispatching task %s", task_id)
        self._heartbeat.running_task_id = task_id

        def _run():
            result = self._runner.execute(task)
            self._heartbeat.running_task_id = None
            self._heartbeat.clear_progress(task_id)
            if result is not None:
                self._submit_result(result)

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def _submit_result(self, result: dict):
        try:
            body, gzip_headers = gzip_json(result)
            resp = self._client.post(
                self._cfg.result_url, content=body, headers=gzip_headers, timeout=10
            )
            resp.raise_for_status()
            self._log.info("Result for task %s submitted", result["task_id"])
        except Exception as e:
            self._log.error("Failed to submit result: %s", e)
