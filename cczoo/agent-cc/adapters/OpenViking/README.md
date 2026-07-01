# OpenViking Adapter

This directory is the Agent-CC adapter entry point for OpenViking.

It represents the service-side integration path for running OpenViking inside the Agent-CC model as a confidential memory control plane. The adapter is intended to consume the shared core services from `core/` rather than reimplementing trust, build, or attestation flows locally.

## Overview

OpenViking is a confidential memory control plane service that provides attestation-gated context storage and retrieval. It works with OpenClaw agents through a trust gate mechanism.

## Current Scope

- Use OpenViking as the reference service workload for Agent-CC end-to-end validation.
- Connect OpenViking confidential memory operations to the shared TC-API verification path.
- Reuse shared trust infrastructure for context gateway operations.

In the real split deployment, OpenViking runs on the service side together with
the Argus Evidence Provider. OpenClaw keeps its own local Guard and fetches
OpenViking evidence remotely through that provider endpoint.

## Examples

- **[OpenViking Service Example](examples/README.md)** - Complete integration example showing:
  - Split deployment with service-side provider and caller-side guard
  - Trust gate verification implementation
  - Context gateway operations (observe, recall, commit)
  - Privacy restore operations
  - Docker Compose configuration

## Related Core Services

- [`../../core/tc-api/`](../../core/tc-api/) for trusted build, publish, launch, and verification orchestration
- [`../../core/tlog/`](../../core/tlog/) for immutable signed runtime evidence and digest rules
- [`../../core/trust-service/`](../../core/trust-service/) for attestation support services used by the deployment flow
- [`../../core/argus/`](../../core/argus/) for TDX quote verification

## OpenClaw Integration

OpenViking works with OpenClaw through a verify-skill trust gate:

- OpenClaw calls local verify skill before sending context
- Verify skill verifies OpenViking or gateway evidence
- Context transfer is denied when verification fails or is unavailable

See [OpenViking Trusted Context Gate Specification](../../openspec/specs/openviking-trusted-context-gate/spec.md) for details.

## Status

This adapter has a working, validated example under `examples/`: a
tc-api-managed Docker launch path (`docker-compose.tc-api.yml` +
`launch_openviking_via_tc_api.sh`), a real Argus Evidence Provider sidecar,
and `openviking_service.py` serving the context gateway API end to end (see
[`examples/README.md`](examples/README.md) for details). Further
OpenViking-specific deployment assets can still be added here as the adapter
path expands.

## Start Here

1. Read [`examples/README.md`](examples/README.md) for a complete integration example.
2. Read [`../../README.md`](../../README.md) for the top-level Agent-CC architecture and end-to-end scenario.
3. Read [`../../openspec/specs/openviking-trusted-context-gate/spec.md`](../../openspec/specs/openviking-trusted-context-gate/spec.md) for trust gate specification.