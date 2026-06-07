import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from gs.db.repository import Repository
from gs.scheduler.router import TaskScheduler


def _make_repo():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = f.name
    f.close()
    repo = Repository(db_path)
    repo.register_ge("ge-1", pool="pool-a", os_tag="linux", total_slots=2)
    return repo, db_path


def _make_scheduler(repo=None):
    if repo is None:
        repo, _ = _make_repo()
    queue = MagicMock()
    lock_mgr = MagicMock()
    cache = MagicMock()
    scheduler = TaskScheduler(repo, queue, lock_mgr, cache)
    return scheduler, repo, queue, lock_mgr, cache


def _create_task(repo, **overrides):
    data = {
        "name": "test-task",
        "priority": "medium",
        "package_name": "pkg",
        "package_version": 1,
        "entrypoint": "run.sh",
    }
    data.update(overrides)
    return repo.create_task(data)


class TestTaskScheduler:

    def test_create_and_enqueue(self):
        repo, db_path = _make_repo()
        try:
            scheduler, _, queue, _, _ = _make_scheduler(repo)
            resp = scheduler.create_and_enqueue({
                "name": "my-task",
                "priority": "high",
                "package_name": "pkg",
                "package_version": 1,
                "entrypoint": "run.sh",
                "target_ge": "ge-1",
            })
            assert resp["name"] == "my-task"
            assert resp["priority"] == "high"
            assert resp["status"] == "pending"
            queue.push.assert_called_once_with(
                resp["task_id"], "high",
                ge_id="ge-1", device_id=None, pool=None, os_tag=None,
            )
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_poll_task_no_ge(self):
        repo, db_path = _make_repo()
        try:
            scheduler, _, _, _, _ = _make_scheduler(repo)
            tasks = scheduler.poll_task("ge-nonexistent", 2)
            assert tasks == []
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_poll_task_empty_queue(self):
        repo, db_path = _make_repo()
        try:
            scheduler, _, queue, _, _ = _make_scheduler(repo)
            queue.pop_by_routing.return_value = None
            tasks = scheduler.poll_task("ge-1", 2)
            assert tasks == []
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_poll_task_lock_failure(self):
        repo, db_path = _make_repo()
        try:
            repo.update_ge("ge-1", idle_slots=2)
            task_id = _create_task(repo, target_ge="ge-1")
            scheduler, _, queue, lock_mgr, _ = _make_scheduler(repo)
            queue.pop_by_routing.side_effect = [task_id, None]
            lock_mgr.lock_task.return_value = None
            tasks = scheduler.poll_task("ge-1", 2)
            assert tasks == []
            queue.push.assert_called_once_with(task_id, "medium")
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_poll_task_success_one(self):
        repo, db_path = _make_repo()
        try:
            task_id = _create_task(repo, target_ge="ge-1", priority="high")
            repo.update_ge("ge-1", idle_slots=2)
            scheduler, _, queue, lock_mgr, _ = _make_scheduler(repo)
            queue.pop_by_routing.side_effect = [task_id, None]
            lock_mgr.lock_task.return_value = "lock-123"
            tasks = scheduler.poll_task("ge-1", 1)
            assert len(tasks) == 1
            t = tasks[0]
            assert t["task_id"] == task_id
            assert t["scheduler_section"]["target_ge"] == "ge-1"
            assert t["package_section"]["package_name"] == "pkg"
            db_task = repo.get_task(task_id)
            assert db_task["status"] == "running"
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_poll_task_routing_target_ge(self):
        repo, db_path = _make_repo()
        try:
            repo.register_ge("ge-a", total_slots=2)
            repo.register_ge("ge-b", total_slots=2)
            repo.update_ge("ge-a", idle_slots=2)
            repo.update_ge("ge-b", idle_slots=2)

            tid_a = _create_task(repo, name="for-ge-a", target_ge="ge-a", priority="high")
            tid_b = _create_task(repo, name="for-ge-b", target_ge="ge-b", priority="high")

            scheduler_a, _, queue_a, lock_mgr_a, _ = _make_scheduler(repo)
            scheduler_b, _, queue_b, lock_mgr_b, _ = _make_scheduler(repo)

            lock_mgr_a.lock_task.return_value = "lock"
            lock_mgr_b.lock_task.return_value = "lock"

            queue_a.pop_by_routing.side_effect = [tid_a, None]
            tasks_a = scheduler_a.poll_task("ge-a", 2)
            assert len(tasks_a) == 1
            assert tasks_a[0]["task_id"] == tid_a

            queue_b.pop_by_routing.side_effect = [tid_b, None]
            tasks_b = scheduler_b.poll_task("ge-b", 2)
            assert len(tasks_b) == 1
            assert tasks_b[0]["task_id"] == tid_b
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_poll_task_routing_pool_os_device(self):
        repo, db_path = _make_repo()
        try:
            repo.register_ge("ge-pool", pool="pool-a", os_tag="linux",
                             device_id="dev-1", total_slots=2)
            repo.update_ge("ge-pool", idle_slots=2)

            scheduler, _, queue, lock_mgr, _ = _make_scheduler(repo)
            lock_mgr.lock_task.return_value = "lock"
            queue.pop_by_routing.return_value = None
            scheduler.poll_task("ge-pool", 2)
            queue.pop_by_routing.assert_called_with(
                "ge-pool", "pool-a", "linux", "dev-1",
            )
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_cancel_task_not_found(self):
        scheduler, _, _, _, _ = _make_scheduler()
        result = scheduler.cancel_task(99999)
        assert result is None

    def test_cancel_task_already_finalised(self):
        repo, db_path = _make_repo()
        try:
            tid = _create_task(repo)
            repo.update_task_status(tid, "success", exit_code=0)
            scheduler, _, _, _, _ = _make_scheduler(repo)
            result = scheduler.cancel_task(tid)
            assert result["message"] == "already finalised"
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_cancel_task_pending_removes_from_queue(self):
        repo, db_path = _make_repo()
        try:
            tid = _create_task(repo, target_ge="ge-1", priority="high")
            scheduler, _, queue, _, _ = _make_scheduler(repo)
            result = scheduler.cancel_task(tid)
            assert result["status"] == "cancelled"
            queue.remove.assert_called_once_with(
                tid, "high",
                ge_id="ge-1", device_id=None, pool=None, os_tag=None,
            )
            db_task = repo.get_task(tid)
            assert db_task["status"] == "cancelled"
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_cancel_task_running_sets_cancel_flag(self):
        repo, db_path = _make_repo()
        try:
            tid = _create_task(repo)
            repo.update_task_status(tid, "running", start_time="2024-01-01T00:00:00Z")
            scheduler, _, _, _, cache = _make_scheduler(repo)
            result = scheduler.cancel_task(tid)
            assert result["status"] == "cancelled"
            cache.set_cancel_flag.assert_called_once_with(tid)
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_submit_result_success(self):
        repo, db_path = _make_repo()
        try:
            tid = _create_task(repo)
            repo.update_task_status(tid, "running", start_time="2024-01-01T00:00:00Z")
            scheduler, _, _, _, cache = _make_scheduler(repo)
            result_data = {
                "task_id": tid,
                "ge_id": "ge-1",
                "result_section": {
                    "status": "success",
                    "exit_code": 0,
                    "duration": 42,
                    "end_time": "2024-01-01T00:01:00Z",
                    "log_file": "/logs/1.log",
                    "output_files": ["/output/report.html"],
                    "error_msg": None,
                },
            }
            ok = scheduler.submit_result(result_data)
            assert ok
            db_task = repo.get_task(tid)
            assert db_task["status"] == "success"
            assert db_task["exit_code"] == 0
            assert db_task["duration"] == 42
            cache.remove_cancel_flag.assert_called_once_with(tid)
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_submit_result_no_task_id(self):
        scheduler, _, _, _, _ = _make_scheduler()
        ok = scheduler.submit_result({})
        assert not ok

    def test_submit_result_updates_ge_slots(self):
        repo, db_path = _make_repo()
        try:
            repo.update_ge("ge-1", idle_slots=0, state="running")
            repo.register_ge("ge-2", total_slots=2)
            repo.update_ge("ge-2", idle_slots=0, state="running")

            tid1 = _create_task(repo)
            repo.update_task_status(tid1, "running", start_time="2024-01-01T00:00:00Z")
            tid2 = _create_task(repo)
            repo.update_task_status(tid2, "running", start_time="2024-01-01T00:00:00Z")

            scheduler, _, _, _, _ = _make_scheduler(repo)
            scheduler.submit_result({"task_id": tid1, "ge_id": "ge-1", "result_section": {"status": "success"}})
            scheduler.submit_result({"task_id": tid2, "ge_id": "ge-2", "result_section": {"status": "success"}})

            ge1 = repo.get_ge("ge-1")
            ge2 = repo.get_ge("ge-2")
            assert ge1["idle_slots"] == 1
            assert ge1["state"] == "online"
            assert ge2["idle_slots"] == 1
            assert ge2["state"] == "online"
        finally:
            Path(db_path).unlink(missing_ok=True)
