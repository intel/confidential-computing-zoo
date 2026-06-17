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
import logging
import os
import socket
import socketserver
import struct
import threading
from http.server import BaseHTTPRequestHandler
from typing import Optional, Tuple

from .internal_transport import (
    AUTH_TRANSPORT_HEADER,
    CALLER_SERVICE_HEADER,
    INTERNAL_PROXY_SECRET_HEADER,
    PEER_GID_HEADER,
    PEER_PID_HEADER,
    PEER_UID_HEADER,
)


logger = logging.getLogger("trucon.uds_gateway")

_PEERCRED_STRUCT = struct.Struct("3i")
_ALLOWED_CALLER_SERVICES = {"tc_api", "docktap"}


def get_peer_credentials(connection: socket.socket) -> Tuple[int, int, int]:
    raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _PEERCRED_STRUCT.size)
    return _PEERCRED_STRUCT.unpack(raw)


class _ThreadedUnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, socket_path: str, handler_cls, gateway):
        self.gateway = gateway
        super().__init__(socket_path, handler_cls)


class _GatewayHandler(BaseHTTPRequestHandler):
    server: _ThreadedUnixHTTPServer

    def log_message(self, format: str, *args):
        logger.debug("UDS gateway %s - %s", self.client_address, format % args)

    def do_GET(self):
        self._handle_request()

    def do_POST(self):
        self._handle_request()

    def do_DELETE(self):
        self._handle_request()

    def _handle_request(self):
        gateway = self.server.gateway

        if gateway.auth_disabled:
            caller_service = self.headers.get(CALLER_SERVICE_HEADER, "auth_bypass")
            peer_pid, peer_uid, peer_gid = (0, 0, 0)
        else:
            caller_service = self.headers.get(CALLER_SERVICE_HEADER)
            if caller_service not in _ALLOWED_CALLER_SERVICES:
                self._send_error(401, b'{"detail":"Invalid or missing caller service"}')
                return

            try:
                peer_pid, peer_uid, peer_gid = get_peer_credentials(self.connection)
            except OSError as exc:
                logger.warning("Could not retrieve peer credentials for UDS request: %s", exc)
                self._send_error(401, b'{"detail":"Unable to validate peer credentials"}')
                return

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(content_length) if content_length else None

        forward_headers = {}
        for key, value in self.headers.items():
            if key.lower() in {
                "host",
                "authorization",
                "connection",
                "content-length",
                INTERNAL_PROXY_SECRET_HEADER.lower(),
                AUTH_TRANSPORT_HEADER.lower(),
                PEER_PID_HEADER.lower(),
                PEER_UID_HEADER.lower(),
                PEER_GID_HEADER.lower(),
            }:
                continue
            forward_headers[key] = value

        forward_headers[INTERNAL_PROXY_SECRET_HEADER] = gateway.internal_proxy_secret
        forward_headers[CALLER_SERVICE_HEADER] = caller_service
        forward_headers[AUTH_TRANSPORT_HEADER] = "uds"
        forward_headers[PEER_PID_HEADER] = str(peer_pid)
        forward_headers[PEER_UID_HEADER] = str(peer_uid)
        forward_headers[PEER_GID_HEADER] = str(peer_gid)

        connection = http.client.HTTPConnection(
            gateway.forward_host,
            gateway.forward_port,
            timeout=gateway.forward_timeout,
        )
        try:
            connection.request(self.command, self.path, body=body, headers=forward_headers)
            response = connection.getresponse()
            payload = response.read()
        except OSError as exc:
            logger.error("UDS gateway failed to reach TruCon HTTP compatibility listener: %s", exc)
            self._send_error(502, b'{"detail":"Internal TruCon compatibility path unavailable"}')
            return
        finally:
            connection.close()

        self.send_response(response.status)
        for key, value in response.getheaders():
            if key.lower() in {"connection", "transfer-encoding", "content-length"}:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _send_error(self, status_code: int, payload: bytes):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class TruConUnixSocketGateway:
    def __init__(
        self,
        *,
        socket_path: str,
        internal_proxy_secret: str,
        forward_host: str = "127.0.0.1",
        forward_port: int = 8001,
        forward_timeout: float = 30.0,
        auth_disabled: bool = False,
    ):
        self.socket_path = socket_path
        self.internal_proxy_secret = internal_proxy_secret
        self.forward_host = forward_host
        self.forward_port = forward_port
        self.forward_timeout = forward_timeout
        self.auth_disabled = auth_disabled
        self._server: Optional[_ThreadedUnixHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        socket_dir = os.path.dirname(self.socket_path)
        if socket_dir:
            os.makedirs(socket_dir, exist_ok=True)
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        self._server = _ThreadedUnixHTTPServer(self.socket_path, _GatewayHandler, self)
        os.chmod(self.socket_path, 0o600)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True, name="trucon-uds-gateway")
        self._thread.start()
        logger.info("TruCon UDS gateway listening at %s", self.socket_path)

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)