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
import platform
import subprocess
import sys
import threading
import shutil
import json
import zipfile
import time
from pathlib import Path
from ..config import GEConfig
from ..log import get_sys_logger, get_task_logger
from ..package.downloader import PackageManager
from .slot import SlotManager
from .._utils import timestamp_from_epoch
from .venv import create_venv, destroy_venv


class TaskRunner:
    def __init__(self, cfg: GEConfig, slot_mgr: SlotManager, pkg_mgr: PackageManager, heartbeat=None):
        self._cfg = cfg
        self._slots = slot_mgr
        self._pkg_mgr = pkg_mgr
        self._heartbeat = heartbeat
        self._procs: dict[int, subprocess.Popen] = {}
        self._proc_lock = threading.Lock()
        self._cancelled: set[int] = set()
        self._cancel_lock = threading.Lock()

    def cancel(self, task_id: int):
        with self._cancel_lock:
            self._cancelled.add(task_id)
        with self._proc_lock:
            proc = self._procs.pop(task_id, None)
        if proc:
            get_sys_logger().info("Cancelling task %s (pid %s)", task_id, proc.pid)
            proc.kill()

    def execute(self, task: dict) -> dict:
        task_id = task["task_id"]
        retry = task.get("scheduler_section", {}).get("retry", 0)
        if not self._cfg.retry_enabled:
            retry = 0
        elif retry == 0:
            retry = self._cfg.retry_count

        if not self._slots.acquire():
            get_sys_logger().error("Task %s: no slot available, discarding", task_id)
            return None

        try:
            while True:
                result = self._run_once(task)
                status = result["result_section"]["status"]

                if status == "failed" and retry > 1:
                    retry -= 1
                    get_sys_logger().info(
                        "Task %s failed, retrying (%s left)", task_id, retry - 1
                    )
                    continue

                return result
        finally:
            self._slots.release()

    def _check_docker(self) -> bool:
        try:
            subprocess.run(["docker", "info"], capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _run_once(self, task: dict) -> dict:
        task_id = task["task_id"]
        sch = task.get("scheduler_section", {})
        pkg = task.get("package_section", {})
        exe = task.get("executor_section", {})

        workdir = Path(exe.get("workdir", f"{self._cfg.workdir_base}/{task_id}"))
        task_log = get_task_logger(task_id, self._cfg.log_dir)

        try:
            task_log.info("Task %s started", task_id)
            workdir.mkdir(parents=True, exist_ok=True)
            if self._heartbeat:
                self._heartbeat.set_progress(task_id, "setting_up")

            docker_ok = self._check_docker()
            if docker_ok:
                task_log.info("Docker daemon: available")
            else:
                task_log.warning("Docker daemon: not available or not installed")

            create_venv(workdir)

            pkg_name = pkg.get("package_name")
            pkg_ver = int(pkg.get("package_version", 0))
            if pkg_name:
                if pkg_ver == 0:
                    pkg_ver = self._pkg_mgr.latest_version(pkg_name)
                self._pkg_mgr.fetch(pkg_name, pkg_ver, workdir)
                if self._heartbeat:
                    self._heartbeat.set_progress(task_id, "downloading")

            entrypoint = pkg.get("entrypoint", "")
            args = pkg.get("args", [])
            package_type = pkg.get("package_type", "shell")
            entry_path = workdir / entrypoint
            if not entry_path.exists():
                name = Path(entrypoint).name
                matches = sorted(
                    f.relative_to(workdir) for f in workdir.rglob(name)
                    if f.is_file() and ".venv" not in f.parts
                )
                hint = ""
                if matches:
                    hint = f"\n  Did you mean: '{matches[0]}'?"
                files = sorted(
                    f.relative_to(workdir) for f in workdir.rglob("*")
                    if f.is_file() and ".venv" not in f.parts
                )
                task_log.error(
                    "Entrypoint '%s' not found in %s.%s\n  Available files (top 30):\n  %s",
                    entrypoint, workdir, hint,
                    "\n  ".join(str(f) for f in files[:30])
                )
                raise FileNotFoundError(
                    f"Entrypoint '{entrypoint}' not found in {workdir}{hint}"
                )
            cmd = self._build_cmd(workdir, entrypoint, args, package_type)

            env = os.environ.copy()
            extra_env = exe.get("env", {})
            env.update(extra_env)

            preexec_fn = None
            user = exe.get("user")
            if user and sys.platform != "win32":
                import pwd
                try:
                    pw = pwd.getpwnam(user)
                    def _switch_user(u=pw.pw_uid, g=pw.pw_gid):
                        os.setgid(g)
                        os.setuid(u)
                    preexec_fn = _switch_user
                except KeyError:
                    get_sys_logger().warning(
                        "User %s not found, running as current user", user
                    )
                except OSError:
                    get_sys_logger().warning(
                        "Failed to switch to user %s, running as current user", user
                    )
            elif user:
                get_sys_logger().warning(
                    "User switching not supported on Windows, running as current user"
                )

            timeout = sch.get("timeout", self._cfg.task_timeout)
            start = time.time()
            if self._heartbeat:
                self._heartbeat.set_progress(task_id, "executing")
            script_dir = entry_path.parent
            popen_kwargs = dict(
                cwd=script_dir, env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            if preexec_fn is not None and sys.platform != "win32":
                popen_kwargs["preexec_fn"] = preexec_fn
            proc = subprocess.Popen(cmd, **popen_kwargs)

            def _read_stdout():
                for line in proc.stdout:
                    task_log.info(line.decode("utf-8", errors="replace").rstrip())

            with self._proc_lock:
                self._procs[task_id] = proc

            reader = threading.Thread(target=_read_stdout, daemon=True)
            reader.start()

            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

            with self._proc_lock:
                self._procs.pop(task_id, None)

            reader.join()
            end = time.time()
            exit_code = proc.returncode

            with self._cancel_lock:
                was_cancelled = task_id in self._cancelled
                self._cancelled.discard(task_id)

            artifacts = []
            output_dirs = [workdir / "output", workdir / "artifacts"]
            output_root = next((d for d in output_dirs if d.exists()), None)
            zip_path = workdir / f"output_{task_id}.zip"
            if output_root:
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in output_root.rglob("*"):
                        if f.is_file():
                            zf.write(f, f.relative_to(output_root))
            if output_root and zip_path.stat().st_size > 22:
                try:
                    url = self._pkg_mgr.upload_result_file(task_id, zip_path)
                    artifacts = [url]
                    task_log.info("Result file uploaded to %s", url)
                except Exception as e:
                    task_log.error("Failed to upload result file: %s", e)
                    artifacts = [str(zip_path)]

            if was_cancelled:
                status = "cancelled"
            elif exit_code == 0:
                status = "success"
            elif end - start >= timeout:
                status = "timeout"
            else:
                status = "failed"

            result = {
                "task_id": task_id,
                "ge_id": self._cfg.id,
                "result_section": {
                    "status": status,
                    "exit_code": exit_code,
                    "start_time": timestamp_from_epoch(start),
                    "end_time": timestamp_from_epoch(end),
                    "duration": int(end - start),
                    "log_file": f"{self._cfg.log_dir}/tasks/{task_id}/output.log",
                    "output_files": artifacts,
                    "error_msg": None if exit_code == 0 else f"exit code {exit_code}",
                },
            }
            task_log.info("Task %s finished: %s", task_id, status)
            return result

        except Exception as e:
            now = time.time()
            get_sys_logger().exception("Task %s exception", task_id)
            return {
                "task_id": task_id,
                "ge_id": self._cfg.id,
                "result_section": {
                    "status": "failed",
                    "exit_code": -1,
                    "start_time": timestamp_from_epoch(now),
                    "end_time": timestamp_from_epoch(now),
                    "duration": 0,
                    "log_file": f"{self._cfg.log_dir}/tasks/{task_id}/output.log",
                    "output_files": [],
                    "error_msg": str(e),
                },
            }
        finally:
            if self._heartbeat:
                self._heartbeat.clear_progress(task_id)
            destroy_venv(workdir)
            shutil.rmtree(workdir, ignore_errors=True)

    @staticmethod
    def _venv_python(workdir: Path) -> Path:
        if sys.platform == "win32":
            return workdir / ".venv" / "Scripts" / "python.exe"
        return workdir / ".venv" / "bin" / "python"

    def _build_cmd(self, workdir: Path, entrypoint: str, args: list, package_type: str = "shell") -> list:
        entry_path = workdir / entrypoint
        if package_type == "shell":
            shell = os.environ.get("SHELL", "/bin/bash") if sys.platform != "win32" else "cmd.exe"
            return [shell, str(entry_path), *args]
        if package_type == "python":
            venv_python = self._venv_python(workdir)
            python = str(venv_python) if venv_python.exists() else "python3"
            return [python, str(entry_path), *args]
        if package_type == "docker":
            return ["docker", "run", "--rm", "-v", f"{workdir}:/workspace", str(entry_path), *args]
        if entrypoint.endswith(".sh") and sys.platform != "win32":
            return ["/bin/bash", str(entry_path), *args]
        venv_python = self._venv_python(workdir)
        if venv_python.exists():
            return [str(venv_python), str(entry_path), *args]
        return [str(entry_path), *args]
