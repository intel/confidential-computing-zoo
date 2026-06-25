//! Core data types for Argus v1
//!
//! Implements the API contract from architecture documentation.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha384};
use std::collections::BTreeMap;

/// Binding domain separator for evidence v1
pub const BINDING_DOMAIN: &[u8] = b"argus-evidence-v1\x00";

/// Binding algorithm identifier
pub const BINDING_ALGORITHM: &str = "argus-evidence-v1-sha384";

// =============================================================================
// Phase 1: Caller Orchestration And Request Construction
// =============================================================================

/// Decision result from Argus Guard.
#[derive(Debug, Clone)]
pub enum GuardDecision {
    /// Allow decision with verified claims
    Allow(VerifiedClaims),
    /// Deny decision with optional reason and claims
    Deny {
        reason: DenyReason,
        claims: Option<VerifiedClaims>,
    },
}

/// Reasons for deny decisions.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DenyReason {
    QuoteInvalid,
    BindingMismatch,
    MeasurementFailure,
    TcbFailure,
    IdentityConflict,
    MissingRequiredClaim,
    PolicyRejected,
}

/// Claim types that can be requested from peer.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RequestedClaim {
    TeeQuote,
    IdentityClaims,
}

/// Caller-controlled verification requirements.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VerificationOptions {
    #[serde(default)]
    pub require_quote: bool,
    #[serde(default)]
    pub require_attested_identity: bool,
    pub expected_verifier: Option<String>,
}

impl Default for VerificationOptions {
    fn default() -> Self {
        Self {
            require_quote: true,
            require_attested_identity: false,
            expected_verifier: None,
        }
    }
}

/// Caller-side inputs that influence request construction and policy evaluation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GuardContext {
    pub caller_id: String,
    #[serde(default)]
    pub requested_claims: Vec<RequestedClaim>,
    #[serde(default)]
    pub verification_options: VerificationOptions,
}

impl GuardContext {
    pub fn new(caller_id: impl Into<String>, requested_claims: Vec<RequestedClaim>) -> Self {
        Self {
            caller_id: caller_id.into(),
            requested_claims,
            verification_options: VerificationOptions::default(),
        }
    }
}

/// Local target descriptor known before any remote evidence is fetched.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TargetService {
    pub service_name: String,
    pub target_uri: String,
}

impl TargetService {
    pub fn new(service_name: impl Into<String>, target_uri: impl Into<String>) -> Self {
        Self {
            service_name: service_name.into(),
            target_uri: target_uri.into(),
        }
    }
}

/// Protocol request sent by agent-side Guard to peer Evidence Provider.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvidenceRequest {
    #[serde(default = "default_version")]
    pub version: String,
    pub nonce: String,
    pub caller_id: String,
    pub target: Option<TargetService>,
    #[serde(default)]
    pub requested_claims: Vec<RequestedClaim>,
    pub profile_digest: Option<String>,
}

fn default_version() -> String {
    "v1".to_string()
}

impl EvidenceRequest {
    /// Serialize to canonical JSON bytes for binding.
    pub fn to_canonical_bytes(&self) -> Vec<u8> {
        let json = serde_json::to_string(self).expect("EvidenceRequest must serialize");
        json.into_bytes()
    }
}

// =============================================================================
// Phase 3: Service-Side Evidence Generation
// =============================================================================

/// Raw service credentials from local runtime binding layer.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ServiceCredentials {
    pub spiffe_id: Option<String>,
    pub certificate_chain_pem: Option<Vec<String>>,
    pub token: Option<String>,
}

/// Local runtime facts binding caller target to workload instance.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RuntimeBindingContext {
    #[serde(default)]
    pub endpoint: String,
    #[serde(default)]
    pub owning_pid: u32,
    #[serde(default)]
    pub process_start_time: String,
    pub container_id: Option<String>,
    pub pod_uid: Option<String>,
    pub vm_instance_id: Option<String>,
    pub namespace: Option<String>,
    pub cgroup_path: Option<String>,
}

/// Binding assurance level indicating how binding claims are anchored.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum BindingAssuranceLevel {
    L0,
    L1,
    L2,
    L3,
}

impl Default for BindingAssuranceLevel {
    fn default() -> Self {
        BindingAssuranceLevel::L0
    }
}

/// Stable service identity and live-instance facts in binding claims.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct BindingIdentityClaims {
    #[serde(default)]
    pub service_name: String,
    pub service_id: Option<String>,
    #[serde(default)]
    pub instance_id: String,
    #[serde(default = "default_instance_scope")]
    pub instance_scope: String,
    pub image_digest: Option<String>,
    pub executable_digest: Option<String>,
    pub spiffe_id: Option<String>,
}

fn default_instance_scope() -> String {
    "process".to_string()
}

/// Service-originated claims that may participate in policy after verification.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct BindingClaims {
    #[serde(default)]
    pub assurance_level: BindingAssuranceLevel,
    #[serde(default)]
    pub service_identity: BindingIdentityClaims,
    #[serde(default)]
    pub runtime_binding: RuntimeBindingContext,
    #[serde(default)]
    pub claim_support: BTreeMap<String, Vec<String>>,
    pub verifier_validated_support: Option<BTreeMap<String, Vec<String>>>,
    #[serde(default)]
    pub provider_claim_assurance: BTreeMap<String, BindingAssuranceLevel>,
}

impl BindingClaims {
    /// Serialize to canonical JSON bytes for binding.
    pub fn to_canonical_bytes(&self) -> Vec<u8> {
        let json = serde_json::to_string(self).expect("BindingClaims must serialize");
        json.into_bytes()
    }
}

/// Metadata describing how request nonce and target context were bound.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NonceBinding {
    #[serde(default = "default_binding_algorithm")]
    pub algorithm: String,
    #[serde(default = "default_binding_domain")]
    pub domain: String,
    pub canonical_request_digest: String,
    #[serde(default)]
    pub bound_fields: Vec<String>,
}

fn default_binding_algorithm() -> String {
    BINDING_ALGORITHM.to_string()
}

fn default_binding_domain() -> String {
    // Domain separator with null byte
    String::from_utf8_lossy(BINDING_DOMAIN).to_string()
}

impl Default for NonceBinding {
    fn default() -> Self {
        Self {
            algorithm: BINDING_ALGORITHM.to_string(),
            domain: "argus-evidence-v1\x00".to_string(),
            canonical_request_digest: String::new(),
            bound_fields: vec![
                "nonce".to_string(),
                "caller_id".to_string(),
                "target".to_string(),
                "requested_claims".to_string(),
                "profile_digest".to_string(),
            ],
        }
    }
}

/// Service-produced response envelope returned to caller.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Evidence {
    #[serde(default = "default_version")]
    pub version: String,
    #[serde(default = "default_evidence_type")]
    pub evidence_type: String,
    #[serde(default = "default_tee_type")]
    pub tee_type: String,
    /// Base64-encoded Intel TDX quote
    pub quote: String,
    pub binding_claims: Option<BindingClaims>,
    #[serde(default = "default_quote_format")]
    pub quote_format: String,
    /// Hex-encoded SHA-384 digest
    pub report_data: String,
    #[serde(default)]
    pub nonce_binding: NonceBinding,
    #[serde(default = "default_generated_at")]
    pub generated_at: String,
}

fn default_evidence_type() -> String {
    "tee_quote".to_string()
}

fn default_tee_type() -> String {
    "tdx".to_string()
}

fn default_quote_format() -> String {
    "tdx".to_string()
}

fn default_generated_at() -> String {
    chrono::Utc::now().to_rfc3339()
}

// =============================================================================
// Phase 4: Verifier Normalization
// =============================================================================

/// Types of TDX verifier implementations.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum VerifierKind {
    Trustee,
    AttestationService,
}

impl Default for VerifierKind {
    fn default() -> Self {
        VerifierKind::Trustee
    }
}

/// Measurement results for reference-value verification.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ExportMeasurementClaims {
    pub image_digest: Option<String>,
    pub executable_digest: Option<String>,
    pub rtmr0: Option<String>,
    pub rtmr1: Option<String>,
    pub rtmr2: Option<String>,
    pub rtmr3: Option<String>,
}

/// Normalized workload identity content.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ExportIdentityClaims {
    pub spiffe_id: Option<String>,
    pub trust_domain: Option<String>,
    pub issuer: Option<String>,
}

/// Verifier assertion that identity was established through attested flow.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ExportAttestedIssuanceClaims {
    #[serde(default)]
    pub identity_type: String,
    #[serde(default)]
    pub issuer: String,
    #[serde(default)]
    pub issued_identity: String,
    #[serde(default)]
    pub issued_at: String,
    pub expires_at: Option<String>,
}

/// Inputs the verifier must check against returned evidence.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ExpectedBinding {
    #[serde(default = "default_binding_algorithm")]
    pub algorithm: String,
    /// Expected report_data digest (hex-encoded)
    pub report_data: String,
    pub canonical_request_digest: String,
}

/// Verifier-normalized output consumed by caller-side policy.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VerifiedClaims {
    #[serde(default)]
    pub verifier_kind: VerifierKind,
    #[serde(default)]
    pub verifier_id: String,
    #[serde(default = "default_tee_type")]
    pub tee_type: String,
    pub quote_valid: bool,
    pub report_data: String,
    #[serde(default)]
    pub binding_assurance_level: BindingAssuranceLevel,
    pub verified_claim_assurance: Option<BTreeMap<String, BindingAssuranceLevel>>,
    pub tcb_status: Option<String>,
    #[serde(default)]
    pub measurements: ExportMeasurementClaims,
    pub binding_claims: Option<BindingClaims>,
    pub attested_issuance: Option<ExportAttestedIssuanceClaims>,
    pub identity_claims: Option<ExportIdentityClaims>,
    #[serde(default = "default_verified_at")]
    pub verified_at: String,
    pub expires_at: Option<String>,
}

fn default_verified_at() -> String {
    chrono::Utc::now().to_rfc3339()
}

// =============================================================================
// Phase 5: Policy Evaluation
// =============================================================================

/// Which identity surface is authoritative for a decision.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AuthorizationSubjectKind {
    Workload,
    Proxy,
    CompositePath,
}

impl Default for AuthorizationSubjectKind {
    fn default() -> Self {
        AuthorizationSubjectKind::Workload
    }
}

/// How proxy claims are treated in request path.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProxyPolicyMode {
    Ignore,
    Require,
    CorroborateOnly,
}

impl Default for ProxyPolicyMode {
    fn default() -> Self {
        ProxyPolicyMode::Ignore
    }
}

/// A required claim group for policy evaluation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompositeRequirement {
    pub claim_path: String,
    #[serde(default)]
    pub required_level: BindingAssuranceLevel,
}

impl Default for CompositeRequirement {
    fn default() -> Self {
        Self {
            claim_path: String::new(),
            required_level: BindingAssuranceLevel::L2,
        }
    }
}

/// Policy model used by PolicyEvaluator.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AuthorizationSubjectPolicy {
    #[serde(default)]
    pub kind: AuthorizationSubjectKind,
    #[serde(default)]
    pub proxy_mode: ProxyPolicyMode,
    #[serde(default)]
    pub composite_requirements: Vec<CompositeRequirement>,
}

// =============================================================================
// Evidence Binding Utilities
// =============================================================================

/// Compute SHA-384 binding digest for report_data.
///
/// Formula: SHA384(domain || canonical_request || canonical_binding_claims)
pub fn compute_binding_digest(canonical_request: &[u8], canonical_binding_claims: &[u8]) -> Vec<u8> {
    let mut hasher = Sha384::new();
    hasher.update(BINDING_DOMAIN);
    hasher.update(canonical_request);
    hasher.update(canonical_binding_claims);
    hasher.finalize().to_vec()
}

/// Encode digest as hex string for quote report_data field.
pub fn encode_report_data(digest: &[u8]) -> String {
    hex::encode(digest)
}

/// Decode hex string back to raw digest bytes.
pub fn decode_report_data(hex_str: &str) -> Result<Vec<u8>, hex::FromHexError> {
    hex::decode(hex_str)
}

/// Generate a fresh caller challenge nonce.
pub fn generate_nonce() -> String {
    use std::io::Read;
    let mut bytes = [0u8; 32];
    // Use getrandom for cryptographic random bytes
    getrandom::getrandom(&mut bytes).ok();
    hex::encode(bytes)
}

/// Return current ISO-8601 timestamp in UTC.
pub fn current_timestamp() -> String {
    chrono::Utc::now().to_rfc3339()
}

/// Encode raw quote bytes as base64 for transport.
pub fn encode_quote(quote_bytes: &[u8]) -> String {
    base64::Engine::encode(&base64::engine::general_purpose::STANDARD, quote_bytes)
}

/// Decode base64-encoded quote back to raw bytes.
pub fn decode_quote(b64_str: &str) -> Result<Vec<u8>, base64::DecodeError> {
    base64::Engine::decode(&base64::engine::general_purpose::STANDARD, b64_str)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_binding_digest_length() {
        let digest = compute_binding_digest(b"request", b"claims");
        assert_eq!(digest.len(), 48); // SHA-384 produces 48 bytes
    }

    #[test]
    fn test_binding_digest_deterministic() {
        let digest1 = compute_binding_digest(b"request", b"claims");
        let digest2 = compute_binding_digest(b"request", b"claims");
        assert_eq!(digest1, digest2);
    }

    #[test]
    fn test_nonce_length() {
        let nonce = generate_nonce();
        assert_eq!(nonce.len(), 64); // 32 bytes * 2 hex chars
    }

    #[test]
    fn test_report_data_encoding() {
        let digest: Vec<u8> = vec![0xab, 0xcd, 0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0xf0, 0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0xf0, 0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc];
        let hex_str = encode_report_data(&digest);
        assert_eq!(hex_str.len(), 48);
        let decoded = decode_report_data(&hex_str).unwrap();
        assert_eq!(decoded, digest);
    }
}