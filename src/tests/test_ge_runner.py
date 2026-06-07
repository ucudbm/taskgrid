import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from ge.executor.runner import TaskRunner


class TestTaskRunner:

    def _make_runner(self, **kwargs):
        cfg = MagicMock()
        cfg.id = "ge-test"
        cfg.workdir_base = "/tmp/taskgrid-test/workspace"
        cfg.log_dir = "/tmp/taskgrid-test/logs"
        cfg.task_timeout = 3600
        cfg.retry_enabled = False
        cfg.retry_count = 0
        cfg.retry_enabled = False
        cfg.retry_count = 0
        slot_mgr = MagicMock()
        slot_mgr.acquire.return_value = True
        pkg_mgr = MagicMock()
        heartbeat = MagicMock()
        runner = TaskRunner(cfg, slot_mgr, pkg_mgr, heartbeat)
        if "extra" in kwargs:
            runner._extra = kwargs["extra"]
        return runner, cfg, slot_mgr, pkg_mgr, heartbeat

    def _make_task(self, **overrides):
        task = {
            "task_id": 1,
            "name": "test-task",
            "priority": "medium",
            "scheduler_section": {
                "target_ge": "ge-test",
                "timeout": 3600,
                "retry": 0,
            },
            "package_section": {
                "package_name": "test-pkg",
                "package_version": 1,
                "package_type": "shell",
                "entrypoint": "run.sh",
                "args": ["--verbose"],
            },
            "executor_section": {
                "env": {"MY_VAR": "hello"},
                "user": None,
            },
            "result_section": {},
        }
        task.update(overrides)
        return task

    def test_execute_no_slot(self):
        runner, _, slot_mgr, _, _ = self._make_runner()
        slot_mgr.acquire.return_value = False
        result = runner.execute(self._make_task())
        assert result is None

    def test_execute_success(self):
        runner, cfg, _, _, _ = self._make_runner()
        task = self._make_task()
        with patch.object(runner, "_run_once") as mock_run:
            mock_run.return_value = {
                "task_id": 1,
                "ge_id": "ge-test",
                "result_section": {
                    "status": "success",
                    "exit_code": 0,
                    "duration": 10,
                },
            }
            result = runner.execute(task)
            assert result["result_section"]["status"] == "success"
            assert result["result_section"]["exit_code"] == 0

    def test_execute_retry_flow(self):
        runner, cfg, _, _, _ = self._make_runner()
        cfg.retry_enabled = True
        cfg.retry_count = 2
        task = self._make_task()
        task["scheduler_section"]["retry"] = 2
        call_count = 0

        def _mock_run_once(t):
            nonlocal call_count
            call_count += 1
            return {
                "task_id": 1,
                "ge_id": "ge-test",
                "result_section": {
                    "status": "failed",
                    "exit_code": 1,
                    "duration": 5,
                },
            }

        with patch.object(runner, "_run_once", side_effect=_mock_run_once):
            result = runner.execute(task)
            assert call_count == 2

    def test_execute_retry_then_success(self):
        runner, cfg, _, _, _ = self._make_runner()
        cfg.retry_enabled = True
        cfg.retry_count = 3
        task = self._make_task()
        task["scheduler_section"]["retry"] = 3
        call_count = 0

        def _mock_run_once(t):
            nonlocal call_count
            call_count += 1
            status = "failed" if call_count < 3 else "success"
            return {
                "task_id": 1,
                "ge_id": "ge-test",
                "result_section": {"status": status, "exit_code": 0 if status == "success" else 1, "duration": 5},
            }

        with patch.object(runner, "_run_once", side_effect=_mock_run_once):
            result = runner.execute(task)
            assert call_count == 3
            assert result["result_section"]["status"] == "success"

    def test_cancel_running_task(self):
        runner, _, _, _, _ = self._make_runner()
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        runner._procs[1] = mock_proc
        runner.cancel(1)
        mock_proc.kill.assert_called_once()
        assert 1 not in runner._procs

    def test_cancel_not_running(self):
        runner, _, _, _, _ = self._make_runner()
        runner.cancel(999)
        assert 999 not in runner._procs

    def test_build_cmd_shell(self):
        runner, _, _, _, _ = self._make_runner()
        with patch("sys.platform", "linux"):
            cmd = runner._build_cmd(Path("/work"), "run.sh", ["--arg"], "shell")
            assert len(cmd) >= 2
            assert str(cmd[-2]).endswith("run.sh")

    def test_build_cmd_python(self):
        runner, _, _, _, _ = self._make_runner()
        with patch("sys.platform", "linux"):
            with patch.object(Path, "exists", return_value=True):
                cmd = runner._build_cmd(Path("/work"), "train.py", ["--lr=0.01"], "python")
                assert cmd[0].endswith("python")

    def test_build_cmd_docker(self):
        runner, _, _, _, _ = self._make_runner()
        cmd = runner._build_cmd(Path("/work"), "myimage:latest", [], "docker")
        assert cmd[0] == "docker"
        assert "run" in cmd

    def test_run_once_raises_exception(self):
        runner, cfg, _, _, _ = self._make_runner()
        task = self._make_task()
        with patch.object(runner, "_check_docker", return_value=False):
            with patch("ge.executor.runner.create_venv", side_effect=Exception("boom")):
                result = runner._run_once(task)
                assert result["result_section"]["status"] == "failed"
                assert "boom" in result["result_section"]["error_msg"]

    def test_was_cancelled_during_run(self):
        runner, cfg, _, _, _ = self._make_runner()
        task = self._make_task()
        workdir = Path(cfg.workdir_base) / "1"
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / "run.sh").write_text("echo hello")
        try:
            with patch.object(runner, "_check_docker", return_value=False):
                with patch("ge.executor.runner.create_venv"):
                    with patch("ge.executor.runner.destroy_venv"):
                        with patch("subprocess.Popen") as mock_popen:
                            proc = MagicMock()
                            proc.returncode = -9
                            proc.stdout = []
                            mock_popen.return_value = proc
                            runner._cancelled.add(1)
                            result = runner._run_once(task)
                            assert result["result_section"]["status"] == "cancelled"
        finally:
            import shutil
            shutil.rmtree(workdir.parent, ignore_errors=True)
