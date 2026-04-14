import socket
import threading
import time

import pytest

from proxy.docker_proxy import DockerProxyServer
from proxy.operation_log import get_operation_type, is_streaming_endpoint, parse_operation_metadata


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
    ],
)
def test_preflight_and_image_inspect_have_deterministic_labels(method: str, path: str, expected: str) -> None:
    assert get_operation_type(method, path) == expected


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
