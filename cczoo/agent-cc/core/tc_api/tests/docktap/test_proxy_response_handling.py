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
import socket
from unittest.mock import patch

from tc_api.docktap.proxy.docker_proxy import DockerProxyServer
from tc_api.docktap.proxy.operation_log import OperationRecord


DEFAULT_CHAIN_ID = "default"


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

    with patch.dict(os.environ, {"DOCKTAP_AUTH_MODE": "delegation_disabled"}, clear=False), \
            patch("tc_api.docktap.proxy.docker_proxy.socket.socket", return_value=docker_socket), \
            patch("tc_api.docktap.proxy.docker_proxy.has_reusable_identity_token", return_value=True), \
            patch.object(proxy, "_read_client_request", side_effect=[(request_data, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("stop", "/v1.41/containers/demo/stop", {})), \
         patch.object(proxy, "_read_docker_response", return_value=response_data) as read_response, \
         patch("tc_api.docktap.proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("tc_api.docktap.proxy.docker_proxy.log_operation_json") as log_operation_json:
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

    with patch.dict(os.environ, {"DOCKTAP_AUTH_MODE": "delegation_disabled"}, clear=False), \
            patch("tc_api.docktap.proxy.docker_proxy.socket.socket", return_value=docker_socket), \
            patch("tc_api.docktap.proxy.docker_proxy.has_reusable_identity_token", return_value=True), \
            patch.object(proxy, "_read_client_request", side_effect=[(request_data, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("pull", "/v1.41/images/create", {})), \
         patch.object(proxy, "_read_docker_response", return_value=response_data) as read_response, \
         patch("tc_api.docktap.proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("tc_api.docktap.proxy.docker_proxy.log_operation_json") as log_operation_json:
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

    with patch.dict(os.environ, {"DOCKTAP_AUTH_MODE": "delegation_disabled"}, clear=False), \
            patch("tc_api.docktap.proxy.docker_proxy.socket.socket", return_value=docker_socket), \
            patch("tc_api.docktap.proxy.docker_proxy.has_reusable_identity_token", return_value=True), \
            patch.object(proxy, "_read_client_request", side_effect=[(request_data, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("stop", "/v1.41/containers/demo/stop", {})), \
         patch.object(proxy, "_read_docker_response", return_value=b""), \
         patch("tc_api.docktap.proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("tc_api.docktap.proxy.docker_proxy.log_operation_json") as log_operation_json:
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

    with patch("tc_api.docktap.proxy.docker_proxy.socket.socket", side_effect=[first_docker_socket, second_docker_socket]), \
         patch.object(proxy, "_read_client_request", side_effect=[(first_request, None), (second_request, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", side_effect=[first_record, second_record]), \
         patch.object(proxy, "_parse_http_request", side_effect=[("preflight_ping", "/_ping", {}), ("preflight_info", "/v1.41/info", {})]), \
         patch.object(proxy, "_read_docker_response", side_effect=[first_response, second_response]), \
         patch("tc_api.docktap.proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("tc_api.docktap.proxy.docker_proxy.log_operation_json") as log_operation_json:
        proxy.handle_client(client_socket)

    assert first_docker_socket.sent == [first_request]
    assert second_docker_socket.sent == [second_request]
    assert first_docker_socket.shutdown_calls == [socket.SHUT_WR]
    assert second_docker_socket.shutdown_calls == [socket.SHUT_WR]
    assert client_socket.sent == [first_response, second_response]
    assert enrich_response.call_count == 2
    assert log_operation_json.call_count == 2
    assert client_socket.closed is True


def test_handle_client_blocks_submittable_requests_without_active_delegation_by_default():
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
        "DOCKTAP_AUTH_MODE": "explicit_delegation",
        "DOCKTAP_ATTESTATION_API_URL": "http://127.0.0.1:8000",
        "DOCKTAP_ATTESTATION_BROWSER_BASE_URL": "http://127.0.0.1:8000",
    }, clear=False), \
         patch("tc_api.docktap.proxy.docker_proxy.socket.socket") as socket_ctor, \
         patch("tc_api.docktap.proxy.docker_proxy.has_reusable_identity_token", return_value=False), \
         patch("tc_api.docktap.proxy.docker_proxy.has_active_delegation", return_value=False), \
         patch.object(proxy, "_read_client_request", side_effect=[(request_data, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("pull", "/v1.41/images/create", {"fromImage": ["hello-world"], "tag": ["latest"]})), \
         patch("tc_api.docktap.proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("tc_api.docktap.proxy.docker_proxy.log_operation_json") as log_operation_json:
        proxy.handle_client(client_socket)

    socket_ctor.assert_not_called()
    assert len(client_socket.sent) == 1
    header_blob, body_blob = client_socket.sent[0].split(b"\r\n\r\n", 1)
    assert header_blob.startswith(b"HTTP/1.1 428 Precondition Required")
    payload = json.loads(body_blob.decode("utf-8"))
    assert payload["message"].startswith("Docktap authorization required before docker pull.\n")
    assert "\nBrowser login: http://127.0.0.1:8000/api/sigstore/interactive-login?operation=docktap" in payload["message"]
    assert "\nRemote login command: tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json\n" in payload["message"]
    assert f"\nEnsure authorization: curl -X POST http://127.0.0.1:8000/api/docktap/authorize -H 'Content-Type: application/json' -d '{{\"chain_id\": \"{DEFAULT_CHAIN_ID}\", \"identity_token\": \"<paste token here>\"}}'\n" in payload["message"]
    assert f"\nDirect delegation fallback: curl -X POST http://127.0.0.1:8000/api/docktap/delegate -H 'Content-Type: application/json' -d '{{\"chain_id\": \"{DEFAULT_CHAIN_ID}\", \"identity_token\": \"<paste token here>\"}}'\n" in payload["message"]
    assert "If tc-client is unavailable, from the tc_api repo root run: bash setup.sh" in payload["message"]
    assert payload["message"].endswith("\nThen retry.")
    assert payload["detail"]["auth_mode"] == "explicit_delegation"
    assert payload["detail"]["interactive_login_url"].startswith("http://127.0.0.1:8000/api/sigstore/interactive-login?operation=docktap")
    assert payload["detail"]["login_status_url"].startswith("http://127.0.0.1:8000/api/sigstore/login-status/")
    assert payload["detail"]["oob_login_command"] == "tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json"
    assert payload["detail"]["oob_login_install_hint"] == "If tc-client is unavailable, from the tc_api repo root run: bash setup.sh, then run ./venv/bin/tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json"
    assert payload["detail"]["authorize_url"] == "http://127.0.0.1:8000/api/docktap/authorize"
    assert payload["detail"]["authorize_command"] == f"curl -X POST http://127.0.0.1:8000/api/docktap/authorize -H 'Content-Type: application/json' -d '{{\"chain_id\": \"{DEFAULT_CHAIN_ID}\", \"identity_token\": \"<paste token here>\"}}'"
    assert payload["detail"]["delegate_url"] == "http://127.0.0.1:8000/api/docktap/delegate"
    assert payload["detail"]["delegate_command"] == f"curl -X POST http://127.0.0.1:8000/api/docktap/delegate -H 'Content-Type: application/json' -d '{{\"chain_id\": \"{DEFAULT_CHAIN_ID}\", \"identity_token\": \"<paste token here>\"}}'"
    assert payload["detail"]["remediation"]["browser_login_url"].startswith("http://127.0.0.1:8000/api/sigstore/interactive-login?operation=docktap")
    assert payload["detail"]["remediation"]["remote_login_command"] == payload["detail"]["oob_login_command"]
    assert payload["detail"]["remediation"]["remote_login_install_hint"] == payload["detail"]["oob_login_install_hint"]
    assert payload["detail"]["remediation"]["authorize_url"] == payload["detail"]["authorize_url"]
    assert payload["detail"]["remediation"]["authorize_command"] == payload["detail"]["authorize_command"]
    assert payload["detail"]["remediation"]["delegate_url"] == payload["detail"]["delegate_url"]
    assert payload["detail"]["remediation"]["delegate_command"] == payload["detail"]["delegate_command"]
    enrich_response.assert_not_called()
    log_operation_json.assert_not_called()
    assert client_socket.closed is True


def test_handle_client_blocks_submittable_requests_without_attestation_token_when_delegation_disabled():
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
        "DOCKTAP_AUTH_MODE": "delegation_disabled",
        "DOCKTAP_ATTESTATION_API_URL": "http://127.0.0.1:8000",
        "DOCKTAP_ATTESTATION_BROWSER_BASE_URL": "http://127.0.0.1:8000",
    }, clear=False), \
         patch("tc_api.docktap.proxy.docker_proxy.socket.socket") as socket_ctor, \
         patch("tc_api.docktap.proxy.docker_proxy.has_reusable_identity_token", return_value=False), \
         patch.object(proxy, "_read_client_request", side_effect=[(request_data, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("pull", "/v1.41/images/create", {"fromImage": ["hello-world"], "tag": ["latest"]})):
        proxy.handle_client(client_socket)

    socket_ctor.assert_not_called()
    payload = json.loads(client_socket.sent[0].split(b"\r\n\r\n", 1)[1].decode("utf-8"))
    assert payload["message"].startswith("Attested Docker login required before docker pull.\n")
    assert payload["detail"]["auth_mode"] == "delegation_disabled"


def test_handle_client_returns_pull_success_before_async_trucon_submission():
    class AsyncCommitter:
        def __init__(self):
            self.submit_called = False
            self.enqueued = []

        def submit_operation(self, *args, **kwargs):
            self.submit_called = True
            return True

        def enqueue_operation(self, op_record, operation_type, *, workload_id=None, launch_id=None):
            self.enqueued.append((op_record, operation_type, workload_id, launch_id))
            return "queued-pull"

    proxy = DockerProxyServer(
        listen_socket_path="/tmp/test-docker-proxy.sock",
        docker_socket_path="/var/run/docker.sock",
        trucon_committer=AsyncCommitter(),
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

    with patch.dict(os.environ, {"DOCKTAP_AUTH_MODE": "delegation_disabled"}, clear=False), \
            patch("tc_api.docktap.proxy.docker_proxy.socket.socket", return_value=docker_socket), \
            patch("tc_api.docktap.proxy.docker_proxy.has_reusable_identity_token", return_value=True), \
         patch.object(proxy, "_read_client_request", side_effect=[(request_data, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("pull", "/v1.41/images/create", {})), \
         patch.object(proxy, "_read_docker_response", return_value=response_data), \
         patch("tc_api.docktap.proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("tc_api.docktap.proxy.docker_proxy.log_operation_json") as log_operation_json:
        proxy.handle_client(client_socket)

    assert len(client_socket.sent) == 1
    assert client_socket.sent[0] == response_data
    assert proxy._trucon_committer.submit_called is False
    assert len(proxy._trucon_committer.enqueued) == 1
    assert proxy._trucon_committer.enqueued[0][1] == "pull"
    enrich_response.assert_called_once_with(op_record, response_data)
    log_operation_json.assert_called_once_with(op_record)


def test_handle_client_returns_create_success_before_async_trucon_submission():
    class AsyncCommitter:
        def __init__(self):
            self.submit_called = False
            self.enqueued = []

        def submit_operation(self, *args, **kwargs):
            self.submit_called = True
            return True

        def enqueue_operation(self, op_record, operation_type, *, workload_id=None, launch_id=None):
            self.enqueued.append((op_record, operation_type, workload_id, launch_id))
            return "queued-123"

    committer = AsyncCommitter()
    proxy = DockerProxyServer(
        listen_socket_path="/tmp/test-docker-proxy.sock",
        docker_socket_path="/var/run/docker.sock",
        trucon_committer=committer,
    )
    client_socket = FakeClientSocket()
    docker_socket = FakeDockerSocket()
    request_data = (
        b"POST /v1.41/containers/create?name=mycontainer HTTP/1.1\r\n"
        b"Host: localhost\r\nContent-Type: application/json\r\n\r\n"
        b'{"Image":"hello-world:latest","Labels":{"io.trucon.workload-id":"demo-workload","io.trucon.launch-id":"launch-1"}}'
    )
    response_data = b"HTTP/1.1 201 Created\r\nContent-Length: 2\r\n\r\n{}"
    op_record = OperationRecord(
        operation={"type": "create", "action": "docker create", "api_path": "/v1.41/containers/create", "method": "POST"},
        image={"name": "hello-world:latest"},
        container={"name": "mycontainer", "id": "cid-123"},
        response={"status": 201},
    )

    with patch.dict(os.environ, {"DOCKTAP_AUTH_MODE": "delegation_disabled"}, clear=False), \
            patch("tc_api.docktap.proxy.docker_proxy.socket.socket", return_value=docker_socket), \
            patch("tc_api.docktap.proxy.docker_proxy.has_reusable_identity_token", return_value=True), \
         patch.object(proxy, "_read_client_request", side_effect=[(request_data, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("create", "/v1.41/containers/create", {})), \
         patch.object(proxy, "_read_docker_response", return_value=response_data), \
         patch("tc_api.docktap.proxy.docker_proxy.enrich_from_response"), \
         patch("tc_api.docktap.proxy.docker_proxy.log_operation_json"):
        proxy.handle_client(client_socket)

    assert client_socket.sent == [response_data]
    assert committer.submit_called is False
    assert len(committer.enqueued) == 1
    assert committer.enqueued[0][1] == "create"
    assert committer.enqueued[0][2] == "demo-workload"
    assert committer.enqueued[0][3] == "launch-1"


def test_handle_client_submits_build_requests_to_trucon_without_background_queueing():
    class TrackingCommitter:
        def __init__(self):
            self.submit_calls = []
            self.enqueue_calls = []

        def submit_operation(self, *args, **kwargs):
            self.submit_calls.append((args, kwargs))
            return True

        def enqueue_operation(self, *args, **kwargs):
            self.enqueue_calls.append((args, kwargs))
            return "queued-build"

    committer = TrackingCommitter()
    proxy = DockerProxyServer(
        listen_socket_path="/tmp/test-docker-proxy.sock",
        docker_socket_path="/var/run/docker.sock",
        trucon_committer=committer,
    )
    client_socket = FakeClientSocket()
    docker_socket = FakeDockerSocket()
    request_data = (
        b"POST /v1.41/build?t=demo:latest HTTP/1.1\r\n"
        b"Host: localhost\r\nContent-Type: application/x-tar\r\n\r\n"
    )
    response_data = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
    op_record = OperationRecord(
        operation={"type": "build", "action": "docker build", "api_path": "/v1.41/build", "method": "POST"},
        response={"status": 200},
    )

    with patch.dict(os.environ, {"DOCKTAP_AUTH_MODE": "delegation_disabled"}, clear=False), \
            patch("tc_api.docktap.proxy.docker_proxy.socket.socket", return_value=docker_socket), \
            patch("tc_api.docktap.proxy.docker_proxy.has_reusable_identity_token", return_value=True), \
         patch.object(proxy, "_read_client_request", side_effect=[(request_data, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=op_record), \
         patch.object(proxy, "_parse_http_request", return_value=("build", "/v1.41/build", {})), \
         patch.object(proxy, "_read_docker_response", return_value=response_data), \
         patch("tc_api.docktap.proxy.docker_proxy.enrich_from_response") as enrich_response, \
         patch("tc_api.docktap.proxy.docker_proxy.log_operation_json") as log_operation_json:
        proxy.handle_client(client_socket)

    assert client_socket.sent == [response_data]
    assert len(committer.submit_calls) == 1
    assert committer.submit_calls[0][0][1] == "build"
    assert committer.enqueue_calls == []
    enrich_response.assert_called_once_with(op_record, response_data)
    log_operation_json.assert_called_once_with(op_record)


def test_create_does_not_grant_followup_start_without_delegation():
    class AsyncCommitter:
        def __init__(self):
            self.enqueued = []

        def submit_operation(self, *args, **kwargs):
            return True

        def enqueue_operation(self, op_record, operation_type, *, workload_id=None, launch_id=None):
            self.enqueued.append((op_record, operation_type, workload_id, launch_id))
            return f"queued-{operation_type}"

    committer = AsyncCommitter()
    proxy = DockerProxyServer(
        listen_socket_path="/tmp/test-docker-proxy.sock",
        docker_socket_path="/var/run/docker.sock",
        trucon_committer=committer,
    )

    create_client_socket = FakeClientSocket()
    create_docker_socket = FakeDockerSocket()
    create_request = (
        b"POST /v1.41/containers/create?name=mycontainer HTTP/1.1\r\n"
        b"Host: localhost\r\nContent-Type: application/json\r\n\r\n"
        b'{"Image":"hello-world:latest"}'
    )
    create_response = b"HTTP/1.1 201 Created\r\nContent-Length: 2\r\n\r\n{}"
    create_record = OperationRecord(
        operation={"type": "create", "action": "docker create", "api_path": "/v1.41/containers/create", "method": "POST"},
        image={"name": "hello-world:latest"},
        container={"name": "mycontainer", "id": "container-1234567890"},
        response={"status": 201},
    )

    with patch.dict(os.environ, {"DOCKTAP_AUTH_MODE": "delegation_disabled"}, clear=False), \
            patch("tc_api.docktap.proxy.docker_proxy.socket.socket", return_value=create_docker_socket), \
            patch("tc_api.docktap.proxy.docker_proxy.has_reusable_identity_token", return_value=True), \
         patch.object(proxy, "_read_client_request", side_effect=[(create_request, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=create_record), \
         patch.object(proxy, "_parse_http_request", return_value=("create", "/v1.41/containers/create", {})), \
         patch.object(proxy, "_read_docker_response", return_value=create_response), \
         patch("tc_api.docktap.proxy.docker_proxy.enrich_from_response"), \
         patch("tc_api.docktap.proxy.docker_proxy.log_operation_json"):
        proxy.handle_client(create_client_socket)

    start_client_socket = FakeClientSocket()
    start_docker_socket = FakeDockerSocket()
    start_request = b"POST /v1.41/containers/container-123456/start HTTP/1.1\r\nHost: localhost\r\n\r\n"
    start_response = b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n"
    start_record = OperationRecord(
        operation={"type": "start", "action": "docker start", "api_path": "/v1.41/containers/container-123456/start", "method": "POST"},
        container={"id": "container-123456"},
        response={"status": 204},
    )

    with patch.dict(os.environ, {"DOCKTAP_AUTH_MODE": "explicit_delegation"}, clear=False), \
            patch("tc_api.docktap.proxy.docker_proxy.socket.socket", return_value=start_docker_socket), \
            patch("tc_api.docktap.proxy.docker_proxy.has_reusable_identity_token", return_value=False), \
            patch("tc_api.docktap.proxy.docker_proxy.has_active_delegation", return_value=False), \
         patch.object(proxy, "_read_client_request", side_effect=[(start_request, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=start_record), \
         patch.object(proxy, "_parse_http_request", return_value=("start", "/v1.41/containers/container-123456/start", {})), \
         patch.object(proxy, "_read_docker_response", return_value=start_response), \
         patch("tc_api.docktap.proxy.docker_proxy.enrich_from_response"), \
         patch("tc_api.docktap.proxy.docker_proxy.log_operation_json"):
        proxy.handle_client(start_client_socket)

    assert start_docker_socket.sent == []
    assert len(start_client_socket.sent) == 1
    assert start_client_socket.sent[0].startswith(b"HTTP/1.1 428 Precondition Required")
    assert [item[1] for item in committer.enqueued] == ["create"]


def test_rm_without_delegation_is_blocked_after_token_expires():
    class AsyncCommitter:
        def __init__(self):
            self.enqueued = []

        def submit_operation(self, *args, **kwargs):
            return True

        def enqueue_operation(self, op_record, operation_type, *, workload_id=None, launch_id=None):
            self.enqueued.append((op_record, operation_type, workload_id, launch_id))
            return f"queued-{operation_type}"

    committer = AsyncCommitter()
    proxy = DockerProxyServer(
        listen_socket_path="/tmp/test-docker-proxy.sock",
        docker_socket_path="/var/run/docker.sock",
        trucon_committer=committer,
    )

    create_record = OperationRecord(
        operation={"type": "create", "action": "docker create", "api_path": "/v1.41/containers/create", "method": "POST"},
        image={"name": "hello-world:latest"},
        container={"name": "mycontainer", "id": "container-abcdef123456"},
        response={"status": 201},
    )
    with patch.dict(os.environ, {"DOCKTAP_AUTH_MODE": "delegation_disabled"}, clear=False), \
            patch("tc_api.docktap.proxy.docker_proxy.socket.socket", return_value=FakeDockerSocket()), \
            patch("tc_api.docktap.proxy.docker_proxy.has_reusable_identity_token", return_value=True), \
         patch.object(proxy, "_read_client_request", side_effect=[(b"POST /v1.41/containers/create?name=mycontainer HTTP/1.1\r\nHost: localhost\r\n\r\n", None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=create_record), \
         patch.object(proxy, "_parse_http_request", return_value=("create", "/v1.41/containers/create", {})), \
         patch.object(proxy, "_read_docker_response", return_value=b"HTTP/1.1 201 Created\r\nContent-Length: 2\r\n\r\n{}"), \
         patch("tc_api.docktap.proxy.docker_proxy.enrich_from_response"), \
         patch("tc_api.docktap.proxy.docker_proxy.log_operation_json"):
        proxy.handle_client(FakeClientSocket())

    rm_client_socket = FakeClientSocket()
    rm_docker_socket = FakeDockerSocket()
    rm_request = b"DELETE /v1.41/containers/container-abcdef123456?force=1 HTTP/1.1\r\nHost: localhost\r\n\r\n"
    rm_response = b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n"
    rm_record = OperationRecord(
        operation={"type": "rm", "action": "docker rm", "api_path": "/v1.41/containers/container-abcdef123456", "method": "DELETE"},
        container={"id": "container-abcdef123456"},
        response={"status": 204},
    )

    with patch.dict(os.environ, {"DOCKTAP_AUTH_MODE": "explicit_delegation"}, clear=False), \
            patch("tc_api.docktap.proxy.docker_proxy.socket.socket", return_value=rm_docker_socket), \
            patch("tc_api.docktap.proxy.docker_proxy.has_reusable_identity_token", return_value=False), \
            patch("tc_api.docktap.proxy.docker_proxy.has_active_delegation", return_value=False), \
         patch.object(proxy, "_read_client_request", side_effect=[(rm_request, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=rm_record), \
         patch.object(proxy, "_parse_http_request", return_value=("rm", "/v1.41/containers/container-abcdef123456", {})), \
         patch.object(proxy, "_read_docker_response", return_value=rm_response), \
         patch("tc_api.docktap.proxy.docker_proxy.enrich_from_response"), \
         patch("tc_api.docktap.proxy.docker_proxy.log_operation_json"):
        proxy.handle_client(rm_client_socket)

    assert rm_docker_socket.sent == []
    assert len(rm_client_socket.sent) == 1
    assert rm_client_socket.sent[0].startswith(b"HTTP/1.1 428 Precondition Required")

    stop_client_socket = FakeClientSocket()
    stop_request = b"POST /v1.41/containers/container-abcdef123456/stop HTTP/1.1\r\nHost: localhost\r\n\r\n"
    stop_record = OperationRecord(
        operation={"type": "stop", "action": "docker stop", "api_path": "/v1.41/containers/container-abcdef123456/stop", "method": "POST"},
        container={"id": "container-abcdef123456"},
    )

    with patch.dict(os.environ, {"DOCKTAP_AUTH_MODE": "explicit_delegation"}, clear=False), \
            patch("tc_api.docktap.proxy.docker_proxy.socket.socket") as socket_ctor, \
            patch("tc_api.docktap.proxy.docker_proxy.has_reusable_identity_token", return_value=False), \
            patch("tc_api.docktap.proxy.docker_proxy.has_active_delegation", return_value=False), \
         patch.object(proxy, "_read_client_request", side_effect=[(stop_request, None), (None, "empty")]), \
         patch.object(proxy._runtime_adapter, "parse_operation_metadata", return_value=stop_record), \
         patch.object(proxy, "_parse_http_request", return_value=("stop", "/v1.41/containers/container-abcdef123456/stop", {})), \
         patch("tc_api.docktap.proxy.docker_proxy.enrich_from_response"), \
         patch("tc_api.docktap.proxy.docker_proxy.log_operation_json"):
        proxy.handle_client(stop_client_socket)

    socket_ctor.assert_not_called()
    assert len(stop_client_socket.sent) == 1
    assert stop_client_socket.sent[0].startswith(b"HTTP/1.1 428 Precondition Required")