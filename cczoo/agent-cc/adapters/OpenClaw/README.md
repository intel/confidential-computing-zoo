# OpenClaw Adapter

This directory is the Agent-CC adapter entry point for OpenClaw.

It represents the deployment-side integration path for running OpenClaw inside the Agent-CC model without requiring invasive framework changes. The adapter is intended to consume the shared core services from `core/` rather than reimplementing trust, build, or attestation flows locally.

## Overview

OpenClaw is a confidential AI agent runtime that runs inside a TDVM (Trust Domain Virtual Machine). It provides:
- LLM client integration
- Context management with attestation-gated storage
- Tool execution with trust verification

## Current Scope

- Use OpenClaw as the reference agent workload for Agent-CC end-to-end validation.
- Connect OpenClaw runtime deployment to the shared TC-API build, launch, and verification path.
- Reuse shared trust infrastructure such as trusted logging, attestation-gated secret release, and encrypted storage helpers.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    OpenClaw Agent Runtime (TDVM)                │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  OpenClaw Agent                                             │ │
│  │  - LLM Client                                               │ │
│  │  - Context Manager                                          │ │
│  │  - Tool Executor                                            │ │
│  │  - Trust Policy Engine                                      │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ Attestation-gated
┌─────────────────────────────────────────────────────────────────┐
│                     Agent-CC Core Services                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Argus     │  │   TC-API    │  │  Trust      │              │
│  │  Verifier   │  │  Service    │  │  Service    │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

## Integration Points

### 1. Trust Gate Verification

OpenClaw calls the local verify skill before sending context to external services:

```python
# Example: Verify service before context transfer
from openclaw_agent import verify_service

# Verify OpenViking service
result = verify_service("openviking-cmem", "https://openviking.local")
if result.trusted:
    # Context transfer allowed
    pass
```

### 2. Attestation-Gated Secrets

OpenClaw retrieves secrets only after attestation verification succeeds:

```python
# API keys are released only to attested environments
secret = get_attestation_gated_secret("openai_api_key", binding_digest)
```

### 3. Context Storage with Binding

Context is stored with attestation binding for verification on retrieval:

```python
# Store context with RTMR binding
store_context(session_id, context_data, binding_digest)

# Retrieve only after binding verification
context = retrieve_context(session_id, binding_digest)
```

## Related Core Services

- [`../../core/tc-api/`](../../core/tc-api/) for trusted build, publish, launch, and verification orchestration
- [`../../core/tlog/`](../../core/tlog/) for immutable signed runtime evidence and digest rules
- [`../../core/trust-service/`](../../core/trust-service/) for attestation support services used by the deployment flow
- [`../../core/argus/`](../../core/argus/) for TDX quote verification and trust policy evaluation

## Status

✅ **Validated** - OpenClaw example has been tested with real TDX quotes on Intel TDX hardware.

See [examples/README.md](examples/README.md) for running the full e2e test.

## Start Here

1. Read [`examples/README.md`](examples/README.md) for the complete integration example with step-by-step instructions.
2. Read [`../../README.md`](../../README.md) for the top-level Agent-CC architecture and end-to-end scenario.
3. Read [`../../core/tc-api/README.md`](../../core/tc-api/README.md) for the trusted build-to-runtime control path.
4. Read [`../../core/trust-service/README.md`](../../core/trust-service/README.md) if you need the attestation service container setup.
