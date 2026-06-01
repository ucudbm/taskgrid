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
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional


class Repository:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR NOT NULL,
                priority VARCHAR NOT NULL DEFAULT 'medium',
                description TEXT DEFAULT '',
                target_ge VARCHAR,
                pool VARCHAR,
                os_tag VARCHAR,
                device_id VARCHAR,
                timeout INTEGER DEFAULT 3600,
                retry INTEGER DEFAULT 0,
                package_name VARCHAR NOT NULL,
                package_version INTEGER NOT NULL,
                package_type VARCHAR DEFAULT 'shell',
                entrypoint VARCHAR NOT NULL,
                args TEXT DEFAULT '[]',
                workdir VARCHAR,
                env TEXT DEFAULT '{}',
                user VARCHAR,
                status VARCHAR NOT NULL DEFAULT 'pending',
                exit_code INTEGER,
                start_time DATETIME,
                end_time DATETIME,
                duration INTEGER,
                log_file VARCHAR,
                output_files TEXT DEFAULT '[]',
                error_msg TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ge_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ge_id VARCHAR UNIQUE NOT NULL,
                state VARCHAR NOT NULL DEFAULT 'offline',
                last_heartbeat DATETIME,
                total_slots INTEGER DEFAULT 1,
                idle_slots INTEGER DEFAULT 1,
                current_task_id INTEGER,
                pool VARCHAR,
                os_tag VARCHAR,
                device_id VARCHAR,
                created_at DATETIME NOT NULL
            );
            CREATE TABLE IF NOT EXISTS task_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL UNIQUE,
                status VARCHAR NOT NULL,
                exit_code INTEGER,
                start_time DATETIME,
                end_time DATETIME,
                duration INTEGER,
                log_file VARCHAR,
                output_files TEXT DEFAULT '[]',
                error_msg TEXT,
                reported_at DATETIME NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            );
        """)
        conn.commit()
        conn.close()

    def _now(self) -> str:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"

    # --- Task operations ---

    def create_task(self, task: dict) -> int:
        conn = self._get_conn()
        now = self._now()
        conn.execute("""
            INSERT INTO tasks (
                name, priority, description, target_ge, pool, os_tag, device_id,
                timeout, retry, package_name, package_version, package_type,
                entrypoint, args, workdir, env, user, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task["name"], task.get("priority", "medium"), task.get("description", ""),
            task.get("target_ge"), task.get("pool"), task.get("os_tag"),
            task.get("device_id"), task.get("timeout", 3600), task.get("retry", 0),
            task["package_name"], task["package_version"], task.get("package_type", "shell"),
            task["entrypoint"], json.dumps(task.get("args", [])),
            task.get("workdir"), json.dumps(task.get("env", {})),
            task.get("user"), "pending", now, now
        ))
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def get_task(self, task_id: int) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_tasks_by_ge(self, ge_id: str, offset: int = 0, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM tasks WHERE target_ge = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (ge_id, limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]

    def list_tasks(self, status: Optional[str] = None, priority: Optional[str] = None,
                   offset: int = 0, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        parts = ["SELECT * FROM tasks"]
        params = []
        conditions = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if priority:
            conditions.append("priority = ?")
            params.append(priority)
        if conditions:
            parts.append("WHERE " + " AND ".join(conditions))
        parts.append("ORDER BY id DESC LIMIT ? OFFSET ?")
        params.extend([limit, offset])
        rows = conn.execute(" ".join(parts), params).fetchall()
        return [dict(r) for r in rows]

    def update_task_status(self, task_id: int, status: str, **extra) -> bool:
        conn = self._get_conn()
        now = self._now()
        fields = {"status": status, "updated_at": now}
        fields.update(extra)
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [task_id]
        conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return conn.execute("SELECT changes()").fetchone()[0] > 0

    def count_tasks_by_status(self, status: str) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = ?", (status,)).fetchone()
        return row[0]

    def count_tasks_grouped(self) -> dict[str, int]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
        ).fetchall()
        counts = {}
        for r in rows:
            counts[r["status"]] = r["cnt"]
        return counts

    def count_all_tasks(self) -> int:
        conn = self._get_conn()
        return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]

    # --- GE operations ---

    def register_ge(self, ge_id: str, pool: Optional[str] = None,
                    os_tag: Optional[str] = None, total_slots: int = 1,
                    device_id: Optional[str] = None) -> bool:
        conn = self._get_conn()
        now = self._now()
        existing = conn.execute("SELECT id FROM ge_nodes WHERE ge_id = ?", (ge_id,)).fetchone()
        if existing:
            return False
        conn.execute("""
            INSERT INTO ge_nodes (ge_id, state, last_heartbeat, total_slots, idle_slots, pool, os_tag, device_id, created_at)
            VALUES (?, 'online', ?, ?, ?, ?, ?, ?, ?)
        """, (ge_id, now, total_slots, total_slots, pool, os_tag, device_id, now))
        conn.commit()
        return True

    def get_ge(self, ge_id: str) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM ge_nodes WHERE ge_id = ?", (ge_id,)).fetchone()
        if row is None:
            return None
        return dict(row)

    def update_ge(self, ge_id: str, **fields) -> bool:
        conn = self._get_conn()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [ge_id]
        conn.execute(f"UPDATE ge_nodes SET {set_clause} WHERE ge_id = ?", values)
        conn.commit()
        return conn.execute("SELECT changes()").fetchone()[0] > 0

    def list_ge(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM ge_nodes ORDER BY ge_id").fetchall()
        return [dict(r) for r in rows]

    def list_online_ge(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM ge_nodes WHERE state IN ('online', 'running') ORDER BY ge_id"
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Result operations ---

    def save_result(self, task_id: int, result: dict) -> bool:
        conn = self._get_conn()
        now = self._now()
        existing = conn.execute(
            "SELECT id FROM task_results WHERE task_id = ?", (task_id,)
        ).fetchone()
        if existing:
            return False
        conn.execute("""
            INSERT INTO task_results (task_id, status, exit_code, start_time, end_time,
                                      duration, log_file, output_files, error_msg, reported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id, result.get("status"), result.get("exit_code"),
            result.get("start_time"), result.get("end_time"),
            result.get("duration"), result.get("log_file"),
            json.dumps(result.get("output_files", [])),
            result.get("error_msg"), now
        ))
        conn.commit()
        return True

    def get_result(self, task_id: int) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM task_results WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)
