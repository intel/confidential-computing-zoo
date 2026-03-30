#!/usr/bin/env python3
"""Single test entrypoint for TC API.

This script consolidates test execution for manual and pytest-based suites.
"""

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import List, Optional


def check_service(url: str = "http://localhost:8000/") -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def start_service() -> Optional[subprocess.Popen]:
    process = subprocess.Popen([sys.executable, "main.py"])

    timeout_seconds = 30
    waited = 0
    while waited < timeout_seconds:
        time.sleep(2)
        waited += 2
        if check_service():
            return process

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    return None


def run_command(command: List[str], label: str, stop_on_fail: bool, env: Optional[dict] = None) -> int:
    print(label)
    result = subprocess.run(command, env=env)
    if result.returncode != 0 and stop_on_fail:
        sys.exit(result.returncode)
    return result.returncode


def build_command(test_type: str, verbose: bool) -> List[str]:
    if test_type == "unit":
        cmd = ["pytest", "test_subprocess_unit.py"]
    elif test_type == "integration":
        cmd = ["pytest", "test_unit.py::TestIntegration"]
    elif test_type == "performance":
        cmd = ["pytest", "test_unit.py::TestPerformance"]
    else:
        cmd = ["pytest", "test_subprocess_unit.py", "test_unit.py"]

    if verbose:
        cmd.extend(["-v", "--tb=short"])

    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(description="TC API single test entrypoint")
    parser.add_argument(
        "-t",
        "--type",
        default="all",
        choices=["all", "manual", "unit", "integration", "performance"],
        help="Test type to run",
    )
    parser.add_argument(
        "-n",
        "--name",
        default="",
        help="Specific manual test name for test_api.py",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument(
        "-s",
        "--stop-on-fail",
        action="store_true",
        help="Stop execution on first failure",
    )
    parser.add_argument(
        "--no-service-management",
        action="store_true",
        help="Do not auto-start/stop API service",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("TC_API_BASE_URL", "http://localhost:8000"),
        help="Base URL for manual API checks (exported as TC_API_BASE_URL for test_api.py)",
    )
    parser.add_argument(
        "--manual-ready-timeout",
        type=int,
        default=60,
        help="Seconds to wait for manual base URL readiness before running test_api.py",
    )
    args = parser.parse_args()

    print("TC API Test Runner")
    print("==================")

    started_process: Optional[subprocess.Popen] = None
    if not args.no_service_management:
        if check_service():
            print("TC API service is already running.")
        else:
            print("TC API service not running. Starting it...")
            started_process = start_service()
            if not started_process:
                print("Failed to start TC API service.")
                return 1
            print(f"Service started successfully (PID: {started_process.pid}).")

    exit_code = 0
    try:
        if args.type == "manual":
            if args.manual_ready_timeout > 0:
                deadline = time.time() + args.manual_ready_timeout
                while time.time() < deadline:
                    if check_service(args.base_url):
                        break
                    time.sleep(2)
            command = [sys.executable, "test_api.py"]
            if args.name:
                command.append(args.name)
            manual_env = os.environ.copy()
            manual_env["TC_API_BASE_URL"] = args.base_url
            exit_code = run_command(command, "Running manual integration tests...", args.stop_on_fail, env=manual_env)
        elif args.type in {"unit", "integration", "performance"}:
            command = build_command(args.type, args.verbose)
            exit_code = run_command(command, f"Running {args.type} tests...", args.stop_on_fail)
        else:
            manual_env = os.environ.copy()
            manual_env["TC_API_BASE_URL"] = args.base_url
            manual_rc = run_command([sys.executable, "test_api.py"], "Running manual integration tests...", args.stop_on_fail, env=manual_env)
            pytest_rc = run_command(build_command("all", args.verbose), "Running automated tests...", args.stop_on_fail)
            exit_code = manual_rc or pytest_rc
    finally:
        if started_process:
            print(f"Stopping TC API service (PID: {started_process.pid})...")
            started_process.terminate()
            try:
                started_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                started_process.kill()
            print("Service stopped.")

    if exit_code == 0:
        print("Test execution completed successfully.")
    else:
        print(f"Test execution completed with failures (exit code: {exit_code}).")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
