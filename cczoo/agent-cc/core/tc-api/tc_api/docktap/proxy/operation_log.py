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

import sys
import json
import uuid
import re
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict


def _safe_stdout_write(text: str) -> None:
    """Best-effort stdout emission for proxy-side structured logs.

    Docktap can run detached from an interactive terminal. In that mode stdout may
    point at a closed pipe; letting BrokenPipeError escape would abort request
    handling and surface as EOF to Docker clients.
    """
    try:
        print(text, file=sys.stdout)
        sys.stdout.flush()
    except (BrokenPipeError, OSError, ValueError):
        return


OBSERVATION_OUTCOME_OPERATIONS = {
    "image_inspect",
    "network_inspect",
    "volume_inspect",
    "plugin_inspect",
}


@dataclass
class OperationRecord:
    """Record of a single Docker operation"""
    version: str = "1.0"
    operation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: Optional[str] = None
    session_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    last_accessed: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    runtime_engine: str = "docker"
    
    operation: Dict[str, str] = field(default_factory=dict)
    image: Dict[str, Any] = field(default_factory=dict)
    container: Dict[str, Any] = field(default_factory=dict)
    exec: Dict[str, Any] = field(default_factory=dict)
    params: Dict[str, str] = field(default_factory=dict)
    response: Dict[str, Any] = field(default_factory=dict)
    user: Dict[str, str] = field(default_factory=dict)


class OperationTracker:
    """Tracks multiple operations and their relationships (thread-safe)"""
    
    def __init__(self):
        self.operations: Dict[str, OperationRecord] = {}
        self.image_to_operation: Dict[str, str] = {}
        self.container_id_to_operation: Dict[str, str] = {}
        self.container_name_to_operation: Dict[str, str] = {}
        self._lock = threading.Lock()
    
    def add(self, op: OperationRecord) -> None:
        """Add operation to tracker (thread-safe)"""
        op.last_accessed = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._lock:
            self.operations[op.operation_id] = op
            
            if op.image and op.image.get("digest"):
                self.image_to_operation[op.image["digest"]] = op.operation_id
            
            if op.container and op.container.get("id"):
                self.container_id_to_operation[op.container["id"]] = op.operation_id
            
            if op.container and op.container.get("name"):
                self.container_name_to_operation[op.container["name"]] = op.operation_id
    
    def touch(self, operation_id: str) -> None:
        """Update last_accessed timestamp (thread-safe)"""
        with self._lock:
            if operation_id in self.operations:
                self.operations[operation_id].last_accessed = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    def get_by_container_name(self, container_name: str) -> Optional[OperationRecord]:
        """Get create operation by container name (thread-safe)"""
        with self._lock:
            op_id = self.container_name_to_operation.get(container_name)
            if op_id:
                return self.operations.get(op_id)
            return None
    
    def get_by_container_id(self, container_id: str) -> Optional[OperationRecord]:
        """Get create operation by container ID (full or short) (thread-safe)"""
        with self._lock:
            op_id = self.container_id_to_operation.get(container_id)
            if op_id:
                return self.operations.get(op_id)
            for cid, oid in self.container_id_to_operation.items():
                if cid.startswith(container_id):
                    return self.operations.get(oid)
            return None
    
    def get_by_container(self, container_id: str) -> List[OperationRecord]:
        """Get all operations for a container (thread-safe)"""
        with self._lock:
            results = []
            for op in self.operations.values():
                if op.container.get("id") == container_id or op.container.get("name") == container_id:
                    results.append(op)
            return sorted(results, key=lambda x: x.timestamp)
    
    def get_by_image(self, image_digest: str) -> List[OperationRecord]:
        """Get all operations for an image (thread-safe)"""
        with self._lock:
            results = []
            for op in self.operations.values():
                if op.image.get("digest") == image_digest:
                    results.append(op)
            return sorted(results, key=lambda x: x.timestamp)
    
    def get_by_session(self, session_id: str) -> List[OperationRecord]:
        """Get all operations in a session (thread-safe)"""
        with self._lock:
            results = [op for op in self.operations.values() if op.session_id == session_id]
            return sorted(results, key=lambda x: x.timestamp)
    
    def get_all_operations(self) -> List[OperationRecord]:
        """Get all operations (thread-safe)"""
        with self._lock:
            return list(self.operations.values())
    
    def get_operation_by_id(self, operation_id: str) -> Optional[OperationRecord]:
        """Get operation by ID (thread-safe)"""
        with self._lock:
            return self.operations.get(operation_id)
    
    def find_pull_for_image(self, image_name: str) -> Optional[OperationRecord]:
        """Find most recent pull operation for this image (thread-safe)"""
        def normalize(img):
            if not img:
                return ""
            return img.split(':')[0].split('/')[-1]
        
        target = normalize(image_name)
        with self._lock:
            candidates = []
            for op in self.operations.values():
                if op.operation.get("type") == "pull":
                    img = op.image.get("name", "")
                    if normalize(img) == target:
                        candidates.append(op)
            
            if candidates:
                candidates.sort(key=lambda x: x.timestamp)
                return candidates[-1]
            return None
    
    def find_create_for_container(self, container_name: str) -> Optional[OperationRecord]:
        """Find most recent create operation for this container (thread-safe)"""
        with self._lock:
            # First try exact name match
            op_id = self.container_name_to_operation.get(container_name)
            if op_id:
                op = self.operations.get(op_id)
                if op and op.operation.get("type") == "create":
                    return op
            
            # Try by ID (full or short)
            op_id = self.container_id_to_operation.get(container_name)
            if op_id:
                op = self.operations.get(op_id)
                if op and op.operation.get("type") == "create":
                    return op
            
            # Search by partial ID match
            for cid, oid in self.container_id_to_operation.items():
                if cid.startswith(container_name):
                    op = self.operations.get(oid)
                    if op and op.operation.get("type") == "create":
                        return op
            return None
    
    def cleanup_old_operations(self, max_age_hours: int = 24) -> int:
        """Remove operations older than max_age_hours (thread-safe)"""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        cutoff_str = cutoff.isoformat().replace("+00:00", "Z")
        
        removed = 0
        with self._lock:
            to_remove = []
            for op_id, op in self.operations.items():
                if op.last_accessed < cutoff_str:
                    to_remove.append(op_id)
            
            for op_id in to_remove:
                op = self.operations.pop(op_id, None)
                if op:
                    removed += 1
                    # Clean up maps
                    if op.image.get("digest"):
                        self.image_to_operation.pop(op.image["digest"], None)
                    if op.container.get("id"):
                        self.container_id_to_operation.pop(op.container["id"], None)
                    if op.container.get("name"):
                        self.container_name_to_operation.pop(op.container["name"], None)
        
        return removed
    
    def get_operation_chain(self, operation_id: str) -> List[OperationRecord]:
        """Get full operation chain starting from given operation (thread-safe)"""
        results = []
        current_id = operation_id
        visited = set()
        
        with self._lock:
            while current_id and current_id not in visited:
                if current_id not in self.operations:
                    break
                visited.add(current_id)
                op = self.operations[current_id]
                results.append(op)
                current_id = op.parent_id
        
        return results


def parse_http_request(request_bytes: bytes) -> tuple:
    """Parse HTTP request bytes into components"""
    try:
        text = request_bytes.decode('utf-8', errors='replace')
    except:
        return ("", "", {}, b"")
    
    parts = text.split("\r\n\r\n", 1)
    header_part = parts[0]
    body = parts[1] if len(parts) > 1 else ""
    
    lines = header_part.split("\r\n")
    if not lines:
        return ("", "", {}, b"")
    
    request_line = lines[0]
    parts = request_line.split(" ")
    method = parts[0] if len(parts) > 0 else ""
    path = parts[1] if len(parts) > 1 else ""
    
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    
    return (method, path, headers, body.encode())


def parse_http_response(response_bytes: bytes) -> tuple:
    """Parse HTTP response bytes into components"""
    if not response_bytes:
        return (0, {}, b"")
    
    try:
        text = response_bytes.decode('utf-8', errors='replace')
    except:
        return (0, {}, b"")
    
    # Find end of headers (double CRLF)
    header_end = text.find("\r\n\r\n")
    if header_end == -1:
        # No body, just headers
        header_part = text
        body = ""
    else:
        header_part = text[:header_end]
        body = text[header_end + 4:]  # Skip \r\n\r\n
    
    lines = header_part.split("\r\n")
    if not lines:
        return (0, {}, b"")
    
    status_line = lines[0]
    parts = status_line.split(" ", 2)
    status = int(parts[1]) if len(parts) > 1 else 0
    
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    
    return (status, headers, body.encode())


def parse_query_params(path: str) -> Dict[str, str]:
    """Extract query parameters from URL path"""
    params = {}
    if "?" in path:
        query = path.split("?", 1)[1]
        for pair in query.split("&"):
            if "=" in pair:
                key, value = pair.split("=", 1)
                params[key] = value
    return params


def parse_json_body(body: bytes) -> Dict[str, Any]:
    """Parse JSON body, return empty dict on failure"""
    if not body:
        return {}
    try:
        import json
        return json.loads(body.decode('utf-8'))
    except:
        return {}


def extract_container_id(path: str) -> Optional[str]:
    """Extract container ID from API path like /v1.45/containers/{id}/start"""
    path_only = path.split("?", 1)[0]
    match = re.match(r'^/(?:v\d+\.\d+/)?containers/([^/]+)', path_only)
    if match:
        return match.group(1)
    return None


def extract_exec_id(path: str) -> Optional[str]:
    """Extract exec ID from API path like /v1.45/exec/{id}/start"""
    path_only = path.split("?", 1)[0]
    match = re.match(r'^/(?:v\d+\.\d+/)?exec/([^/]+)', path_only)
    if match:
        return match.group(1)
    return None


def extract_digest_from_pull_response(body: bytes) -> Optional[str]:
    """Extract image digest from pull response (NDJSON)"""
    if not body:
        return None
    
    try:
        text = body.decode('utf-8', errors='replace')
        for line in text.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                if "status" in data and "Digest" in data:
                    return data["Digest"]
                if "aux" in data and isinstance(data["aux"], dict) and "Digest" in data["aux"]:
                    return data["aux"]["Digest"]
            except:
                continue
    except:
        pass
    return None


def is_streaming_endpoint(path: str) -> bool:
    """Check if endpoint uses streaming response"""
    path_only = path.split("?", 1)[0]
    normalized = re.sub(r'^/v\d+\.\d+', '', path_only)
    if normalized in ("/images/create", "/build", "/events"):
        return True
    if re.match(r'^/containers/[^/]+/(wait|logs)$', normalized):
        return True
    return False


def get_operation_type(method: str, path: str) -> str:
    """Map HTTP method + path to operation type"""
    path_only = path.split("?", 1)[0]
    normalized = re.sub(r'^/v\d+\.\d+', '', path_only)

    if normalized == "/_ping":
        return "preflight_ping"
    elif normalized == "/info":
        return "preflight_info"
    elif method == "GET" and re.match(r'^/images/[^/]+/json$', normalized):
        return "image_inspect"
    elif method == "GET" and re.match(r'^/networks/[^/]+$', normalized):
        return "network_inspect"
    elif method == "GET" and re.match(r'^/volumes/[^/]+$', normalized):
        return "volume_inspect"
    elif method == "GET" and re.match(r'^/plugins/[^/]+/json$', normalized):
        return "plugin_inspect"
    elif method == "GET" and normalized == "/containers/json":
        return "container_list"
    elif method == "GET" and re.match(r'^/containers/[^/]+/logs$', normalized):
        return "container_logs"
    elif method == "POST" and re.match(r'^/containers/[^/]+/exec$', normalized):
        return "exec_create"
    elif method == "POST" and re.match(r'^/exec/[^/]+/start$', normalized):
        return "exec_start"
    elif normalized == "/images/create":
        return "pull"
    elif normalized == "/build":
        return "build"
    elif normalized == "/containers/create":
        return "create"
    elif re.match(r'^/containers/[^/]+/start$', normalized):
        return "start"
    elif re.match(r'^/containers/[^/]+/stop$', normalized):
        return "stop"
    elif re.match(r'^/containers/[^/]+/wait$', normalized):
        return "wait"
    elif method == "DELETE" and re.match(r'^/containers/[^/]+$', normalized):
        return "rm"
    elif normalized.startswith("/containers/"):
        return "inspect"
    elif method == "DELETE" and re.match(r'^/images/[^/]+$', normalized):
        return "rmi"
    else:
        return "unknown"


def parse_operation_metadata(
    request_bytes: bytes,
    session_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    runtime_engine: str = "docker",
) -> OperationRecord:
    """Parse HTTP request to extract operation and relationships"""
    
    method, path, headers, body = parse_http_request(request_bytes)
    operation_type = get_operation_type(method, path)
    params = parse_query_params(path)
    body_json = parse_json_body(body)
    
    op = OperationRecord(
        session_id=session_id,
        parent_id=parent_id,
        runtime_engine=runtime_engine,
        operation={
            "type": operation_type,
            "action": f"{runtime_engine} {operation_type}" if operation_type != "unknown" else f"{runtime_engine} unknown",
            "api_path": path,
            "method": method
        },
        params=params
    )

    def _split_image_ref(image_ref: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        if not image_ref:
            return None, None
        repository, _, tag = image_ref.rpartition(":")
        if repository and "/" not in tag:
            return repository, tag
        return image_ref, None
    
    if "/images/create" in path:
        image = params.get("fromImage", body_json.get("Image"))
        tag = params.get("tag", "latest")
        op.image = {
            "name": image,
            "tag": tag,
            "digest": None,
            "platform": body_json.get("platform")
        }

    elif "/build" in path:
        image_name, image_tag = _split_image_ref(params.get("t"))
        op.image = {
            "name": image_name,
            "tag": image_tag,
            "digest": None,
            "platform": params.get("platform") or body_json.get("platform"),
        }
    
    elif "/containers/create" in path:
        image = body_json.get("Image")
        if image:
            op.image = {
                "name": image,
                "tag": "latest",
                "digest": None
            }
        container_name = params.get("name") or body_json.get("name") or body_json.get("Name")
        op.container = {
            "id": None,
            "name": container_name,
            "created_from_image": None
        }
        if body_json.get("Cmd"):
            op.container["command"] = body_json.get("Cmd")
    
    elif re.search(r'/(?:v\d+\.\d+/)?containers/[^/]+/exec(?:\?|$)', path):
        container_id = extract_container_id(path)
        if container_id:
            op.container = {
                "id": container_id,
                "name": body_json.get("name")
            }

    elif "/containers/" in path:
        container_id = extract_container_id(path)
        if container_id:
            op.container = {
                "id": container_id,
                "name": body_json.get("name")
            }

    if "/exec/" in path:
        exec_id = extract_exec_id(path)
        if exec_id:
            op.exec = {"id": exec_id}
    
    return op


def enrich_from_response(op: OperationRecord, response_bytes: bytes) -> OperationRecord:
    """Extract additional data from Docker API response"""
    
    status, headers, body = parse_http_response(response_bytes)
    body_json = parse_json_body(body)
    op.response = {"status": status}

    if op.operation.get("type") in OBSERVATION_OUTCOME_OPERATIONS:
        if 200 <= status < 400:
            op.response["outcome"] = "ok"
        elif status == 404:
            op.response["outcome"] = "miss"
        else:
            op.response["outcome"] = "error"
    
    if op.operation["type"] == "pull":
        # Even if body is empty, record the pull attempt
        digest = extract_digest_from_pull_response(body)
        if digest:
            op.image["digest"] = digest
        elif op.image.get("name"):
            # For cached images, construct digest from image name
            # Docker uses sha256 for content-addressable images
            op.image["digest"] = f"sha256:cached_{op.image['name']}"
    
    elif op.operation["type"] == "create":
        container_id = body_json.get("Id")
        if container_id:
            op.container["id"] = container_id
            # Store the image info for linking
            op.container["created_from_image"] = op.image.get("name")
            op.container["created_from_digest"] = op.image.get("digest")
    
    elif op.operation["type"] == "wait":
        exit_code = body_json.get("StatusCode")
        if exit_code is not None:
            op.response["container_exit_code"] = exit_code

    elif op.operation["type"] == "exec_create":
        exec_id = body_json.get("Id")
        if exec_id:
            op.exec["id"] = exec_id
    
    return op


def log_operation_json(op: OperationRecord) -> None:
    """Log operation as JSON to stdout"""
    output = asdict(op)
    _safe_stdout_write(json.dumps(output))


def log_operation(
    operation: str,
    timestamp: Optional[str] = None,
    image: Optional[str] = None,
    tag: Optional[str] = None,
    container_id: Optional[str] = None,
    command: Optional[str] = None,
    path: Optional[str] = None,
    method: Optional[str] = None,
    from_image: Optional[str] = None,
    **kwargs
) -> None:
    """Legacy log_operation for backward compatibility"""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    log_parts = [
        f"[TRUSTED_LOG]",
        f"TIMESTAMP={timestamp}",
        f"OPERATION={operation}",
    ]
    
    if image:
        log_parts.append(f"IMAGE={image}")
    if tag:
        log_parts.append(f"TAG={tag}")
    if container_id:
        log_parts.append(f"CONTAINER_ID={container_id}")
    if command:
        log_parts.append(f"COMMAND={command}")
    if path:
        log_parts.append(f"PATH={path}")
    if method:
        log_parts.append(f"METHOD={method}")
    if from_image:
        log_parts.append(f"FROM_IMAGE={from_image}")
    
    for key, value in kwargs.items():
        if value is not None:
            log_parts.append(f"{key.upper()}={value}")
    
    log_line = " ".join(log_parts)

    _safe_stdout_write(log_line)


def log_event(event_data: Dict[str, Any]) -> None:
    """Legacy log_event for backward compatibility"""
    log_operation(
        operation=event_data.get('operation', 'unknown'),
        timestamp=event_data.get('timestamp'),
        image=event_data.get('image'),
        tag=event_data.get('tag'),
        container_id=event_data.get('container_id'),
        command=event_data.get('command'),
        path=event_data.get('path'),
        method=event_data.get('method'),
        from_image=event_data.get('fromImage')
    )


if __name__ == "__main__":
    print("Testing new OperationRecord and tracker...")
    
    tracker = OperationTracker()
    
    op1 = OperationRecord(
        operation={"type": "pull", "action": "docker pull", "api_path": "/v1.45/images/create", "method": "POST"},
        image={"name": "nginx", "tag": "latest", "digest": "sha256:abc123"}
    )
    tracker.add(op1)
    print(f"Added pull operation: {op1.operation_id}")
    
    op2 = OperationRecord(
        parent_id=op1.operation_id,
        session_id=op1.session_id,
        operation={"type": "create", "action": "docker run", "api_path": "/v1.45/containers/create", "method": "POST"},
        image={"name": "nginx", "tag": "latest", "digest": "sha256:abc123"},
        container={"id": "edbc938", "name": "webapp"}
    )
    tracker.add(op2)
    print(f"Added create operation: {op2.operation_id}")
    
    op3 = OperationRecord(
        parent_id=op2.operation_id,
        session_id=op2.session_id,
        operation={"type": "start", "action": "docker start", "api_path": "/v1.45/containers/edbc938/start", "method": "POST"},
        container={"id": "edbc938", "name": "webapp"}
    )
    tracker.add(op3)
    print(f"Added start operation: {op3.operation_id}")
    
    print("\n--- Query by container 'edbc938' ---")
    for op in tracker.get_by_container("edbc938"):
        print(f"  {op.operation['type']} at {op.timestamp}")
    
    print("\n--- Query by image digest 'sha256:abc123' ---")
    for op in tracker.get_by_image("sha256:abc123"):
        print(f"  {op.operation['type']} at {op.timestamp}")
    
    print("\n--- Full operation chain from create ---")
    for op in tracker.get_operation_chain(op2.operation_id):
        print(f"  {op.operation['type']} ({op.operation_id[:8]})")
    
    print("\n--- Full JSON output ---")
    log_operation_json(op2)
    
    print("\nLogger test complete.")
