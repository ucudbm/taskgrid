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
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Form, UploadFile, File

from .auth import verify_token

router = APIRouter(prefix="/api/packages", tags=["packages"])


def _get_gp_url():
    from ..app import get_cfg
    return get_cfg().gp_url


def _get_gp_headers():
    from ..app import get_cfg
    cfg = get_cfg()
    if cfg.auth_token:
        return {"Authorization": f"Bearer {cfg.auth_token}"}
    return {}


def _proxy(method: str, path: str, **kwargs):
    gp_url = _get_gp_url()
    headers = _get_gp_headers()
    if "headers" in kwargs:
        headers.update(kwargs.pop("headers"))
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.request(method, f"{gp_url}{path}", headers=headers, **kwargs)
            resp.raise_for_status()
            return resp.json()
    except httpx.RequestError as e:
        raise HTTPException(502, f"GP unavailable: {e}")


@router.get("/search")
def search_packages(
    q: str = Query("", description="Search query"),
    _=Depends(verify_token),
):
    return _proxy("GET", "/api/packages/search", params={"q": q})


@router.get("")
def list_packages(_=Depends(verify_token)):
    try:
        packages = _proxy("GET", "/api/packages")
    except HTTPException:
        return []
    gp_url = _get_gp_url()
    headers = _get_gp_headers()
    with httpx.Client(timeout=30) as client:
        for pkg in packages:
            try:
                vresp = client.get(
                    f"{gp_url}/api/packages/{pkg['name']}/versions",
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
    return packages


@router.post("", status_code=201)
def create_package(
    name: str = Form(...),
    description: str = Form(""),
    tasks: str = Form("[]"),
    file: UploadFile = File(...),
    _=Depends(verify_token),
):
    return _proxy(
        "POST", "/api/packages",
        data={"name": name, "description": description, "tasks": tasks},
        files={"file": (file.filename, file.file.read(), file.content_type or "application/octet-stream")},
    )


@router.get("/{name}/versions")
def list_versions(name: str, _=Depends(verify_token)):
    return _proxy("GET", f"/api/packages/{name}/versions")


@router.post("/{name}/versions", status_code=201)
def publish_version(
    name: str,
    description: str = Form(""),
    tasks: str = Form("[]"),
    file: UploadFile = File(...),
    _=Depends(verify_token),
):
    return _proxy(
        "POST", f"/api/packages/{name}/versions",
        data={"description": description, "tasks": tasks},
        files={"file": (file.filename, file.file.read(), file.content_type or "application/octet-stream")},
    )
