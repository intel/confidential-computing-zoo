# Argus Design Decisions & Rationale

This document records rationale for a few decisions that are easy to
get wrong by analogy with unrelated systems. It exists so that future
contributors do not have to re-derive these answers from source code.

## 1. TCB Status Checking: Is It Needed, And Where Does It Belong?

### The question

Intel's DCAP quote-generation library (`tdx_attest.c`, used inside the TD to
call `tdx_att_get_quote()`) does not perform any TCB status evaluation. See
[`tdx_attest.c` in `intel/SGXDataCenterAttestationPrimitives`](https://github.com/intel/SGXDataCenterAttestationPrimitives/blob/DCAP_1.23/QuoteGeneration/quote_wrapper/tdx_attest/tdx_attest.c):
it only calls `TDX_CMD_GET_REPORT0` / `TDX_CMD_GET_QUOTE` (or the vsock/configfs
equivalents) to obtain a TD report and hand it to the Quote Generation Service
for signing. There is no PCCS call, no PCK certificate handling, and no TCB
Info parsing anywhere in that file. This confirms that **TCB status is not a
property the quote-generation side computes or asserts** — a quote only
proves "this TD produced this report_data"; it does not self-report whether
the platform's TCB is up to date.

### Why Argus still needs a TCB status concept

TCB status is a **verifier-side** concept in the real DCAP flow:

1. The TD (via `tdx_attest.c`) produces a quote containing PCK certificate
   data and the platform's raw TCB component versions, but does not
   interpret them.
2. A verifier (Intel DCAP Quote Verification Library, Intel QVE/QVL, or a
   remote attestation service such as Trustee) fetches collateral from PCCS
   (PCK certificate chain, TCB Info, QE Identity, CRLs), matches the quote's
   TCB components against that collateral, and only then produces a TCB
   status such as `UpToDate`, `OutOfDate`, `ConfigurationNeeded`, or
   `Revoked`.
3. The relying party (Argus Guard, in our case) is expected to enforce policy
   over that verifier-produced status.

So the question "does quote generation check TCB" has answer **no**, but the
follow-up question "does something need to check TCB before trusting a peer"
still has answer **yes** — that job just belongs to the verifier/collateral
step, not to the TD or its attestation library.

### What `tdx_verify.c` actually is (and isn't)

It is tempting to assume the DCAP repo's `tdx_verify.c` is "the verifier" by
name alone, so it is worth being precise about what it contains. See
[`tdx_verify.c`](https://github.com/intel/SGXDataCenterAttestationPrimitives/blob/DCAP_1.23/QuoteGeneration/quote_wrapper/tdx_verify/tdx_verify.c)
and its header
[`tdx_verify.h`](https://github.com/intel/SGXDataCenterAttestationPrimitives/blob/DCAP_1.23/QuoteGeneration/quote_wrapper/tdx_verify/tdx_verify.h):

- The header declares exactly two functions: `tdx_att_get_collateral()` and
  `tdx_att_free_collateral()`. There is no `verify_quote`-style entry point in
  this file.
- `tdx_att_get_collateral()` sends a `GET_COLLATERAL` request (via the same
  vsock/configfs channel used for quote generation) to the Quote Generation
  Service and receives back a `tdx_ql_qve_collateral_t` bundle: PCK CRL +
  issuer chain, root CA CRL, TCB Info + issuer chain, and QE Identity +
  issuer chain. It does not parse, validate, or interpret any of that data —
  it only assembles and returns the raw collateral bytes.
- **This file is a collateral-fetching helper, not the verification
  algorithm.** The actual signature verification, PCK-cert-to-TCB-Info
  matching, and TCB status derivation happen in a separate component: the
  DCAP Quote Verification Library (commonly `libsgx_dcap_quoteverify`, invoked
  as `tdx_qv_verify_quote()` / `sgx_qv_verify_quote()`), which lives under
  `QuoteVerification/` in the same repository, not under `QuoteGeneration/`.
- That real verification path produces a much richer result type than
  Argus's current 4-value `TcbStatusType` — Intel's `sgx_ql_qv_result_t`
  (declared in `sgx_ql_lib_common.h`, referenced by `tdx_verify.h`) has values
  including `SGX_QL_QV_RESULT_OK`, `SGX_QL_QV_RESULT_CONFIG_NEEDED`,
  `SGX_QL_QV_RESULT_OUT_OF_DATE`,
  `SGX_QL_QV_RESULT_OUT_OF_DATE_CONFIG_NEEDED`,
  `SGX_QL_QV_RESULT_SW_HARDENING_NEEDED`,
  `SGX_QL_QV_RESULT_CONFIG_AND_SW_HARDENING_NEEDED`,
  `SGX_QL_QV_RESULT_INVALID_SIGNATURE`, `SGX_QL_QV_RESULT_REVOKED`, and
  `SGX_QL_QV_RESULT_UNSPECIFIED`.

### Mapping to the current Argus implementation

| Real DCAP component | What it does | Argus equivalent | Status |
|---|---|---|---|
| `tdx_attest.c` (`tdx_att_get_quote`) | TD-side: obtain TD report, get it signed into a quote | `argus-evidence-provider` calling the TSM/configfs quote path | Implemented |
| `tdx_verify.c` (`tdx_att_get_collateral`) | Fetch PCK CRL, TCB Info, QE Identity collateral bundle | *(none)* | **Out of scope by design** — see decision below; Argus does not fetch PCCS/QGS collateral |
| DCAP QVL (`tdx_qv_verify_quote`, in `QuoteVerification/`) | Verify quote signature against collateral, derive `sgx_ql_qv_result_t` | `TdxQuoteVerifier::check_tcb_status` | **Out of scope by design** — always reports `Unknown`, does not evaluate collateral |
| DCAP QVL signature check (data-integrity half) | Verify quote/report signed by the embedded key | `crypto_verifier.rs` (`SignatureVerifier`), now called from `verify_quote_signature` | **Implemented** — real ECDSA P-384 check; not yet validated against real hardware quote layout |
| DCAP QVL cert-chain checks | Validate PCK cert chain to Intel Root CA | `crypto_verifier.rs::verify_trust_anchor` | **Implemented, optional CA pinning** via `TdxQuoteVerifier::with_intel_ca_cert` |
| Policy enforcement on `sgx_ql_qv_result_t` | Relying-party decision over verifier result | `policy.rs` | **Not applicable** — Argus does not produce a real TCB verdict to police, by design |


### Decision: Argus v1 scope is "basic quote verification" only

After weighing the roadmap below against actually needing a full
collateral-aware verifier (PCCS calls, CRL handling, a richer TCB status
enum), we decided **not** to build that into Argus. Argus v1's scope is
intentionally limited to:

1. Quote structure validation.
2. Real ECDSA P-384 signature verification over the TD report, checked
   against the certificate embedded in the quote (and, if an Intel CA is
   configured, pinned to that CA) — via
   [`SignatureVerifier`](../src/crypto_verifier.rs), now wired into
   [`TdxQuoteVerifier::verify_quote_signature`](../src/tdx_verifier.rs).
3. Nonce binding verification for request freshness.

Collateral-backed TCB freshness checking (PCK CRL / TCB Info / QE Identity
matching, `sgx_ql_qv_result_t`) is explicitly **out of scope for Argus**, not
a gap to fill later. If a deployment needs that level of assurance, it should
sit in front of or alongside Argus as a separate, dedicated attestation
service (e.g. a hosted Trustee/Attestation Service) rather than be absorbed
into Argus's own codebase. This keeps Argus small, auditable, and focused on
what it can reliably verify itself.

### Current Argus implementation state (as of this writing)

- [`TdxQuoteVerifier::verify_quote_signature`](../src/tdx_verifier.rs) now
  calls [`SignatureVerifier::verify_signature`](../src/crypto_verifier.rs)
  (real ECDSA P-384 check) and `verify_trust_anchor` (certificate validity,
  plus CA pinning if `with_intel_ca_cert` was configured). **Known
  limitation:** the certificate/signature extraction logic uses fixed byte
  offsets and a simplified PEM-in-quote-bytes assumption that has not been
  validated against real hardware-generated TDX quotes' actual TLV-encoded
  `auth_data`/`cert_data` layout — validate and adjust before relying on this
  in production.
- [`TdxQuoteVerifier::check_tcb_status`](../src/tdx_verifier.rs) always
  reports `TcbStatusType::Unknown` rather than fabricating a freshness claim.
  This is intentional (see decision above), not a placeholder awaiting a
  future fix.
- [`policy.rs`](../src/policy.rs) does not read or gate on `tcb_status` in any
  decision path, which is consistent with TCB checking being out of scope.

Net effect: Guard's `TCB Status` output now honestly reads `Unknown` instead
of a fabricated `UpToDate`. Signature verification is real, but has not yet
been validated against genuine hardware-generated quotes.

### Roadmap

1. Validate `SignatureVerifier`'s certificate/signature extraction against a
   real hardware-generated TDX quote (not just synthetic test data), and fix
   the extraction logic if the real `auth_data`/`cert_data` TLV layout
   differs from the current fixed-offset assumption.
2. Optionally wire `with_intel_ca_cert` through Guard's configuration (env
   var or config file) so operators can pin verification to Intel's real
   root CA rather than trusting whatever certificate is embedded in the
   quote.
3. If a deployment later needs collateral-backed TCB freshness checking,
   integrate it as a separate service (hosted Trustee/Attestation Service,
   or Intel's DCAP QVL) in front of or alongside Argus — do not re-absorb
   that scope into Argus itself.

## 2. Is An Envoy/Nginx Sidecar Necessary?

`architecture.md` lists "pluggable infrastructure: direct evidence endpoints
and Envoy/Nginx routing" as a design goal. In practice:

- **Not necessary for the v1 baseline.** The recommended v1 path is a direct
  `POST /ra/v1/verify` (Guard) and `GET /ra/v1/evidence` (Provider) HTTP
  call. Both OpenClaw and OpenViking examples already work end-to-end this
  way without any proxy in front of Argus.
- **Useful, but as an optional deployment shape**, when:
  - the caller cannot be modified to add a Guard call before its normal
    request (mesh-style transparent enforcement), or
  - the deployment already runs Envoy/Nginx for other reasons (mTLS
    termination, routing) and centralizing evidence-fetch routing there
    avoids duplicating that logic per service.
- **Cost of adding it now:** an extra moving part, another config surface to
  keep in sync with Guard's policy semantics, and a risk of the proxy
  becoming an unattested trust decision point if it starts making allow/deny
  calls instead of just routing.

Conclusion: keep Envoy/Nginx integration as a documented optional deployment
profile, not a required component. Do not block the v1 protocol or examples
on it. Revisit only if/when a caller shape appears that genuinely cannot add
a direct Guard call.

## 3. Is The Five-Minute Trust Cache Necessary?

[`openviking-trusted-context-gate/spec.md`](../../../openspec/specs/openviking-trusted-context-gate/spec.md)
requires that a successful context-send verification result may be reused for
up to five minutes if the cache key (target URL, service instance,
measurement, ledger head, policy version) still matches.

Arguments for keeping it:

- Without caching, every context-send call pays a full evidence-fetch +
  quote-verify round trip, which is meaningfully more latency than a normal
  memory-service call. For interactive agent loops that call OpenViking
  frequently, this is a real cost.
- The cache key already includes the fields that would change if the trust
  decision should change (target, instance, measurement, ledger head, policy
  version), so a cache hit is not simply "assume nothing changed" — it is
  "nothing observable in the cache key changed."
- Five minutes bounds the worst case: a compromise that happens after a
  cached `allow` is issued can be trusted with stale data for at most that
  window, which is a deliberate, explicit trade rather than an unbounded one.

Arguments against / risks:

- Five minutes is long relative to `EVIDENCE_CACHE_TTL=300` already used
  elsewhere in Argus (see `configuration.md`) — the two TTLs should be kept
  conceptually aligned or explicitly justified if they diverge, otherwise a
  reader may assume one governs the other.
- A cache means a revoked/rotated policy or a freshly detected `OutOfDate`
  TCB will not be enforced immediately; it will lag until either the TTL
  expires or a cache-key field changes.
- Today, `check_tcb_status` always returns `UpToDate` (see Section 1), so the
  cache is not currently caching a meaningfully time-varying TCB signal —
  this makes the cache's real benefit latency-only until real TCB
  verification lands.

Conclusion: keep the cache, but treat it as a latency optimization with a
bounded staleness window, not as a security control. It should be
re-evaluated once real TCB/collateral verification (Section 1) is wired in,
since that is the point where "5 minutes stale" starts to have real security
consequences instead of only latency benefits.
