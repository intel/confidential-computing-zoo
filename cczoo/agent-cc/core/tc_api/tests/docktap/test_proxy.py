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

"""
Test process to verify docktap proxy intercepts Docker operations.

This test process can be run to verify the proxy is working correctly.
It starts the proxy and makes test Docker API calls through it.
"""

import sys
import time
import threading

from tc_api.docktap.proxy.docker_proxy import DockerProxyServer


def test_proxy_start_stop():
    """Test that proxy can start and stop"""
    print("\n=== Test: Proxy Start/Stop ===")
    
    proxy = DockerProxyServer(
        listen_socket_path="/tmp/test-docker-proxy.sock",
        docker_socket_path="/var/run/docker.sock"
    )
    
    def run_proxy():
        time.sleep(0.5)
        proxy.stop()
    
    thread = threading.Thread(target=run_proxy)
    thread.start()
    
    try:
        proxy.start()
        print("✓ Proxy started and stopped successfully")
    except Exception as e:
        print(f"✗ Proxy failed: {e}")
        raise


def test_http_parsing():
    """Test HTTP request parsing"""
    print("\n=== Test: HTTP Request Parsing ===")
    
    proxy = DockerProxyServer()
    
    test_cases = [
        (
            b"POST /v1.41/images/create?fromImage=nginx&tag=latest HTTP/1.1\r\nHost: localhost\r\n\r\n",
            "pull", "nginx"
        ),
        (
            b"POST /v1.41/containers/create HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n\r\n{\"Image\":\"nginx\"}",
            "create", "nginx"
        ),
        (
            b"POST /v1.41/containers/abc123/start HTTP/1.1\r\nHost: localhost\r\n\r\n",
            "start", None
        ),
        (
            b"POST /v1.41/containers/abc123/stop HTTP/1.1\r\nHost: localhost\r\n\r\n",
            "stop", None
        ),
    ]
    
    all_passed = True
    for request_data, expected_op, expected_image in test_cases:
        operation, path, params = proxy._parse_http_request(request_data)
        
        if operation != expected_op:
            print(f"✗ Operation mismatch: got {operation}, expected {expected_op}")
            all_passed = False
        elif expected_image:
            image = proxy._extract_image_name(params)
            if image != expected_image:
                print(f"✗ Image mismatch: got {image}, expected {expected_image}")
                all_passed = False
            else:
                print(f"✓ {operation}: {path}")
        else:
            print(f"✓ {operation}: {path}")
    
    assert all_passed


def test_operation_mapping():
    """Test path to operation mapping"""
    print("\n=== Test: Operation Mapping ===")
    
    proxy = DockerProxyServer()
    
    test_cases = [
        ("/v1.41/images/create", "POST", "pull"),
        ("/v1.41/containers/create", "POST", "create"),
        ("/v1.41/networks/bridge", "GET", "network_inspect"),
        ("/v1.41/volumes/data-cache", "GET", "volume_inspect"),
        ("/v1.41/plugins/example/json", "GET", "plugin_inspect"),
        ("/v1.41/containers/abc/logs?stdout=1", "GET", "container_logs"),
        ("/v1.41/containers/abc/exec", "POST", "exec_create"),
        ("/v1.41/exec/exec123/start", "POST", "exec_start"),
        ("/v1.41/containers/abc/start", "POST", "start"),
        ("/v1.41/containers/abc/stop", "POST", "stop"),
        ("/v1.41/containers/abc/restart", "POST", "inspect"),
        ("/v1.41/containers/abc/kill", "POST", "inspect"),
        ("/v1.41/containers/abc", "DELETE", "rm"),
        ("/v1.41/images/push", "POST", "unknown"),
        ("/v1.41/images/tag", "POST", "unknown"),
        ("/v1.41/build", "POST", "build"),
    ]
    
    all_passed = True
    for path, method, expected_op in test_cases:
        operation = proxy._map_path_to_operation(path, method)
        if operation == expected_op:
            print(f"✓ {path} -> {operation}")
        else:
            print(f"✗ {path}: got {operation}, expected {expected_op}")
            all_passed = False
    
    assert all_passed


def test_logger():
    """Test the trusted log logger"""
    print("\n=== Test: Logger ===")
    
    from tc_api.docktap.proxy.operation_log import log_operation
    
    test_cases = [
        {"operation": "pull", "image": "nginx", "tag": "latest"},
        {"operation": "run", "image": "nginx", "command": '["echo", "hello"]'},
        {"operation": "start", "container_id": "abc123"},
        {"operation": "stop", "container_id": "abc123"},
    ]
    
    print("Log output:")
    for params in test_cases:
        log_operation(**params)
    
    print("✓ Logger test complete")


def run_all_tests():
    """Run all tests"""
    print("=" * 50)
    print("SOCK-BRIDGE TEST SUITE")
    print("=" * 50)
    
    results = []
    
    results.append(("HTTP Parsing", test_http_parsing()))
    results.append(("Operation Mapping", test_operation_mapping()))
    results.append(("Logger", test_logger()))
    results.append(("Proxy Start/Stop", test_proxy_start_stop()))
    
    print("\n" + "=" * 50)
    print("TEST RESULTS SUMMARY")
    print("=" * 50)
    
    all_passed = True
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())