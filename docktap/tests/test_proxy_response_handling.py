import json
import os
import socket
from unittest.mock import patch

from proxy.docker_proxy import DockerProxyServer
from proxy.operation_log import OperationRecord


class FakeClientSocket:
    def __init__(self, recv_chunks=None):
        self.timeout = None
        self.sent = []
        self.closed = False
        self.recv_chunks = list(recv_chunks or [])

    def settimeout(self, value):
        self.timeout = value

    def recv(self, _size):
        if self.recv_chunks:
            return self.recv_chunks.pop(0)
        return b""

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True


class FakeDockerSocket:
    def __init__(self):
        self.timeout = None
        self.connected = None
        self.sent = []
        self.shutdown_calls = []
        self.closed = False

    def settimeout(self, value):
        self.timeout = value

    def connect(self, path):
        self.connected = path

    def sendall(self, data):
        self.sent.append(data)

    def shutdown(self, how):
        self.shutdown_calls.append(how)

    def close(self):
        self.closed = True


def test_handle_client_uses_shared_response_reader_and_half_closes_non_streaming_upstream_socket():
    proxy = DockerProxyServer(
        listen_socket_path="/tmp/test-docker-proxy.sock",
        docker_socket_path="/var/run/docker.sock",
    )
    client_socket = FakeClientSocket()
    docker_socket = FakeDockerSocket()
    request_data = b"POST /v1.41/containers/demo/stop HTTP/1.1\r\nHost: localhost\r\n\r\n"
    response_data = b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n"
    op_record = OperationRecord(
        operation={"type": "stop", "action": "docker stop", "api_path": "/v1.41/containers/demo/stop", "method": "POST"},
        container={"id": "demo"},
    )

    with patch("proxy.docker_proxy.socket.socket", return_value=docker_socket), \
            patch("proxy.docker_proxy.has_reusable_identity_token", return_value=True), \
            patch.object(proxy, "_read_client_request", side_effect=[(request_data, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("stop", "/v1.41/containers/demo/stop", {})), \
         patch.object(proxy, "_read_docker_response", return_value=response_data) as read_response, \
         patch("proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("proxy.docker_proxy.log_operation_json") as log_operation_json:
        proxy.handle_client(client_socket)

    assert docker_socket.timeout == 30
    assert docker_socket.connected == "/var/run/docker.sock"
    assert docker_socket.sent == [request_data]
    assert docker_socket.shutdown_calls == [socket.SHUT_WR]
    read_response.assert_called_once_with(docker_socket, "/v1.41/containers/demo/stop")
    assert client_socket.sent == [response_data]
    enrich_response.assert_called_once_with(op_record, response_data)
    log_operation_json.assert_called_once_with(op_record)
    assert docker_socket.closed is True
    assert client_socket.closed is True


def test_handle_client_keeps_streaming_upstream_socket_open_for_pull_requests():
    proxy = DockerProxyServer(
        listen_socket_path="/tmp/test-docker-proxy.sock",
        docker_socket_path="/var/run/docker.sock",
    )
    client_socket = FakeClientSocket()
    docker_socket = FakeDockerSocket()
    request_data = b"POST /v1.41/images/create?fromImage=hello-world&tag=latest HTTP/1.1\r\nHost: localhost\r\n\r\n"
    response_data = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
    op_record = OperationRecord(
        operation={"type": "pull", "action": "docker pull", "api_path": "/v1.41/images/create", "method": "POST"},
        image={"name": "hello-world"},
    )

    with patch("proxy.docker_proxy.socket.socket", return_value=docker_socket), \
            patch("proxy.docker_proxy.has_reusable_identity_token", return_value=True), \
            patch.object(proxy, "_read_client_request", side_effect=[(request_data, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("pull", "/v1.41/images/create", {})), \
         patch.object(proxy, "_read_docker_response", return_value=response_data) as read_response, \
         patch("proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("proxy.docker_proxy.log_operation_json") as log_operation_json:
        proxy.handle_client(client_socket)

    assert docker_socket.sent == [request_data]
    assert docker_socket.shutdown_calls == []
    read_response.assert_called_once_with(docker_socket, "/v1.41/images/create?fromImage=hello-world&tag=latest")
    assert client_socket.sent == [response_data]
    enrich_response.assert_called_once_with(op_record, response_data)
    log_operation_json.assert_called_once_with(op_record)
    assert docker_socket.closed is True
    assert client_socket.closed is True


def test_handle_client_records_no_response_when_shared_reader_returns_empty_bytes():
    proxy = DockerProxyServer(
        listen_socket_path="/tmp/test-docker-proxy.sock",
        docker_socket_path="/var/run/docker.sock",
    )
    client_socket = FakeClientSocket()
    docker_socket = FakeDockerSocket()
    request_data = b"POST /v1.41/containers/demo/stop HTTP/1.1\r\nHost: localhost\r\n\r\n"
    op_record = OperationRecord(
        operation={"type": "stop", "action": "docker stop", "api_path": "/v1.41/containers/demo/stop", "method": "POST"},
        container={"id": "demo"},
    )

    with patch("proxy.docker_proxy.socket.socket", return_value=docker_socket), \
            patch("proxy.docker_proxy.has_reusable_identity_token", return_value=True), \
            patch.object(proxy, "_read_client_request", side_effect=[(request_data, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("stop", "/v1.41/containers/demo/stop", {})), \
         patch.object(proxy, "_read_docker_response", return_value=b""), \
         patch("proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("proxy.docker_proxy.log_operation_json") as log_operation_json:
        proxy.handle_client(client_socket)

    assert client_socket.sent == []
    enrich_response.assert_not_called()
    log_operation_json.assert_not_called()
    assert docker_socket.shutdown_calls == [socket.SHUT_WR]
    assert client_socket.closed is True


def test_handle_client_processes_multiple_requests_on_one_client_connection():
    proxy = DockerProxyServer(
        listen_socket_path="/tmp/test-docker-proxy.sock",
        docker_socket_path="/var/run/docker.sock",
    )
    client_socket = FakeClientSocket(recv_chunks=[b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n", b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"])
    first_docker_socket = FakeDockerSocket()
    second_docker_socket = FakeDockerSocket()
    first_request = b"HEAD /_ping HTTP/1.1\r\nHost: localhost\r\n\r\n"
    second_request = b"GET /v1.41/info HTTP/1.1\r\nHost: localhost\r\n\r\n"
    first_response = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
    second_response = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"
    first_record = OperationRecord(
        operation={"type": "preflight_ping", "action": "docker preflight_ping", "api_path": "/_ping", "method": "HEAD"},
    )
    second_record = OperationRecord(
        operation={"type": "preflight_info", "action": "docker preflight_info", "api_path": "/v1.41/info", "method": "GET"},
    )

    with patch("proxy.docker_proxy.socket.socket", side_effect=[first_docker_socket, second_docker_socket]), \
         patch.object(proxy, "_read_client_request", side_effect=[(first_request, None), (second_request, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", side_effect=[first_record, second_record]), \
         patch.object(proxy, "_parse_http_request", side_effect=[("preflight_ping", "/_ping", {}), ("preflight_info", "/v1.41/info", {})]), \
         patch.object(proxy, "_read_docker_response", side_effect=[first_response, second_response]), \
         patch("proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("proxy.docker_proxy.log_operation_json") as log_operation_json:
        proxy.handle_client(client_socket)

    assert first_docker_socket.sent == [first_request]
    assert second_docker_socket.sent == [second_request]
    assert first_docker_socket.shutdown_calls == [socket.SHUT_WR]
    assert second_docker_socket.shutdown_calls == [socket.SHUT_WR]
    assert client_socket.sent == [first_response, second_response]
    assert enrich_response.call_count == 2
    assert log_operation_json.call_count == 2
    assert client_socket.closed is True


def test_handle_client_blocks_submittable_requests_without_attestation_token():
    proxy = DockerProxyServer(
        listen_socket_path="/tmp/test-docker-proxy.sock",
        docker_socket_path="/var/run/docker.sock",
    )
    client_socket = FakeClientSocket()
    request_data = b"POST /v1.41/images/create?fromImage=hello-world&tag=latest HTTP/1.1\r\nHost: localhost\r\n\r\n"
    op_record = OperationRecord(
        operation={"type": "pull", "action": "docker pull", "api_path": "/v1.41/images/create", "method": "POST"},
        image={"name": "hello-world"},
    )

    with patch.dict(os.environ, {
        "DOCKTAP_REQUIRE_ATTESTATION": "1",
        "DOCKTAP_ATTESTATION_API_URL": "http://127.0.0.1:8000",
        "DOCKTAP_ATTESTATION_BROWSER_BASE_URL": "http://127.0.0.1:8000",
    }, clear=False), \
         patch("proxy.docker_proxy.socket.socket") as socket_ctor, \
         patch("proxy.docker_proxy.has_reusable_identity_token", return_value=False), \
         patch.object(proxy, "_read_client_request", side_effect=[(request_data, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("pull", "/v1.41/images/create", {"fromImage": ["hello-world"], "tag": ["latest"]})), \
         patch("proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("proxy.docker_proxy.log_operation_json") as log_operation_json:
        proxy.handle_client(client_socket)

    socket_ctor.assert_not_called()
    assert len(client_socket.sent) == 1
    header_blob, body_blob = client_socket.sent[0].split(b"\r\n\r\n", 1)
    assert header_blob.startswith(b"HTTP/1.1 428 Precondition Required")
    payload = json.loads(body_blob.decode("utf-8"))
    assert payload["message"].startswith("Attested Docker login required before docker pull.\n")
    assert "\nBrowser login: http://127.0.0.1:8000/api/sigstore/interactive-login?operation=docktap" in payload["message"]
    assert "\nRemote login command: tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json\n" in payload["message"]
    assert "If tc-client is unavailable, from the tc_api repo root run: bash setup.sh" in payload["message"]
    assert payload["message"].endswith("\nThen retry.")
    assert payload["detail"]["interactive_login_url"].startswith("http://127.0.0.1:8000/api/sigstore/interactive-login?operation=docktap")
    assert payload["detail"]["login_status_url"].startswith("http://127.0.0.1:8000/api/sigstore/login-status/")
    assert payload["detail"]["oob_login_command"] == "tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json"
    assert payload["detail"]["oob_login_install_hint"] == "If tc-client is unavailable, from the tc_api repo root run: bash setup.sh, then run ./venv/bin/tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json"
    assert payload["detail"]["remediation"]["browser_login_url"].startswith("http://127.0.0.1:8000/api/sigstore/interactive-login?operation=docktap")
    assert payload["detail"]["remediation"]["remote_login_command"] == payload["detail"]["oob_login_command"]
    assert payload["detail"]["remediation"]["remote_login_install_hint"] == payload["detail"]["oob_login_install_hint"]
    enrich_response.assert_not_called()
    log_operation_json.assert_not_called()
    assert client_socket.closed is True


def test_handle_client_returns_503_when_trucon_commit_fails_after_successful_docker_pull():
    class FailingCommitter:
        def submit_operation(self, *args, **kwargs):
            return False

    proxy = DockerProxyServer(
        listen_socket_path="/tmp/test-docker-proxy.sock",
        docker_socket_path="/var/run/docker.sock",
        trucon_committer=FailingCommitter(),
    )
    client_socket = FakeClientSocket()
    docker_socket = FakeDockerSocket()
    request_data = b"POST /v1.41/images/create?fromImage=hello-world&tag=latest HTTP/1.1\r\nHost: localhost\r\n\r\n"
    response_data = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"
    op_record = OperationRecord(
        operation={"type": "pull", "action": "docker pull", "api_path": "/v1.41/images/create", "method": "POST"},
        image={"name": "hello-world"},
        response={"status": 200},
    )

    with patch("proxy.docker_proxy.socket.socket", return_value=docker_socket), \
         patch("proxy.docker_proxy.has_reusable_identity_token", return_value=True), \
         patch.object(proxy, "_read_client_request", side_effect=[(request_data, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("pull", "/v1.41/images/create", {})), \
         patch.object(proxy, "_read_docker_response", return_value=response_data), \
         patch("proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("proxy.docker_proxy.log_operation_json") as log_operation_json:
        proxy.handle_client(client_socket)

    assert len(client_socket.sent) == 1
    assert client_socket.sent[0].startswith(b"HTTP/1.1 503 Service Unavailable")
    assert b"Trusted log submission failed for docker pull after Docker returned 200" in client_socket.sent[0]
    enrich_response.assert_called_once_with(op_record, response_data)
    log_operation_json.assert_called_once_with(op_record)