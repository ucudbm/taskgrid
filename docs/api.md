# TaskGrid API Reference

- **GS** — Grid Scheduler, HTTP `:8000`
- **GP** — Grid Package, HTTP `:8001`
- **Auth** — All endpoints marked 🔒 require `Authorization: Bearer <token>`.  
  Token set via environment variable `TASKGRID_TOKEN` on GS/GP. If empty, auth is disabled.
- **Content-Type** — `application/json` unless noted otherwise.

---

## GE Management (GS)

### POST /api/ge/register
Register a GE worker.

**Request body:**
```json
{
  "ge_id": "ge-node-01",
  "pool": "qa_cluster",
  "os_tag": "linux",
  "device_id": "DEVICENO_01",
  "total_slots": 3
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `ge_id` | string | yes | Unique GE identifier |
| `pool` | string | no | Logical group for routing |
| `os_tag` | string | no | `linux`, `windows`, or `mac` |
| `device_id` | string | no | Device-level identifier |
| `total_slots` | int | no | Max concurrent tasks (default 1) |
| `force` | bool | no | Re-register if ID exists (default false) |

**Response:** `{"ge_id": "...", "status": "registered"}` or `"reconnected"` on force re-register.  
**409** on ID conflict without `force`.

---

### POST /api/ge/heartbeat
Report GE liveness and state.

**Request body:**
```json
{
  "ge_id": "ge-node-01",
  "state": "idle",
  "task_id": null,
  "progress": null,
  "slots": {"total": 3, "idle": 2}
}
```

---

### GET /api/ge  🔒
List all registered GE workers.

**Response:**
```json
[
  {
    "ge_id": "ge-3050-01",
    "state": "online",
    "last_heartbeat": "2026-05-29T20:00:00.000Z",
    "total_slots": 3,
    "idle_slots": 3,
    "current_task_id": null,
    "pool": "",
    "os_tag": "",
    "device_id": null,
    "registered_at": "2026-05-29T12:00:00.000Z"
  }
]
```

---

### GET /api/ge/{ge_id}  🔒
Get details for a specific GE. **404** if not found.

---

### PUT /api/ge/{ge_id}  🔒
Update GE attributes (only provided fields are changed).

**Request body** (at least one field required):
```json
{
  "device_id": "DEVICENO_01",
  "pool": "qa_cluster",
  "os_tag": "linux"
}
```

---

## Task Management (GS)

### POST /api/tasks  🔒
Create and enqueue a new task.

Fields can be passed flat or nested under `package_section`, `scheduler_section`, `executor_section`.

**Flat example:**
```json
{
  "name": "my-task",
  "priority": "medium",
  "package_name": "X",
  "package_version": 1,
  "package_type": "shell",
  "entrypoint": "tests/host-runsuite",
  "args": ["-p", "tp_example.xml"],
  "target_ge": "ge-node-01",
  "pool": null,
  "os_tag": null,
  "device_id": null,
  "timeout": 3600,
  "retry": 0,
  "workdir": null,
  "env": {"X_DOMAIN": "stability"},
  "user": null
}
```

**Nested example:**
```json
{
  "name": "use-gp",
  "package_section": {
    "package_name": "X",
    "package_type": "shell",
    "entrypoint": "tests/host-runsuite",
    "args": ["-p", "tp_example.xml"]
  },
  "executor_section": {
    "env": {"X_DOMAIN": "stability"}
  },
  "target_ge": "ge-node-01"
}
```

| Field | Routing priority | Description |
|---|---|---|
| `target_ge` | 1 (highest) | Directly target a specific GE by ID |
| `device_id` | 2 | Route to GE with matching `device_id` |
| `pool` | 3 | Route to any GE in the logical group |
| `os_tag` | 4 | Route to GE with matching OS tag |
| *(none set)* | 5 | Assign to any idle GE |

`package_version` can be omitted (auto-use latest from GP).

---

### GET /api/tasks  🔒
List tasks with optional filtering.

| Query param | Type | Default | Description |
|---|---|---|---|
| `status` | string | — | `pending`, `running`, `success`, `failed`, `cancelled`, `timeout` |
| `priority` | string | — | `high`, `medium`, `low` |
| `offset` | int | 0 | Pagination offset |
| `limit` | int | 100 | Page size (max 1000) |

---

### GET /api/tasks/{task_id}  🔒
Get full task detail and result. **404** if not found.

---

### POST /api/tasks/{task_id}/cancel  🔒
Cancel a pending or running task. **404** if not found.

---

### POST /api/tasks/poll
GE worker polls for queued tasks.

**Request body:**
```json
{"ge_id": "ge-node-01", "idle_slots": 2}
```

---

### POST /api/tasks/result
GE submits task execution result.

**Request body:**
```json
{
  "ge_id": "ge-node-01",
  "task_id": 1,
  "result_section": {
    "status": "success",
    "exit_code": 0,
    "start_time": "...",
    "end_time": "...",
    "duration": 12,
    "log_file": "http://gp:8001/api/results/1/logs/output.log",
    "output_files": ["http://gp:8001/api/results/1/files/output/report.xml"]
  }
}
```

---

### GET /api/tasks/results/{task_id}/files  🔒
List result files for a completed task.

**Response:**
```json
{
  "task_id": 1,
  "log_file": "http://gp:8001/api/results/1/logs/output.log",
  "output_files": ["http://gp:8001/api/results/1/files/output/report.xml"]
}
```

---

### GET /api/packages/search  🔒
Proxy search to GP. See GP section below.

---

## Package Management (GP)

All GP endpoints are 🔒 (token set via GP's `auth_token` config or `TASKGRID_TOKEN` env).

### GET /api/packages
List all packages.

### GET /api/packages/search
Search packages by name/description.

| Query param | Default | Description |
|---|---|---|
| `q` | `""` | Search query (empty = list all) |

### POST /api/packages
Create a new package with version 1.

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Package name |
| `description` | string | no | Human-readable description |
| `file` | file | yes | `.tar` archive of the package |

### GET /api/packages/{name}/versions
List all versions of a package. **404** if not found.

### POST /api/packages/{name}/versions
Publish a new version (auto-incremented).

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `description` | string | no | Version description |
| `file` | file | yes | `.tar` archive |

### GET /api/packages/{name}/versions/{version}
Download the `.tar` archive for a specific version.

### POST /api/results/{task_id}/files
Upload a result file (log or output artifact).

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | file | yes | File to upload |

### GET /api/results/{task_id}/files/{filename}
Download a stored result file. `filename` can include sub-paths.
