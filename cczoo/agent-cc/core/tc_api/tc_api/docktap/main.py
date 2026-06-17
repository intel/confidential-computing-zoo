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
Docktap: Docker operation interception and trusted logging sidecar.

Usage:
    python main.py [--socket-path PATH] [--docker-socket-path PATH]

Environment:
    DOCKER_HOST=unix:///tmp/docker-proxy.sock  # Configure Docker CLI to use proxy
"""

import sys
import signal
import argparse
import logging
import threading
from dataclasses import dataclass
from http.server import HTTPServer, BaseHTTPRequestHandler

from .proxy.docker_proxy import DockerProxyServer
from .proxy.operation_log import log_event
from .trucon_client import TruConCommitter
from .workload_store import WorkloadStore


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class DocktapRetentionConfig:
    gc_interval_seconds: float = 300.0
    operation_retention_hours: float = 24.0
    removed_container_retention_hours: float = 24.0
    acknowledged_retry_retention_hours: float = 24.0
    terminal_retry_retention_hours: float = 168.0

    @classmethod
    def from_env(cls) -> "DocktapRetentionConfig":
        from .config import (
            GC_INTERVAL_SECONDS,
            OPERATION_RETENTION_HOURS,
            REMOVED_CONTAINER_RETENTION_HOURS,
            ACKED_RETRY_RETENTION_HOURS,
            TERMINAL_RETRY_RETENTION_HOURS,
        )
        return cls(
            gc_interval_seconds=GC_INTERVAL_SECONDS,
            operation_retention_hours=OPERATION_RETENTION_HOURS,
            removed_container_retention_hours=REMOVED_CONTAINER_RETENTION_HOURS,
            acknowledged_retry_retention_hours=ACKED_RETRY_RETENTION_HOURS,
            terminal_retry_retention_hours=TERMINAL_RETRY_RETENTION_HOURS,
        )


class HealthHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for /healthz endpoint."""

    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress default stderr logging for health checks
        pass


def start_health_server(port: int = 8002) -> None:
    """Start a lightweight HTTP health server as a daemon thread."""
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logger.info("Health server listening on port %d", port)


class SockBridge:
    """Main application for the docktap sidecar"""
    
    def __init__(self, socket_path: str, docker_socket_path: str):
        self.socket_path = socket_path
        self.docker_socket_path = docker_socket_path
        self.retention_config = DocktapRetentionConfig.from_env()
        self.workload_store = WorkloadStore()
        self.workload_store.init_db()
        self.trucon_committer = TruConCommitter(
            workload_store=self.workload_store,
            acknowledged_retention_hours=self.retention_config.acknowledged_retry_retention_hours,
            terminal_retention_hours=self.retention_config.terminal_retry_retention_hours,
        )
        self.proxy: DockerProxyServer = None
        self.running = False
        self._sweeper_stop = threading.Event()
        self._sweeper_thread: threading.Thread | None = None
    
    def log_callback(self, event_data: dict):
        """Callback to log operations via proxy logger"""
        log_event(event_data)

    def _start_sweeper(self) -> None:
        if self._sweeper_thread is not None:
            return
        self._sweeper_thread = threading.Thread(
            target=self._sweeper_loop,
            daemon=True,
            name="docktap-local-state-sweeper",
        )
        self._sweeper_thread.start()

    def _sweeper_loop(self) -> None:
        while not self._sweeper_stop.wait(self.retention_config.gc_interval_seconds):
            tracker_removed = 0
            if self.proxy is not None:
                tracker_removed = self.proxy.tracker.cleanup_old_operations(
                    self.retention_config.operation_retention_hours
                )
            removed_mappings = self.workload_store.cleanup_removed(
                self.retention_config.removed_container_retention_hours
            )
            removed_retries = self.trucon_committer.cleanup_resolved_submissions()
            if tracker_removed or removed_mappings or removed_retries:
                logger.info(
                    "Docktap sweeper removed tracker=%d mappings=%d retries=%d",
                    tracker_removed,
                    removed_mappings,
                    removed_retries,
                )
    
    def start(self):
        """Start the docktap sidecar"""
        logger.info("Starting docktap...")

        # Start health endpoint before proxy accept loop
        from .config import HEALTH_PORT
        start_health_server(HEALTH_PORT)

        self.proxy = DockerProxyServer(
            listen_socket_path=self.socket_path,
            docker_socket_path=self.docker_socket_path,
            trucon_committer=self.trucon_committer,
        )
        self.proxy.set_log_callback(self.log_callback)
        self._start_sweeper()
        
        self.running = True
        
        logger.info(f"Proxy listening on: {self.socket_path}")
        logger.info(f"Forwarding to Docker: {self.docker_socket_path}")
        logger.info("Use 'export DOCKER_HOST=unix://{}' to use proxy".format(self.socket_path))
        
        try:
            self.proxy.start()
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
            self.stop()
        except Exception as e:
            logger.error(f"Proxy error: {e}")
            self.stop()
    
    def stop(self):
        """Stop the docktap sidecar"""
        logger.info("Stopping docktap...")
        self.running = False
        self._sweeper_stop.set()
        if self._sweeper_thread is not None:
            self._sweeper_thread.join(timeout=1.0)
        if self.proxy:
            self.proxy.stop()
        self.trucon_committer.shutdown()
        logger.info("Docktap stopped")


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Docktap: Docker operation interception and trusted logging"
    )
    parser.add_argument(
        '--socket-path',
        default=None,
        help='Path for the proxy socket (default: /tmp/docker-proxy.sock)'
    )
    parser.add_argument(
        '--docker-socket-path',
        default=None,
        help='Path to Docker daemon socket (default: /var/run/docker.sock)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    return parser.parse_args()


def main():
    """Main entry point"""
    from .config import SOCK_BRIDGE_SOCKET, DOCKER_SOCKET
    args = parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    app = SockBridge(
        socket_path=args.socket_path or SOCK_BRIDGE_SOCKET,
        docker_socket_path=args.docker_socket_path or DOCKER_SOCKET,
    )
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        app.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    app.start()


if __name__ == "__main__":
    main()