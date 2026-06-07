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
from fastapi import APIRouter, Depends, HTTPException

from ..ge_manager.registry import GERegistry
from ..ge_manager.heartbeat import HeartbeatProcessor
from ..ge_manager.state import GEStateManager
from .auth import verify_token

router = APIRouter(prefix="/api/ge", tags=["ge"])


def _get_deps():
    from ..app import get_registry, get_heartbeat_processor, get_state_manager
    return get_registry(), get_heartbeat_processor(), get_state_manager()


@router.post("/register")
def register_ge(body: dict):
    registry, _, _ = _get_deps()
    ge_id = body.get("ge_id")
    if not ge_id:
        raise HTTPException(400, "'ge_id' is required")

    result = registry.register(
        ge_id=ge_id,
        pool=body.get("pool"),
        os_tag=body.get("os_tag"),
        total_slots=body.get("total_slots", 1),
        device_id=body.get("device_id"),
        force=body.get("force", False),
    )
    if result["status"] == "conflict":
        raise HTTPException(409, result)
    return result


@router.post("/heartbeat")
def heartbeat_ge(body: dict):
    _, processor, _ = _get_deps()
    ge_id = body.get("ge_id")
    if not ge_id:
        raise HTTPException(400, "'ge_id' is required")

    result = processor.process(
        ge_id=ge_id,
        state=body.get("state", "idle"),
        task_id=body.get("task_id"),
        progress=body.get("progress"),
        slots=body.get("slots"),
        version=body.get("version"),
        task_ids=body.get("task_ids"),
    )
    return result


@router.get("")
def list_ge(_=Depends(verify_token)):
    _, _, mgr = _get_deps()
    return mgr.get_ge_list()


@router.get("/{ge_id}")
def get_ge_detail(ge_id: str, _=Depends(verify_token)):
    _, _, mgr = _get_deps()
    detail = mgr.get_ge_detail(ge_id)
    if detail is None:
        raise HTTPException(404, f"GE '{ge_id}' not found")
    return detail


@router.put("/{ge_id}")
def update_ge(ge_id: str, body: dict, _=Depends(verify_token)):
    registry, _, mgr = _get_deps()
    detail = mgr.get_ge_detail(ge_id)
    if detail is None:
        raise HTTPException(404, f"GE '{ge_id}' not found")

    fields = {}
    for key in ("device_id", "pool", "os_tag", "update_url", "update_version"):
        if key in body:
            fields[key] = body[key] or None

    if not fields:
        raise HTTPException(400, "No updatable fields provided")

    registry.update(ge_id, **fields)
    return mgr.get_ge_detail(ge_id)
