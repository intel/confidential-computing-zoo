# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import http.client
import io
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


CALLER_SERVICE_HEADER = "X-TruCon-Caller-Service"
AUTH_TRANSPORT_HEADER = "X-TruCon-Auth-Transport"
PEER_PID_HEADER = "X-TruCon-Peer-Pid"
PEER_UID_HEADER = "X-TruCon-Peer-Uid"
PEER_GID_HEADER = "X-TruCon-Peer-Gid"
INTERNAL_PROXY_SECRET_HEADER = "X-TruCon-Internal-Proxy-Secret"


class UnixSocketHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: Optional[float] = None):
        super().__init__(host="localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if self.timeout is not None:
            self.sock.settimeout(self.timeout)
        self.sock.connect(self._socket_path)


def resolve_trucon_uds_path(explicit_path: Optional[str] = None) -> Optional[str]:
    return explicit_path if explicit_path is not None else os.environ.get("TRUCON_UDS_PATH") or None


def resolve_trucon_url(explicit_url: Optional[str] = None) -> str:
    return explicit_url or os.environ.get("TRUCON_URL", "http://127.0.0.1:8001")


def build_internal_headers(
    *,
    caller_service: Optional[str] = None,
    include_compat_token: bool = False,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    headers = dict(extra_headers or {})
    if caller_service:
        headers.setdefault(CALLER_SERVICE_HEADER, caller_service)
    if include_compat_token:
        service_token = os.environ.get("TRUCON_SERVICE_TOKEN", "")
        if service_token:
            headers.setdefault("Authorization", f"Bearer {service_token}")
    return headers


def request_json(
    method: str,
    path: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    caller_service: Optional[str] = None,
    timeout: float = 30.0,
    trucon_url: Optional[str] = None,
    uds_path: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    normalized_path = path if path.startswith("/") else f"/{path}"
    resolved_uds_path = resolve_trucon_uds_path(uds_path)
    body = None if json_body is None else json.dumps(json_body).encode("utf-8")
    base_headers = build_internal_headers(
        caller_service=caller_service,
        include_compat_token=False,
        extra_headers=extra_headers,
    )
    if body is not None:
        base_headers.setdefault("Content-Type", "application/json")

    if resolved_uds_path and os.path.exists(resolved_uds_path):
        connection = UnixSocketHTTPConnection(resolved_uds_path, timeout=timeout)
        try:
            connection.request(method.upper(), normalized_path, body=body, headers=base_headers)
            response = connection.getresponse()
            payload = response.read()
        except OSError as exc:
            raise urllib.error.URLError(exc) from exc
        finally:
            connection.close()

        if response.status >= 400:
            raise urllib.error.HTTPError(
                f"http+unix://{resolved_uds_path}{normalized_path}",
                response.status,
                response.reason,
                dict(response.getheaders()),
                io.BytesIO(payload),
            )
        if not payload:
            return {}
        return json.loads(payload.decode("utf-8"))

    url = f"{resolve_trucon_url(trucon_url).rstrip('/')}{normalized_path}"
    http_headers = build_internal_headers(
        caller_service=caller_service,
        include_compat_token=True,
        extra_headers=extra_headers,
    )
    if body is not None:
        http_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=body, headers=http_headers, method=method.upper())
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    if not payload:
        return {}
    return json.loads(payload.decode("utf-8"))