import json
import time
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from ..config import GEConfig
from ..executor.runner import TaskRunner
from ..executor.slot import SlotManager
from ..heartbeat import HeartbeatReporter


class _WebState:
    cfg: GEConfig = None
    slots: SlotManager = None
    heartbeat: HeartbeatReporter = None
    runner: TaskRunner = None


state = _WebState()

_templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))
app = FastAPI(title="GE Local Web UI")


def set_engine_refs(
    cfg: GEConfig,
    slots: SlotManager,
    heartbeat: HeartbeatReporter,
    runner: TaskRunner,
):
    state.cfg = cfg
    state.slots = slots
    state.heartbeat = heartbeat
    state.runner = runner


@app.get("/api/status")
def api_status():
    hb = state.heartbeat
    cfg = state.cfg
    slots = state.slots
    return {
        "ge_id": cfg.id,
        "state": "running" if hb and hb.running_task_id else "idle",
        "total_slots": slots.total,
        "idle_slots": slots.idle,
        "used_slots": slots.used,
        "running_task_id": hb.running_task_id if hb else None,
        "pool": cfg.pool,
        "os_tag": cfg.os_tag,
        "device_id": cfg.device_id,
    }


def _scan_tasks():
    tasks = []
    log_dir = Path(state.cfg.log_dir) / "tasks"
    running_ids = set(state.runner._procs.keys()) if state.runner else set()

    if log_dir.exists():
        for d in sorted(log_dir.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            try:
                task_id = int(d.name)
            except ValueError:
                continue
            result_json = d / "result.json"
            task_info = {"task_id": task_id}
            if task_id in running_ids:
                task_info["status"] = "running"
                task_info["progress"] = state.heartbeat._task_progress.get(task_id) if state.heartbeat else None
            elif result_json.exists():
                try:
                    with open(result_json) as f:
                        r = json.load(f)
                    task_info["status"] = r.get("status", "unknown")
                    rs = r.get("result_section", {})
                    if rs:
                        task_info["exit_code"] = rs.get("exit_code")
                        task_info["duration"] = rs.get("duration")
                        task_info["start_time"] = rs.get("start_time")
                        task_info["end_time"] = rs.get("end_time")
                        task_info["error_msg"] = rs.get("error_msg")
                except (json.JSONDecodeError, OSError):
                    task_info["status"] = "unknown"
            else:
                task_info["status"] = "unknown"
            tasks.append(task_info)

    for tid in running_ids:
        if not any(t["task_id"] == tid for t in tasks):
            tasks.insert(0, {
                "task_id": tid,
                "status": "running",
                "progress": state.heartbeat._task_progress.get(tid) if state.heartbeat else None,
            })

    return tasks


@app.get("/api/tasks")
def api_tasks():
    return _scan_tasks()


@app.get("/api/tasks/{task_id}/log")
def api_task_log(task_id: int):
    log_path = Path(state.cfg.log_dir) / "tasks" / str(task_id) / "output.log"
    if not log_path.exists():
        raise HTTPException(404, "Log not found")
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raise HTTPException(500, "Failed to read log")
    return PlainTextResponse(text)


@app.get("/api/tasks/{task_id}/log/stream")
def api_task_log_stream(task_id: int):
    log_path = Path(state.cfg.log_dir) / "tasks" / str(task_id) / "output.log"
    if not log_path.exists():
        raise HTTPException(404, "Log not found")

    def event_generator():
        pos = log_path.stat().st_size
        while True:
            try:
                if not log_path.exists():
                    break
                current_size = log_path.stat().st_size
                if current_size > pos:
                    with open(log_path, "r") as f:
                        f.seek(pos)
                        new_data = f.read()
                        pos = f.tell()
                    if new_data:
                        yield f"data: {json.dumps(new_data)}\n\n"

                is_running = task_id in (state.runner._procs if state.runner else {})
                if not is_running:
                    time.sleep(0.5)
                    if log_path.stat().st_size > pos:
                        with open(log_path, "r") as f:
                            f.seek(pos)
                            remaining = f.read()
                        if remaining:
                            yield f"data: {json.dumps(remaining)}\n\n"
                    break
                time.sleep(1)
            except Exception:
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/tasks/{task_id}/cancel")
def api_cancel_task(task_id: int):
    if not state.runner or task_id not in state.runner._procs:
        raise HTTPException(404, "Task not running")
    state.runner.cancel(task_id)
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {
        "tasks": _scan_tasks(),
    })


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(request: Request, task_id: int):
    log_path = Path(state.cfg.log_dir) / "tasks" / str(task_id) / "output.log"
    is_running = task_id in (state.runner._procs if state.runner else {})
    result = None
    result_json = Path(state.cfg.log_dir) / "tasks" / str(task_id) / "result.json"
    if result_json.exists():
        try:
            with open(result_json) as f:
                result = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return templates.TemplateResponse(request, "task_detail.html", {
        "task_id": task_id,
        "is_running": is_running,
        "result": result,
    })
