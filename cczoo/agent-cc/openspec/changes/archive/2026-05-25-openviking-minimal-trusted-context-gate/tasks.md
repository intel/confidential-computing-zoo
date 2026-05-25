## 1. Evidence Surface Contract

- [x] 1.1 Add the OpenViking evidence endpoint contract with the required context-send claims and plaintext-free response rules.
- [x] 1.2 Add the separate OpenViking posture endpoint contract without treating posture as attested evidence.
- [x] 1.3 Define how evidence freshness is represented with `generated_at` and `expires_at` and document the five-minute trust window.

## 2. Local Verify Skill

- [x] 2.1 Implement the local OpenClaw verify-skill entrypoint for `send_context` decisions.
- [x] 2.2 Validate required evidence claims, identity binding, freshness, and policy compatibility before returning `allow`.
- [x] 2.3 Return fail-closed `deny` results when evidence fetch, verification, or policy evaluation fails.

## 3. Trust Cache and Decision Outcomes

- [x] 3.1 Implement a five-minute trust cache keyed by target URL, service instance, measurement, ledger head, and policy version.
- [x] 3.2 Require re-verification whenever the cache entry expires or any cache-key field changes.
- [x] 3.3 Enforce that `deny` blocks context transfer entirely and does not degrade into partial or fallback context sending.

## 4. Minimal Decision Recording

- [x] 4.1 Add metadata-only `context_send.allow` decision recording without storing prompt or context plaintext.
- [x] 4.2 Add metadata-only `context_send.deny` decision recording with denial reason and verification metadata only.

## 5. Verification and Documentation

- [x] 5.1 Add focused tests for allow, deny, expired evidence, and cache-expiry behavior.
- [x] 5.2 Add focused tests for missing required claims and cache-key mismatch behavior.
- [x] 5.3 Update the relevant OpenViking and cmem-control docs to reflect the implemented minimal trusted context gate behavior.