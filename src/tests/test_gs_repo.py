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
import json
import tempfile
from pathlib import Path

from gs.db.repository import Repository


def test_create_and_get_task():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        repo = Repository(db_path)
        task_id = repo.create_task({
            "name": "test-task",
            "priority": "high",
            "description": "a test",
            "package_name": "test-pkg",
            "package_version": 1,
            "package_type": "shell",
            "entrypoint": "run.sh",
            "args": ["--verbose"],
            "env": {"KEY": "val"},
            "target_ge": "ge-1",
            "pool": "pool-a",
            "os_tag": "linux",
            "device_id": "dev-1",
            "timeout": 100,
            "retry": 2,
            "user": "runner",
        })
        assert task_id > 0

        task = repo.get_task(task_id)
        assert task is not None
        assert task["name"] == "test-task"
        assert task["priority"] == "high"
        assert task["status"] == "pending"
        assert json.loads(task["args"]) == ["--verbose"]
        assert json.loads(task["env"]) == {"KEY": "val"}
        assert task["target_ge"] == "ge-1"
        assert task["retry"] == 2

        task2 = repo.get_task(99999)
        assert task2 is None
    finally:
        Path(db_path).unlink(missing_ok=True)


def test_list_tasks():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        repo = Repository(db_path)
        for i in range(5):
            repo.create_task({
                "name": f"task-{i}",
                "priority": "medium" if i % 2 == 0 else "high",
                "package_name": "pkg",
                "package_version": 1,
                "entrypoint": "run.sh",
            })

        tasks = repo.list_tasks()
        assert len(tasks) == 5

        high_tasks = repo.list_tasks(priority="high")
        assert len(high_tasks) == 2

        tasks_p1 = repo.list_tasks(limit=2, offset=0)
        assert len(tasks_p1) == 2

        tasks_p2 = repo.list_tasks(limit=2, offset=2)
        assert len(tasks_p2) == 2
    finally:
        Path(db_path).unlink(missing_ok=True)


def test_update_task_status():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        repo = Repository(db_path)
        task_id = repo.create_task({
            "name": "test",
            "package_name": "pkg",
            "package_version": 1,
            "entrypoint": "run.sh",
        })

        ok = repo.update_task_status(task_id, "running", start_time="2024-01-01T00:00:00Z")
        assert ok

        task = repo.get_task(task_id)
        assert task["status"] == "running"

        ok = repo.update_task_status(task_id, "success", exit_code=0)
        assert ok

        task = repo.get_task(task_id)
        assert task["status"] == "success"
        assert task["exit_code"] == 0
    finally:
        Path(db_path).unlink(missing_ok=True)


def test_ge_operations():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        repo = Repository(db_path)
        ok = repo.register_ge("ge-1", pool="qa", os_tag="linux", total_slots=4)
        assert ok

        dup = repo.register_ge("ge-1")
        assert not dup

        ge = repo.get_ge("ge-1")
        assert ge is not None
        assert ge["ge_id"] == "ge-1"
        assert ge["pool"] == "qa"
        assert ge["os_tag"] == "linux"
        assert ge["total_slots"] == 4
        assert ge["state"] == "online"

        repo.update_ge("ge-1", idle_slots=2, state="running")

        ge = repo.get_ge("ge-1")
        assert ge["idle_slots"] == 2
        assert ge["state"] == "running"

        ge_missing = repo.get_ge("ge-nonexistent")
        assert ge_missing is None

        all_ge = repo.list_ge()
        assert len(all_ge) == 1

        repo.register_ge("ge-2", total_slots=2)
        online = repo.list_online_ge()
        assert len(online) == 2

        repo.update_ge("ge-2", state="offline")
        online = repo.list_online_ge()
        assert len(online) == 1
    finally:
        Path(db_path).unlink(missing_ok=True)


def test_save_and_get_result():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        repo = Repository(db_path)
        task_id = repo.create_task({
            "name": "test",
            "package_name": "pkg",
            "package_version": 1,
            "entrypoint": "run.sh",
        })

        result = {
            "status": "success",
            "exit_code": 0,
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-01T00:01:00Z",
            "duration": 60,
            "log_file": "/logs/1.log",
            "output_files": ["/output/report.html"],
            "error_msg": None,
        }

        ok = repo.save_result(task_id, result)
        assert ok

        dup = repo.save_result(task_id, result)
        assert not dup

        saved = repo.get_result(task_id)
        assert saved is not None
        assert saved["status"] == "success"
        assert saved["exit_code"] == 0
    finally:
        Path(db_path).unlink(missing_ok=True)
