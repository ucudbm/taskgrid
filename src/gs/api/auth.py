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
import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_TOKEN = os.environ.get("TASKGRID_TOKEN", "")


def verify_token(cred: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))):
    if not _TOKEN:
        return
    if cred is None or cred.credentials != _TOKEN:
        raise HTTPException(401, "Invalid or missing token")
