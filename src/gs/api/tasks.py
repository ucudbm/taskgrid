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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ..db.repository import Repository
from ..scheduler.router import TaskScheduler
from ..result.collector import ResultCollector
from .auth import verify_token

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _get_deps():
    from ..app import get_scheduler, get_repo, get_collector
    return get_scheduler(), get_repo(), get_collector()


def _normalize_task_input(body: dict) -> dict:
    pkg = body.get("package_section", {})
    sched = body.get("scheduler_section", {})
    exec_sec = body.get("executor_section", {})

    normalized = {
        "name": body.get("name"),
        "priority": body.get("priority", sched.get("priority", "medium")),
        "description": body.get("description", ""),
        "package_name": body.get("package_name") or pkg.get("package_name"),
        "package_version": body.get("package_version") if body.get("package_version") is not None else pkg.get("package_version"),
        "package_type": body.get("package_type") or pkg.get("package_type", "shell"),
        "entrypoint": body.get("entrypoint") or pkg.get("entrypoint"),
        "args": body.get("args") if body.get("args") is not None else pkg.get("args", []),
        "target_ge": body.get("target_ge") or sched.get("target_ge"),
        "pool": body.get("pool") or sched.get("pool") or None,
        "os_tag": body.get("os_tag") or sched.get("os_tag") or None,
        "device_id": body.get("device_id") or sched.get("device_id"),
        "timeout": body.get("timeout") or sched.get("timeout", 3600),
        "retry": body.get("retry") or sched.get("retry", 0),
        "workdir": body.get("workdir") or exec_sec.get("workdir"),
        "env": body.get("env") if body.get("env") is not None else exec_sec.get("env", {}),
        "user": body.get("user") or exec_sec.get("user"),
    }
    return normalized


@router.post("")
def create_task(
    body: dict,
    _=Depends(verify_token),
):
    scheduler, repo, _ = _get_deps()
    normalized = _normalize_task_input(body)
    if not normalized.get("name"):
        raise HTTPException(422, "'name' is required")
    if not normalized.get("package_name"):
        raise HTTPException(422, "'package_name' is required")
    if not normalized.get("entrypoint"):
        raise HTTPException(422, "'entrypoint' is required")

    pv = normalized.get("package_version")
    if pv is None:
        pv = 0
    else:
        try:
            pv = int(pv)
            if pv < 0:
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(422, "'package_version' must be a positive integer")
    normalized["package_version"] = pv

    result = scheduler.create_and_enqueue(normalized)
    return result


@router.get("")
def list_tasks(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    _=Depends(verify_token),
):
    _, repo, _ = _get_deps()
    rows = repo.list_tasks(status, priority, offset, limit)
    return {"tasks": rows, "total": len(rows), "offset": offset, "limit": limit}


@router.get("/{task_id}")
def get_task(
    task_id: int,
    _=Depends(verify_token),
):
    _, repo, collector = _get_deps()
    result = collector.get_result(task_id)
    if result is None:
        raise HTTPException(404, f"Task {task_id} not found")
    return result


@router.post("/poll")
def poll_tasks(
    body: dict,
):
    ge_id = body.get("ge_id")
    idle_slots = body.get("idle_slots", 1)
    if not ge_id:
        raise HTTPException(400, "'ge_id' is required")

    scheduler, _, _ = _get_deps()
    tasks = scheduler.poll_task(ge_id, idle_slots)
    return tasks


@router.post("/result")
def submit_result(
    body: dict,
):
    _, _, collector = _get_deps()
    ok = collector.collect(body)
    if not ok:
        raise HTTPException(400, "Invalid result payload")
    return {"status": "ok"}


@router.post("/{task_id}/cancel")
def cancel_task(
    task_id: int,
    _=Depends(verify_token),
):
    scheduler, _, _ = _get_deps()
    result = scheduler.cancel_task(task_id)
    if result is None:
        raise HTTPException(404, f"Task {task_id} not found")
    if result.get("status") == "cancelled":
        return {"task_id": task_id, "status": "cancelled"}
    return result


@router.get("/results/{task_id}/files")
def get_result_files(
    task_id: int,
    _=Depends(verify_token),
):
    _, _, collector = _get_deps()
    result = collector.get_result(task_id)
    if result is None:
        raise HTTPException(404, f"Task {task_id} not found")

    result_section = result.get("result_section", {})
    return {
        "task_id": task_id,
        "log_file": result_section.get("log_file"),
        "output_files": result_section.get("output_files", []),
    }


@router.get("/results/{task_id}/files/{filename:path}")
def download_result_file(
    task_id: int,
    filename: str,
    _=Depends(verify_token),
):
    from ..app import get_cfg
    import httpx
    cfg = get_cfg()
    headers = {}
    if cfg.auth_token:
        headers["Authorization"] = f"Bearer {cfg.auth_token}"
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{cfg.gp_url}/api/results/{task_id}/files/{filename}",
                headers=headers,
            )
            resp.raise_for_status()
            return Response(content=resp.content, media_type="application/octet-stream")
    except httpx.RequestError as e:
        raise HTTPException(502, f"GP unavailable: {e}")
