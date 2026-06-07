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
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Form, UploadFile, File

from ..api.tasks import _normalize_task_input
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["web"])

_templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


def _get_deps():
    from ..app import get_repo, get_scheduler, get_collector, get_state_manager
    return get_repo(), get_scheduler(), get_collector(), get_state_manager()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    repo, _, _, state_mgr = _get_deps()
    counts = repo.count_tasks_grouped()
    total = repo.count_all_tasks()
    ges = repo.list_ge()
    online_ges = [g for g in ges if g["state"] in ("online", "running")]
    total_slots = sum(g["total_slots"] for g in online_ges)
    idle_slots = sum(g["idle_slots"] for g in online_ges)
    recent = repo.list_tasks(limit=10)

    return templates.TemplateResponse(request, "dashboard.html", {
        "total_tasks": total,
        "counts": counts,
        "total_ges": len(ges),
        "online_ges": len(online_ges),
        "total_slots": total_slots,
        "idle_slots": idle_slots,
        "recent_tasks": recent,
    })


@router.get("/tasks", response_class=HTMLResponse)
def task_list(
    request: Request,
    status: str = Query(None),
    priority: str = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    repo, _, _, _ = _get_deps()
    rows = repo.list_tasks(status, priority, offset, limit)
    counts = repo.count_tasks_grouped()
    return templates.TemplateResponse(request, "tasks.html", {
        "tasks": rows,
        "counts": counts,
        "status": status,
        "priority": priority,
        "offset": offset,
        "limit": limit,
    })


@router.get("/tasks/new", response_class=HTMLResponse)
def task_new_form(request: Request):
    repo, _, _, _ = _get_deps()
    ges = repo.list_ge()
    return templates.TemplateResponse(request, "task_new.html", {
        "ges": ges,
    })


@router.post("/tasks/new")
def task_new_submit(request: Request, body: dict):
    _, scheduler, _, _ = _get_deps()
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
    return RedirectResponse(url=f"/tasks/{result['task_id']}", status_code=303)


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(request: Request, task_id: int):
    repo, _, collector, _ = _get_deps()
    task = repo.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    result = collector.get_result(task_id)
    return templates.TemplateResponse(request, "task_detail.html", {
        "task": task,
        "result": result,
    })


@router.get("/ges", response_class=HTMLResponse)
def ge_list(request: Request):
    _, _, _, state_mgr = _get_deps()
    ges = state_mgr.get_ge_list()
    return templates.TemplateResponse(request, "ges.html", {
        "ges": ges,
    })


@router.get("/ges/{ge_id}", response_class=HTMLResponse)
def ge_detail(request: Request, ge_id: str):
    repo, _, _, state_mgr = _get_deps()
    detail = state_mgr.get_ge_detail(ge_id)
    if detail is None:
        raise HTTPException(404, f"GE '{ge_id}' not found")
    tasks = repo.list_tasks_by_ge(ge_id, limit=50)
    return templates.TemplateResponse(request, "ge_detail.html", {
        "ge": detail,
        "tasks": tasks,
    })


@router.get("/packages", response_class=HTMLResponse)
def packages_list(request: Request):
    from ..app import get_cfg
    cfg = get_cfg()
    headers = {}
    if cfg.auth_token:
        headers["Authorization"] = f"Bearer {cfg.auth_token}"

    packages = []
    gp_error = None
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{cfg.gp_url}/api/packages", headers=headers)
            if resp.status_code == 200:
                packages = resp.json()
                for pkg in packages:
                    try:
                        vresp = client.get(
                            f"{cfg.gp_url}/api/packages/{pkg['name']}/versions",
                            headers=headers,
                        )
                        if vresp.status_code == 200:
                            versions = vresp.json()
                            pkg["version_count"] = len(versions)
                            pkg["latest_version"] = max(
                                v["version"] for v in versions
                            ) if versions else None
                    except Exception:
                        pkg["version_count"] = 0
                        pkg["latest_version"] = None
    except Exception as e:
        gp_error = str(e)

    return templates.TemplateResponse(request, "packages.html", {
        "packages": packages,
        "gp_error": gp_error,
    })


@router.post("/packages/create")
def package_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    tasks: str = Form("[]"),
    file: UploadFile = File(...),
):
    from ..app import get_cfg
    cfg = get_cfg()
    headers = {}
    if cfg.auth_token:
        headers["Authorization"] = f"Bearer {cfg.auth_token}"

    try:
        with httpx.Client(timeout=30) as client:
            files = {"file": (file.filename, file.file.read(), file.content_type or "application/octet-stream")}
            data = {"name": name, "description": description, "tasks": tasks}
            resp = client.post(
                f"{cfg.gp_url}/api/packages", data=data, files=files, headers=headers
            )
            resp.raise_for_status()
    except Exception as e:
        raise HTTPException(502, f"GP unavailable: {e}")

    return RedirectResponse(url="/packages", status_code=303)


@router.post("/packages/{name}/versions/new")
def package_new_version(
    request: Request,
    name: str,
    description: str = Form(""),
    tasks: str = Form("[]"),
    file: UploadFile = File(...),
):
    from ..app import get_cfg
    cfg = get_cfg()
    headers = {}
    if cfg.auth_token:
        headers["Authorization"] = f"Bearer {cfg.auth_token}"

    try:
        with httpx.Client(timeout=30) as client:
            files = {"file": (file.filename, file.file.read(), file.content_type or "application/octet-stream")}
            data = {"description": description, "tasks": tasks}
            resp = client.post(
                f"{cfg.gp_url}/api/packages/{name}/versions", data=data, files=files, headers=headers
            )
            resp.raise_for_status()
    except Exception as e:
        raise HTTPException(502, f"GP unavailable: {e}")

    return RedirectResponse(url="/packages", status_code=303)
