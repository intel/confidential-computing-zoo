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

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tc_api.trucon.internal_transport import (
    AUTH_TRANSPORT_HEADER,
    CALLER_SERVICE_HEADER,
    PEER_PID_HEADER,
    UnixSocketHTTPConnection,
    request_json,
)
from tc_api.trucon.uds_gateway import TruConUnixSocketGateway


class _EchoHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        payload = {
            "path": self.path,
            "caller_service": self.headers.get(CALLER_SERVICE_HEADER),
            "auth_transport": self.headers.get(AUTH_TRANSPORT_HEADER),
            "peer_pid": self.headers.get(PEER_PID_HEADER),
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _start_echo_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_request_json_uses_uds_gateway_and_injects_internal_headers(tmp_path):
    echo_server, echo_thread = _start_echo_server()
    socket_path = str(tmp_path / "trucon.sock")
    gateway = TruConUnixSocketGateway(
        socket_path=socket_path,
        internal_proxy_secret="proxy-secret",
        forward_port=echo_server.server_port,
    )
    gateway.start()

    try:
        response = request_json(
            "GET",
            "/status",
            caller_service="tc_api",
            uds_path=socket_path,
            trucon_url="http://127.0.0.1:1",
        )
    finally:
        gateway.stop()
        echo_server.shutdown()
        echo_server.server_close()
        echo_thread.join(timeout=5)

    assert response["path"] == "/status"
    assert response["caller_service"] == "tc_api"
    assert response["auth_transport"] == "uds"
    assert response["peer_pid"] is not None


def test_uds_gateway_rejects_missing_caller_service(tmp_path):
    echo_server, echo_thread = _start_echo_server()
    socket_path = str(tmp_path / "trucon.sock")
    gateway = TruConUnixSocketGateway(
        socket_path=socket_path,
        internal_proxy_secret="proxy-secret",
        forward_port=echo_server.server_port,
    )
    gateway.start()

    connection = UnixSocketHTTPConnection(socket_path, timeout=5)
    try:
        connection.request("GET", "/status")
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()
        gateway.stop()
        echo_server.shutdown()
        echo_server.server_close()
        echo_thread.join(timeout=5)

    assert response.status == 401
    assert payload["detail"] == "Invalid or missing caller service"


def test_uds_gateway_socket_permissions_are_owner_only(tmp_path):
    echo_server, echo_thread = _start_echo_server()
    socket_path = str(tmp_path / "trucon.sock")
    gateway = TruConUnixSocketGateway(
        socket_path=socket_path,
        internal_proxy_secret="proxy-secret",
        forward_port=echo_server.server_port,
    )
    gateway.start()

    try:
        mode = os.stat(socket_path).st_mode & 0o777
    finally:
        gateway.stop()
        echo_server.shutdown()
        echo_server.server_close()
        echo_thread.join(timeout=5)

    assert mode == 0o600