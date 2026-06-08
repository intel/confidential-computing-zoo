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

import socket
import threading
import logging
import os
import time
import uuid
import json
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from urllib.parse import parse_qs, urlencode, urljoin

from .operation_log import (
    OperationTracker,
    enrich_from_response,
    log_operation_json,
    is_streaming_endpoint,
)
from .runtime_adapter import DEFAULT_RUNTIME_ENGINE, DockerRuntimeAdapter
from .. import config as _cfg
from ..trucon_client import SUBMITTABLE_OPERATIONS, has_reusable_identity_token, has_active_delegation


def _has_active_delegation_for_chain(chain_id: str) -> bool:
    """Check if there is an active delegation for the given chain."""
    try:
        from tc_api.trucon.database import get_active_delegation
        return get_active_delegation(chain_id) is not None
    except Exception:
        return False

WORKLOAD_LABEL = "io.trucon.workload-id"
LAUNCH_LABEL = "io.trucon.launch-id"

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class DockerProxyServer:
    """Unix socket proxy server that intercepts Docker CLI operations"""

    def __init__(
        self,
        listen_socket_path: str = "/tmp/docker-proxy.sock",
        docker_socket_path: str = "/var/run/docker.sock",
        trucon_committer=None,
        runtime_engine: str = DEFAULT_RUNTIME_ENGINE,
    ):
        self.listen_socket_path = listen_socket_path
        self.docker_socket_path = docker_socket_path
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.client_handler_thread: Optional[threading.Thread] = None
        self._log_callback = None
        self.tracker = OperationTracker()
        self._trucon_committer = trucon_committer
        self._runtime_adapter = DockerRuntimeAdapter(runtime_engine=runtime_engine)

    def set_log_callback(self, callback):
        """Set callback function for logging operations"""
        self._log_callback = callback

    def _parse_http_request(self, data: bytes) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """Parse HTTP request to extract operation and parameters"""
        parsed_request = self._runtime_adapter.parse_request(data)
        return parsed_request.operation_type, parsed_request.path_only, parsed_request.params

    def _map_path_to_operation(self, path: str, method: str) -> Optional[str]:
        """Backward-compatible wrapper around canonical operation mapping."""
        return self._runtime_adapter.map_operation(path, method)

    def _read_client_request(
        self,
        client_socket: socket.socket,
        timeout_seconds: float = 10.0,
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """Read a full HTTP request including body bytes indicated by Content-Length."""
        request_data = b''
        header_end = -1
        deadline = time.time() + timeout_seconds

        while header_end == -1 and time.time() < deadline:
            try:
                chunk = client_socket.recv(4096)
            except socket.timeout:
                continue

            if not chunk:
                break

            request_data += chunk
            header_end = request_data.find(b'\r\n\r\n')

        if not request_data:
            return None, "empty"

        if header_end == -1:
            return None, "incomplete_headers"

        header_blob = request_data[:header_end].decode('utf-8', errors='replace')
        content_length = self._get_content_length(header_blob)
        if content_length is None:
            return request_data, None

        if content_length < 0:
            return None, "invalid_content_length"

        expected_total = header_end + 4 + content_length
        while len(request_data) < expected_total and time.time() < deadline:
            try:
                chunk = client_socket.recv(min(4096, expected_total - len(request_data)))
            except socket.timeout:
                continue

            if not chunk:
                break

            request_data += chunk

        if len(request_data) < expected_total:
            return None, "incomplete_body"

        return request_data, None

    def _extract_image_name(self, params: Dict[str, Any]) -> Optional[str]:
        """Extract image name from parameters"""
        if 'fromImage' in params:
            return params['fromImage'][0] if isinstance(params['fromImage'], list) else params['fromImage']

        if 'body' in params:
            body = params['body']
            if 'Image' in body:
                try:
                    import json
                    body_json = json.loads(body)
                    return body_json.get('Image')
                except:
                    pass

        return None

    def _extract_container_id(self, path: str) -> Optional[str]:
        """Extract container ID from path"""
        parts = path.split('/')
        for i, part in enumerate(parts):
            if part == 'containers' and i + 1 < len(parts):
                return parts[i + 1]
        return None

    @staticmethod
    def _extract_label_value(request_data: bytes, label_name: str) -> Optional[str]:
        """Extract a label value from a create request body's Labels dict."""
        try:
            text = request_data.decode('utf-8', errors='replace')
            for part in text.split('\r\n\r\n'):
                try:
                    body = json.loads(part)
                    labels = body.get('Labels') or {}
                    value = labels.get(label_name)
                    if value:  # non-empty string
                        return value
                except Exception:
                    continue
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_workload_id(request_data: bytes) -> Optional[str]:
        """Extract io.trucon.workload-id from a create request body's Labels dict."""
        return DockerProxyServer._extract_label_value(request_data, WORKLOAD_LABEL)

    @staticmethod
    def _extract_launch_id(request_data: bytes) -> Optional[str]:
        """Extract io.trucon.launch-id from a create request body's Labels dict."""
        return DockerProxyServer._extract_label_value(request_data, LAUNCH_LABEL)

    def _normalize_image(self, img: Optional[str]) -> str:
        if not img:
            return ""
        return img.split(':')[0].split('/')[-1]

    def forward_to_docker(self, request_data: bytes, request_path: str = "") -> Optional[bytes]:
        """Forward request to real Docker daemon and return response"""
        try:
            docker_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            docker_sock.settimeout(10)
            docker_sock.connect(self.docker_socket_path)
            
            docker_sock.sendall(request_data)
            
            response = self._read_docker_response(docker_sock, request_path)
            
            docker_sock.close()
            return response

        except FileNotFoundError:
            logger.error(f"Docker socket not found: {self.docker_socket_path}")
            return self._create_error_response("Docker daemon not available")
        except ConnectionRefusedError:
            logger.error(f"Connection refused to Docker socket: {self.docker_socket_path}")
            return self._create_error_response("Docker daemon not running")
        except socket.timeout:
            logger.error("Timeout waiting for Docker response")
            return self._create_error_response("Docker operation timed out")
        except Exception as e:
            logger.error(f"Error forwarding to Docker: {e}")
            return self._create_error_response(f"Proxy error: {str(e)}")

    def _read_docker_response(self, docker_sock: socket.socket, request_path: str = "") -> bytes:
        """Read Docker response with fast completion for non-streaming requests."""
        response = b''
        header_end = -1
        header_deadline = time.time() + 10

        # Phase 1: read until we have headers.
        while header_end == -1 and time.time() < header_deadline:
            try:
                chunk = docker_sock.recv(16384)
                if not chunk:
                    break
                response += chunk
                header_end = response.find(b"\r\n\r\n")
            except socket.timeout:
                continue

        if header_end == -1:
            logger.debug(f"Read {len(response)} bytes from Docker (no complete headers)")
            return response

        header_blob = response[:header_end].decode('utf-8', errors='replace')
        content_length = self._get_content_length(header_blob)

        # Phase 2a: fixed-size body.
        if content_length is not None:
            expected_total = header_end + 4 + content_length
            while len(response) < expected_total:
                try:
                    chunk = docker_sock.recv(min(16384, expected_total - len(response)))
                    if not chunk:
                        break
                    response += chunk
                except socket.timeout:
                    break
            logger.debug(f"Read {len(response)} bytes from Docker")
            return response

        # Phase 2b: unknown size/streaming body.
        idle_timeout = 8 if is_streaming_endpoint(request_path) else 2
        last_data_time = time.time()
        while True:
            try:
                chunk = docker_sock.recv(16384)
                if not chunk:
                    break
                response += chunk
                last_data_time = time.time()
            except socket.timeout:
                if time.time() - last_data_time >= idle_timeout:
                    break

        logger.debug(f"Read {len(response)} bytes from Docker")
        return response

    def _get_content_length(self, headers: str) -> Optional[int]:
        """Extract Content-Length from headers"""
        for line in headers.split('\r\n'):
            if line.lower().startswith('content-length:'):
                try:
                    return int(line.split(':')[1].strip())
                except:
                    pass
        return None

    def _create_error_response(self, message: str) -> bytes:
        """Create HTTP error response"""
        body = f'{{"message": "{message}"}}'
        response = (
            "HTTP/1.1 503 Service Unavailable\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "\r\n"
            f"{body}"
        )
        return response.encode('utf-8')

    def _create_commit_failed_response(self, operation_type: str, docker_status: Optional[int]) -> bytes:
        status_suffix = f" after Docker returned {docker_status}" if docker_status is not None else ""
        return self._create_error_response(
            f"Trusted log submission failed for docker {operation_type}{status_suffix}. "
            "The Docker operation may already have completed; inspect Docktap and TruCon logs before retrying."
        )

    def _create_bad_request_response(self, message: str) -> bytes:
        """Create HTTP 400 response for malformed client requests."""
        body = f'{{"message": "{message}"}}'
        response = (
            "HTTP/1.1 400 Bad Request\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "\r\n"
            f"{body}"
        )
        return response.encode('utf-8')

    def _attestation_gate_enabled(self) -> bool:
        return _cfg.require_attestation()

    @staticmethod
    def _delegation_required() -> bool:
        return _cfg.delegation_required()

    @staticmethod
    def _delegation_enabled() -> bool:
        return _cfg.delegation_enabled()

    @staticmethod
    def _absolute_url(base_url: str, path: str) -> str:
        return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))

    @staticmethod
    def _sigstore_oob_login_command(api_base_url: str) -> str:
        return (
            "tc-client "
            f"--base-url {api_base_url} --sigstore-login oob sigstore-token --format json"
        )

    def _create_auth_required_response(self, operation_type: str, session_id: str) -> bytes:
        api_base_url = _cfg.ATTESTATION_API_URL
        browser_base_url = _cfg.ATTESTATION_BROWSER_BASE_URL
        interactive_login_path = f"/api/sigstore/interactive-login?{urlencode({'operation': 'docktap', 'session_id': session_id})}"
        login_status_path = f"/api/sigstore/login-status/{session_id}"
        authorize_path = "/api/docktap/authorize"
        delegate_path = "/api/docktap/delegate"
        interactive_login_url = self._absolute_url(browser_base_url, interactive_login_path)
        login_status_url = self._absolute_url(api_base_url, login_status_path)
        authorize_url = self._absolute_url(api_base_url, authorize_path)
        delegate_url = self._absolute_url(api_base_url, delegate_path)
        oob_login_command = self._sigstore_oob_login_command(api_base_url)
        authorize_command = (
            "curl -X POST "
            f"{authorize_url} "
            "-H 'Content-Type: application/json' "
            f"-d '{{\"chain_id\": \"{_cfg.RUNTIME_CHAIN_ID}\", \"identity_token\": \"<paste token here>\"}}'"
        )
        delegate_command = (
            "curl -X POST "
            f"{delegate_url} "
            "-H 'Content-Type: application/json' "
            f"-d '{{\"chain_id\": \"{_cfg.RUNTIME_CHAIN_ID}\", \"identity_token\": \"<paste token here>\"}}'"
        )
        install_hint = (
            "If tc-client is unavailable, from the tc_api repo root run: bash setup.sh, "
            f"then run ./venv/bin/tc-client --base-url {api_base_url} --sigstore-login oob sigstore-token --format json"
        )
        if self._delegation_required():
            message = (
                f"Docktap authorization required before docker {operation_type}.\n"
                f"Browser login: {interactive_login_url}\n"
                f"Remote login command: {oob_login_command}\n"
                f"Ensure authorization: {authorize_command}\n"
                f"Direct delegation fallback: {delegate_command}\n"
                f"{install_hint}\n"
                "Then retry."
            )
        else:
            message = (
                f"Attested Docker login required before docker {operation_type}.\n"
                f"Browser login: {interactive_login_url}\n"
                f"Remote login command: {oob_login_command}\n"
                f"{install_hint}\n"
                "Then retry."
            )
        body = json.dumps(
            {
                "message": message,
                "detail": {
                    "auth_mode": _cfg.auth_mode(),
                    "interactive_login_url": interactive_login_url,
                    "interactive_continue_url": interactive_login_url,
                    "login_status_url": login_status_url,
                    "oob_login_command": oob_login_command,
                    "oob_login_install_hint": install_hint,
                    "authorize_url": authorize_url,
                    "authorize_command": authorize_command,
                    "delegate_url": delegate_url,
                    "delegate_command": delegate_command,
                    "remediation": {
                        "browser_login_url": interactive_login_url,
                        "remote_login_command": oob_login_command,
                        "remote_login_install_hint": install_hint,
                        "authorize_url": authorize_url,
                        "authorize_command": authorize_command,
                        "delegate_url": delegate_url,
                        "delegate_command": delegate_command,
                    },
                    "session_id": session_id,
                },
            }
        )
        response = (
            "HTTP/1.1 428 Precondition Required\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body.encode('utf-8'))}\r\n"
            "\r\n"
            f"{body}"
        )
        return response.encode("utf-8")

    def handle_client(self, client_socket: socket.socket):
        """Handle client connection with operation tracking and parent linking."""
        try:
            client_socket.settimeout(10)
            session_id = str(uuid.uuid4())

            while True:
                request_data, request_error = self._read_client_request(client_socket)
                if request_error:
                    if request_error != "empty":
                        client_socket.sendall(
                            self._create_bad_request_response(f"Malformed request: {request_error}")
                        )
                    break

                req_line = request_data.decode('utf-8', errors='replace').split('\r\n')[0]
                path = req_line.split(' ')[1] if len(req_line.split(' ')) > 1 else ""
                image_name = None
                if "fromImage=" in path:
                    parsed_qs = dict(parse_qs(path.split("?", 1)[1] if "?" in path else ""))
                    val = parsed_qs.get("fromImage")
                    if isinstance(val, list) and val:
                        image_name = val[0]
                    elif isinstance(val, str):
                        image_name = val

                body_image = None
                if b"Image" in request_data:
                    try:
                        body_text = request_data.decode('utf-8', errors='replace')
                        for part in body_text.split('\r\n\r\n'):
                            try:
                                body = json.loads(part)
                                body_image = body.get("Image", "")
                            except Exception:
                                pass
                    except Exception:
                        pass

                image_name_normalized = self._normalize_image(image_name or body_image)

                container_name = None
                if "/containers/" in path:
                    parts = path.split("/containers/")
                    if len(parts) > 1:
                        container_from_path = parts[1].split("/")[0]
                        if "?" in container_from_path:
                            container_from_path = container_from_path.split("?")[0]
                        container_name = container_from_path

                if b'"name"' in request_data:
                    try:
                        body_text = request_data.decode('utf-8', errors='replace')
                        for part in body_text.split('\r\n\r\n'):
                            try:
                                body = json.loads(part)
                                if body.get("name"):
                                    container_name = body.get("name")
                            except Exception:
                                pass
                    except Exception:
                        pass

                last_container_op_id = None
                last_image_op_id = None

                if container_name:
                    create_op = self.tracker.find_create_for_container(container_name)
                    if create_op:
                        last_container_op_id = create_op.operation_id

                if image_name_normalized:
                    pull_op = self.tracker.find_pull_for_image(image_name_normalized)
                    if pull_op:
                        last_image_op_id = pull_op.operation_id

                op_record = self._runtime_adapter.parse_operation_metadata(request_data, session_id)
                if op_record.operation.get("type") == "create":
                    op_record.parent_id = last_image_op_id
                elif op_record.operation.get("type") in ("start", "stop", "rm"):
                    op_record.parent_id = last_container_op_id

                operation, path_only, params = self._parse_http_request(request_data)
                if self._log_callback:
                    log_data = {
                        'operation': operation,
                        'path': path_only,
                        'method': params.get('method'),
                        'timestamp': datetime.now().isoformat() + 'Z',
                        'runtime_engine': self._runtime_adapter.runtime_engine,
                    }
                    image_for_callback = self._extract_image_name(params)
                    if image_for_callback:
                        log_data['image'] = image_for_callback
                    container_id = self._extract_container_id(path_only or "")
                    if container_id:
                        log_data['container_id'] = container_id
                    if 'fromImage' in params:
                        log_data['fromImage'] = params['fromImage']
                    if 'tag' in params:
                        log_data['tag'] = params['tag']
                    self._log_callback(log_data)

                if operation in SUBMITTABLE_OPERATIONS and self._attestation_gate_enabled():
                    delegation_ok = self._delegation_enabled() and has_active_delegation()
                    token_ok = has_reusable_identity_token()
                    if (self._delegation_required() and not delegation_ok) or (
                        not self._delegation_required() and not token_ok
                    ):
                        response = self._create_auth_required_response(operation, session_id)
                        client_socket.sendall(response)
                        logger.info("Blocked docker %s until required Docktap authorization becomes available", operation)
                        break

                docker_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                docker_sock.settimeout(30)
                docker_sock.connect(self.docker_socket_path)
                docker_sock.sendall(request_data)
                if not is_streaming_endpoint(path):
                    docker_sock.shutdown(socket.SHUT_WR)

                response = self._read_docker_response(docker_sock, path)
                docker_sock.close()

                if response:
                    logger.debug(f"Sent response: {len(response)} bytes buffered")
                    enrich_from_response(op_record, response)
                    self.tracker.add(op_record)
                    log_operation_json(op_record)

                    should_delay_success_response = False
                    async_submission = None
                    if self._trucon_committer is not None:
                        op_type = op_record.operation.get("type")
                        response_status = (op_record.response or {}).get("status")
                        should_delay_success_response = (
                            op_type in SUBMITTABLE_OPERATIONS
                            and isinstance(response_status, int)
                            and 200 <= response_status < 400
                        )

                        if op_type in SUBMITTABLE_OPERATIONS:
                            workload_id = None
                            launch_id = None
                            if op_type == "create":
                                workload_id = self._extract_workload_id(request_data)
                                launch_id = self._extract_launch_id(request_data)

                            if should_delay_success_response and op_type in {"pull", "create", "start", "stop", "rm"}:
                                async_submission = (op_type, workload_id, launch_id)
                            else:
                                commit_ok = self._trucon_committer.submit_operation(
                                    op_record,
                                    op_type,
                                    workload_id=workload_id,
                                    launch_id=launch_id,
                                )
                                if should_delay_success_response and not commit_ok:
                                    client_socket.sendall(
                                        self._create_commit_failed_response(op_type, response_status)
                                    )
                                    logger.warning(
                                        "Returned Docker error to client because TruCon commit failed for %s after Docker status %s",
                                        op_type,
                                        response_status,
                                    )
                                    break

                    client_socket.sendall(response)
                    if async_submission is not None:
                        op_type, workload_id, launch_id = async_submission
                        queue_id = self._trucon_committer.enqueue_operation(
                            op_record,
                            op_type,
                            workload_id=workload_id,
                            launch_id=launch_id,
                        )
                        logger.info(
                            "Queued background TruCon submission for %s after Docker returned %s (queue_id=%s)",
                            op_type,
                            response_status,
                            queue_id,
                        )
                else:
                    logger.error("No response from Docker")
                    break

        except Exception as e:
            logger.error(f"Error handling client: {e}", exc_info=True)
        finally:
            client_socket.close()

    def start(self):
        """Start the proxy server"""
        if os.path.exists(self.listen_socket_path):
            os.remove(self.listen_socket_path)

        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(self.listen_socket_path)
        self.server_socket.listen(5)
        
        os.chmod(self.listen_socket_path, 0o777)
        
        self.running = True
        logger.info(f"Docker proxy listening on {self.listen_socket_path}")
        logger.info(f"Forwarding to Docker at {self.docker_socket_path}")

        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                client_socket, _ = self.server_socket.accept()
                thread = threading.Thread(target=self.handle_client, args=(client_socket,))
                thread.daemon = True
                thread.start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error accepting connection: {e}")
                break

    def stop(self):
        """Stop the proxy server"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        if os.path.exists(self.listen_socket_path):
            os.remove(self.listen_socket_path)
        logger.info("Docker proxy stopped")