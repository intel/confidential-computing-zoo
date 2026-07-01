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
OpenViking Service Example - Integration with Agent-CC Argus Guard

This example demonstrates how OpenViking integrates with Agent-CC core services
for attestation-gated context storage and retrieval.

Prerequisites:
- Intel TDX-enabled platform
- TSM (Trusted Security Module) configured
- Argus Guard running at localhost:8007
- Argus Evidence Provider running at localhost:8008
- LUKS encrypted storage mounted at /mnt/encrypted
"""

import os
import sys
import json
import asyncio
import logging
import hmac
import hashlib
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GatewayError(Exception):
    """Gateway operation failed"""
    pass


class AccessDeniedError(GatewayError):
    """Access denied due to attestation failure"""
    pass


class InsufficientPrivilegesError(GatewayError):
    """Insufficient privileges for operation"""
    pass


class TcbStatus(Enum):
    """TCB Status values"""
    UP_TO_DATE = "UpToDate"
    OUT_OF_DATE = "OutOfDate"
    CONFIGURATION_REQUIRED = "ConfigurationRequired"
    UNKNOWN = "Unknown"


class PrivacyLevel(Enum):
    """Privacy restore levels"""
    STANDARD = "standard"
    ENHANCED = "enhanced"
    MAXIMUM = "maximum"


@dataclass
class AttestationEvidence:
    """Attestation evidence from caller"""
    quote_hex: str
    quote_size: int
    tcb_status: TcbStatus
    rtmr0: str
    rtmr1: str
    rtmr2: str
    rtmr3: str
    binding_digest: str


@dataclass
class ContextMetadata:
    """Context metadata (no actual content)"""
    context_id: str
    size: int
    binding: str
    created_at: str
    privacy_level: PrivacyLevel = PrivacyLevel.STANDARD


@dataclass
class EncryptedContext:
    """Encrypted context for materialization"""
    context_id: str
    encrypted_data: bytes
    binding: str
    stored_at: str


@dataclass
class CommitReceipt:
    """Receipt for committed context"""
    context_id: str
    committed_at: str
    binding: str


@dataclass
class PrivacyRestoredContext:
    """Context with privacy transformations applied"""
    context_id: str
    restored_data: bytes
    privacy_level: PrivacyLevel
    applied_transforms: List[str]


@dataclass
class TrustPolicy:
    """Trust policy for evaluating callers"""
    minimum_assurance_level: str = "L2"
    require_tcb_up_to_date: bool = False
    allowed_td_types: List[str] = field(default_factory=lambda: ["TDX"])
    
    def evaluate(self, evidence: AttestationEvidence) -> bool:
        """
        Evaluate caller against trust policy
        
        Args:
            evidence: Caller's attestation evidence
            
        Returns:
            True if caller meets policy requirements
        """
        # Check TCB status
        if self.require_tcb_up_to_date:
            if evidence.tcb_status != TcbStatus.UP_TO_DATE:
                logger.warn(f"Caller TCB not up to date: {evidence.tcb_status.value}")
                return False
        
        # Check binding digest
        if not evidence.binding_digest:
            logger.warn("Caller missing binding digest")
            return False
        
        return True


def load_trust_policy() -> TrustPolicy:
    strict_mode = os.getenv("STRICT_MODE", "false").lower() == "true"
    return TrustPolicy(require_tcb_up_to_date=strict_mode)


class OpenVikingTrustGate:
    """
    OpenViking Trust Gate
    
    Implements verify-skill trust gate that OpenClaw calls before context transfer.
    """
    
    def __init__(self, guard_endpoint: str = "http://localhost:8007"):
        self.guard_endpoint = guard_endpoint
        self.policy = load_trust_policy()
        self._verification_cache: Dict[str, datetime] = {}
    
    async def verify_caller(self, caller_evidence: AttestationEvidence) -> bool:
        """
        Verify OpenClaw caller before allowing context access
        
        Args:
            caller_evidence: Caller's attestation evidence
            
        Returns:
            True if caller is trusted and verified
        """
        logger.info("Verifying caller attestation")
        
        # Check cache to avoid repeated verification
        cache_key = caller_evidence.binding_digest[:16]
        if cache_key in self._verification_cache:
            cached_at = self._verification_cache[cache_key]
            if (datetime.utcnow() - cached_at).seconds < 300:  # 5 min cache
                logger.info("Using cached verification")
                return True

        # In the runnable example, OpenClaw has already called Argus Guard and
        # forwards the verified binding and measurements to OpenViking.
        is_trusted = self.policy.evaluate(caller_evidence)
        
        if is_trusted:
            self._verification_cache[cache_key] = datetime.utcnow()
        
        return is_trusted


class OpenVikingContextGateway:
    """
    OpenViking Context Gateway
    
    Provides context operations gated by attestation verification.
    """
    
    def __init__(
        self,
        trust_gate: OpenVikingTrustGate,
        encrypted_vfs_path: str = "/mnt/encrypted"
    ):
        self.trust_gate = trust_gate
        self.encrypted_vfs_path = encrypted_vfs_path
        self._context_store: Dict[str, Dict[str, Any]] = {}
    
    async def observe_context(
        self,
        caller: AttestationEvidence,
        context_id: str
    ) -> ContextMetadata:
        """
        Observe context (read-only, no materialization)
        
        Args:
            caller: Caller's attestation evidence
            context_id: Context to observe
            
        Returns:
            ContextMetadata (no actual content)
            
        Raises:
            AccessDeniedError: If caller verification fails
        """
        # Verify caller first
        if not await self.trust_gate.verify_caller(caller):
            raise AccessDeniedError("Caller verification failed")
        
        # Return metadata only
        if context_id not in self._context_store:
            raise ValueError(f"Context {context_id} not found")
        
        ctx = self._context_store[context_id]
        
        return ContextMetadata(
            context_id=context_id,
            size=ctx["size"],
            binding=ctx["binding"],
            created_at=ctx["created_at"],
            privacy_level=PrivacyLevel(ctx.get("privacy_level", "standard"))
        )
    
    async def recall_context(
        self,
        caller: AttestationEvidence,
        context_id: str
    ) -> EncryptedContext:
        """
        Recall context (materialize for processing)
        
        Args:
            caller: Caller's attestation evidence
            context_id: Context to recall
            
        Returns:
            EncryptedContext for caller processing
            
        Raises:
            AccessDeniedError: If caller verification fails
        """
        # Full verification for materialization
        if not await self.trust_gate.verify_caller(caller):
            raise AccessDeniedError("Caller verification failed")
        
        # Check if context exists
        if context_id not in self._context_store:
            raise ValueError(f"Context {context_id} not found")
        
        ctx = self._context_store[context_id]
        
        logger.info(f"Recalling context {context_id}")
        
        return EncryptedContext(
            context_id=context_id,
            encrypted_data=ctx["data"],
            binding=ctx["binding"],
            stored_at=ctx["stored_at"]
        )
    
    async def commit_context(
        self,
        caller: AttestationEvidence,
        context_id: str,
        content: bytes
    ) -> CommitReceipt:
        """
        Commit new context (archive with encryption)
        
        Args:
            caller: Caller's attestation evidence
            context_id: Unique context identifier
            content: Context content to store
            
        Returns:
            CommitReceipt for the operation
            
        Raises:
            AccessDeniedError: If caller verification fails
        """
        # Verify caller can write
        if not await self.trust_gate.verify_caller(caller):
            raise AccessDeniedError("Caller verification failed")
        
        # Compute binding from caller evidence
        binding = self._compute_binding(caller)
        
        # Store context
        now = datetime.utcnow().isoformat()
        self._context_store[context_id] = {
            "data": content,
            "binding": binding,
            "size": len(content),
            "stored_at": now,
            "created_at": now
        }
        
        logger.info(f"Committed context {context_id} with binding {binding[:16]}...")
        
        return CommitReceipt(
            context_id=context_id,
            committed_at=now,
            binding=binding
        )
    
    def _compute_binding(self, evidence: AttestationEvidence) -> str:
        """
        Compute binding digest from attestation evidence
        
        Args:
            evidence: Attestation evidence
            
        Returns:
            Binding digest string
        """
        # Use HMAC-SHA384 with RTMR0 as key material
        binding_key = evidence.rtmr0.encode()
        h = hmac.new(binding_key, b"openviking-context-binding", hashlib.sha384)
        return h.hexdigest()


class OpenVikingPrivacyRestore:
    """
    OpenViking Privacy Restore
    
    Provides privacy transformations for context data.
    """
    
    def __init__(self, gateway: OpenVikingContextGateway):
        self.gateway = gateway
    
    async def privacy_restore(
        self,
        caller: AttestationEvidence,
        context_id: str,
        privacy_level: PrivacyLevel
    ) -> PrivacyRestoredContext:
        """
        Restore context with privacy preservation
        
        Args:
            caller: Caller's attestation evidence
            context_id: Context to restore
            privacy_level: Desired privacy level
            
        Returns:
            PrivacyRestoredContext with transformations applied
            
        Raises:
            AccessDeniedError: If caller verification fails
        """
        # Verify caller and privacy claims
        if not await self.gateway.trust_gate.verify_caller(caller):
            raise AccessDeniedError("Caller verification failed")
        
        # Retrieve context
        context = await self.gateway.recall_context(caller, context_id)
        
        # Apply privacy transformations
        restored_data = context.encrypted_data
        applied_transforms = []
        
        if privacy_level == PrivacyLevel.ENHANCED:
            # Redact specific patterns
            restored_data = self._redact_patterns(restored_data, [b"password", b"token"])
            applied_transforms.append("pattern_redaction")
        elif privacy_level == PrivacyLevel.MAXIMUM:
            # Full anonymization
            restored_data = self._anonymize(restored_data)
            applied_transforms.append("full_anonymization")
        
        logger.info(f"Applied privacy transforms: {applied_transforms}")
        
        return PrivacyRestoredContext(
            context_id=context_id,
            restored_data=restored_data,
            privacy_level=privacy_level,
            applied_transforms=applied_transforms
        )
    
    def _redact_patterns(self, data: bytes, patterns: List[bytes]) -> bytes:
        """Redact specific patterns from data"""
        result = data
        for pattern in patterns:
            if pattern in result:
                result = result.replace(pattern, b"[REDACTED]")
        return result
    
    def _anonymize(self, data: bytes) -> bytes:
        """Anonymize all identifiable information"""
        return b"[ANONYMIZED]" + data[:0]  # Placeholder


class OpenVikingHTTPHandler(BaseHTTPRequestHandler):
    """
    HTTP handler for OpenViking Context Gateway API
    """
    
    def __init__(self, gateway: OpenVikingContextGateway, *args, **kwargs):
        self.gateway = gateway
        super().__init__(*args, **kwargs)
    
    def log_message(self, format, *args):
        """Log HTTP requests"""
        logger.info(f"{self.address_string()} - {format % args}")

    def _caller_evidence_from_headers(self) -> AttestationEvidence:
        quote_hex = self.headers.get("X-TDX-Quote", "")
        tcb_status = self.headers.get("X-TCB-Status", TcbStatus.UP_TO_DATE.value)

        return AttestationEvidence(
            quote_hex=quote_hex,
            quote_size=len(quote_hex) // 2,
            tcb_status=TcbStatus(tcb_status),
            rtmr0=self.headers.get("X-RTMR0", "demo-rtmr0"),
            rtmr1=self.headers.get("X-RTMR1", "demo-rtmr1"),
            rtmr2=self.headers.get("X-RTMR2", "demo-rtmr2"),
            rtmr3=self.headers.get("X-RTMR3", "demo-rtmr3"),
            binding_digest=self.headers.get("X-Binding-Digest", ""),
        )
    
    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)
        
        if parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy"}).encode())
        
        elif parsed.path.startswith("/context/"):
            if "/metadata" in parsed.path:
                # Observe context
                context_id = parsed.path.split("/")[-2]
                self._handle_observe(context_id)
            else:
                # Recall context
                context_id = parsed.path.split("/")[-1]
                self._handle_recall(context_id)
        
        elif parsed.path == "/trust/status":
            self._handle_trust_status()
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        """Handle POST requests"""
        parsed = urlparse(self.path)
        
        if parsed.path == "/context":
            self._handle_commit()
        elif parsed.path.startswith("/context/") and "/privacy-restore" in parsed.path:
            context_id = parsed.path.split("/")[2]
            self._handle_privacy_restore(context_id)
        elif parsed.path == "/verify/caller":
            self._handle_verify_caller()
        else:
            self.send_response(404)
            self.end_headers()
    
    def _handle_observe(self, context_id: str):
        """Handle context observation"""
        try:
            evidence = self._caller_evidence_from_headers()
            if not evidence.binding_digest:
                self.send_error(401, "Missing attestation evidence")
                return

            metadata = asyncio.run(
                self.gateway.observe_context(evidence, context_id)
            )
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "context_id": metadata.context_id,
                "size": metadata.size,
                "created_at": metadata.created_at,
                "privacy_level": metadata.privacy_level.value
            }).encode())
            
        except AccessDeniedError as e:
            self.send_error(403, str(e))
        except ValueError as e:
            self.send_error(404, str(e))
    
    def _handle_recall(self, context_id: str):
        """Handle context recall"""
        try:
            evidence = self._caller_evidence_from_headers()

            context = asyncio.run(
                self.gateway.recall_context(evidence, context_id)
            )
            
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(context.encrypted_data)
            
        except AccessDeniedError as e:
            self.send_error(403, str(e))
        except ValueError as e:
            self.send_error(404, str(e))
    
    def _handle_commit(self):
        """Handle context commit"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            content = self.rfile.read(content_length)
            
            # Parse request body
            body = json.loads(content)
            context_id = body.get("context_id")
            data = body.get("data", b"").encode()
            
            if not context_id:
                self.send_error(400, "Missing context_id")
                return
            
            evidence = self._caller_evidence_from_headers()

            receipt = asyncio.run(
                self.gateway.commit_context(evidence, context_id, data)
            )
            
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "context_id": receipt.context_id,
                "committed_at": receipt.committed_at,
                "binding": receipt.binding
            }).encode())
            
        except AccessDeniedError as e:
            self.send_error(403, str(e))
        except Exception as e:
            self.send_error(500, str(e))
    
    def _handle_verify_caller(self):
        """Handle caller verification"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            content = self.rfile.read(content_length)
            
            body = json.loads(content)
            quote_hex = body.get("quote_hex", "")
            
            evidence = AttestationEvidence(
                quote_hex=quote_hex,
                quote_size=len(quote_hex) // 2,
                tcb_status=TcbStatus(body.get("tcb_status", TcbStatus.UP_TO_DATE.value)),
                rtmr0=body.get("rtmr0", "demo-rtmr0"),
                rtmr1=body.get("rtmr1", "demo-rtmr1"),
                rtmr2=body.get("rtmr2", "demo-rtmr2"),
                rtmr3=body.get("rtmr3", "demo-rtmr3"),
                binding_digest=body.get("binding_digest", "")
            )
            
            is_trusted = asyncio.run(
                self.gateway.trust_gate.verify_caller(evidence)
            )
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "trusted": is_trusted,
                "verified_at": datetime.utcnow().isoformat()
            }).encode())
            
        except Exception as e:
            self.send_error(500, str(e))
    
    def _handle_trust_status(self):
        """Handle trust status query"""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "service": "openviking-cmem",
            "version": "1.0.0",
            "trust_model": "attestation-gated",
            "supported_operations": [
                "observe",
                "recall", 
                "commit",
                "privacy_restore"
            ]
        }).encode())


def create_server(
    gateway: OpenVikingContextGateway,
    host: str = "0.0.0.0",
    port: int = 8010
) -> HTTPServer:
    """Create OpenViking HTTP server"""
    
    class HandlerFactory:
        def __init__(self, gateway):
            self.gateway = gateway
        
        def __call__(self, *args, **kwargs):
            return OpenVikingHTTPHandler(self.gateway, *args, **kwargs)
    
    return HTTPServer((host, port), HandlerFactory(gateway))


async def run_demo(gateway: OpenVikingContextGateway):
    """Run the short in-memory OpenViking demo."""
    caller = AttestationEvidence(
        quote_hex="",
        quote_size=0,
        tcb_status=TcbStatus.UP_TO_DATE,
        rtmr0="demo-rtmr0",
        rtmr1="demo-rtmr1",
        rtmr2="demo-rtmr2",
        rtmr3="demo-rtmr3",
        binding_digest=hashlib.sha384(b"openclaw-to-openviking-demo").hexdigest(),
    )

    print("\n[1] Committing context with verified caller binding...")
    receipt = await gateway.commit_context(caller, "session-001", b"user=alice token=abc123")
    print(f"    Binding: {receipt.binding[:32]}...")

    print("\n[2] Observing context metadata...")
    metadata = await gateway.observe_context(caller, "session-001")
    print(f"    Size: {metadata.size} bytes")

    print("\n[3] Recalling protected context...")
    context = await gateway.recall_context(caller, "session-001")
    print(f"    Retrieved bytes: {len(context.encrypted_data)}")

    print("\n[4] Applying privacy restore...")
    privacy_restore = OpenVikingPrivacyRestore(gateway)
    restored = await privacy_restore.privacy_restore(caller, "session-001", PrivacyLevel.ENHANCED)
    print(f"    Transforms: {', '.join(restored.applied_transforms) or 'none'}")
    print(f"    Result: {restored.restored_data.decode(errors='replace')}")

    print("\nDemo completed successfully.")


def main():
    """Main example demonstrating OpenViking integration with Agent-CC."""

    print("=" * 60)
    print("OpenViking Service - Agent-CC Integration Example")
    print("=" * 60)

    # Initialize components
    trust_gate = OpenVikingTrustGate()
    gateway = OpenVikingContextGateway(trust_gate)

    if "--serve" in sys.argv:
        server = create_server(gateway, "0.0.0.0", 8010)

        print(f"\nOpenViking Context Gateway starting on port 8010")
        print("Endpoints:")
        print("  GET  /health                - Health check")
        print("  GET  /context/{id}/metadata - Observe context")
        print("  GET  /context/{id}          - Recall context")
        print("  POST /context               - Commit new context")
        print("  POST /verify/caller         - Verify caller attestation")
        print("  GET  /trust/status          - Get trust status")
        print("\nRequired caller headers: X-Binding-Digest, X-TCB-Status, X-RTMR0")
        print("Press Ctrl+C to stop")

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
            server.shutdown()
        return

    asyncio.run(run_demo(gateway))


if __name__ == "__main__":
    main()