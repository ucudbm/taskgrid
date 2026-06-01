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
import socket
import time
import httpx


class DNSResilientClient(httpx.Client):
    """Client that resolves hostnames to IPs before each request,
    falling back to a cache when DNS is unavailable.

    This keeps load-balancer compatibility (fresh resolution per request)
    while tolerating transient mDNS / Avahi failures.
    """

    _dns_cache: dict[str, str] = {}

    def send(self, request, **kwargs):
        hostname = request.url.host
        if hostname and hostname not in ("localhost", "127.0.0.1", "::1"):
            ip = self._resolve(hostname)
            if ip and ip != hostname:
                request = self._rewrite_url(request, hostname, ip)
                request.headers["Host"] = hostname
        return super().send(request, **kwargs)

    def _resolve(self, hostname: str) -> str | None:
        try:
            ip = socket.gethostbyname(hostname)
            self._dns_cache[hostname] = ip
            return ip
        except OSError:
            return self._dns_cache.get(hostname)

    def _rewrite_url(self, request: httpx.Request, hostname: str, ip: str) -> httpx.Request:
        new = request.url.copy_with(host=ip)
        return httpx.Request(
            method=request.method,
            url=new,
            headers=request.headers,
            content=request.content,
        )
