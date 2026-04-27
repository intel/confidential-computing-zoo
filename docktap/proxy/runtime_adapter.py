from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .operation_log import get_operation_type, parse_operation_metadata


DEFAULT_RUNTIME_ENGINE = "docker"
SUPPORTED_RUNTIME_ENGINES = {DEFAULT_RUNTIME_ENGINE, "podman"}


def normalize_runtime_engine(runtime_engine: Optional[str]) -> str:
    if not runtime_engine:
        return DEFAULT_RUNTIME_ENGINE
    normalized = str(runtime_engine).strip().lower()
    if not normalized:
        return DEFAULT_RUNTIME_ENGINE
    aliases = {
        "docker-engine": "docker",
        "moby": "docker",
        "libpod": "podman",
    }
    return aliases.get(normalized, normalized)


@dataclass(frozen=True)
class ParsedRuntimeRequest:
    operation_type: Optional[str]
    path_only: Optional[str]
    params: Dict[str, Any]


class RuntimeAdapter:
    runtime_engine: str

    def parse_request(self, data: bytes) -> ParsedRuntimeRequest:
        raise NotImplementedError

    def map_operation(self, path: str, method: str) -> Optional[str]:
        raise NotImplementedError

    def parse_operation_metadata(self, request_bytes: bytes, session_id: Optional[str] = None, parent_id: Optional[str] = None):
        raise NotImplementedError


class DockerRuntimeAdapter(RuntimeAdapter):
    def __init__(self, runtime_engine: str = DEFAULT_RUNTIME_ENGINE) -> None:
        self.runtime_engine = normalize_runtime_engine(runtime_engine)

    def parse_request(self, data: bytes) -> ParsedRuntimeRequest:
        try:
            request_str = data.decode("utf-8", errors="ignore")
            lines = request_str.split("\r\n")
            if not lines:
                return ParsedRuntimeRequest(None, None, {})

            request_line = lines[0]
            parts = request_line.split(" ")
            if len(parts) < 2:
                return ParsedRuntimeRequest(None, None, {})

            method = parts[0]
            path = parts[1]

            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(path)
            path_only = parsed.path
            query_params = parse_qs(parsed.query)

            params: Dict[str, Any] = {}
            if query_params:
                params.update(query_params)

            body_start = request_str.find("\r\n\r\n")
            if body_start != -1:
                body = request_str[body_start + 4 :]
                if body:
                    params["body"] = body

            params["method"] = method
            params["path"] = path_only
            params["runtime_engine"] = self.runtime_engine
            return ParsedRuntimeRequest(get_operation_type(method, path), path_only, params)
        except Exception:
            return ParsedRuntimeRequest(None, None, {})

    def map_operation(self, path: str, method: str) -> Optional[str]:
        return get_operation_type(method, path)

    def parse_operation_metadata(self, request_bytes: bytes, session_id: Optional[str] = None, parent_id: Optional[str] = None):
        return parse_operation_metadata(
            request_bytes,
            session_id=session_id,
            parent_id=parent_id,
            runtime_engine=self.runtime_engine,
        )