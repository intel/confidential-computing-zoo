## Why

The attested-head evidence contract is now frozen, but remote verification still has no way to obtain that evidence from a running CVM. Without a strict export surface, `tc-verify` remains coupled to live TruCon APIs and the external verification architecture described in the docs is still incomplete.

## What Changes

- Add a read-only TruCon HTTP surface that exports attested-head evidence for a chain.
- Restrict v1 export to the latest confirmed public head only; chains without a confirmed immutable-log head SHALL fail export rather than returning degraded evidence.
- Have TruCon fetch quote material directly from the TDX configfs TSM interface and assemble the evidence package using the existing v1 contract.
- Define how TruCon computes `report_data_binding.expected_value` from canonical serialization of the bound fields before comparing it to quote-backed report data.
- Document strict export behavior, failure cases, and the relationship between exported evidence, Rekor replay, and Event Log 0.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `attested-head-evidence`: Extend the capability from a static contract to a concrete TruCon export surface with strict latest-confirmed-head semantics and quote-backed evidence assembly.

## Impact

- Affected code: `src/tc_api/trucon/` HTTP handlers, quote acquisition path, chain-state lookup, and shared evidence assembly utilities.
- Affected systems: TruCon read-only operator surfaces, remote verification handoff, and later `tc-verify` evidence-consumption work.
- Affected docs: trusted-log verification and architecture docs describing exported evidence behavior and failure semantics.