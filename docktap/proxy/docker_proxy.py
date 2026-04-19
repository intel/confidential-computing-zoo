import socket
import threading
import logging
import os
import time
import uuid
import json
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from urllib.parse import parse_qs, urlparse

from .operation_log import (
    OperationTracker,
    get_operation_type,
    parse_operation_metadata,
    enrich_from_response,
    log_operation_json,
    is_streaming_endpoint,
)

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
    ):
        self.listen_socket_path = listen_socket_path
        self.docker_socket_path = docker_socket_path
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.client_handler_thread: Optional[threading.Thread] = None
        self._log_callback = None
        self.tracker = OperationTracker()
        self._trucon_committer = trucon_committer

    def set_log_callback(self, callback):
        """Set callback function for logging operations"""
        self._log_callback = callback

    def _parse_http_request(self, data: bytes) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """Parse HTTP request to extract operation and parameters"""
        try:
            request_str = data.decode('utf-8', errors='ignore')
            lines = request_str.split('\r\n')
            
            if not lines:
                return None, None, {}

            request_line = lines[0]
            parts = request_line.split(' ')
            
            if len(parts) < 2:
                return None, None, {}

            method = parts[0]
            path = parts[1]

            parsed = urlparse(path)
            path_only = parsed.path
            query_params = parse_qs(parsed.query)

            operation = get_operation_type(method, path)

            params = {}
            if query_params:
                params.update(query_params)

            body_start = request_str.find('\r\n\r\n')
            if body_start != -1:
                body = request_str[body_start + 4:]
                if body:
                    params['body'] = body

            params['method'] = method
            params['path'] = path_only

            return operation, path_only, params

        except Exception as e:
            logger.error(f"Error parsing HTTP request: {e}")
            return None, None, {}

    def _map_path_to_operation(self, path: str, method: str) -> Optional[str]:
        """Backward-compatible wrapper around canonical operation mapping."""
        return get_operation_type(method, path)

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

    def handle_client(self, client_socket: socket.socket):
        """Handle client connection with operation tracking and parent linking."""
        try:
            session_id = str(uuid.uuid4())
            client_socket.settimeout(10)

            request_data, request_error = self._read_client_request(client_socket)
            if request_error:
                if request_error != "empty":
                    client_socket.sendall(
                        self._create_bad_request_response(f"Malformed request: {request_error}")
                    )
                client_socket.close()
                return

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

            op_record = parse_operation_metadata(request_data, session_id)
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
                    'timestamp': datetime.now().isoformat() + 'Z'
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
            
            # Stream response to client as it arrives to avoid client-side stalls.
            docker_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            docker_sock.settimeout(10)
            docker_sock.connect(self.docker_socket_path)
            docker_sock.sendall(request_data)

            response = b""
            header_end = -1
            content_length = None
            body_bytes_received = 0
            idle_timeout = 8 if is_streaming_endpoint(path) else 2
            max_duration = 45 if is_streaming_endpoint(path) else 15
            started_at = time.time()
            last_data_time = time.time()

            while True:
                if time.time() - started_at >= max_duration:
                    logger.warning(
                        "Response read deadline reached for path %s (streaming=%s)",
                        path,
                        is_streaming_endpoint(path),
                    )
                    break

                try:
                    chunk = docker_sock.recv(16384)
                except socket.timeout:
                    if time.time() - last_data_time >= idle_timeout:
                        break
                    continue

                if not chunk:
                    break

                last_data_time = time.time()
                client_socket.sendall(chunk)

                # Keep a bounded buffer for metadata extraction/logging.
                if len(response) < 262144:
                    remaining = 262144 - len(response)
                    response += chunk[:remaining]

                if header_end == -1:
                    header_end = response.find(b"\r\n\r\n")
                    if header_end != -1:
                        header_blob = response[:header_end].decode('utf-8', errors='replace')
                        content_length = self._get_content_length(header_blob)
                        body_part = response[header_end + 4:]
                        body_bytes_received = len(body_part)
                else:
                    body_bytes_received += len(chunk)

                if content_length is not None and body_bytes_received >= content_length:
                    break

            docker_sock.close()

            if response:
                logger.debug(f"Sent response: {len(response)} bytes buffered")
                enrich_from_response(op_record, response)
                self.tracker.add(op_record)
                log_operation_json(op_record)

                # Best-effort TruCon commit (after response already returned to CLI)
                if self._trucon_committer is not None:
                    op_type = op_record.operation.get("type")
                    from trucon_client import SUBMITTABLE_OPERATIONS
                    if op_type in SUBMITTABLE_OPERATIONS:
                        # Resolve workload_id for create ops from labels
                        workload_id = None
                        launch_id = None
                        if op_type == "create":
                            workload_id = self._extract_workload_id(request_data)
                            launch_id = self._extract_launch_id(request_data)
                        self._trucon_committer.submit_operation(
                            op_record,
                            op_type,
                            workload_id=workload_id,
                            launch_id=launch_id,
                        )
            else:
                logger.error("No response from Docker")

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