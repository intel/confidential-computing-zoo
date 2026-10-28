# Workload attestation deployment

This directory attests one registered application process in a TDX guest
and provides an NGINX endpoint using that workload's SPIFFE identity.
Trustee verifies the TDX Quote and recorded workload history before SPIRE
Server issues the workload certificate (X.509-SVID). Helper delivers the
certificate to NGINX and monitors the registered process and configuration.
Normal requests use mTLS, client SPIFFE-ID authorization and the application's
own authorization. OpenViking is the supplied application example.
Read the [architecture](ARCHITECTURE.md),
[plugin configuration](../plugins/argus-tdx-workloadattestor/README.md) and
[Trustee integration](trustee/README.md) before deployment.

The deployment uses SPIRE **1.15.3**, Trustee **0.21.0** and the Helper build
provided here. It requires SPIRE's experimental Broker API and supports one
SPIRE Agent and one registered application process.

## Prerequisites and configuration

Use Linux x86_64 with real TDX/TSM Quote support, Docker, systemd, Python 3.11+,
NGINX with `http_auth_request_module`, `nsenter`, OpenSSL, `timeout`, `curl`
and SSH. Build dependencies include a patched Go toolchain: Go 1.26.9 or a
later 1.26 patch, or Go 1.27.2 or a later 1.27 patch. Rust 1.88+, pkg-config
and OpenSSL development files are also required. TC API, Docktap, TruCon and their existing trust
services must be configured on the guest.

The build checks and pins the effective Go toolchain for all local Go artifacts,
including the existing NodeAttestor. The language minimum in `go.mod` alone does
not ensure patched standard-library code. Other Go release lines require review
before the build accepts them.

Create a separate root-owned `0600` input based on
[environment.example.json](config/environment.example.json). All placeholders
must be replaced with approved values; unknown fields are rejected. Use this
configuration with the Provider, plugins, Helper and Trustee integration
built from this source tree.

| Configuration | Required content |
|---|---|
| `identity` | Trust domain and distinct Agent, Helper, target and authorized client SPIFFE IDs; configure either `client_id` or `allowed_client_ids` |
| `paths` | Dedicated installation, configuration, record and SPIRE binary directories; `run_name` derives protected runtime paths |
| `workload` | Host/container configuration and data paths, ports, `config_env`, `environment` and `config_json_checks` |
| `approved` | Policy ID, actual image config ID (`sha256:`), exact configuration SHA-256, executable, `mr_td`, `rtmr_0/1` and pre-TruCon `rtmr2_baseline` |
| Node/Trustee inputs | Approved Node Agent HCL, proof-key/bootstrap trust, Trustee HTTPS CA/name, fixed EAR P-256 public key, issuer and profile |
| Server/TC API inputs | Existing Server unit/socket, optional validated SSH alias, TC API origin/user and approved registry image |
| Client inputs | Operator-supplied SVID, key, bundle, an HTTPS business URL, and optional `business_headers` mapping HTTP header names to environment variable names |

An image config ID is Docker image inspect `.Id` / container inspect `.Image`.
It is distinct from a registry manifest digest. Measurements and digests are
operator-approved inputs; registration does not approve whatever it observes.
See the [OpenViking adapter](../../../adapters/OpenViking/README.md) for image
and application configuration.

Application conventions are explicit deployment inputs:

| Field | Meaning |
|---|---|
| `workload.config_env` | Environment variable naming the configuration path; `environment[config_env]` must equal `config_path` |
| `workload.environment` | Container environment strings; the example selects OpenViking's configuration and disables its bot component |
| `workload.config_json_checks` | JSON Pointer equality checks, each with either a scalar `value` or a `workload_field` reference |
| `business_headers` | Probe headers supplied only from named client-side environment variables; `{}` or omission sends no business credentials |

For example, `{"pointer":"/server/port","workload_field":"listen_port"}`
compares an application field with the declared listener port. JSON Pointer
uses `~0` for `~` and `~1` for `/`; comparisons require the same value and type.
An empty check list permits a non-JSON configuration. Its exact bytes remain
subject to configuration digest checks. Supported `workload_field` references
are `id`, `config_path`, `data_path`, `listen_port`, `tls_port` and `published_port`.
This declaration describes the application's expected startup interface; it
does not prove that application code consumes or continues using that file.

The current isolation model requires an environment-selected configuration
file and one loopback listener, a read-only rootfs/configuration, and one
separate writable data mount. Applications must fit these constraints.
Changing settings alone does not establish compatibility with every service.

## Build and install

From this directory on the Linux build host:

```bash
bash scripts/build.sh
sudo bash scripts/install.sh --config /root/workload-environment.json
```

`build.sh` compiles the project runtime, downloads checksum-pinned official
SPIRE binaries and writes `build-manifest.json` and `SHA256SUMS`. The
[artifact list](scripts/build-artifacts.sh) contains 11 executables. Installation
checks the complete artifact list, binaries, installed source inputs and build
inputs. `ARGUS_WORKLOAD_BUILD_DIR` can select a different build directory.

Install the same payload and consistent identity/baseline configuration on
the guest and SPIRE Server host. Server-side entry checks require the same
Helper path and binary hash. Installation writes configuration and systemd
units but does not start services. Stop the existing authentication stack
before installing or rendering changed configuration.

The remaining commands use the example installation paths. Adjust them if
`paths` differs. The existing Node configuration remains the source for Agent
bootstrap and NodeAttestor settings.

## Trustee policy and SPIRE entries

Deploy the [Trustee hook and verifier](trustee/README.md), including approved
Rekor/Sigstore trust and RTMR2 baselines. On the guest, render configuration:

```bash
sudo python3 /opt/argus-workload/scripts/workload.py render \
  --config /etc/argus-workload/environment.json
```

Review the generated `<policy_id>_cpu.rego` and install it through the Trustee
administrator's policy-management channel. Trustee v0.21.0 `POST /policy`
accepts `policy_id` and unpadded base64url `policy`. Store the CPU policy as
`<policy_id>_cpu`; appraisal requests use `<policy_id>`. Preflight reads back
the policy bytes and compares them with the approved local policy.

The default template requires `UpToDate` TCB. An explicitly reviewed custom
policy can be supplied through `approved_policy_artifact.path` and its exact
`sha256`; the same byte comparison applies. Runtime EAR verification checks
the policy ID, so administration of policy contents remains trusted.

On the configured SPIRE Server host, with its Server and Node plugin running:

```bash
sudo python3 /opt/argus-workload/scripts/workload.py apply-entries \
  --config /etc/argus-workload/environment.json
sudo python3 /opt/argus-workload/scripts/workload.py server-check \
  --config /etc/argus-workload/environment.json
```

The Helper entry requires root UID, executable path and SHA-256. The target
entry requires all six verified TDX selectors and disables X.509-SVID prefetch.
Broader entries for either identity cause rejection and must be reviewed by
the Server administrator. The tool does not delete existing entries.

## TC API launch and registration

Installation exports `/etc/argus-workload/tc-api-workload.json`, containing
the workload launch settings. Set TC API's
`ARGUS_WORKLOAD_CONFIG` to that protected file. For containerized TC API,
mount it read-only, and make `config_host_path` and `data_host_path` visible
at the same paths used by the Docker host. The workload config's
`docker_host_proc_path`, `docker_host_pid_path`, and
`docker_host_sysfs_dev_block_path` must point to read-only views of the Docker
daemon host's `/proc`, its Docker PID file, and `/sys/dev/block`, respectively.
TC API reads the daemon PID, requires its process name to be `dockerd`, and
uses that process's mount table. Do not point these settings at TC API's private
container namespace. The OpenViking Compose example mounts these host resources.
For a host-native TC API, configure the corresponding host paths.

The exported workload configuration pins `data_encryption` to
`luks-dm-crypt` and `data_luks_uuid` to the expected LUKS UUID. Immediately
before launching the container, TC API checks that the configured data path
is a real directory, has no nested mounts, resolves to a visible device-mapper
LUKS mapping in the Docker daemon process's mount table, and matches that exact
UUID. The TC API process's `stat` device ID must match the daemon mount table.
Ordinary filesystems, other LUKS volumes, unavailable host metadata and
mismatched mount devices are rejected. Every ancestor in the Docker daemon's
resolved data path must be root-owned or owned by the TC API process and not
group/other-writable; root-owned sticky directories are accepted only when the
next path component is trusted-owned. This prevents an untrusted local user
from replacing a path component between validation and container creation.
The final data directory may be owned by the application UID, but must not be
group/other-writable.

The application must listen on `127.0.0.1:<listen_port>`. The OpenViking
example declares `/server/host`, `/server/port` and `/storage/workspace`
checks in `config_json_checks`; TC API evaluates those declarations without
recognizing OpenViking fields. Application environment values pass through
a temporary owner-only Docker env file, removed after `docker run`, rather
than appearing in command arguments or launch records.
Configuration is a read-only bind mount outside the writable data directory.
The `nginx-spiffe` profile uses read-only
rootfs, a private bridge network namespace, no capabilities, separate data
storage and limited `/tmp`. Only `published_port:tls_port` is published;
the application port, TDX devices and management sockets are not published or
mounted into the business container.

Provide `TC_API_BEARER_TOKEN` and the existing signing-identity inputs
required by TC API. Then launch and register the actual listener:

```bash
sudo --preserve-env=TC_API_BEARER_TOKEN,TC_API_IDENTITY_TOKEN \
  python3 /opt/argus-workload/scripts/workload.py launch \
  --config /etc/argus-workload/environment.json
sudo python3 /opt/argus-workload/scripts/workload.py register \
  --config /etc/argus-workload/environment.json
```

If launch polling or signing is interrupted, use `resume-launch` with the
same configuration and saved launch ID. If submission returned no ID,
reconcile TC API state and pass its known ID through `--launch-id`.
Recovery queries or finishes the existing operation; it does not create a
replacement container or replay a Docker mutation with an unknown result.
The default TruCon SQLite database is under `/dev/shm`: saved-state recovery
covers process restarts within the same guest boot when RTMR extension and
database commit completed. It does not preserve state across guest reboot.
Never clear TruCon state to bypass pending history.

## Start, inspect and stop

```bash
sudo python3 /opt/argus-workload/scripts/workload.py preflight \
  --config /etc/argus-workload/environment.json
sudo python3 /opt/argus-workload/scripts/workload.py start \
  --config /etc/argus-workload/environment.json
sudo python3 /opt/argus-workload/scripts/workload.py verify \
  --config /etc/argus-workload/environment.json
sudo python3 /opt/argus-workload/scripts/workload.py status \
  --config /etc/argus-workload/environment.json
```

Preflight checks configuration, binaries, entries, policy and target readiness.
`start` begins the authentication stack and waits for current target
credentials to be loaded by NGINX. `verify` checks the live instance, target
SVID, an authorized client service request and correlated appraisal logs.
The example's `business_headers` explicitly maps `X-API-Key` to
`OPENVIKING_API_KEY`; preserve that variable with
`sudo --preserve-env=OPENVIKING_API_KEY` when running `verify`. A service
using bearer authorization can instead map `Authorization` to a variable
containing its complete header value, including `Bearer `. A configured
variable that is missing, empty or invalid fails verification; there are
no implicit application-specific credentials.
Verification correlates structured JSON events with the current boot, Helper
invocation, registered instance and SVID serial. The Agent overlay selects
JSON INFO logs to its standard output/error stream for journald; the Helper
emits compatible structured events. Human-readable log phrases are not parsed.
The result is a local operational check, not independent Quote/EAR verification.
Operational records are written under `paths.records_dir`; `manifest`
reports current build/configuration/instance correlation.

When client credentials remain on a separate client host, use
`--client-mode remote` with `preflight` and `start`. That mode still checks
the target and server configuration. Run `spiffe-mtls-probe` on the client
host with its own `-cert`, `-key`, `-bundle`, `-url` and exact `-server-id`.
Pass each business header explicitly, for example
`-header-env X-API-Key=OPENVIKING_API_KEY`. Header values remain in the client's
environment, outside command arguments and probe output. The `-tls-only`
readiness check does not read or send business credentials.
Provisioning a client's SVID and application integration is outside this
server-side runtime.

Stop the authentication stack before replacing the registered instance:

```bash
sudo python3 /opt/argus-workload/scripts/workload.py stop \
  --config /etc/argus-workload/environment.json
```

This stops the identity/TLS stack and removes registration. Manage the
business container through the existing TC API/Docktap path, then launch
and register its replacement. A new PID instance requires a new registration
and admission. Certificate renewal on the same valid Broker subscription
reuses workload admission without a new Quote; a new subscription collects
fresh evidence even when the target is unchanged.

The shipped [NodeAttestor Server plugin](../plugins/argus-tdx-nodeattestor/internal/server/plugin.go)
advertises `CanReattest=true`, allowing SPIRE to request node reattestation.
That capability flag is not a periodic workload-attestation schedule and
does not change the Broker subscription behavior above.
