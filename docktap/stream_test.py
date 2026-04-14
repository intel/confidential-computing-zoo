#!/usr/bin/env python3
"""Sock-bridge runtime launcher for the stream test socket.

Concurrency and per-request handling are implemented in
`proxy.docker_proxy.DockerProxyServer.handle_client`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proxy.docker_proxy import DockerProxyServer


SOCKET_PATH = "/tmp/test-stream.sock"
DOCKER_SOCKET = "/var/run/docker.sock"


def main() -> None:
    proxy = DockerProxyServer(
        listen_socket_path=SOCKET_PATH,
        docker_socket_path=DOCKER_SOCKET,
    )
    proxy.start()


if __name__ == "__main__":
    main()
