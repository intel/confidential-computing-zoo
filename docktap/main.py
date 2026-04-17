#!/usr/bin/env python3
"""
Docktap: Docker operation interception and trusted logging sidecar.

Usage:
    python main.py [--socket-path PATH] [--docker-socket-path PATH]

Environment:
    DOCKER_HOST=unix:///tmp/docker-proxy.sock  # Configure Docker CLI to use proxy
"""

import os
import sys
import signal
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proxy.docker_proxy import DockerProxyServer
from proxy.operation_log import log_event
from trucon_client import TruConCommitter
from workload_store import WorkloadStore


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SockBridge:
    """Main application for the docktap sidecar"""
    
    def __init__(self, socket_path: str, docker_socket_path: str):
        self.socket_path = socket_path
        self.docker_socket_path = docker_socket_path
        self.workload_store = WorkloadStore()
        self.workload_store.init_db()
        self.trucon_committer = TruConCommitter(workload_store=self.workload_store)
        self.proxy: DockerProxyServer = None
        self.running = False
    
    def log_callback(self, event_data: dict):
        """Callback to log operations via proxy logger"""
        log_event(event_data)
    
    def start(self):
        """Start the docktap sidecar"""
        logger.info("Starting docktap...")
        
        self.proxy = DockerProxyServer(
            listen_socket_path=self.socket_path,
            docker_socket_path=self.docker_socket_path,
            trucon_committer=self.trucon_committer,
        )
        self.proxy.set_log_callback(self.log_callback)
        
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
        if self.proxy:
            self.proxy.stop()
        logger.info("Docktap stopped")


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Docktap: Docker operation interception and trusted logging"
    )
    parser.add_argument(
        '--socket-path',
        default=os.environ.get('SOCK_BRIDGE_SOCKET', '/tmp/docker-proxy.sock'),
        help='Path for the proxy socket (default: /tmp/docker-proxy.sock)'
    )
    parser.add_argument(
        '--docker-socket-path',
        default=os.environ.get('DOCKER_SOCKET', '/var/run/docker.sock'),
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
    args = parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    app = SockBridge(
        socket_path=args.socket_path,
        docker_socket_path=args.docker_socket_path
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