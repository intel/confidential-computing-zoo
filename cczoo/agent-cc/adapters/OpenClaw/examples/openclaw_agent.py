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
OpenClaw Agent Example - Integration with Agent-CC Argus Verifier

This example demonstrates how OpenClaw integrates with Agent-CC core services
for attestation-gated operations.

Prerequisites:
- Intel TDX-enabled platform
- TSM (Trusted Security Module) configured
- Argus Evidence Provider running at localhost:8008
- Argus Guard running at localhost:8007
"""

import os
import sys
import json
import asyncio
import logging
import http.client
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AttestationError(Exception):
    """Attestation verification failed"""
    pass


class SecretAccessError(Exception):
    """Secret retrieval failed"""
    pass


class TcbStatus(Enum):
    """TCB Status values"""
    UP_TO_DATE = "UpToDate"
    OUT_OF_DATE = "OutOfDate"
    CONFIGURATION_REQUIRED = "ConfigurationRequired"
    UNKNOWN = "Unknown"


def parse_tcb_status(value: str) -> TcbStatus:
    try:
        return TcbStatus(value)
    except ValueError:
        logger.warning("Unknown TCB status from verifier: %s; treating as Unknown", value)
        return TcbStatus.UNKNOWN


@dataclass
class AttestationEvidence:
    """Attestation evidence returned by Argus Guard"""
    quote_hex: str
    quote_size: int
    tcb_status: TcbStatus
    rtmr0: str
    rtmr1: str
    rtmr2: str
    rtmr3: str
    report_data: str = ""
    service_name: str = ""
    service_id: str = ""
    launch_id: str = ""
    image_digest: str = ""
    transparency_log_id: str = ""
    rekor_uuid: str = ""
    td_eventlog: Optional[str] = None


@dataclass
class AttestationContext:
    """Verified attestation context"""
    is_trusted: bool
    evidence: AttestationEvidence
    binding_digest: str
    verified_at: datetime


class ArgusGuardClient:
    """
    OpenClaw caller-side verifier using Agent-CC Argus Guard.

    OpenClaw does not verify raw quotes itself in this example. It asks the
    local Argus Guard to verify the target service and returns the normalized
    claims that OpenClaw can safely consume.
    """

    def __init__(self, guard_endpoint: str = "http://localhost:8007"):
        self.guard_endpoint = guard_endpoint

    async def verify_target(
        self,
        service_name: str,
        target_uri: str,
        caller_id: str,
    ) -> AttestationEvidence:
        """
        Verify a target service through Argus Guard.
        """
        import http.client

        logger.info("Verifying target via %s", self.guard_endpoint)

        parsed_url = urlparse(self.guard_endpoint)
        conn = http.client.HTTPConnection(parsed_url.netloc)
        
        try:
            payload = json.dumps({
                "target": {
                    "service_name": service_name,
                    "target_uri": target_uri,
                },
                "caller_id": caller_id,
                "requested_claims": [],
            })

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            path = parsed_url.path.rstrip("/")
            if not path.endswith("/ra/v1/verify"):
                path = f"{path}/ra/v1/verify" if path else "/ra/v1/verify"

            conn.request("POST", path, body=payload, headers=headers)
            response = conn.getresponse()

            if response.status != 200:
                raise AttestationError(
                    f"Verification request failed: HTTP {response.status}"
                )

            result = json.loads(response.read().decode())

            if result.get("decision") != "ALLOW":
                raise AttestationError(
                    f"Target verification denied: {result.get('reason', 'Unknown')}"
                )

            claims = result.get("claims") or {}
            measurements = claims.get("measurements") or {}
            binding_claims = claims.get("binding_claims") or {}
            service_identity = binding_claims.get("service_identity") or {}
            tcb_status = claims.get("tcb_status") or "Unknown"

            return AttestationEvidence(
                quote_hex="",
                quote_size=0,
                tcb_status=parse_tcb_status(tcb_status),
                rtmr0=measurements.get("rtmr0") or "",
                rtmr1=measurements.get("rtmr1") or "",
                rtmr2=measurements.get("rtmr2") or "",
                rtmr3=measurements.get("rtmr3") or "",
                report_data=claims.get("report_data", ""),
                service_name=service_identity.get("service_name", ""),
                service_id=service_identity.get("service_id", "") or "",
                launch_id=service_identity.get("launch_id", "") or "",
                image_digest=service_identity.get("image_digest", "") or "",
                transparency_log_id=service_identity.get("transparency_log_id", "") or "",
                rekor_uuid=service_identity.get("rekor_uuid", "") or "",
            )
                
        finally:
            conn.close()


class OpenClawEvidenceProvider:
    """
    OpenClaw Evidence Provider
    
    Provides TDX attestation evidence for OpenClaw runtime.
    """
    
    def __init__(self, guard_endpoint: str = "http://localhost:8007"):
        self.guard_endpoint = guard_endpoint
        self.guard = ArgusGuardClient(guard_endpoint)
    
    async def fetch_runtime_attestation(self) -> AttestationEvidence:
        """
        Ask Argus Guard to verify the target service for OpenClaw.
        
        Returns:
            AttestationEvidence containing quote and measurements
            
        Raises:
            AttestationError: If evidence fetch fails
        """
        service_name = os.getenv("TARGET_SERVICE_NAME", "openviking-cmem")
        target_uri = os.getenv("TARGET_URI", "https://openviking.local")
        caller_id = os.getenv("AGENT_SERVICE_NAME", "openclaw-agent")

        logger.info("Verifying target service %s (%s)", service_name, target_uri)
        evidence = await self.guard.verify_target(service_name, target_uri, caller_id)
        logger.info("Target verified: TCB status=%s", evidence.tcb_status.value)

        return evidence


class OpenVikingClient:
    """Minimal client that exercises the launched OpenViking workload."""

    def __init__(self, target_uri: str):
        self.target_uri = target_uri

    def _headers_from_evidence(self, evidence: AttestationEvidence) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Binding-Digest": evidence.report_data,
            "X-TCB-Status": evidence.tcb_status.value,
            "X-RTMR0": evidence.rtmr0,
            "X-RTMR1": evidence.rtmr1,
            "X-RTMR2": evidence.rtmr2,
            "X-RTMR3": evidence.rtmr3,
        }

    def _request(self, method: str, path: str, *, headers: Dict[str, str], body: Optional[Dict[str, Any]] = None) -> Any:
        parsed_url = urlparse(self.target_uri)
        conn = http.client.HTTPConnection(parsed_url.netloc)
        try:
            payload = json.dumps(body) if body is not None else None
            conn.request(method, path, body=payload, headers=headers)
            response = conn.getresponse()
            raw = response.read().decode()
            if response.status not in (200, 201):
                raise RuntimeError(f"OpenViking request failed: {method} {path} -> HTTP {response.status}: {raw}")
            if not raw:
                return None
            content_type = response.getheader("Content-Type", "")
            if "application/json" in content_type:
                return json.loads(raw)
            return raw.encode()
        finally:
            conn.close()

    async def verify_caller(self, evidence: AttestationEvidence) -> Dict[str, Any]:
        body = {
            "quote_hex": evidence.quote_hex,
            "tcb_status": evidence.tcb_status.value,
            "rtmr0": evidence.rtmr0,
            "rtmr1": evidence.rtmr1,
            "rtmr2": evidence.rtmr2,
            "rtmr3": evidence.rtmr3,
            "binding_digest": evidence.report_data,
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        return await asyncio.to_thread(self._request, "POST", "/verify/caller", headers=headers, body=body)

    async def commit_context(self, context_id: str, data: str, evidence: AttestationEvidence) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self._request,
            "POST",
            "/context",
            headers=self._headers_from_evidence(evidence),
            body={"context_id": context_id, "data": data},
        )

    async def observe_context(self, context_id: str, evidence: AttestationEvidence) -> Dict[str, Any]:
        headers = {key: value for key, value in self._headers_from_evidence(evidence).items() if key != "Content-Type"}
        return await asyncio.to_thread(
            self._request,
            "GET",
            f"/context/{context_id}/metadata",
            headers=headers,
        )

    async def recall_context(self, context_id: str, evidence: AttestationEvidence) -> bytes:
        headers = {key: value for key, value in self._headers_from_evidence(evidence).items() if key != "Content-Type"}
        return await asyncio.to_thread(
            self._request,
            "GET",
            f"/context/{context_id}",
            headers=headers,
        )


class OpenClawSecretManager:
    """
    OpenClaw Secret Manager with Attestation-Gated Access
    
    Retrieves secrets only after attestation verification succeeds.
    """
    
    def __init__(self, guard_endpoint: str = "http://localhost:8007"):
        self.guard_endpoint = guard_endpoint
        self._secrets_cache: Dict[str, Any] = {}
    
    async def get_api_key(
        self, 
        key_id: str, 
        attestation: AttestationContext
    ) -> str:
        """
        Retrieve API key only if attestation passes
        
        Args:
            key_id: Identifier for the secret
            attestation: Verified attestation context
            
        Returns:
            The secret value
            
        Raises:
            SecretAccessError: If access is denied
        """
        if not attestation.is_trusted:
            raise SecretAccessError(
                f"Attestation verification failed, cannot access secret {key_id}"
            )
        
        logger.info(f"Retrieving secret {key_id} with attestation binding")
        
        # In production, this would call the Guard service to release the secret
        # For now, simulate secret retrieval
        secrets = {
            "openai_api_key": "sk-test-1234567890abcdef",
            "discord_token": "ODc2MTkxOTc2MjY3ODkyMzI2.GxBbXx",
            "luks_passphrase": "super-secret-luks-key"
        }
        
        if key_id in secrets:
            return secrets[key_id]
        else:
            raise SecretAccessError(f"Secret {key_id} not found")


class OpenClawContextManager:
    """
    OpenClaw Context Manager with Encrypted Storage
    
    Manages context storage with attestation binding.
    """
    
    def __init__(self, encrypted_vfs_path: str = "/mnt/encrypted"):
        self.encrypted_vfs_path = encrypted_vfs_path
        self._context_index: Dict[str, Dict[str, Any]] = {}
    
    async def store_context(
        self,
        context_id: str,
        context_data: bytes,
        binding_digest: str
    ) -> None:
        """
        Store context with attestation binding
        
        Args:
            context_id: Unique context identifier
            context_data: Context data to store
            binding_digest: Attestation binding digest
        """
        context_path = os.path.join(self.encrypted_vfs_path, f"{context_id}.ctx")
        
        # In production, this would encrypt and store the context
        # For now, just track the metadata
        self._context_index[context_id] = {
            "path": context_path,
            "binding": binding_digest,
            "size": len(context_data),
            "stored_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Stored context {context_id} with binding {binding_digest[:16]}...")
    
    async def retrieve_context(
        self,
        context_id: str,
        expected_binding: str
    ) -> bytes:
        """
        Retrieve context only if attestation matches
        
        Args:
            context_id: Unique context identifier
            expected_binding: Expected attestation binding
            
        Returns:
            Decrypted context data
            
        Raises:
            ValueError: If binding mismatch
        """
        if context_id not in self._context_index:
            raise ValueError(f"Context {context_id} not found")
        
        stored_binding = self._context_index[context_id]["binding"]
        if stored_binding != expected_binding:
            raise ValueError(
                f"Binding mismatch for context {context_id}: "
                f"expected {expected_binding[:16]}..., got {stored_binding[:16]}..."
            )
        
        logger.info(f"Retrieved context {context_id}")
        
        # In production, this would decrypt and return the context
        return b"decrypted context data"


async def main():
    """Main example demonstrating OpenClaw integration with Agent-CC"""
    
    print("=" * 60)
    print("OpenClaw Agent - Agent-CC Integration Example")
    print("=" * 60)
    
    # Initialize components
    evidence_provider = OpenClawEvidenceProvider()
    secret_manager = OpenClawSecretManager()
    context_manager = OpenClawContextManager()
    target_uri = os.getenv("TARGET_URI", "http://127.0.0.1:8010")
    openviking_client = OpenVikingClient(target_uri)
    
    try:
        # Step 1: Fetch and verify attestation
        print("\n[1] Verifying OpenViking through Argus Guard...")
        evidence = await evidence_provider.fetch_runtime_attestation()
        print(f"    TCB Status: {evidence.tcb_status.value}")
        if evidence.service_name:
            print(f"    Service Name: {evidence.service_name}")
        if evidence.service_id:
            print(f"    Workload ID: {evidence.service_id}")
        if evidence.launch_id:
            print(f"    Launch ID: {evidence.launch_id}")
        if evidence.image_digest:
            print(f"    Image Digest: {evidence.image_digest[:40]}...")
        if evidence.rekor_uuid:
            print(f"    Rekor UUID: {evidence.rekor_uuid}")
        if evidence.transparency_log_id:
            print(f"    Transparency Log ID: {evidence.transparency_log_id}")
        print(f"    RTMR0: {evidence.rtmr0[:32]}...")
        print(f"    RTMR1: {evidence.rtmr1[:32]}...")
        
        # Step 2: Create attestation context
        print("\n[2] Creating attestation context...")
        attestation = AttestationContext(
            is_trusted=True,
            evidence=evidence,
            binding_digest=evidence.report_data,
            verified_at=datetime.utcnow()
        )
        print(f"    Trusted: {attestation.is_trusted}")
        print(f"    Binding: {attestation.binding_digest[:32]}...")
        
        # Step 3: Retrieve attestation-gated secret
        print("\n[3] Retrieving attestation-gated secret...")
        api_key = await secret_manager.get_api_key("openai_api_key", attestation)
        print(f"    API Key: {api_key[:20]}...")
        
        # Step 4: Store context with attestation binding
        print("\n[4] Storing context with attestation binding...")
        await context_manager.store_context(
            context_id="session-001",
            context_data=b"User context: Hello, this is a test session",
            binding_digest=attestation.binding_digest
        )
        print("    Context stored successfully")
        
        # Step 5: Retrieve context (verifying binding)
        print("\n[5] Retrieving context with binding verification...")
        retrieved = await context_manager.retrieve_context(
            context_id="session-001",
            expected_binding=attestation.binding_digest
        )
        print(f"    Retrieved: {retrieved}")

        # Step 6: Call the real OpenViking workload through its HTTP API
        print("\n[6] Calling OpenViking verify endpoint...")
        verify_result = await openviking_client.verify_caller(evidence)
        print(f"    Trusted by OpenViking: {verify_result.get('trusted')}")

        print("\n[7] Committing context to OpenViking...")
        remote_context_id = "session-e2e-001"
        commit_result = await openviking_client.commit_context(
            remote_context_id,
            "OpenClaw to OpenViking end-to-end context payload",
            evidence,
        )
        print(f"    Remote binding: {commit_result.get('binding', '')[:32]}...")

        print("\n[8] Observing OpenViking context metadata...")
        metadata_result = await openviking_client.observe_context(remote_context_id, evidence)
        print(f"    Remote size: {metadata_result.get('size')} bytes")

        print("\n[9] Recalling OpenViking context payload...")
        recalled = await openviking_client.recall_context(remote_context_id, evidence)
        print(f"    Remote payload: {recalled!r}")
        
        print("\n" + "=" * 60)
        print("Example completed successfully!")
        print("=" * 60)
        
    except AttestationError as e:
        print(f"\n[!] Attestation failed: {e}")
        sys.exit(1)
    except SecretAccessError as e:
        print(f"\n[!] Secret access denied: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[!] Unexpected error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())