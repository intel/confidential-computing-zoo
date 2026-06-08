# Argus Testing And Validation

## Overview

This document defines how Argus v1 should be validated across canonicalization, evidence binding, verifier normalization, policy evaluation, governance inputs, and rollout safety.

Current validation scope targets the A2S path only. S2S-specific triggering, session models, and caller-shared state behavior are out of scope for the current draft.

Argus is a protocol-heavy system. Validation must prove more than code correctness:

- Different implementations must compute the same canonical bytes.
- Verifier adapters must normalize results into the same decision surface.
- Profiles, extensions, reference bundles, and runtime collectors must fail safely when they drift, expire, or disappear.

## Test Strategy

Argus validation should be layered:

| Layer | Goal | Typical Artifacts |
|------|------|-------------------|
| Unit tests | Validate local canonicalization, parsing, policy evaluation, and deny-reason mapping | Function tests, schema validation, parser tests |
| Conformance tests | Prove cross-implementation protocol equivalence | Golden vectors, expected canonical bytes, oracle verdicts |
| Integration tests | Prove end-to-end behavior with real verifier adapters and evidence fetch paths | Direct evidence endpoint tests, SPIRE or Trustee adapter tests |
| Security regression tests | Prevent replay, downgrade, ambiguity, or governance bypass regressions | Negative vectors, stale evidence tests, extension rejection tests |
| Rollout tests | Validate audit mode, dry-run mode, and production fail-closed transitions | Shadow-policy runs, disagreement telemetry, cache invalidation checks |

## Conformance And Golden Vectors

Argus v1 requires a shared conformance suite so independent implementations do not drift in subtle ways.

Minimum conformance artifacts:

1. Golden vectors for `canonical_request` and `canonical_binding_claims`.
2. Golden vectors for `report_data` calculation by binding algorithm version.
3. Profile-version mismatch vectors covering caller, provider, and verifier disagreement.
4. Continuity-predicate pass and fail vectors per deployment profile.
5. Freshness-window pass and fail vectors for startup-bound and request-bound claims.
6. Composite-verifier merge vectors for conflicting quote, issuance, and posture outcomes.

Negative vectors should also cover at least:

- JSON key order differences with the same semantic content
- `null` versus missing field cases
- Unicode normalization differences
- uppercase versus lowercase digest encodings
- SPIFFE URI alias or federation confusion
- image tag versus resolved manifest digest confusion
- clock skew and stale posture windows
- same `profile_version` string with different profile content digests
- proxy identity incorrectly treated as workload identity

Each conformance vector must include:

- canonical input artifact
- profile version and profile digest
- expected canonical bytes or canonical digest
- expected normalized claims or expected deny reason
- oracle verdict: `pass` or `fail`

Canonical byte storage rules:

- If raw canonical bytes are stored, they must be UTF-8 encoded canonical JSON without trailing newline.
- If digests are stored instead of raw bytes, the digest algorithm and exact byte-production procedure must be recorded alongside the vector.
- Unicode inputs must be normalized according to the active canonicalization profile before byte serialization.

## Builtin Predicate Validation

Builtin predicates are protocol-level semantics, not implementation hints. Each predicate version must define:

- required input facts
- supported platforms
- collection preconditions
- deterministic pass or fail behavior
- negative conformance vectors

### Minimum V1 Predicate Matrix

| Predicate | Required Facts | Platform Preconditions | Fail Condition |
|-----------|----------------|------------------------|----------------|
| `same_live_instance` | stable instance identifier, collection epoch, re-check epoch | profile defines instance continuity source and maximum drift window | cannot prove the same instance across the required observation window |
| `same_pid_starttime_namespace` | PID, process start time, PID namespace inode | shared PID visibility or equivalent trusted collector path | missing fact, namespace remap without trusted translation, or start time change |
| `same_socket_inode_cgroup` | socket inode, cgroup identity, listener process mapping | socket ownership inspection and cgroup mapping supported | socket cannot be joined to expected cgroup or join path is ambiguous |
| `same_workload_identity_path` | workload identity, endpoint identity, continuity predicate result | profile defines how endpoint and workload identities are joined | endpoint-to-workload join depends on an untrusted or missing intermediary |

### Platform Coverage Expectations

At minimum, implementations should test:

- Linux with cgroup v2
- Linux with cgroup v1 where still supported
- containerd-based Kubernetes
- CRI-O-based Kubernetes if supported by the deployment profile
- rootless container edge cases where relevant
- service mesh sidecar environments when `CompositePath` or endpoint binding depends on proxy join behavior

Unsupported platform conditions must fail closed for policy-required claims rather than silently degrading to weaker heuristics.

## Evidence And Verifier Validation

### Evidence Binding Tests

Required test categories:

1. Nonce-bound evidence matches expected `report_data`.
2. Binding claims included in evidence are exactly the fields covered by canonical binding claims.
3. Request-bound dynamic posture expires on time.
4. Startup-bound identity can be cached only within its allowed freshness window.
5. Quote-bound claims and verifier-normalized claims remain consistent when both are present.

### Verifier Normalization Tests

Verifier adapters should be tested for:

- quote validity mapping
- TCB status mapping
- measurement and reference-value mapping
- attested identity issuance mapping
- deny-reason precedence consistency
- missing-field behavior and fail-closed handling

Composite verifier tests must prove:

1. Quote validity and report-data binding remain mandatory gates.
2. Attested identity issuance cannot override failed quote-bound identity.
3. Freshness failures on policy-required posture still deny.
4. Effective assurance is the minimum of policy-required verification paths.

## Governance Validation

Argus v1 depends on three governance-sensitive inputs:

1. Profile governance.
2. Collector governance.
3. Reference-value governance.

### Profile Governance Tests

Required checks:

- `ProfileBody` and `ProfileEnvelope` digest behavior
- unknown extension handling for `reject-if-unknown` and `ignore-if-unknown`
- rollback detection
- signer mismatch handling
- profile digest mismatch between caller, provider, and verifier
- performance profile binding into the active profile digest

### Collector Governance Tests

Required checks:

- signer-to-runtime binding
- binding-scope mismatch detection
- replay rejection outside the allowed freshness window
- collector revocation behavior
- optional versus policy-required collector failure behavior

Collector-validated support must never replace quote-bound workload identity for workload-authoritative claims. Regression tests should explicitly prove that a collector path cannot silently become the effective root of trust.

### Reference-Value Governance Tests

Required checks:

- trusted publisher acceptance and rejection
- allowed bundle digest filtering
- bundle freshness handling
- rollback baseline enforcement
- ambiguity handling for multi-architecture artifacts
- build provenance mode reporting

If `multi_arch_resolution` depends on external provenance, test cases must verify both supported modes:

- bundle-asserted mapping
- independently verified provenance mapping

## Policy And Diagnostics Tests

### Policy Evaluation Tests

Policy tests should prove:

1. Fail closed when required fields are missing.
2. Fail closed when nonce binding is absent but required.
3. Fail closed when a policy-required claim is not evidence-bound.
4. Fail closed when `verified_claim_assurance` is missing for a policy-required claim.
5. Proxy identity is not mistaken for workload identity.
6. `CompositePath` policies are incomplete unless proxy and workload requirements are both explicit.

### Diagnostics And Deny Reason Tests

The top-level diagnostic taxonomy should remain stable across integrations.

Minimum diagnostic dimensions:

1. policy evaluation deny
2. profile governance failure
3. reference-value failure
4. collector governance failure
5. verifier adapter normalization failure

Test each deny dimension with both:

- machine-readable deny code assertions
- operator-facing explanation payloads

## Performance Profile Validation

Argus currently defines three performance profiles:

1. `strict-per-request`
2. `startup-bound-cacheable`
3. `identity-mode-periodic-quote`

Validation rules:

- performance profile must be present in the active profile
- performance profile must not override assurance floors
- startup-bound cache hits must not hide request-bound posture failures

### Identity Mode Periodic Quote

`identity-mode-periodic-quote` requires explicit validation of:

- maximum stale window
- revocation triggers
- runtime change-detection source
- behavior when runtime change cannot be detected before next scheduled quote or attested renewal

If the deployment cannot detect relevant runtime changes before the next periodic revalidation point, the profile must not treat periodic revalidation as sufficient for policy-required freshness.

## Rollout And MVP Validation

### Rollout Modes

Argus supports:

1. Enforce mode
2. Audit mode
3. Dry-run policy mode

Rollout tests must prove that audit and dry-run do not smuggle L0 or L1 claims into production authorization.

### Recommended V1 MVP Validation

The baseline MVP should validate one minimum closed loop:

1. Python prototype under `argus/`
2. SDK mode on the caller side
3. direct `/ra/v1/evidence` endpoint
4. Trustee or equivalent verifier
5. static signed profile
6. single governed reference bundle source
7. no service-mesh-authoritative joins
8. no verifier-trusted runtime collector required for policy-authoritative claims

This MVP is protocol-closed and implementation-closed first. It reaches production-suitable L2 only for profiles whose continuity and endpoint binding can be satisfied by quote-bound claims, reference-value validation, and approved local binding without a verifier-trusted collector.

### Suggested CI Gates

A reasonable initial CI policy is:

1. Schema validation for active profiles
2. Canonicalization golden vectors
3. Policy engine unit suite
4. Verifier adapter normalization suite
5. One end-to-end SDK-mode integration path
6. Negative governance regression suite for profile, collector, and reference-value drift

## Recommended Future Artifacts

To move from README-level specification to executable validation, the repository should eventually add:

- machine-readable profile schema files
- canonicalization golden vectors
- builtin predicate vectors
- deny-code taxonomy definitions
- sample governed reference bundles
- sample extension declarations

## Related Documents

- [Architecture](./architecture.md)
- [API Contract](./api.md)
