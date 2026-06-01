# TaskGrid

TaskGrid is a distributed task execution system with three components:

- **GS** (Grid Scheduler) — Central scheduler, web UI, REST API
- **GP** (Grid Package) — Package storage and version management
- **GE** (Grid Executor) — Worker nodes that execute tasks

## Quick Start

### Prerequisites

- Python 3.10+
- Redis 6.x (required by GS)

### Installation

```bash
pip install -e .
```

### Start Services

Open three terminals.

Terminal 1 — GP (Package Server):

```bash
taskgrid-gp
```

Terminal 2 — GS (Scheduler + Web UI):

```bash
taskgrid-gs -c config.yaml.example
```

Terminal 3 — GE (Executor Worker):

```bash
taskgrid-ge -c config.yaml.example
```

The GE will register with GS and start polling for tasks. Open [http://localhost:8000](http://localhost:8000) to see the dashboard.

### Load Demo Packages

With GP and GS running, publish the three demo packages:

```bash
cd packages
for f in *.tar.gz; do
  name="${f%.tar.gz}"
  tasks=$(cat "$name.tasks.json")
  curl -s -X POST http://localhost:8000/api/packages \
    -H "Authorization: Bearer" \
    -F "name=$name" \
    -F "description=Hello World demo - $name" \
    -F "tasks=$tasks" \
    -F "file=@$f"
  echo ""
done
```

### Create Your First Task

1. Open [http://localhost:8000/tasks/new](http://localhost:8000/tasks/new)
2. Type `hello_world_single` in the package field (autocomplete will match)
3. Select the **Hello World** task template
4. Set **Target GE** to `ge-node-01`
5. Click **Create Task**
6. The task enters the queue. The GE polls and picks it up automatically.
7. Go to the [Tasks page](http://localhost:8000/tasks) — the task transitions from `pending` → `running` → `success`.
8. Click the task to see the detail page with timing, exit code, and download link for output logs.

### Demo Package Reference

| Package | Template Mode | Tasks |
|---|---|---|
| `hello_world_single` | Single task | One task: prints "Hello, World!" |
| `hello_world_multi` | Same entrypoint, different args | Two tasks: "Hello Alice!" / "Hello Bob!" (args differ) |
| `hello_world_advanced` | Different entrypoints | Two tasks: hello.sh (prints "Hello!") / ping.sh (pings localhost) |

## Project Structure

```
taskgrid/
├── src/
│   ├── ge/          # Grid Executor — runs on worker nodes
│   ├── gp/          # Grid Package — package registry
│   └── gs/          # Grid Scheduler — web UI + API + scheduler
├── packages/        # Demo package tarballs
├── docs/
│   └── api.md       # REST API reference
├── config.yaml.example
├── pyproject.toml
└── LICENSE
```

## License

Apache 2.0