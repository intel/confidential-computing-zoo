# Argus

Argus is an application-non-invasive runtime trust verification framework for agent-to-service (A2S) communication in confidential computing environments.

Its job is narrow: before a caller sends sensitive data to a peer service, Argus fetches evidence for that peer, verifies the evidence through an external attestation or identity system, and evaluates caller-local policy to decide whether the call should proceed.

Current document scope: Argus v1 is specified only for A2S. Service-to-service triggering, caching, and rollout semantics are intentionally left out of the current draft.

## Status

Argus v1 is implemented in Rust and validated end-to-end on real Intel TDX hardware:

- `argus-evidence-provider` (service side): generates real TDX quotes through the Linux TSM/configfs interface (`/sys/kernel/config/tsm/report/`), optionally enriched with TC-API service metadata.
- `argus-guard` (caller side): fetches evidence, verifies quote structure, signature, and nonce binding, and evaluates policy to produce an ALLOW/DENY decision.
- Both binaries build from this crate with `cargo build --release` and also ship as a single Docker image (see `Dockerfile`) for containerized deployment.
- Validated end-to-end together with the [OpenClaw](../../adapters/OpenClaw) and [OpenViking](../../adapters/OpenViking) adapters and `core/tc-api`, via `adapters/OpenViking/examples/run_openclaw_openviking_e2e.sh`.
- TCB/collateral (PCCS-based freshness) verification is intentionally out of scope for v1 — see [Design Decisions](./docs/design-decisions.md) for the rationale.

## Documentation

- [Quick Start](./docs/quickstart.md): build, run, and smoke-test Argus locally or via Docker.
- [Architecture](./docs/architecture.md): system model, trust boundaries, deployment modes, governance boundary, and v1 MVP.
- [API Contract](./docs/api.md): evidence request and response, verifier contract, profile model, policy model, and diagnostics surface.
- [Configuration](./docs/configuration.md): environment variables and runtime configuration reference.
- [Deployment](./docs/deployment.md): Docker and systemd deployment options.
- [Design Decisions](./docs/design-decisions.md): scope decisions, including why TCB/collateral verification is out of scope for v1.
- [Testing And Validation](./docs/tests.md): conformance vectors, predicate validation, governance regression tests, rollout strategy, and MVP validation.
- [Troubleshooting](./docs/troubleshooting.md): common issues and fixes.

## What Argus Covers

Argus standardizes:

- caller-side trust enforcement
- service-side evidence production
- verifier-normalized claims
- profile-driven authorization decisions
- governance-aware fail-closed behavior for profiles, collectors, and reference values

Argus does not require the repository itself to own every governance system. Profile publication, collector PKI, and reference-value bundle distribution may be provided by external systems as long as they satisfy the contract described in the documentation.

## Recommended V1 Path

The recommended baseline path for v1 is:

1. SDK mode on the caller side.
2. Direct `/ra/v1/evidence` endpoint on the service side.
3. Trustee or equivalent verifier for quote and report-data validation.
4. Static signed profile loaded locally or from a simple governed bundle.
5. No service-mesh-authoritative joins or policy-authoritative runtime collector requirement in the base path.

This path is intended to close the protocol loop first, then expand into mesh, collector-heavy, and more automated governance integrations as profile extensions.

## How To Use This Repository Today

If you are integrating Argus into a caller or service:

1. Start with [Quick Start](./docs/quickstart.md) to build and smoke-test the binaries.
2. Read [Architecture](./docs/architecture.md) to understand scope and deployment assumptions.
3. Read [API Contract](./docs/api.md) before implementing any endpoint, verifier adapter, profile loader, or policy engine.
4. Use [Testing And Validation](./docs/tests.md) as the acceptance bar for conformance vectors, deny reasons, and rollout behavior.
5. Check [Troubleshooting](./docs/troubleshooting.md) if a service fails to start or attestation fails unexpectedly.

The Rust implementation under `src/` is the shipping stack: `argus-evidence-provider` and `argus-guard` binaries, built with `cargo build --release` or the provided `Dockerfile`. There is no separate Python prototype — this crate is the reference implementation.

## Repository Layout

```text
argus/
├── README.md
├── README_CN.md
├── Cargo.toml / Cargo.lock
├── Dockerfile
├── docker-compose.yml
├── start_argus.sh          # build/validate/start/stop/status/test helper script
├── src/
│   ├── lib.rs
│   ├── binding.rs          # runtime binding context (endpoint, pid, container id, ...)
│   ├── crypto_verifier.rs  # signature/cert verification helpers used by tdx_verifier.rs
│   ├── engine.rs           # caller-side ArgusEngine (fetch -> verify -> policy -> decision)
│   ├── errors.rs
│   ├── policy.rs           # policy evaluator
│   ├── tc_api_client.rs    # optional TC-API metadata/quote client
│   ├── tdx_verifier.rs     # TDX quote structure/signature/nonce-binding verification
│   ├── types.rs
│   ├── verifier.rs         # RaAdapter (RaVerifier trait implementation)
│   ├── bin/
│   │   ├── evidence_provider.rs   # argus-evidence-provider HTTP server
│   │   └── guard.rs               # argus-guard HTTP server
│   └── service/
│       └── engine.rs      # service-side EvidenceEngine (quote generation, TC-API metadata)
├── tests/                  # integration and unit test suites
├── test-fixtures/
└── docs/
    ├── quickstart.md
    ├── architecture.md
    ├── api.md
    ├── configuration.md
    ├── deployment.md
    ├── design-decisions.md
    ├── tests.md
    └── troubleshooting.md
```

## Quick Start

Requires Intel TDX hardware with `/dev/tdx_guest` and TSM configfs mounted at `/sys/kernel/config/tsm/report/`. See [Quick Start](./docs/quickstart.md) for full prerequisites, manual `curl` testing, Docker, and systemd deployment options.

```bash
cd core/argus

# Build both binaries (argus-evidence-provider, argus-guard)
cargo build --release

# Inject a stable workload identity for the Evidence Provider
export ARGUS_WORKLOAD_IDENTITY=openviking-cmem

# Validate the environment, then start and smoke-test both services
./start_argus.sh validate
./start_argus.sh start
./start_argus.sh test
./start_argus.sh status
./start_argus.sh stop
```

`ARGUS_WORKLOAD_IDENTITY` is now the recommended way to inject a real, stable workload identity for the Evidence Provider. `ARGUS_SERVICE_NAME`, `SERVICE_NAME`, and `K_SERVICE` remain accepted as compatibility inputs, but `HOSTNAME` is no longer accepted as a service-identity source.

To exercise the full multi-service flow (Argus + TC-API + OpenViking + OpenClaw) with real TDX quotes over Docker Compose, see [adapters/OpenViking/examples/README.md](../../adapters/OpenViking/examples/README.md) and run `run_openclaw_openviking_e2e.sh`.

## Security Guarantees

On the validated path, Argus currently provides:

- Replay resistance via a caller-generated nonce bound into `report_data`.
- A single verifiable chain linking the caller request, the returned `BindingClaims`, and the `report_data` in the evidence.
- Fail-closed behavior on the caller side whenever evidence fetch or verification fails.
- Extraction of RTMR values and TCB status for upstream policy to further restrict access.
- Separation of caller-side trust enforcement from service-side evidence generation, so application code never directly controls the attestation flow.

Current boundaries to keep in mind: the default request path performs structural validation and request-binding validation of a live TSM quote, but does not yet perform full Intel collateral/certificate-chain verification in the Guard's main path. The current implementation is more accurately described as "request-bound TDX evidence verification" rather than "full PKI-based remote attestation verification". See [Design Decisions](./docs/design-decisions.md) for the full rationale and roadmap.

## Next Steps

The most natural follow-on work is:

1. Wire collateral-aware TCB verification (PCCS/QVL) into the Guard's main verification path, per the roadmap in [Design Decisions](./docs/design-decisions.md).
2. Create machine-readable schema artifacts for `ProfileBody`, `ProfileEnvelope`, and related contracts.
3. Add conformance vectors for canonicalization, builtin predicates, and deny-reason taxonomy per [Testing And Validation](./docs/tests.md).
