#!/usr/bin/env python3

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

"""Sock-bridge runtime launcher for the stream test socket.

Concurrency and per-request handling are implemented in
`proxy.docker_proxy.DockerProxyServer.handle_client`.
"""

import os
import sys

from .proxy.docker_proxy import DockerProxyServer


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
