# Argus

Argus is an application-non-invasive runtime trust verification framework for agent-to-service (A2S) communication in confidential computing environments.

Its job is narrow: before a caller sends sensitive data to a peer service, Argus fetches evidence for that peer, verifies the evidence through an external attestation or identity system, and evaluates caller-local policy to decide whether the call should proceed.

Current document scope: Argus v1 is specified only for A2S. Service-to-service triggering, caching, and rollout semantics are intentionally left out of the current draft.

## Status

Argus is currently documented as a protocol and architecture draft in this repository.

- The main deliverable today is the specification and decomposition under `docs/`.
- The intended first implementation is a Python prototype under `argus/`.
- The long-term reusable core is expected to move into Rust once the protocol stabilizes.

## Documentation

- [Architecture](./docs/architecture.md): system model, trust boundaries, deployment modes, governance boundary, and v1 MVP.
- [API Contract](./docs/api.md): evidence request and response, verifier contract, profile model, policy model, and diagnostics surface.
- [Testing And Validation](./docs/tests.md): conformance vectors, predicate validation, governance regression tests, rollout strategy, and MVP validation.

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

If you are reading Argus for design or implementation work:

1. Start with [Architecture](./docs/architecture.md) to understand scope and deployment assumptions.
2. Read [API Contract](./docs/api.md) before implementing any endpoint, verifier adapter, profile loader, or policy engine.
3. Use [Testing And Validation](./docs/tests.md) as the acceptance bar for conformance vectors, deny reasons, and rollout behavior.

If you are building the first prototype, the current recommended stack is Python, FastAPI, Pydantic, pytest, and the existing TDX quote adapter logic already present elsewhere in this repository.

## Repository Layout

```text
argus/
├── README.md
└── docs/
    ├── architecture.md
    ├── api.md
    └── tests.md
```

## Next Steps

The most natural follow-on work is:

1. Create machine-readable schema artifacts for `ProfileBody`, `ProfileEnvelope`, and related contracts.
2. Add conformance vectors for canonicalization, builtin predicates, and deny-reason taxonomy.
3. Implement the Python MVP described in the architecture document.
