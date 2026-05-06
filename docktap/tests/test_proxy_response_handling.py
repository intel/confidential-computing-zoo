import socket
from unittest.mock import patch

from proxy.docker_proxy import DockerProxyServer
from proxy.operation_log import OperationRecord


class FakeClientSocket:
    def __init__(self):
        self.timeout = None
        self.sent = []
        self.closed = False

    def settimeout(self, value):
        self.timeout = value

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True


class FakeDockerSocket:
    def __init__(self):
        self.timeout = None
        self.timeout_history = []
        self.connected = None
        self.sent = []
        self.shutdown_calls = []
        self.closed = False

    def settimeout(self, value):
        self.timeout = value
        self.timeout_history.append(value)

    def connect(self, path):
        self.connected = path

    def sendall(self, data):
        self.sent.append(data)

    def shutdown(self, how):
        self.shutdown_calls.append(how)

    def close(self):
        self.closed = True


def test_handle_client_uses_shared_response_reader_without_half_closing_upstream_socket():
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
         patch.object(proxy, "_read_client_request", return_value=(request_data, None)), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("stop", "/v1.41/containers/demo/stop", {})), \
         patch.object(proxy, "_read_docker_response", return_value=response_data) as read_response, \
         patch("proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("proxy.docker_proxy.log_operation_json") as log_operation_json:
        proxy.handle_client(client_socket)

    assert docker_socket.timeout == 30
    assert docker_socket.connected == "/var/run/docker.sock"
    assert docker_socket.sent == [request_data]
    assert docker_socket.shutdown_calls == []
    read_response.assert_called_once_with(docker_socket, "/v1.41/containers/demo/stop")
    assert client_socket.sent == [response_data]
    enrich_response.assert_called_once_with(op_record, response_data)
    log_operation_json.assert_called_once_with(op_record)
    assert docker_socket.closed is True
    assert client_socket.closed is True


def test_handle_client_blocks_submittable_request_until_attestation_login_is_ready(monkeypatch):
    proxy = DockerProxyServer(
        listen_socket_path="/tmp/test-docker-proxy.sock",
        docker_socket_path="/var/run/docker.sock",
        trucon_committer=object(),
    )
    client_socket = FakeClientSocket()
    request_data = b"POST /v1.41/images/create?fromImage=hello-world&tag=latest HTTP/1.1\r\nHost: localhost\r\n\r\n"
    op_record = OperationRecord(
        operation={"type": "pull", "action": "docker pull", "api_path": "/v1.41/images/create", "method": "POST"},
        image={"name": "hello-world", "tag": "latest"},
    )

    monkeypatch.setenv("DOCKTAP_REQUIRE_ATTESTATION", "1")

    with patch.object(proxy, "_read_client_request", return_value=(request_data, None)), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("pull", "/v1.41/images/create", {"fromImage": "hello-world", "tag": "latest"})), \
         patch("proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("proxy.docker_proxy.log_operation_json") as log_operation_json, \
         patch("trucon_client._resolve_identity_token_str", return_value=None), \
         patch("trucon_client.get_attestation_challenge", return_value={
             "status": "login_required",
             "interactive_login_url": "http://127.0.0.1:8000/api/sigstore/interactive-login?operation=docktap",
             "auth_url": "https://oauth2.sigstore.dev/auth?client_id=sigstore",
             "session_id": "sess-1",
             "login_status_url": "http://127.0.0.1:8000/api/sigstore/login-status/sess-1",
         }):
        proxy.handle_client(client_socket)

    assert len(client_socket.sent) == 1
    response_text = client_socket.sent[0].decode("utf-8")
    assert "428 Precondition Required" in response_text
    assert "Attested Docker login required before docker pull" in response_text
    assert "http://127.0.0.1:8000/api/sigstore/interactive-login?operation=docktap" in response_text
    enrich_response.assert_not_called()
    log_operation_json.assert_not_called()


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
         patch.object(proxy, "_read_client_request", return_value=(request_data, None)), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("stop", "/v1.41/containers/demo/stop", {})), \
         patch.object(proxy, "_read_docker_response", return_value=b""), \
         patch("proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("proxy.docker_proxy.log_operation_json") as log_operation_json:
        proxy.handle_client(client_socket)

    assert client_socket.sent == []
    enrich_response.assert_not_called()
    log_operation_json.assert_not_called()
    assert docker_socket.shutdown_calls == []
    assert client_socket.closed is True


class SequencedDockerSocket:
    def __init__(self, responses):
        self.responses = list(responses)
        self.timeout = None
        self.timeout_history = []

    def settimeout(self, value):
        self.timeout = value
        self.timeout_history.append(value)

    def recv(self, _size):
        if not self.responses:
            raise AssertionError("recv called after response sequence exhausted")
        next_item = self.responses.pop(0)
        if isinstance(next_item, BaseException):
            raise next_item
        return next_item


def test_read_docker_response_uses_idle_timeout_for_unknown_length_non_streaming_response():
    proxy = DockerProxyServer()
    docker_socket = SequencedDockerSocket(
        [
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n",
            b"payload",
            socket.timeout(),
        ]
    )

    response = proxy._read_docker_response(docker_socket, "/v1.41/containers/demo/stop")

    assert response == b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\npayload"
    assert docker_socket.timeout_history[-1] == 2