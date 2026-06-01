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
import logging
import sys
from pathlib import Path

import uvicorn

from .config import GSConfig
from .app import create_app


def main():
    parser = argparse.ArgumentParser(description="TaskGrid Scheduler")
    parser.add_argument(
        "-c", "--config",
        default="/etc/taskgrid/config.yaml",
        help="Path to config file",
    )
    parser.add_argument("--host", default=None, help="Bind address (overrides config)")
    parser.add_argument("--port", type=int, default=None, help="Bind port (overrides config)")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"Config not found: {cfg_path}", file=sys.stderr)
        print(f"Hint: use -c <path> to specify config file (e.g. -c config/config.yaml)", file=sys.stderr)
        sys.exit(1)

    cfg = GSConfig(cfg_path)

    if args.host:
        cfg.host = args.host
    if args.port:
        cfg.port = args.port

    app = create_app(cfg)
    logging.getLogger("gs").info("Starting GS on http://%s:%s", cfg.host, cfg.port)
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info", log_config=None)


if __name__ == "__main__":
    main()
