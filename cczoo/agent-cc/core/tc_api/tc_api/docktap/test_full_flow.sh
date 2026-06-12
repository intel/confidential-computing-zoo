#!/bin/bash

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

# Full test of docker operations through proxy

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PROXY_LOG="${PROXY_LOG:-/tmp/proxy.log}"

SOCKET_PATH="/tmp/test-stream.sock"
IMAGE_NAME="nginx:latest"
CONTAINER_NAME="test-nginx-proxy"

echo "=== Full Docker Flow Test ==="

# Clean up
echo "[1] Cleanup..."
docker rm -f $CONTAINER_NAME 2>/dev/null || true
docker rmi -f $IMAGE_NAME 2>/dev/null || true

# Start proxy
echo "[2] Start proxy..."
cd "$SCRIPT_DIR"
rm -f $SOCKET_PATH
"$PYTHON_BIN" stream_test.py > "$PROXY_LOG" 2>&1 &
PROXY_PID=$!
sleep 2

if ! kill -0 $PROXY_PID 2>/dev/null; then
    echo "ERROR: Proxy failed"
    cat "$PROXY_LOG"
    exit 1
fi
echo "Proxy running (PID: $PROXY_PID)"

export DOCKER_HOST=unix://$SOCKET_PATH

# Pull
echo ""
echo "[3] docker pull $IMAGE_NAME"
docker pull $IMAGE_NAME

# Run
echo ""
echo "[4] docker run -d --name $CONTAINER_NAME $IMAGE_NAME"
docker run -d --name $CONTAINER_NAME $IMAGE_NAME

# Stop
echo ""
echo "[5] docker stop $CONTAINER_NAME"
docker stop $CONTAINER_NAME

# Start
echo ""
echo "[6] docker start $CONTAINER_NAME"
docker start $CONTAINER_NAME

# Remove
echo ""
echo "[7] docker rm -f $CONTAINER_NAME"
docker rm -f $CONTAINER_NAME

echo ""
echo "=== Test Complete ==="
kill $PROXY_PID 2>/dev/null
echo ""
echo "=== Proxy Logs ==="
cat "$PROXY_LOG"