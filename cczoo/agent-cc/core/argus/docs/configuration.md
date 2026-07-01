# Argus Configuration Reference

This document provides a comprehensive reference for all configuration options available in Argus Evidence Provider and Guard Service.

## Table of Contents

- [Environment Variables](#environment-variables)
- [Configuration File](#configuration-file)
- [CLI Arguments](#cli-arguments)
- [Binding Assurance Levels](#binding-assurance-levels)
- [Verifier Configuration](#verifier-configuration)
- [Policy Configuration](#policy-configuration)
- [Logging Configuration](#logging-configuration)
- [Network Configuration](#network-configuration)
- [Security Configuration](#security-configuration)

---

## Environment Variables

### Evidence Provider Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Host address to bind the Evidence Provider HTTP server |
| `PORT` | `8008` | Port number for the Evidence Provider HTTP server |
| `RUST_LOG` | `info` | Logging level (trace, debug, info, warn, error) |
| `TC_API_URL` | `http://localhost:8080` | TC-API base URL, used for both service-metadata lookup **and** TDX quote generation (`/v1/attestation`). Set to the literal string `disabled` to skip TC-API entirely and use local runtime binding + TSM/mock quote generation only. |
| `TC_API_WORKLOAD_ID` | _(optional)_ | Workload ID used to query TC-API metadata directly (`query_by_workload_id`), checked before `ARGUS_SERVICE_ID`. If neither is set, metadata lookup falls back to `CONTAINER_ID`/`HOSTNAME`. |
| `ARGUS_WORKLOAD_IDENTITY` | _(required for stable identity)_ | Preferred stable workload identity bound into service evidence |
| `ARGUS_SERVICE_NAME` | _(compatibility alias)_ | Backward-compatible logical service name input |
| `ARGUS_SERVICE_ID` | _(optional)_ | Stable service identifier from deployment domain; also used as a fallback for `TC_API_WORKLOAD_ID` when querying TC-API metadata |
| `ARGUS_IMAGE_DIGEST` | _(optional)_ | Container image digest (sha256:...) |
| `ARGUS_EXECUTABLE_DIGEST` | _(optional)_ | Canonical executable digest |

### Guard Service Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Host address to bind the Guard HTTP server |
| `PORT` | `8007` | Port number for the Guard HTTP server |
| `RUST_LOG` | `info` | Logging level (trace, debug, info, warn, error) |
| `EVIDENCE_ENDPOINT` | `http://localhost:8008` | Peer Evidence Provider endpoint URL |
| `VERIFIER_KIND` | `trustee` | TDX verifier backend (trustee, mock) |
| `BINDING_ASSURANCE_LEVEL` | `L2` | Minimum binding assurance level required |
| `POLICY_STRICT_MODE` | `false` | Enable strict policy evaluation |
| `EVIDENCE_CACHE_TTL` | `300` | Evidence cache TTL in seconds (0 to disable) |

### Runtime Metadata (Auto-populated)

| Variable | Source | Description |
|----------|--------|-------------|
| `HOSTNAME` | Kubernetes/Docker | Pod or container hostname |
| `CONTAINER_ID` | Docker/Containerd | Container identifier |
| `POD_UID` | Kubernetes | Kubernetes pod UID |
| `NAMESPACE` | Kubernetes | Pod namespace |
| `VM_INSTANCE_ID` | Cloud environment | VM instance identifier |

`HOSTNAME` is no longer used as a fallback for `service_identity.service_name`.
To keep default Guard policy strict, inject a stable workload identity through
`ARGUS_WORKLOAD_IDENTITY`, `ARGUS_SERVICE_NAME`, `SERVICE_NAME`, or `K_SERVICE`.

See [Architecture § TC-API Integration](./architecture.md#tc-api-integration)
for the full request/response wire format for both the service-metadata query
and the TDX quote-generation call, the TC-API/TSM/mock quote fallback
priority, and known gaps (e.g. bearer-token auth support exists in
`TcApiClient` but is not wired to any env var in the shipped binary).

---

## Configuration File

Argus supports YAML configuration files for more complex deployments.

### Example Configuration File

```yaml
# filepath: /etc/argus/evidence-provider.yaml
evidence_provider:
  host: "0.0.0.0"
  port: 8008
  tc_api_url: "http://localhost:8080"
  
  # Service identity
  service_name: "my-service"
  service_id: "service-001"
  image_digest: "sha256:abc123..."
  
  # Logging
  log_level: "info"
  log_format: "json"  # or "text"

guard:
  host: "0.0.0.0"
  port: 8007
  evidence_endpoint: "http://localhost:8008"
  
  # Verifier configuration
  verifier:
    kind: "trustee"
    timeout: 30
    
  # Policy configuration
  policy:
    minimum_assurance_level: "L2"
    strict_mode: false
    composite_requirements:
      - claim_path: "service_identity.service_name"
        required_level: "L2"
      - claim_path: "service_identity.instance_id"
        required_level: "L2"

  # Evidence caching
  cache:
    enabled: true
    ttl: 300
```

### Configuration File Schema

```rust
// Configuration schema (pseudocode)
struct EvidenceProviderConfig {
    host: String,
    port: u16,
    tc_api_url: Option<String>,
    service_name: Option<String>,
    service_id: Option<String>,
    image_digest: Option<String>,
    executable_digest: Option<String>,
    log_level: LogLevel,
    log_format: LogFormat,
}

struct GuardConfig {
    host: String,
    port: u16,
    evidence_endpoint: String,
    verifier: VerifierConfig,
    policy: PolicyConfig,
    cache: CacheConfig,
}

struct VerifierConfig {
    kind: VerifierKind,  // trustee, mock
    timeout: u64,
    expected_verifier: Option<String>,
}

struct PolicyConfig {
    minimum_assurance_level: BindingAssuranceLevel,
    strict_mode: bool,
    composite_requirements: Vec<CompositeRequirement>,
}

struct CacheConfig {
    enabled: bool,
    ttl: u64,
}
```

---

## CLI Arguments

### Evidence Provider CLI

```bash
argus-evidence-provider [OPTIONS]
```

| Argument | Short | Description |
|----------|-------|-------------|
| `--version` | `-v` | Print version information and exit |
| `--short-version` | `-V` | Print short version and exit |
| `--help` | `-h` | Show help message |
| `--config` | `-c` | Path to configuration file |

### Guard CLI

```bash
argus-guard [OPTIONS]
```

| Argument | Short | Description |
|----------|-------|-------------|
| `--version` | `-v` | Print version information and exit |
| `--short-version` | `-V` | Print short version and exit |
| `--help` | `-h` | Show help message |
| `--config` | `-c` | Path to configuration file |

---

## Binding Assurance Levels

Argus defines four levels of binding assurance that indicate how claims are anchored:

| Level | Name | Description | Policy Use |
|-------|------|-------------|------------|
| `L0` | Local metadata | Local metadata collected but not corroborated | Diagnostics only |
| `L1` | Corroborated | At least two independent local observations agree | Audit and rollout only |
| `L2` | Quote-bound | L1 plus canonical binding claims in quote report data | **Minimum for production authorization** |
| `L3` | Attested identity | L2 plus attested identity issuance tied to attestation | Strongest identity mode |

### Configuration

```bash
# Set minimum binding assurance level
export BINDING_ASSURANCE_LEVEL=L2

# In YAML configuration
binding:
  minimum_assurance_level: L2
```

---

## Quote Verification Implementation

### Quote Validation

The default Argus verifier validates live TDX quotes using the checks that are
implemented in the normal request path today:

1. **Quote Structure Validation**: Validates the quote header (version, type, subtype) matches expected TDX format
2. **Request Binding Validation**: Confirms the returned `report_data` and nonce binding match the caller-expected digest
3. **Measurement Extraction**: Extracts RTMR values for downstream policy checks
4. **TCB Status Checking**: Surfaces platform status so callers can enforce stricter policy

This path intentionally does not claim that a freshly regenerated quote will be
byte-identical to a presented quote. Real TSM quotes are not stable enough for
that comparison to be a sound authenticity check.

### TDX Quote Format

| Field | Offset | Size | Description |
|-------|--------|------|-------------|
| Version | 0-1 | 2 bytes | Little-endian version (0x0004 for TDX 2.0) |
| Type | 2-3 | 2 bytes | Little-endian type (0x0002 for TD Quote) |
| Subtype | 4-5 | 2 bytes | Little-endian subtype (0x0081 for standard TD quote) |
| Reserved | 6-7 | 2 bytes | Reserved for future use |
| UUID | 8-15 | 8 bytes | Quote instance identifier |
| TD Report | 16-1039 | 1024 bytes | TD report body with measurements |
| Signature | 1040+ | Variable | Quote signature data |

### Nonce Binding Verification

The nonce binding ensures quote freshness and prevents replay attacks:

1. **Binding Digest Computation**: `SHA384(domain || canonical_request || binding_claims)`
2. **Report Data Embedding**: The binding digest is embedded in the TD report's report_data field
3. **Verification**: Compares the quote's report_data against the expected binding digest

### TCB Status Checking

TCB (Trusted Computing Base) status indicates the security state of the TDX environment:

| Status | Description |
|--------|-------------|
| `UpToDate` | TCB is current and meets security requirements |
| `OutOfDate` | TCB needs update - potential security vulnerability |
| `ConfigurationRequired` | TCB requires additional configuration |
| `Unknown` | Unable to determine TCB status |

**Current implementation status:** Argus intentionally does **not** evaluate
TCB freshness. `check_tcb_status()` in `tdx_verifier.rs` always reports
`Unknown` rather than fabricating a status — this is a deliberate scope
decision, not a placeholder awaiting a fix. Real TCB freshness checking
requires fetching PCCS/QGS collateral (PCK certificate chain, TCB Info, QE
Identity) and matching it against the quote, which is a materially heavier
verifier (Intel's DCAP Quote Verification Library, or a hosted
Trustee/Attestation Service) that Argus does not implement. No shipped
policy evaluator gates on this field. See [Design Decisions § TCB Status
Checking](./design-decisions.md#1-tcb-status-checking-is-it-needed-and-where-does-it-belong)
for the full rationale and scope decision.

### Trust Anchor Verification

`crypto_verifier.rs` implements ECDSA P-384 signature verification and
certificate validity checking for TDX attestation quotes (`SignatureVerifier`),
and it **is called** by `TdxQuoteVerifier::verify_quote_signature` — the
actual `RaVerifier` path used by Argus Guard. This is the real cryptographic
check Argus performs; certificate-chain pinning to a specific Intel CA is
optional and enabled via `TdxQuoteVerifier::with_intel_ca_cert`.

**Known limitation:** the certificate/signature extraction logic uses fixed
byte offsets and a simplified assumption that a PEM certificate is embedded
verbatim in the quote bytes. This has not yet been validated against a real
hardware-generated TDX quote's actual TLV-encoded `auth_data`/`cert_data`
layout. Validate against real quotes and adjust the extraction logic before
relying on this in production. See [Design Decisions § TCB Status
Checking](./design-decisions.md#1-tcb-status-checking-is-it-needed-and-where-does-it-belong)
for the full scope decision.

#### Certificate Chain Structure

| Level | Certificate | Description |
|-------|-------------|-------------|
| 1 | Quote Identity Certificate | Embedded in TDX quote, contains TD identity key |
| 2 | Attestation Key Certificate (AKC) | Signed by Intel CA, validates TD identity |
| 3 | Intel Root CA | Self-signed root of trust for Intel SGX/TDX |

#### Trust Anchor Validation

The verifier validates:

1. **Certificate Structure**: Validates X.509 certificate DER encoding
2. **Certificate Validity**: Checks not_before and not_after dates
3. **Issuer Validation**: Verifies issuer is Intel SGX or TDX trusted CA
4. **Subject Validation**: Confirms subject contains expected Intel TDX identifiers
5. **Extension Checking**: Looks for TDX-specific OID extensions

#### Signature Verification

ECDSA P-384 signature verification is performed using:

- **Signature Parsing**: Extracts r and s components from 64-byte signature
- **Public Key Parsing**: Parses SEC1-encoded public key from certificate SPKI
- **Prehash Verification**: Uses P384 ECDSA with SHA-384 prehash

#### Configuration

```yaml
# Trust anchor configuration
crypto_verifier:
  # Intel CA certificate in PEM format
  intel_ca_cert_path: "/etc/argus/intel_ca.pem"
  
  # Enable strict certificate chain validation
  strict_chain_validation: true
  
  # Require TDX-specific extensions
  require_tdx_extensions: false
```

### Certificate Chain Verification (AKC)

The Attestation Key Certificate chain verification includes:

| Check | Description |
|-------|-------------|
| Leaf Certificate | Quote identity certificate from quote |
| Intermediate CA | Intel Provisioning CA (if present) |
| Root CA | Intel Root CA (self-signed) |

#### Verification Steps

1. **Extract PEM Certificate**: Parse certificate from quote bytes
2. **Validate Certificate Structure**: Verify DER encoding and required fields
3. **Check Certificate Validity**: Ensure certificate is within validity period
4. **Verify Issuer Chain**: Confirm issuer matches expected Intel CA
5. **Verify Subject**: Validate subject contains Intel TD Quote identity
6. **Check TDX Extensions**: Look for Intel TDX-specific OID extensions

### RTMR Measurement Extraction

RTMR (Runtime Measurement Register) values are extracted from specific offsets in the TD report:

| Register | Offset | Size | Description |
|----------|--------|------|-------------|
| RTMR0 | 832 | 48 bytes | Runtime measurements (SHA-384) |
| RTMR1 | 880 | 48 bytes | Additional measurements |
| RTMR2 | 928 | 48 bytes | Additional measurements |
| RTMR3 | 976 | 48 bytes | Additional measurements |
  minimum_assurance_level: L2
```

---

## Verifier Configuration

### Supported Verifier Backends

| Verifier | Description | Status |
|----------|-------------|--------|
| `trustee` | Intel Trustee verifier for TDX quote validation | **Recommended** |
| `mock` | Mock verifier for testing only | Development only |

### Trustee Verifier Configuration

```bash
# Environment variables
export VERIFIER_KIND=trustee
export TRUSTEE_ENDPOINT=http://localhost:8080
```

```yaml
# YAML configuration
verifier:
  kind: "trustee"
  timeout: 30
  expected_verifier: "trustee-v1"
```

### Verifier Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `kind` | `VerifierKind` | `trustee` | Verifier backend type |
| `timeout` | `u64` | `30` | Verification timeout in seconds |
| `expected_verifier` | `Option<String>` | `None` | Expected verifier identifier |

---

## Policy Configuration

### Authorization Subject Policy

```yaml
policy:
  kind: "workload"  # workload, proxy, hybrid
  proxy_mode: "ignore"  # ignore, allow, require
  minimum_assurance_level: "L2"
  strict_mode: false
  composite_requirements:
    - claim_path: "service_identity.service_name"
      required_level: "L2"
    - claim_path: "service_identity.instance_id"
      required_level: "L2"
    - claim_path: "service_identity.image_digest"
      required_level: "L2"
```

### Composite Requirements

Each composite requirement specifies:

| Field | Type | Description |
|-------|------|-------------|
| `claim_path` | `String` | Dot-separated path to the claim (e.g., `service_identity.service_name`) |
| `required_level` | `BindingAssuranceLevel` | Minimum binding assurance level required |

### Supported Claim Paths

| Claim Path | Description | Minimum Level |
|------------|-------------|----------------|
| `service_identity.service_name` | Logical service name | L2 |
| `service_identity.service_id` | Stable service identifier | L2 |
| `service_identity.instance_id` | Runtime instance identifier | L2 |
| `service_identity.image_digest` | Container image digest | L2 |
| `service_identity.executable_digest` | Executable digest | L2 |
| `service_identity.spiffe_id` | SPIFFE identity | L3 |
| `runtime_binding.endpoint` | Target endpoint URI | L2 |
| `runtime_binding.owning_pid` | Process ID | L1 |
| `runtime_binding.container_id` | Container identifier | L1 |

---

## Logging Configuration

### Log Levels

| Level | Description | Use Case |
|-------|-------------|----------|
| `trace` | Detailed execution tracing | Debugging complex issues |
| `debug` | Debug information | Development and troubleshooting |
| `info` | Informational messages | **Default for production** |
| `warn` | Warning conditions | Degraded but functional |
| `error` | Error conditions | Failures requiring attention |

### Log Formats

| Format | Description | Configuration Value |
|--------|-------------|---------------------|
| `text` | Human-readable text format | `text` (default) |
| `json` | Structured JSON format | `json` |

### Environment Configuration

```bash
# Set log level
export RUST_LOG=info

# Set JSON log format
export RUST_LOG_FORMAT=json
```

### Structured Logging Fields

When using JSON log format, each log entry includes:

```json
{
  "timestamp": "2024-01-01T00:00:00.000Z",
  "level": "INFO",
  "target": "argus::engine",
  "message": "Evidence fetched successfully",
  "fields": {
    "endpoint": "http://localhost:8008",
    "tee_type": "tdx",
    "quote_valid": true
  }
}
```

---

## Network Configuration

### Service Binding

```bash
# Bind to specific address
export HOST=127.0.0.1

# Use specific port
export PORT=8008
```

### CORS Configuration

The Evidence Provider and Guard service use CORS with the following defaults:

| Setting | Value | Description |
|---------|-------|-------------|
| `allow_origins` | `Any` | Allow all origins |
| `allow_methods` | `GET, POST, OPTIONS` | Allowed HTTP methods |
| `allow_headers` | `Content-Type, Authorization` | Allowed headers |

### Timeouts

| Timeout | Default | Description |
|---------|---------|-------------|
| `connect_timeout` | `10s` | HTTP connection timeout |
| `request_timeout` | `30s` | Evidence request timeout |
| `verifier_timeout` | `30s` | Verifier operation timeout |

---

## Security Configuration

### Quote Validation

```yaml
# Quote validation configuration
verification:
  require_quote: true
  require_attested_identity: false
  expected_verifier: "trustee-v1"
  freshness_window: 300  # seconds
```

### Freshness Requirements

| Setting | Default | Description |
|---------|---------|-------------|
| `freshness_window` | `300` | Maximum age of evidence in seconds |
| `nonce_size` | `64` | Nonce size in bytes (512 bits for TDX) |

### TLS Configuration (Future)

| Setting | Default | Description |
|---------|---------|-------------|
| `tls_enabled` | `false` | Enable TLS for HTTP endpoints |
| `tls_cert_path` | _(none)_ | Path to TLS certificate |
| `tls_key_path` | _(none)_ | Path to TLS private key |

---

## Environment Variable Precedence

Configuration values are resolved in the following order (highest to lowest):

1. CLI arguments
2. Environment variables
3. Configuration file
4. Default values

Example:
```bash
# CLI argument takes precedence over environment variable
argus-evidence-provider --port 9000

# Environment variable takes precedence over config file
export PORT=9000
```

---

## Full Configuration Example

```yaml
# filepath: /etc/argus/production.yaml
evidence_provider:
  host: "0.0.0.0"
  port: 8008
  tc_api_url: "http://tc-api-service:8080"
  service_name: "production-service"
  service_id: "prod-001"
  image_digest: "sha256:productiondigest123"
  log_level: "info"
  log_format: "json"

guard:
  host: "0.0.0.0"
  port: 8007
  evidence_endpoint: "http://evidence-provider:8008"
  verifier:
    kind: "trustee"
    timeout: 30
  policy:
    kind: "workload"
    proxy_mode: "ignore"
    minimum_assurance_level: "L2"
    strict_mode: true
    composite_requirements:
      - claim_path: "service_identity.service_name"
        required_level: "L2"
      - claim_path: "service_identity.instance_id"
        required_level: "L2"
      - claim_path: "service_identity.image_digest"
        required_level: "L2"
  cache:
    enabled: true
    ttl: 300
  log_level: "info"
  log_format: "json"
```

---

## Troubleshooting Configuration Issues

### Common Configuration Problems

1. **Port already in use**
   ```bash
   # Check what's using the port
   lsof -i :8008
   netstat -tlnp | grep 8008
   ```

2. **Invalid binding assurance level**
   ```bash
   # Valid levels are: L0, L1, L2, L3
   export BINDING_ASSURANCE_LEVEL=L2
   ```

3. **Evidence endpoint unreachable**
   ```bash
   # Test connectivity
   curl -v http://localhost:8008/health
   
   # Check environment configuration
   echo $EVIDENCE_ENDPOINT
   ```

4. **Verifier timeout**
   ```bash
   # Increase verifier timeout
   export VERIFIER_TIMEOUT=60
   ```

### Validation Commands

```bash
# Validate environment setup
./start_argus.sh validate

# Check configuration
./target/release/argus-evidence-provider --help

# Test evidence endpoint
curl -X POST http://localhost:8008/ra/v1/evidence \
  -H "Content-Type: application/json" \
  -d '{
    "version": "v1",
    "nonce": "test-nonce",
    "caller_id": "test",
    "target": {
      "service_name": "test",
      "target_uri": "https://test.local"
    },
    "requested_claims": []
  }'
```