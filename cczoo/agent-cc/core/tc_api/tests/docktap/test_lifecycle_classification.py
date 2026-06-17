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
import time

import pytest

from tc_api.docktap.proxy.docker_proxy import DockerProxyServer
from tc_api.docktap.proxy.operation_log import enrich_from_response, get_operation_type, is_streaming_endpoint, parse_operation_metadata


def _send_fragments(sock: socket.socket, fragments, delay: float = 0.03) -> None:
    try:
        for frag in fragments:
            sock.sendall(frag)
            time.sleep(delay)
    finally:
        sock.close()


def test_read_client_request_handles_fragmented_body() -> None:
    proxy = DockerProxyServer()
    server_sock, client_sock = socket.socketpair()
    server_sock.settimeout(0.1)

    body = b'{"Image":"busybox","name":"frag"}'
    headers = (
        f"POST /v1.41/containers/create?name=frag HTTP/1.1\r\n"
        f"Host: localhost\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    ).encode("utf-8")

    sender = threading.Thread(
        target=_send_fragments,
        args=(client_sock, [headers[:25], headers[25:], body[:7], body[7:]], 0.02),
        daemon=True,
    )
    sender.start()

    request_data, error = proxy._read_client_request(server_sock, timeout_seconds=2.0)
    server_sock.close()
    sender.join(timeout=1)

    assert error is None
    assert request_data is not None
    assert request_data.endswith(body)
    assert b"Content-Length" in request_data


def test_read_client_request_detects_incomplete_body() -> None:
    proxy = DockerProxyServer()
    server_sock, client_sock = socket.socketpair()
    server_sock.settimeout(0.1)

    partial_body = b'{"Image":"busybox"}'
    headers = (
        "POST /v1.41/containers/create HTTP/1.1\r\n"
        "Host: localhost\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: 999\r\n\r\n"
    ).encode("utf-8")

    client_sock.sendall(headers + partial_body)
    client_sock.close()

    request_data, error = proxy._read_client_request(server_sock, timeout_seconds=1.0)
    server_sock.close()

    assert request_data is None
    assert error == "incomplete_body"


def test_callback_and_structured_mapping_are_consistent() -> None:
    proxy = DockerProxyServer()
    request_data = (
        b"POST /v1.41/containers/create?name=demo HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: 19\r\n\r\n"
        b'{"Image":"nginx"}'
    )

    operation, _, _ = proxy._parse_http_request(request_data)
    op_record = parse_operation_metadata(request_data, session_id="s")

    assert operation == op_record.operation["type"]
    assert operation == "create"


@pytest.mark.parametrize(
    "method,path,expected",
    [
        ("GET", "/_ping", "preflight_ping"),
        ("GET", "/v1.41/info", "preflight_info"),
        ("GET", "/v1.41/images/busybox/json", "image_inspect"),
        ("GET", "/v1.41/networks/bridge", "network_inspect"),
        ("GET", "/v1.41/volumes/data-cache", "volume_inspect"),
        ("GET", "/v1.41/plugins/example/json", "plugin_inspect"),
        ("GET", "/containers/json", "container_list"),
        ("GET", "/v1.41/containers/json", "container_list"),
        ("GET", "/v1.41/containers/abc123/logs", "container_logs"),
        ("GET", "/containers/abc123/logs?stdout=1", "container_logs"),
        ("POST", "/v1.41/containers/abc123/exec", "exec_create"),
        ("POST", "/v1.41/exec/exec123/start", "exec_start"),
    ],
)
def test_preflight_and_image_inspect_have_deterministic_labels(method: str, path: str, expected: str) -> None:
    assert get_operation_type(method, path) == expected


def test_container_list_preserves_query_params_in_metadata() -> None:
    request_data = (
        b"GET /v1.41/containers/json?all=1&limit=5 HTTP/1.1\r\n"
        b"Host: localhost\r\n\r\n"
    )

    op_record = parse_operation_metadata(request_data, session_id="s")

    assert op_record.operation["type"] == "container_list"
    assert op_record.params == {"all": "1", "limit": "5"}


def test_container_detail_inspect_boundary_is_unchanged() -> None:
    assert get_operation_type("GET", "/v1.41/containers/abc123/json") == "inspect"


def test_resource_probe_paths_do_not_change_existing_container_or_image_boundaries() -> None:
    assert get_operation_type("GET", "/v1.41/images/busybox/json") == "image_inspect"
    assert get_operation_type("GET", "/v1.41/containers/abc123/json") == "inspect"
    assert get_operation_type("GET", "/v1.41/containers/abc123/logs?stdout=1") == "container_logs"
    assert get_operation_type("POST", "/v1.41/networks/bridge/connect") == "unknown"


def test_exec_create_preserves_target_container_identity() -> None:
    request_data = (
        b"POST /v1.41/containers/abc123/exec HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: 17\r\n\r\n"
        b'{"Cmd":["/bin/sh"]}'
    )

    op_record = parse_operation_metadata(request_data, session_id="s")

    assert op_record.operation["type"] == "exec_create"
    assert op_record.container["id"] == "abc123"


def test_exec_start_preserves_exec_identity() -> None:
    request_data = (
        b"POST /v1.41/exec/exec123/start HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: 14\r\n\r\n"
        b'{"Detach":false}'
    )

    op_record = parse_operation_metadata(request_data, session_id="s")

    assert op_record.operation["type"] == "exec_start"
    assert op_record.exec == {"id": "exec123"}


@pytest.mark.parametrize(
    "path,response,expected_outcome",
    [
        ("/v1.41/images/busybox/json", b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}", "ok"),
        (
            "/v1.41/networks/bridge",
            b"HTTP/1.1 404 Not Found\r\nContent-Length: 2\r\n\r\n{}",
            "miss",
        ),
        (
            "/v1.41/volumes/data-cache",
            b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: 2\r\n\r\n{}",
            "error",
        ),
        (
            "/v1.41/plugins/example/json",
            b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 2\r\n\r\n{}",
            "error",
        ),
    ],
)
def test_selected_probe_observations_record_response_outcomes(
    path: str,
    response: bytes,
    expected_outcome: str,
) -> None:
    request_data = f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode("utf-8")

    op_record = parse_operation_metadata(request_data, session_id="s")
    enrich_from_response(op_record, response)

    assert op_record.response["outcome"] == expected_outcome


def test_container_detail_inspect_404_outcome_remains_deferred() -> None:
    request_data = (
        b"GET /v1.41/containers/abc123/json HTTP/1.1\r\n"
        b"Host: localhost\r\n\r\n"
    )

    op_record = parse_operation_metadata(request_data, session_id="s")
    enrich_from_response(
        op_record,
        b"HTTP/1.1 404 Not Found\r\nContent-Length: 2\r\n\r\n{}",
    )

    assert op_record.operation["type"] == "inspect"
    assert op_record.response["status"] == 404
    assert "outcome" not in op_record.response


def test_proxy_synthesized_probe_error_is_distinct_from_daemon_miss() -> None:
    proxy = DockerProxyServer()
    request_data = (
        b"GET /v1.41/images/busybox/json HTTP/1.1\r\n"
        b"Host: localhost\r\n\r\n"
    )

    op_record = parse_operation_metadata(request_data, session_id="s")
    enrich_from_response(op_record, proxy._create_error_response("Docker daemon not available"))

    assert op_record.operation["type"] == "image_inspect"
    assert op_record.response["status"] == 503
    assert op_record.response["outcome"] == "error"


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/v1.41/containers/abc/wait", True),
        ("/containers/abc/wait", True),
        ("/v1.41/containers/abc/logs?stdout=1", True),
        ("/containers/abc/logs?stderr=1", True),
        ("/v1.41/containers/abc/start", False),
    ],
)
def test_streaming_detection_is_version_agnostic(path: str, expected: bool) -> None:
    assert is_streaming_endpoint(path) is expected
