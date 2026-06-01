# OpenClaw Adapter

This directory is the Agent-CC adapter entry point for OpenClaw.

It represents the deployment-side integration path for running OpenClaw inside the Agent-CC model without requiring invasive framework changes. The adapter is intended to consume the shared core services from `core/` rather than reimplementing trust, build, or attestation flows locally.

## Current Scope

- Use OpenClaw as the reference agent workload for Agent-CC end-to-end validation.
- Connect OpenClaw runtime deployment to the shared TC-API build, launch, and verification path.
- Reuse shared trust infrastructure such as trusted logging, attestation-gated secret release, and encrypted storage helpers.

## Related Core Services

- [`../../core/tc-api/`](../../core/tc-api/) for trusted build, publish, launch, and verification orchestration
- [`../../core/tlog/`](../../core/tlog/) for immutable signed runtime evidence and digest rules
- [`../../core/trust-service/`](../../core/trust-service/) for attestation support services used by the deployment flow

## Status

This adapter currently serves as a documentation and integration entry point. Concrete OpenClaw-specific deployment assets will be added here as the adapter path is expanded.

## Start Here

1. Read [`../../README.md`](../../README.md) for the top-level Agent-CC architecture and end-to-end scenario.
2. Read [`../../core/tc-api/README.md`](../../core/tc-api/README.md) for the trusted build-to-runtime control path.
3. Read [`../../core/trust-service/README.md`](../../core/trust-service/README.md) if you need the attestation service container setup.
