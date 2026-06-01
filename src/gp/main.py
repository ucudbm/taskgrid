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
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Depends
from fastapi.responses import Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .store import PackageStore


_TOKEN = os.environ.get("TASKGRID_TOKEN", "")
_SECURITY = HTTPBearer(auto_error=False)


def _verify_token(cred: HTTPAuthorizationCredentials = Depends(_SECURITY)):
    if not _TOKEN:
        return
    if cred is None or cred.credentials != _TOKEN:
        raise HTTPException(401, "Invalid or missing token")


class GPFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        s = time.strftime("%Y-%m-%dT%H:%M:%S", ct)
        return f"{s}.{int(record.msecs):03d}"

    def format(self, record):
        record.component = "GP"
        return super().format(record)


_LOG_FMT = "%(asctime)s [%(component)s] [%(levelname)s] %(message)s"


def _setup_gp_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(GPFormatter(_LOG_FMT))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).addHandler(handler)
        logging.getLogger(name).propagate = False

app = FastAPI(title="TaskGrid GP")
app.add_middleware(GZipMiddleware, minimum_size=100)
_store: PackageStore = None


def get_store() -> PackageStore:
    global _store
    if _store is None:
        raise RuntimeError("PackageStore not initialized")
    return _store


def create_app(store_dir: str) -> FastAPI:
    global _store
    _store = PackageStore(store_dir)
    return app


@app.get("/api/packages/search")
def search_packages(
    q: str = Query("", description="Search query"),
    token: HTTPAuthorizationCredentials = Depends(_verify_token),
):
    store = get_store()
    if not q:
        return store.list_packages()
    return store.search(q)


@app.get("/api/packages")
def list_packages(token: HTTPAuthorizationCredentials = Depends(_verify_token)):
    return get_store().list_packages()


@app.post("/api/packages", status_code=201)
def create_package(
    name: str = Form(...),
    description: str = Form(""),
    tasks: str = Form("[]"),
    file: UploadFile = File(...),
    token: HTTPAuthorizationCredentials = Depends(_verify_token),
):
    store = get_store()
    data = file.file.read()
    store.create_package(name, description)
    version = store.next_version(name)
    tasks_list = json.loads(tasks) if tasks else []
    store.publish_version(name, version, data, description, tasks_list)
    return {"name": name, "version": version, "status": "created", "tasks": tasks_list}


@app.get("/api/packages/{name}/versions")
def list_versions(
    name: str,
    token: HTTPAuthorizationCredentials = Depends(_verify_token),
):
    store = get_store()
    meta = store.get_package_meta(name)
    if not meta:
        raise HTTPException(404, f"Package '{name}' not found")
    return store.list_versions(name)


@app.post("/api/packages/{name}/versions", status_code=201)
def publish_version(
    name: str,
    description: str = Form(""),
    tasks: str = Form("[]"),
    file: UploadFile = File(...),
    token: HTTPAuthorizationCredentials = Depends(_verify_token),
):
    store = get_store()
    meta = store.get_package_meta(name)
    if not meta:
        raise HTTPException(404, f"Package '{name}' not found")
    version = store.next_version(name)
    data = file.file.read()
    tasks_list = json.loads(tasks) if tasks else []
    store.publish_version(name, version, data, description, tasks_list)
    return {"name": name, "version": version, "status": "published", "tasks": tasks_list}


@app.post("/api/results/{task_id}/files", status_code=201)
def upload_result_file(
    task_id: int,
    file: UploadFile = File(...),
    token: HTTPAuthorizationCredentials = Depends(_verify_token),
):
    store = get_store()
    data = file.file.read()
    filename = file.filename or f"output_{task_id}.zip"
    store.save_result_file(task_id, filename, data)
    return {
        "task_id": task_id,
        "filename": filename,
        "url": f"/api/results/{task_id}/files/{filename}",
    }


@app.get("/api/results/{task_id}/files/{filename:path}")
def download_result_file(
    task_id: int,
    filename: str,
    token: HTTPAuthorizationCredentials = Depends(_verify_token),
):
    store = get_store()
    data = store.get_result_file(task_id, filename)
    if data is None:
        raise HTTPException(404, "Result file not found")
    return Response(content=data, media_type="application/octet-stream")


@app.get("/api/packages/{name}/versions/{version}")
def download_package(
    name: str,
    version: int,
    token: HTTPAuthorizationCredentials = Depends(_verify_token),
):
    store = get_store()
    meta = store.get_package_meta(name)
    if not meta:
        raise HTTPException(404, f"Package '{name}' not found")
    ver_meta = store.get_version_meta(name, version)
    if not ver_meta:
        raise HTTPException(404, f"Version {version} not found for '{name}'")
    data = store.get_package_file(name, version)
    if data is None:
        raise HTTPException(404, "Package file not found")
    return Response(content=data, media_type="application/octet-stream")


def main():
    parser = argparse.ArgumentParser(description="TaskGrid Packages")
    parser.add_argument("-c", "--config", default="/etc/taskgrid/config.yaml", help="Path to config file")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8001, help="Bind port")
    parser.add_argument("--store-dir", default="/var/lib/taskgrid/packages", help="Package storage directory")
    args = parser.parse_args()

    store_dir = args.store_dir
    if args.config:
        import yaml
        cfg_path = Path(args.config)
        if cfg_path.exists():
            raw = yaml.safe_load(cfg_path.read_text())
            gp_cfg = raw.get("gp", {})
            store_dir = gp_cfg.get("store_dir", store_dir)
            args.host = gp_cfg.get("host", args.host)
            args.port = gp_cfg.get("port", args.port)
            global _TOKEN
            _TOKEN = _TOKEN or gp_cfg.get("auth_token", "")
        else:
            print(f"Warning: config not found: {cfg_path}, using defaults", file=sys.stderr)
            print(f"Hint: use -c <path> to specify config file (e.g. -c config/config.yaml)", file=sys.stderr)

    Path(store_dir).mkdir(parents=True, exist_ok=True)
    _setup_gp_logging()
    create_app(store_dir)
    logging.getLogger("gp").info("Starting on http://%s:%s", args.host, args.port)
    logging.getLogger("gp").info("Store: %s", store_dir)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info", log_config=None)


if __name__ == "__main__":
    main()
