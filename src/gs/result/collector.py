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

from ..db.repository import Repository
from ..scheduler.router import TaskScheduler


class ResultCollector:
    def __init__(self, scheduler: TaskScheduler, repo: Repository):
        self._scheduler = scheduler
        self._repo = repo

    def collect(self, payload: dict) -> bool:
        result_section = payload.get("result_section", {})
        task_id = payload.get("task_id")

        if task_id is None:
            return False

        return self._scheduler.submit_result(payload)

    def get_result(self, task_id: int) -> dict:
        result = self._repo.get_result(task_id)
        if result is None:
            task = self._repo.get_task(task_id)
            if task is None:
                return None
            return {
                "task_id": task["id"],
                "status": task["status"],
                "result_section": {
                    "status": task["status"],
                    "exit_code": task.get("exit_code"),
                    "start_time": task.get("start_time"),
                    "end_time": task.get("end_time"),
                    "duration": task.get("duration"),
                    "log_file": task.get("log_file"),
                    "output_files": json.loads(task.get("output_files", "[]")),
                    "error_msg": task.get("error_msg"),
                },
            }
        return {
            "task_id": result["task_id"],
            "status": result["status"],
            "result_section": {
                "status": result["status"],
                "exit_code": result.get("exit_code"),
                "start_time": result.get("start_time"),
                "end_time": result.get("end_time"),
                "duration": result.get("duration"),
                "log_file": result.get("log_file"),
                "output_files": json.loads(result.get("output_files", "[]")),
                "error_msg": result.get("error_msg"),
                "reported_at": result.get("reported_at"),
            },
        }
