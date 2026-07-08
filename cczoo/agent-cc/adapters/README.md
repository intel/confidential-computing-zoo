# Agent-CC Adapters

Agent-CC adapters provide reference implementations for integrating various workloads into TDX trusted execution environments.

## OpenClaw Adapter

For deploying OpenClaw workloads in TDX environments, providing comprehensive container protection. Use cases include:

- Containerized AI workloads and secure sandboxes - see [English Guide](OpenClaw/openclaw_container_protection.md)
- A2S secure communication - see [English Guide](OpenClaw/openclaw_to_service_protection.md)

## Related Core Services

- [`TC API`](../core/tc_api/README.md) - TC API and trust chain control
- [`Trust Log`](../core/tlog/README.md) - Immutable signed evidence
- [`Argus`](../core/argus/README.md) - A2S secure communication