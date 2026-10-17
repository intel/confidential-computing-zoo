# SPIFFE Helper with Argus Broker support

This directory extends the official SPIFFE Helper runtime with Argus Broker
support. See [UPSTREAM.md](UPSTREAM.md) for its source release, local changes and the
retained [Apache-2.0 license](LICENSE).

The optional `broker {}` block selects the Argus workload path. Helper obtains
its own infrastructure SVID from the Workload API, authenticates the approved
Agent over the Broker UDS, and subscribes using the registered target PID.
It validates the returned target identity and publishes complete certificate,
key and bundle generations for guest-managed NGINX. The Helper SVID identifies
the delivery component; the target SVID authenticates the managed service
endpoint. The business process receives neither of their private keys.

Broker mode requires Linux, daemon operation, a protected root-owned tmpfs
credential directory and the supplied systemd/NGINX lifecycle. It supervises
the registered instance, configuration, listener and credential validity;
observed binding or supervision failure withdraws readiness, cleans up
credentials and initiates ingress shutdown. A protected `ready` file and
service state report readiness. The ordinary upstream
Workload API path remains available when no Broker block is configured.

The included companion commands are:

| Command | Purpose |
|---|---|
| `argus-agent-config` | Merge the approved Node configuration with the WorkloadAttestor and Broker overlay |
| `spiffe-authz` | Authorize the exact configured client SPIFFE IDs from NGINX's verified client certificate |
| `spiffe-mtls-probe` | Check a service request using operator-supplied client credentials and an exact target SPIFFE ID |

The probe sends business credentials only through explicit, repeatable
`-header-env HEADER=ENV_VAR` bindings. For example, use
`-header-env Authorization=SERVICE_TOKEN` when that variable contains the
complete authorization value. Missing or invalid configured values fail the
probe; unrelated environment variables are ignored. Credential values are
excluded from command arguments and output. `-tls-only` does not read them.

Broker lifecycle and successful workload attestation use structured JSON events.
The generated Agent configuration enables INFO JSON output to journald so
verification can correlate fields rather than human-readable log wording.

Use the [deployment guide](../../workload/README.md), generated
[Helper configuration](../../workload/config/helper.conf) and
[architecture](../../workload/ARCHITECTURE.md) for installation and lifecycle.
