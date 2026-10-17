# Trustee integration for TruCon workload history

After Trustee verifies the TDX Quote and its `REPORTDATA` binding, the
Attestation Service hook verifies the recorded workload history. This happens
before Rego policy evaluation and signing the attestation result (EAR).
The hook adds only server-owned `trucon` claims. Rekor addresses, keys
and identity trust come from the server's configuration; evidence supplies
entry references, not a verification verdict.

## Build and install

This repository contains the hook and its verifier, rather than a vendored
Trustee tree. The patch targets
[Trustee v0.21.0](https://github.com/confidential-containers/trustee/tree/v0.21.0).
`apply.py` also checks the reviewed `attestation-service/src/lib.rs` SHA-256
and refuses a different or already patched base.

On a Linux build host with Python 3.11+ and Trustee's TDX/DCAP dependencies, from
`cczoo/agent-cc`:

```bash
git clone --branch v0.21.0 --depth 1 \
  https://github.com/confidential-containers/trustee.git /srv/trustee-trucon
bash core/spire/workload/trustee/build.sh /srv/trustee-trucon
sudo bash core/spire/workload/trustee/install-verifier.sh /opt/argus-trucon
sudo install -d -m 0700 /etc/argus-trucon
sudo install -m 0600 core/spire/workload/trustee/config.example.json \
  /etc/argus-trucon/config.json
```

Fill the configuration placeholders before starting the service. Deploy the
resulting `target/release/restful-as` with the existing TLS, DCAP, EAR-signing
and policy configuration, and set:

```ini
Environment=ARGUS_TRUCON_VERIFIER=/opt/argus-trucon/verify-trucon
Environment=ARGUS_TRUCON_CONFIG=/etc/argus-trucon/config.json
```

The verifier/configuration must be regular root-owned files without group or
other write permission. Their parent directories and the Python environment
must also remain administrator-controlled.

### Python verifier dependency

The verifier pins `sigstore==3.6.7`. The
[upstream release](https://github.com/sigstore/sigstore-python/releases/tag/v3.6.7)
backports the OIDC state-validation fix for CVE-2026-24408, also included in
4.2.0. Its [OAuth callback](https://github.com/sigstore/sigstore-python/blob/v3.6.7/sigstore/oidc.py#L332-L333)
rejects a returned state that differs from the session state. Review this
backport evidence alongside vulnerability-feed version ranges.

This pin also retains the reviewed 3.x APIs for the original Rekor
`intoto` entry and its authenticated signing time. Sigstore 4.x changes the
log-entry/trust models and verifier API, and its standard entry conversion
rejects `intoto`; changing only the requirement would break this path.
Any upgrade must preserve verification of the original leaf, checkpoint/SET,
Fulcio chain/SCT, signer identity, signed time and DSSE payload.

## Trust configuration

Use [config.example.json](config.example.json) to configure:

- A fixed HTTPS `rekor_url` and approved `rekor_public_key_path`.
- An approved `sigstore_trusted_root_path`, exact TC API OIDC `signer_identity`
  and `signer_issuer` for Fulcio/CT/signing-time verification.
- `allowed_baseline_rtmr`: approved pre-TruCon RTMR2 baselines, as 96 lowercase
  hexadecimal characters.
- Optional `https_proxy`: an administrator-configured HTTP CONNECT proxy.
  HTTPS certificate/hostname checks still apply. Without it the verifier
  does not inherit ambient proxy configuration.

The verifier validates UUID or numeric Rekor references, authenticated entry
identity, signatures, inclusion proof/checkpoint and chain-owner linkage. It
replays RTMR2 over the complete ordered chain and compares it with the RTMR2
authenticated by Trustee. History must contain exactly one successful measured
launch matching the observed workload, launch, container and image. No later
successful `stop`/`rm` may terminate that container's launch basis; a subsequent
`start` does not restore it. Permitted unrelated events may extend the history.
Missing history, changed bindings, invalid cryptography or unavailable trust
material reject admission. The hook permits at most four concurrent verifier
subprocesses and imposes a 50-second budget including the wait for a slot.

These checks authenticate the submitted chain against the current Quote.
Cross-run history continuity, storage rollback protection and global log-fork
prevention require additional mechanisms beyond this verifier.

Install the generated workload policy using the Trustee administrator's
policy-management channel. The default
[template](../policy/workload_cpu.rego.tmpl) requires approved TD measurements,
`UpToDate` TCB, workload bindings and the verified `trucon` result. See the
[deployment guide](../README.md) for policy IDs and SPIRE entries.
