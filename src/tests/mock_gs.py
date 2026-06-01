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
import gzip
import json
import os
import time
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

_STATE_FILE = "/tmp/taskgrid/gs_state.json"
_AUTH_TOKEN = os.environ.get("TASKGRID_TOKEN", "")

# Endpoints that don't require auth (register + heartbeat)
_NO_AUTH_PATHS = ("/api/ge/register", "/api/ge/heartbeat", "/api/tasks/poll", "/api/tasks/result")


def _gs_timestamp():
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}"


def _gs_log(msg):
    print(f"{_gs_timestamp()} [GS] [INFO] {msg}")


def _load_state():
    try:
        with open(_STATE_FILE) as f:
            data = json.load(f)
            _gs_log(f"Loaded state: {len(data.get('task_queue', []))} pending task(s)")
            return data.get("task_queue", []), data.get("task_id_counter", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return [], 0


def _save_state(task_queue, task_id_counter):
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    with open(_STATE_FILE, "w") as f:
        json.dump({"task_queue": task_queue, "task_id_counter": task_id_counter}, f)


class MockGSHandler(BaseHTTPRequestHandler):
    ge_nodes = {}
    cancelled = {}

    task_queue, task_id_counter = _load_state()

    def _check_auth(self) -> bool:
        if not _AUTH_TOKEN or self.path in _NO_AUTH_PATHS:
            return True
        auth = self.headers.get("Authorization", "")
        if auth == f"Bearer {_AUTH_TOKEN}":
            return True
        self._json_response({"error": "unauthorized"}, 401)
        return False

    def do_GET(self):
        if not self._check_auth():
            return
        if self.path == "/api/ge":
            self._json_response(self.ge_nodes)
        elif self.path == "/api/tasks":
            self._json_response({
                "tasks": self.task_queue,
                "pending": len(self.task_queue),
            })
        else:
            self._json_response({"error": "not found"}, 404)

    def do_POST(self):
        if not self._check_auth():
            return
        body = self._read_body()

        if self.path == "/api/ge/register":
            ge_id = body.get("ge_id", "unknown")
            if ge_id in self.ge_nodes and not body.get("force"):
                self._json_response({"error": "conflict"}, 409)
            else:
                ts = int(time.time())
                final_id = ge_id
                if ge_id in self.ge_nodes:
                    final_id = f"{ge_id}_{ts}"
                self.ge_nodes[final_id] = {"state": "idle", "registered_at": ts}
                self._json_response({"ge_id": final_id, "status": "registered"})

        elif self.path == "/api/ge/heartbeat":
            ge_id = body.get("ge_id")
            if ge_id in self.ge_nodes:
                self.ge_nodes[ge_id].update({
                    "state": body.get("state"),
                    "last_heartbeat": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "slots": body.get("slots"),
                })
                resp = {"status": "ok"}
                if ge_id in self.cancelled:
                    resp["cancelled_task_ids"] = list(self.cancelled[ge_id])
                self._json_response(resp)
            else:
                self._json_response({"error": "unknown ge"}, 404)

        elif self.path == "/api/tasks/poll":
            idle = body.get("idle_slots", 1)
            tasks = MockGSHandler.task_queue[:idle]
            MockGSHandler.task_queue = MockGSHandler.task_queue[idle:]
            _save_state(MockGSHandler.task_queue, MockGSHandler.task_id_counter)
            self._json_response(tasks)

        elif self.path == "/api/tasks/result":
            task_id = body.get("task_id")
            status = body.get("result_section", {}).get("status", "unknown")
            _gs_log(f"Task {task_id} -> {status}")
            self._json_response({"status": "ok"})

        elif self.path == "/api/tasks":
            MockGSHandler.task_id_counter += 1
            pkg_section = body.get("package_section", {})
            task = {
                "task_id": MockGSHandler.task_id_counter,
                "name": body.get("name", f"test-task-{MockGSHandler.task_id_counter}"),
                "priority": body.get("priority", "medium"),
                "scheduler_section": body.get("scheduler_section", {}),
                "package_section": pkg_section,
                "executor_section": body.get("executor_section", {}),
                "result_section": {},
            }
            MockGSHandler.task_queue.append(task)
            _save_state(MockGSHandler.task_queue, MockGSHandler.task_id_counter)
            _gs_log(f"Task queued: {task['task_id']} ({task['name']})")
            self._json_response({"task_id": task["task_id"], "status": "queued"})

        else:
            self._json_response({"error": "not found"}, 404)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        if raw and self.headers.get("Content-Encoding", "") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw) if raw else {}

    def _json_response(self, data, code=200):
        body = json.dumps(data).encode()
        accept_gzip = "gzip" in self.headers.get("Accept-Encoding", "")
        if accept_gzip and len(body) > 100:
            body = gzip.compress(body)
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Encoding", "gzip")
        else:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        _gs_log(f"{fmt % args}")


if __name__ == "__main__":
    port = 8000
    server = HTTPServer(("", port), MockGSHandler)
    _gs_log(f"Mock GS listening on http://localhost:{port}")
    _gs_log("POST /api/tasks  to submit a task")
    _gs_log("GET  /api/tasks  to list queued tasks")
    _gs_log("GET  /api/ge     to list GE nodes")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _gs_log("Shutting down")
        server.server_close()
