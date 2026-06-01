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
import random
import time
from datetime import datetime, timezone
from typing import Optional

from ..db.repository import Repository
from ..redis_client.state_cache import StateCache
from .priority_queue import PriorityQueue
from .lock_manager import LockManager


class TaskScheduler:
    def __init__(self, repo: Repository, queue: PriorityQueue,
                 lock_mgr: LockManager, cache: StateCache):
        self._repo = repo
        self._queue = queue
        self._lock_mgr = lock_mgr
        self._cache = cache

    def create_and_enqueue(self, task_data: dict) -> dict:
        task_id = self._repo.create_task(task_data)
        priority = task_data.get("priority", "medium")
        target_ge = task_data.get("target_ge")
        device_id = task_data.get("device_id")
        pool = task_data.get("pool")
        os_tag = task_data.get("os_tag")

        if target_ge:
            self._queue.push(task_id, priority, ge_id=target_ge)
        elif device_id:
            self._queue.push_with_device(task_id, priority, device_id)
        elif pool:
            self._queue.push_with_pool(task_id, priority, pool)
        elif os_tag:
            self._queue.push_with_os_tag(task_id, priority, os_tag)
        else:
            self._queue.push(task_id, priority)

        task_row = self._repo.get_task(task_id)
        return self._row_to_response(task_row)

    def poll_task(self, ge_id: str, idle_slots: int) -> list[dict]:
        ge_row = self._repo.get_ge(ge_id)
        if ge_row is None:
            return []

        pool = ge_row.get("pool")
        os_tag = ge_row.get("os_tag")
        device_id = ge_row.get("device_id")
        tasks = []
        remaining_idle = ge_row.get("idle_slots", 0)

        for _ in range(min(idle_slots, remaining_idle)):
            task_id = self._queue.pop_by_routing(ge_id, pool, os_tag, device_id)
            if task_id is None:
                break

            task = self._repo.get_task(task_id)
            if task is None:
                continue

            lock_value = self._lock_mgr.lock_task(task_id)
            if lock_value is None:
                self._queue.push(task_id, task.get("priority", "medium"))
                continue

            now_dt = datetime.now(timezone.utc)
            now = now_dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now_dt.microsecond // 1000:03d}Z"
            workdir = task.get("workdir") or f"/tmp/taskgrid/workspace/{task_id}"
            env = json.loads(task.get("env", "{}"))
            args = json.loads(task.get("args", "[]"))

            remaining_idle -= 1

            task_resp = {
                "task_id": task_id,
                "name": task["name"],
                "priority": task["priority"],
                "description": task.get("description", ""),
                "scheduler_section": {
                    "target_ge": task.get("target_ge"),
                    "pool": task.get("pool"),
                    "os_tag": task.get("os_tag"),
                    "device_id": task.get("device_id"),
                    "timeout": task.get("timeout", 3600),
                    "retry": task.get("retry", 0),
                },
                "package_section": {
                    "package_name": task["package_name"],
                    "package_version": task["package_version"],
                    "package_type": task.get("package_type", "shell"),
                    "entrypoint": task["entrypoint"],
                    "args": args,
                },
                "executor_section": {
                    "workdir": workdir,
                    "env": env,
                    "user": task.get("user"),
                },
                "result_section": {},
            }

            self._repo.update_task_status(
                task_id, "running",
                start_time=now,
            )
            self._repo.update_ge(
                ge_id,
                state="running" if remaining_idle <= 0 else "online",
                idle_slots=remaining_idle,
                current_task_id=task_id,
            )

            tasks.append(task_resp)

        return tasks

    def cancel_task(self, task_id: int) -> Optional[dict]:
        task = self._repo.get_task(task_id)
        if task is None:
            return None
        if task["status"] in ("success", "failed", "cancelled", "timeout"):
            return {"task_id": task_id, "status": task["status"], "message": "already finalised"}

        if task["status"] == "pending":
            priority = task.get("priority", "medium")
            target_ge = task.get("target_ge")
            device_id = task.get("device_id")
            pool = task.get("pool")
            os_tag = task.get("os_tag")
            if target_ge:
                self._queue.remove(task_id, priority, ge_id=target_ge)
            elif device_id:
                self._queue.remove_from_device(task_id, priority, device_id)
            elif pool:
                self._queue.remove_from_pool(task_id, priority, pool)
            elif os_tag:
                self._queue.remove_from_os_tag(task_id, priority, os_tag)
            else:
                self._queue.remove(task_id, priority)
        else:
            self._cache.set_cancel_flag(task_id)
        self._repo.update_task_status(task_id, "cancelled")
        return {"task_id": task_id, "status": "cancelled"}

    def submit_result(self, result_data: dict) -> bool:
        task_id = result_data.get("task_id")
        if task_id is None:
            return False

        result_section = result_data.get("result_section", {})
        status = result_section.get("status", "failed")
        now_dt = datetime.now(timezone.utc)
        now = now_dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now_dt.microsecond // 1000:03d}Z"

        self._repo.save_result(task_id, result_section)
        self._repo.update_task_status(
            task_id, status,
            exit_code=result_section.get("exit_code"),
            end_time=result_section.get("end_time", now),
            duration=result_section.get("duration"),
            log_file=result_section.get("log_file"),
            output_files=json.dumps(result_section.get("output_files", [])),
            error_msg=result_section.get("error_msg"),
        )
        self._cache.remove_cancel_flag(task_id)

        ge_id = result_data.get("ge_id")
        if ge_id:
            ge_row = self._repo.get_ge(ge_id)
            if ge_row:
                self._repo.update_ge(
                    ge_id,
                    state="online",
                    idle_slots=min(ge_row["total_slots"], ge_row["idle_slots"] + 1),
                    current_task_id=None,
                )

        return True

    def _row_to_response(self, row: dict) -> dict:
        if row is None:
            return None
        return {
            "task_id": row["id"],
            "name": row["name"],
            "priority": row["priority"],
            "description": row.get("description", ""),
            "scheduler_section": {
                "target_ge": row.get("target_ge"),
                "pool": row.get("pool"),
                "os_tag": row.get("os_tag"),
                "device_id": row.get("device_id"),
                "timeout": row.get("timeout", 3600),
                "retry": row.get("retry", 0),
            },
            "package_section": {
                "package_name": row["package_name"],
                "package_version": row["package_version"],
                "package_type": row.get("package_type", "shell"),
                "entrypoint": row["entrypoint"],
                "args": json.loads(row.get("args", "[]")),
            },
            "executor_section": {
                "workdir": row.get("workdir"),
                "env": json.loads(row.get("env", "{}")),
                "user": row.get("user"),
            },
            "result_section": {},
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
