# Argus TDX WorkloadAttestor

This external SPIRE Agent plugin returns verified selectors for one registered
workload instance when the Broker requests an X.509-SVID through `AttestReference`.
The supported reference is `type.googleapis.com/spiffe.broker.WorkloadPIDReference`.
Ordinary Workload API `Attest` calls return no TDX selectors.

The plugin checks the approved target and live PID instance, requests fresh
nonce-bound evidence from the local Provider, asks Trustee to appraise the
Quote and authenticated history, verifies Trustee's signed attestation result
(EAR), and rechecks the instance before returning selectors. Trustee must run the
[TruCon history integration](../../workload/trustee/README.md).

## Configuration

Use [workload.py](../../workload/scripts/workload.py) to generate the Agent HCL
from the [deployment configuration](../../workload/config/environment.example.json).
The `WorkloadAttestor "argus_tdx"` block accepts:

| Input | Contract |
|---|---|
| `evidence_endpoint` | `unix:///absolute/socket`; the client uses `POST /ra/v1/workload-evidence` |
| `target_registration_path` | Absolute path to the protected registration for this PID instance |
| `agent_id`, `workload_id`, `policy_id` | Approved identities and Trustee policy; must match the registration |
| `image_config_digest`, `config_digest` | Approved `sha256:` content digests; image config ID is distinct from a registry manifest digest |
| `config_env` | Approved environment variable naming the configuration path; must match registration and the actual process |
| `trustee_endpoint`, `trustee_ca_path`, `trustee_server_name` | HTTPS origin and fixed TLS trust |
| `ear_public_key_path`, `ear_expected_issuer`, `ear_expected_profile` | Fixed P-256 public key and expected EAR claims |
| `request_timeout` | Defaults to `55s`; must be greater than 50 seconds and at most 60 seconds |
| `max_response_bytes` | Defaults to 2 MiB; positive and at most 4 MiB |

Unknown fields, missing trust, mismatched target bindings, invalid evidence
or failed appraisal prevent the plugin from returning verified selectors.

## Registration selectors

After successful appraisal, SPIRE prefixes these selector values with the
plugin type `argus_tdx`:

```text
verified:true
workload_id:<approved-workload-id>
policy:<approved-policy-id>
image_config_digest:sha256:<approved-image-config-digest>
config_digest:sha256:<approved-config-digest>
agent_id:<approved-agent-spiffe-id>
```

The target registration entry must require all six selectors and use the
approved Agent ID as its parent. The deployment tool creates this entry with
X.509-SVID prefetch disabled and rejects broader entries for the same target.
SPIRE Server's CA issues the SVID after entry matching.

These checks apply at instance admission. Normal SVID updates on the same
valid Broker subscription reuse that admission without another workload Quote.
A new subscription requires fresh evidence and history appraisal. See the
[architecture](../../workload/ARCHITECTURE.md) and
[deployment guide](../../workload/README.md) for runtime lifecycle handling.
