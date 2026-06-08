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

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote, urljoin, urlparse

import requests


class OciBundleMirror:
    OCI_MANIFEST_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
    OCI_CONFIG_MEDIA_TYPE = "application/vnd.unknown.config.v1+json"
    BUNDLE_LAYER_MEDIA_TYPE = "application/vnd.tc-api.bundle.v1+json"
    MIRROR_ARTIFACT_MEDIA_TYPE = "application/vnd.tc-api.bundle.mirror.v1+json"
    ANNOTATIONS_BLOB_KEY = "io.tc-api.bundle-annotations"
    PAYLOAD_HASH_KEY = "io.tc-api.payload-hash"

    def __init__(self, location: str):
        self.location = location
        parsed = urlparse(location)
        self._registry_mode = parsed.scheme in {"http", "https"}
        if self._registry_mode:
            repository = parsed.path.lstrip("/")
            if not repository:
                raise ValueError("Registry-backed mirror location must include a repository path")
            self.registry_base_url = f"{parsed.scheme}://{parsed.netloc}"
            self.repository = repository
            self.base_dir = None
        else:
            self.base_dir = Path(location)
            self.registry_base_url = None
            self.repository = None

    @staticmethod
    def _normalize_payload_hash(payload_hash: str) -> tuple[str, str]:
        algorithm, _, value = payload_hash.partition(":")
        if not algorithm or not value:
            raise ValueError("payload_hash must be in '<algorithm>:<hex>' form")
        if not all(ch in "0123456789abcdef" for ch in value.lower()):
            raise ValueError("payload_hash value must be hex-encoded")
        return algorithm, value.lower()

    @staticmethod
    def _artifact_digest(bundle_json: str) -> str:
        return "sha256:" + hashlib.sha256(bundle_json.encode("utf-8")).hexdigest()

    @staticmethod
    def _registry_reference(payload_hash: str) -> str:
        algorithm, value = OciBundleMirror._normalize_payload_hash(payload_hash)
        return f"payload-{algorithm}-{value}"

    @staticmethod
    def _encode_manifest_annotations(payload_hash: str, annotations: Dict[str, Any]) -> Dict[str, str]:
        manifest_annotations = {
            OciBundleMirror.PAYLOAD_HASH_KEY: payload_hash,
            OciBundleMirror.ANNOTATIONS_BLOB_KEY: json.dumps(annotations, sort_keys=True),
        }
        for key, value in annotations.items():
            manifest_annotations[f"io.tc-api.{key.replace('_', '-')}"] = str(value)
        return manifest_annotations

    @staticmethod
    def _decode_manifest_annotations(manifest_annotations: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(manifest_annotations, dict):
            return {}
        encoded = manifest_annotations.get(OciBundleMirror.ANNOTATIONS_BLOB_KEY)
        if isinstance(encoded, str):
            try:
                decoded = json.loads(encoded)
                if isinstance(decoded, dict):
                    return decoded
            except json.JSONDecodeError:
                return {}
        return {}

    def _registry_url(self, path: str) -> str:
        assert self.registry_base_url is not None
        return f"{self.registry_base_url}{path}"

    def _resolve_location(self, location: str) -> str:
        if location.startswith("http://") or location.startswith("https://"):
            return location
        assert self.registry_base_url is not None
        return urljoin(self.registry_base_url, location)

    def _push_blob(self, content: bytes) -> Dict[str, Any]:
        assert self.repository is not None
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        start = requests.post(self._registry_url(f"/v2/{self.repository}/blobs/uploads/"), timeout=5)
        start.raise_for_status()
        upload_url = self._resolve_location(start.headers["Location"])
        separator = "&" if "?" in upload_url else "?"
        finalize = requests.put(
            f"{upload_url}{separator}digest={quote(digest, safe=':')}",
            data=content,
            headers={"Content-Type": "application/octet-stream"},
            timeout=15,
        )
        finalize.raise_for_status()
        return {"digest": digest, "size": len(content)}

    def _pull_blob(self, digest: str) -> bytes:
        assert self.repository is not None
        response = requests.get(self._registry_url(f"/v2/{self.repository}/blobs/{digest}"), timeout=15)
        if response.status_code == 404:
            raise FileNotFoundError(digest)
        response.raise_for_status()
        return response.content

    def _put_manifest(self, reference: str, manifest: Dict[str, Any]) -> str:
        assert self.repository is not None
        response = requests.put(
            self._registry_url(f"/v2/{self.repository}/manifests/{reference}"),
            data=json.dumps(manifest, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": self.OCI_MANIFEST_MEDIA_TYPE},
            timeout=15,
        )
        response.raise_for_status()
        return response.headers.get("Docker-Content-Digest", "")

    def _get_manifest(self, reference: str) -> Optional[Dict[str, Any]]:
        assert self.repository is not None
        response = requests.get(
            self._registry_url(f"/v2/{self.repository}/manifests/{reference}"),
            headers={"Accept": self.OCI_MANIFEST_MEDIA_TYPE},
            timeout=15,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def _artifact_dir(self, payload_hash: str) -> Path:
        algorithm, value = self._normalize_payload_hash(payload_hash)
        assert self.base_dir is not None
        return self.base_dir / algorithm / value[:2] / value[2:4] / value

    def publish_bundle(
        self,
        *,
        payload_hash: str,
        bundle_json: str,
        annotations: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_annotations = annotations or {}
        self._normalize_payload_hash(payload_hash)

        if self._registry_mode:
            config_descriptor = self._push_blob(b"{}")
            bundle_descriptor = self._push_blob(bundle_json.encode("utf-8"))
            manifest = {
                "schemaVersion": 2,
                "mediaType": self.OCI_MANIFEST_MEDIA_TYPE,
                "artifactType": self.MIRROR_ARTIFACT_MEDIA_TYPE,
                "config": {
                    "mediaType": self.OCI_CONFIG_MEDIA_TYPE,
                    "digest": config_descriptor["digest"],
                    "size": config_descriptor["size"],
                },
                "layers": [
                    {
                        "mediaType": self.BUNDLE_LAYER_MEDIA_TYPE,
                        "digest": bundle_descriptor["digest"],
                        "size": bundle_descriptor["size"],
                        "annotations": {"org.opencontainers.image.title": "bundle.json"},
                    }
                ],
                "annotations": self._encode_manifest_annotations(payload_hash, normalized_annotations),
            }
            manifest_digest = self._put_manifest(self._registry_reference(payload_hash), manifest)
            return {
                "mediaType": self.MIRROR_ARTIFACT_MEDIA_TYPE,
                "payloadHash": payload_hash,
                "artifactDigest": bundle_descriptor["digest"],
                "manifestDigest": manifest_digest,
                "annotations": normalized_annotations,
                "bundlePath": "bundle.json",
            }

        artifact_dir = self._artifact_dir(payload_hash)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        bundle_path = artifact_dir / "bundle.json"
        bundle_path.write_text(bundle_json, encoding="utf-8")

        manifest = {
            "mediaType": self.MIRROR_ARTIFACT_MEDIA_TYPE,
            "payloadHash": payload_hash,
            "artifactDigest": self._artifact_digest(bundle_json),
            "annotations": normalized_annotations,
            "bundlePath": "bundle.json",
        }
        (artifact_dir / "manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        return manifest

    def resolve_bundle(self, payload_hash: str) -> Optional[Dict[str, Any]]:
        self._normalize_payload_hash(payload_hash)

        if self._registry_mode:
            manifest = self._get_manifest(self._registry_reference(payload_hash))
            if manifest is None:
                return None
            layers = manifest.get("layers")
            if not isinstance(layers, list) or not layers:
                return None
            layer = layers[0]
            digest = layer.get("digest") if isinstance(layer, dict) else None
            if not isinstance(digest, str):
                return None
            try:
                bundle_json = self._pull_blob(digest).decode("utf-8")
            except FileNotFoundError:
                return None
            return {
                "payload_hash": payload_hash,
                "bundle_json": bundle_json,
                "artifact_digest": digest,
                "annotations": self._decode_manifest_annotations(manifest.get("annotations")),
                "media_type": manifest.get("artifactType") or manifest.get("mediaType"),
            }

        artifact_dir = self._artifact_dir(payload_hash)
        manifest_path = artifact_dir / "manifest.json"
        bundle_path = artifact_dir / "bundle.json"
        if not manifest_path.exists() or not bundle_path.exists():
            return None

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        bundle_json = bundle_path.read_text(encoding="utf-8")
        return {
            "payload_hash": payload_hash,
            "bundle_json": bundle_json,
            "artifact_digest": manifest.get("artifactDigest"),
            "annotations": manifest.get("annotations") or {},
            "media_type": manifest.get("mediaType"),
        }


def build_mirror_annotations(
    *,
    chain_id: str,
    sequence_num: int,
    event_digest: Optional[str],
    rekor_log_id: Optional[str],
    payload_b64: str,
    event_id: Optional[str] = None,
    prev_event_digest: Optional[str] = None,
    prev_lookup_hash: Optional[str] = None,
) -> Dict[str, Any]:
    annotations: Dict[str, Any] = {
        "chain_id": chain_id,
        "sequence_num": sequence_num,
        "payload_b64": payload_b64,
    }
    if event_digest is not None:
        annotations["event_digest"] = event_digest
    if rekor_log_id is not None:
        annotations["rekor_log_id"] = rekor_log_id
    if event_id is not None:
        annotations["event_id"] = event_id
    if prev_event_digest is not None:
        annotations["prev_event_digest"] = prev_event_digest
    if prev_lookup_hash is not None:
        annotations["prev_lookup_hash"] = prev_lookup_hash
    return annotations