## Context

The current tc_api trusted-log pipeline uses Sigstore DSSE bundles as the internal contract between tc_api, TruCon, and the Rekor adapter. That internal choice has worked well for signing and queueing, but the current public replay story is weaker than the internal model because Rekor DSSE readback often exposes only hash-oriented body fields. As a result, verifier-critical predecessor facts such as `sequence_num`, `prev_event_digest`, and `prev_lookup_hash` are not always reconstructible from public Rekor material alone.

The repository already compensates for this with two mechanisms: a process-local cache in `SigstoreLogAdapter` and an OCI bundle mirror that preserves replayable payload material. This is enough for prototype verification, but it makes `public-only` verification weaker than the signed contract and keeps OCI mirror on the hot path even though public Rekor appears to support attestation storage for `intoto` uploads.

This change targets a prototype-stage architecture adjustment rather than a compatibility-only patch. The project can still keep the internal DSSE bundle flow while shifting the Rekor-facing entry type and replay-materialization priority toward `intoto` v0.0.2 plus Rekor attestation storage.

## Goals / Non-Goals

**Goals:**
- Make `intoto` v0.0.2 the primary Rekor upload type for replayable tc_api records while retaining the existing internal Sigstore bundle model.
- Use public Rekor attestation storage as the primary way to re-materialize verifier-critical payload fields during immutable replay.
- Preserve OCI bundle mirror as an explicit fallback and policy-driven compatibility path.
- Extend CLI output and verifier provenance so operators can distinguish `public-only`, `public+attestation-storage`, and `public+mirrored` outcomes.
- Add real Rekor integration coverage that proves `intoto` upload and replay can succeed without OCI mirror when attestation storage is available.

**Non-Goals:**
- Replacing internal DSSE signing with COSE or another signing format.
- Removing OCI mirror support in this change.
- Reworking TruCon queue storage away from bundle-oriented payload persistence.
- Changing TDX quote, attested-head evidence binding, or RTMR ordering semantics.

## Decisions

### 1. Preserve internal DSSE bundles and change only the Rekor-facing type

The system will continue to construct replayable predicates as DSSE statements and continue to persist `bundle_json` inside tc_api and TruCon. The change point is `SigstoreLogAdapter.submit_bundle()`: instead of always converting a bundle into a Rekor DSSE proposed entry, it will support a primary `intoto` v0.0.2 proposed-entry path.

Rationale:
- This keeps tc_api, TruCon, and the submit daemon aligned with the current bundle-centric implementation.
- It avoids broad changes to queue schema, baseline bootstrap, and internal transport contracts.
- It isolates the migration to the Rekor adapter and replay normalization path.

Alternatives considered:
- Replace DSSE signing with COSE end-to-end: rejected because it would force a much larger migration across signing, bundle parsing, queue persistence, and verification.
- Store only intoto envelopes in the queue: rejected because it would unnecessarily widen the change surface before proving the replay/materialization path.

### 2. Treat Rekor attestation storage as the primary replay-materialization source

Immutable replay will add a new materialization step between public body-only replay and OCI mirror fallback. For Rekor entries uploaded as `intoto`, the verifier will read the top-level `attestation` field, validate it against the body's recorded payload hash, and then normalize it into the same replayable payload facts currently recovered from DSSE payload material.

The materialization priority becomes:
1. Replayable facts already present in the public body.
2. Rekor attestation storage.
3. OCI mirror.
4. Process-local cache only as a debugging fallback that does not count as public proof.

Rationale:
- This is the only path that can reduce OCI dependence without changing the trust boundary to a completely different service.
- It preserves public-Rekor-centric verification when the public instance exposes attestation storage.

Alternatives considered:
- Continue preferring OCI mirror over attestation storage: rejected because it keeps an optional project-managed store in the default path even when public Rekor can provide the required payload material.
- Treat cache-assisted replay as equivalent to public proof: rejected because existing tests already define cache-assisted replay as not publicly auditable.

### 3. Add a distinct `attestation-storage` provenance class and CLI verification tier

Replay normalization and CLI reporting will introduce an explicit provenance source for payload material recovered from Rekor attestation storage. The JSON model and human-readable output will distinguish this from `public` and `mirror` provenance.

The target tier model becomes:
- `public-only`
- `public+attestation-storage`
- `public+mirrored`
- `public+mirrored+attested`

Rationale:
- Operators need to know whether historical continuity was proven from body fields, Rekor attestation storage, or an external mirror.
- This prevents `attestation-storage` runs from being misreported as either pure `public-only` or mirror-backed verification.

Alternatives considered:
- Collapse attestation storage into `public-only`: rejected because it hides a materialization dependency that matters during outages and policy evaluation.
- Collapse attestation storage into `public+mirrored`: rejected because it conflates Rekor-hosted retrieval with project-managed mirror materialization.

### 4. Keep OCI mirror as a supported fallback and explicit policy option

The OCI bundle mirror remains implemented and tested. Mirror-required policy continues to exist, but mirror becomes a fallback path instead of the default replay-materialization strategy.

Rationale:
- It preserves portability if public Rekor attestation storage is temporarily unavailable or insufficient.
- It gives operators a self-managed replay-materialization option while the public-Rekor assumptions are still being validated.

Alternatives considered:
- Remove OCI mirror immediately: rejected because attestation-storage behavior still needs real-Rekor validation and OCI remains the controlled fallback.

### 5. Drive rollout through tests before changing defaults globally

The migration is intentionally staged. First the verifier will support attestation-storage materialization, then the adapter will default to intoto uploads once the new real-Rekor tests prove the path. Old DSSE-type regression tests remain because they still document the current public replay limit.

Rationale:
- This avoids coupling a new upload type and a new replay-materialization path into one unverifiable step.
- It retains a clear regression signal if public Rekor behavior changes.

## Risks / Trade-offs

- [Public Rekor attestation behavior differs from repository assumptions] → Add real-Rekor smoke tests that clear local cache and verify predecessor continuity without OCI mirror before promoting the new path to default.
- [Signer identity extraction differs between DSSE and intoto retrieval shapes] → Extend normalization and signer extraction tests so `signer_identity` filtering is validated for both body-native and attestation-materialized entries.
- [OCI mirror fallback and attestation-storage success produce confusing operator output] → Introduce a first-class provenance state and verification tier instead of overloading existing `public-only` and `public+mirrored` labels.
- [Migration leaves mixed DSSE-type and intoto-type records in the same deployment window] → Preserve both adapter paths and keep replay classification explicit so mixed history remains diagnosable.

## Migration Plan

1. Extend `SigstoreLogAdapter.get_entry()` and replay normalization to consume Rekor top-level `attestation` and expose `attestation-storage` provenance.
2. Add unit tests and CLI tests that prove predecessor continuity from attestation-storage materialization.
3. Add real-Rekor `intoto` round-trip and multi-entry predecessor-proof smoke tests with cache cleared and no OCI mirror.
4. Add a configurable Rekor entry-type switch in the adapter, default it to `intoto` for the new path, and retain DSSE-type compatibility for rollback and regression tests.
5. Update architecture and trusted-log documentation to describe `intoto` + attestation storage as the primary design and OCI mirror as fallback.
6. If real-Rekor tests fail or public behavior changes, roll back by switching the adapter default back to DSSE-type upload while leaving the verifier's attestation-storage support in place.

## Open Questions

- Should the first default verification tier for successful attestation-storage runs be `public+attestation-storage`, or should attestation storage count as a subtype inside `public` in operator summaries while remaining explicit in diagnostics?
- Should baseline/Event Log 0 uploads switch to intoto at the same time as ordinary workload records, or should baseline stay DSSE-type for one rollout step while ordinary records validate the new path first?
- Should `--require-mirror` remain a strict operator flag even when attestation storage succeeds, or should a future policy flag express "require external self-managed materialization" more explicitly?