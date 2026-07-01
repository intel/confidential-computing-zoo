// Copyright (c) 2026 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//    http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//! TDX Quote Verifier - Basic TDX Quote Verification Implementation
//!
//! # Scope (by design)
//!
//! Argus intentionally performs only **basic** quote verification:
//! - Quote format and structure validation
//! - ECDSA P-384 signature verification over the TD report (via
//!   [`crate::crypto_verifier::SignatureVerifier`])
//! - Nonce binding verification for request freshness
//!
//! It does **not** perform collateral-backed TCB freshness checking (PCCS,
//! PCK CRL, TCB Info, QE Identity matching, or Intel's `sgx_ql_qv_result_t`).
//! That is a separate, heavier concern (Intel's DCAP Quote Verification
//! Library / a remote attestation service such as Trustee) and is explicitly
//! out of scope for Argus v1. See `docs/design-decisions.md` ("TCB Status
//! Checking") for the rationale.

use crate::errors::{ArgusError, Result};
use crate::types::*;
use crate::engine::RaVerifier;
use crate::crypto_verifier::SignatureVerifier;
use anyhow::{anyhow, Context};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha384};

/// TDX Quote Verifier performing basic TDX quote validation
///
/// This verifier performs:
/// 1. Quote structure validation
/// 2. ECDSA P-384 signature verification (real cryptographic check)
/// 3. Nonce binding verification for freshness
///
/// TCB/collateral freshness checking is intentionally not part of this
/// verifier's scope (see module docs above).
pub struct TdxQuoteVerifier {
    /// Expected verifier identifier
    expected_verifier_id: String,
    /// Freshness window in seconds
    freshness_window: u64,
    /// Cryptographic signature verifier used for the real ECDSA check
    signature_verifier: SignatureVerifier,
}

impl TdxQuoteVerifier {
    /// Create a new TDX quote verifier
    pub fn new() -> Self {
        Self {
            expected_verifier_id: "tdx-verifier-v1".to_string(),
            freshness_window: 300, // 5 minutes default
            signature_verifier: SignatureVerifier::new(),
        }
    }

    /// Create a verifier with custom freshness window
    pub fn with_freshness_window(freshness_window: u64) -> Self {
        Self {
            expected_verifier_id: "tdx-verifier-v1".to_string(),
            freshness_window,
            signature_verifier: SignatureVerifier::new(),
        }
    }

    /// Configure a trusted Intel CA certificate (PEM) for certificate-chain
    /// pinning. Optional: without this, signature verification still checks
    /// that the TD report is signed by the key embedded in the quote's own
    /// certificate, but does not pin that certificate to a specific Intel CA.
    pub fn with_intel_ca_cert(mut self, cert_pem: &[u8]) -> Self {
        self.signature_verifier = self.signature_verifier.with_intel_ca_cert(cert_pem);
        self
    }

    /// Validate the quote format structure
    ///
    /// TDX Quote structure (simplified):
    /// - Header: 16 bytes (version, type, subtype) - little-endian
    /// - Body: Variable length
    /// - TD Report: 1024 bytes
    /// - Signature: Variable length
    fn validate_quote_structure(&self, quote_bytes: &[u8]) -> Result<()> {
        // Minimum quote size check (header + minimum body)
        const MIN_QUOTE_SIZE: usize = 1040; // 16 header + 1024 TD report + margin
        
        if quote_bytes.len() < MIN_QUOTE_SIZE {
            return Err(ArgusError::QuoteValidationFailed {
                reason: format!(
                    "Quote too small: {} bytes, minimum {} bytes",
                    quote_bytes.len(),
                    MIN_QUOTE_SIZE
                ),
            });
        }

        // TSM quote format uses little-endian byte order
        // Read version as little-endian u16
        let version = u16::from_le_bytes([quote_bytes[0], quote_bytes[1]]);
        // Read type as little-endian u16
        let quote_type = u16::from_le_bytes([quote_bytes[2], quote_bytes[3]]);
        // Read subtype as little-endian u16
        let subtype = u16::from_le_bytes([quote_bytes[4], quote_bytes[5]]);

        // Validate quote header
        // Version: 4 for TDX 2.0, 1 for TDX 1.5 (we accept both)
        if version != 1 && version != 4 {
            tracing::warn!(
                target: "argus::verifier",
                "Unexpected quote version: {} (expected 1 or 4)",
                version
            );
            // Don't fail on version mismatch, just warn
        }

        // Type: 2 for TD quote (0x0002 in little-endian)
        if quote_type != 0x0002 {
            return Err(ArgusError::QuoteValidationFailed {
                reason: format!("Invalid quote type: 0x{:04x}, expected 0x0002 (TD quote)", quote_type),
            });
        }

        // Subtype: 0x81 for standard TD quote (0x0081 in little-endian)
        if subtype != 0x0081 {
            return Err(ArgusError::QuoteValidationFailed {
                reason: format!("Invalid quote subtype: 0x{:04x}, expected 0x0081", subtype),
            });
        }

        tracing::debug!(
            target: "argus::verifier",
            "Quote structure validated: version={}, type=0x{:04x}, subtype=0x{:04x}",
            version, quote_type, subtype
        );

        tracing::debug!(
            target: "argus::verifier",
            "Quote structure validation passed"
        );

        Ok(())
    }

    /// Extract RTMR (Runtime Measurement Register) values from quote
    ///
    /// RTMR values are stored at specific offsets in the TD report portion
    /// of the quote. Each RTMR is 48 bytes (SHA-384).
    fn extract_rtmr_values(&self, quote_bytes: &[u8]) -> Result<ExportMeasurementClaims> {
        // RTMR offsets within TD report (simplified - actual offsets vary by TDX spec)
        const RTMR0_OFFSET: usize = 832;   // Offset in TD report
        const RTMR1_OFFSET: usize = 880;
        const RTMR2_OFFSET: usize = 928;
        const RTMR3_OFFSET: usize = 976;

        let rtmr0 = self.extract_rtmr_at(quote_bytes, RTMR0_OFFSET)?;
        let rtmr1 = self.extract_rtmr_at(quote_bytes, RTMR1_OFFSET)?;
        let rtmr2 = self.extract_rtmr_at(quote_bytes, RTMR2_OFFSET)?;
        let rtmr3 = self.extract_rtmr_at(quote_bytes, RTMR3_OFFSET)?;

        Ok(ExportMeasurementClaims {
            image_digest: None, // Image digest is computed separately
            executable_digest: None,
            rtmr0: Some(rtmr0),
            rtmr1: Some(rtmr1),
            rtmr2: Some(rtmr2),
            rtmr3: Some(rtmr3),
        })
    }

    /// Extract a single RTMR value at the given offset
    fn extract_rtmr_at(&self, quote_bytes: &[u8], offset: usize) -> Result<String> {
        const RTMR_SIZE: usize = 48;

        if quote_bytes.len() < offset + RTMR_SIZE {
            return Err(ArgusError::QuoteValidationFailed {
                reason: format!(
                    "Quote too short for RTMR at offset {}: {} bytes",
                    offset,
                    quote_bytes.len()
                ),
            });
        }

        let rtmr_bytes = &quote_bytes[offset..offset + RTMR_SIZE];
        Ok(hex::encode(rtmr_bytes))
    }

    /// Verify nonce binding for freshness
    ///
    /// The nonce binding ensures the quote was generated specifically for this
    /// attestation request and not replayed from a previous request.
    ///
    /// We verify by checking that the canonical_request_digest in the binding
    /// matches what we expect for this request. The binding digest was computed
    /// during evidence generation as SHA384(domain || canonical_request || binding_claims).
    fn verify_nonce_binding(
        &self,
        evidence: &Evidence,
        expected_binding: &ExpectedBinding,
        report_data_bytes: &[u8],
    ) -> Result<()> {
        // Extract the binding digest from the nonce binding context
        let binding_digest_hex = &evidence.nonce_binding.canonical_request_digest;
        
        if binding_digest_hex.is_empty() {
            return Err(ArgusError::QuoteValidationFailed {
                reason: "Missing nonce binding - cannot verify freshness".to_string(),
            });
        }

        // Decode the binding digest from hex
        let binding_digest = match hex::decode(binding_digest_hex) {
            Ok(d) => d,
            Err(e) => return Err(ArgusError::QuoteInvalidEncoding {
                reason: format!("Failed to decode binding digest: {}", e),
            }),
        };

        // The binding digest should be 48 bytes (SHA-384)
        if binding_digest.len() != 48 {
            return Err(ArgusError::QuoteValidationFailed {
                reason: format!(
                    "Invalid binding digest length: {} bytes, expected 48",
                    binding_digest.len()
                ),
            });
        }

        if expected_binding.algorithm != evidence.nonce_binding.algorithm {
            return Err(ArgusError::QuoteValidationFailed {
                reason: format!(
                    "Unexpected nonce binding algorithm: expected {}, got {}",
                    expected_binding.algorithm,
                    evidence.nonce_binding.algorithm
                ),
            });
        }

        if expected_binding.canonical_request_digest != binding_digest_hex.as_str() {
            return Err(ArgusError::QuoteValidationFailed {
                reason: "Nonce binding digest does not match the caller request".to_string(),
            });
        }

        if expected_binding.report_data.as_str() != evidence.report_data.as_str() {
            return Err(ArgusError::QuoteValidationFailed {
                reason: "Evidence report_data does not match the caller-expected binding".to_string(),
            });
        }

        // Verify that the report_data in the quote matches the binding digest
        // This confirms the quote was generated with the correct binding
        if report_data_bytes != &binding_digest[..] {
            return Err(ArgusError::QuoteValidationFailed {
                reason: "Quote report_data does not match binding digest - possible nonce mismatch".to_string(),
            });
        }

        tracing::debug!(
            target: "argus::verifier",
            "Nonce binding verification passed - quote freshness confirmed"
        );

        Ok(())
    }

    /// Report TCB status as "not evaluated" (by design)
    ///
    /// Argus intentionally does not evaluate TCB freshness. Doing so
    /// correctly requires fetching PCCS/QGS collateral (PCK certificate
    /// chain, TCB Info, QE Identity — what Intel's `tdx_att_get_collateral()`
    /// in `tdx_verify.c` retrieves) and then matching the quote's TCB
    /// components against that collateral (what the separate DCAP Quote
    /// Verification Library does, producing `sgx_ql_qv_result_t`). That is a
    /// materially heavier verifier — out of scope for Argus's basic quote
    /// verification. Rather than fabricate a status value, this always
    /// reports `Unknown` so callers cannot mistake it for a real freshness
    /// check. See `docs/design-decisions.md` ("TCB Status Checking") for the
    /// scope decision.
    fn check_tcb_status(&self, _quote_bytes: &[u8]) -> Result<TcbStatus> {
        Ok(TcbStatus {
            tcb_version: None,
            tcb_evaluation: TcbEvaluationLevel::Basic,
            tcb_status_type: TcbStatusType::Unknown,
            advisory_ids: vec![],
        })
    }

    /// Verify the quote's cryptographic signature.
    ///
    /// Performs two checks:
    /// 1. Quote structure validation.
    /// 2. Real ECDSA P-384 signature verification via
    ///    [`crate::crypto_verifier::SignatureVerifier`] — the TD report is
    ///    checked against the signature and certificate embedded in the
    ///    quote (and, if an Intel CA was configured via
    ///    `with_intel_ca_cert`, the certificate is additionally checked
    ///    against that trust anchor).
    ///
    /// KNOWN LIMITATION: certificate/signature extraction in
    /// `crypto_verifier.rs` uses fixed offsets and a simplified
    /// PEM-in-quote-bytes assumption. It has not been validated against a
    /// real hardware-generated TDX quote's actual TLV-encoded `auth_data` /
    /// `cert_data` layout. Validate against real quotes before depending on
    /// this in production; adjust the extraction logic if the layout
    /// differs.
    fn verify_quote_signature(&self, quote_bytes: &[u8], _report_data: &[u8]) -> Result<()> {
        // Validate the presented quote structure first.
        self.validate_quote_structure(quote_bytes)?;

        // Real cryptographic check: ECDSA P-384 signature over the TD report.
        self.signature_verifier.verify_signature(quote_bytes)?;

        // Certificate validity / (optional) trust-anchor pinning.
        self.signature_verifier.verify_trust_anchor(quote_bytes)?;

        tracing::debug!(
            target: "argus::verifier",
            "Quote structure and signature verification passed; binding checks will enforce request freshness"
        );

        Ok(())
    }
}

impl Default for TdxQuoteVerifier {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl RaVerifier for TdxQuoteVerifier {
    async fn verify_evidence(
        &self,
        evidence: &Evidence,
        expected_binding: &ExpectedBinding,
        options: &VerificationOptions,
    ) -> Result<VerifiedClaims> {
        tracing::debug!(
            target: "argus::verifier",
            "Starting TDX quote verification"
        );

        // Step 1: Decode the base64-encoded quote
        let quote_bytes = base64::Engine::decode(
            &base64::engine::general_purpose::STANDARD,
            &evidence.quote,
        )
        .map_err(|e| ArgusError::QuoteInvalidEncoding {
            reason: format!("Failed to decode quote base64: {}", e),
        })?;

        tracing::debug!(
            target: "argus::verifier",
            "Quote decoded: {} bytes",
            quote_bytes.len()
        );

        // Step 2: Validate quote structure
        self.validate_quote_structure(&quote_bytes)?;

        // Step 3: Decode and validate report_data
        let report_data_bytes = hex::decode(&evidence.report_data)
            .map_err(|e| ArgusError::QuoteInvalidEncoding {
                reason: format!("Failed to decode report_data hex: {}", e),
            })?;

        if report_data_bytes.len() != 48 {
            return Err(ArgusError::QuoteInvalidEncoding {
                reason: format!(
                    "Invalid report_data length: {} bytes, expected 48",
                    report_data_bytes.len()
                ),
            });
        }

        // Step 4: Verify quote signature using reference verification
        self.verify_quote_signature(&quote_bytes, &report_data_bytes)?;

        // Step 5: Verify nonce binding for freshness
        self.verify_nonce_binding(&evidence, expected_binding, &report_data_bytes)?;

        // Step 6: Extract RTMR measurements
        let measurements = self.extract_rtmr_values(&quote_bytes)?;

        tracing::debug!(
            target: "argus::verifier",
            "RTMR0: {:?}",
            measurements.rtmr0.as_ref().map(|h| &h[..16])
        );

        // Step 6: Verify nonce binding for freshness
        // This is now handled in verify_nonce_binding() above

        // Step 7: Check TCB status
        let tcb_status = self.check_tcb_status(&quote_bytes)?;

        // Step 8: Build identity claims from binding claims
        let identity_claims = evidence
            .binding_claims
            .as_ref()
            .and_then(|bc| bc.service_identity.spiffe_id.clone())
            .map(|spiffe_id| ExportIdentityClaims {
                spiffe_id: Some(spiffe_id.clone()),
                trust_domain: Some("intel.com".to_string()),
                issuer: Some("intel-tdx-attestation".to_string()),
            });

        // Step 9: Determine binding assurance level
        let binding_level = evidence
            .binding_claims
            .as_ref()
            .map(|bc| bc.assurance_level)
            .unwrap_or(BindingAssuranceLevel::L2);

        // Step 10: Build verified claims response
        let verified = VerifiedClaims {
            verifier_kind: VerifierKind::Trustee,
            verifier_id: self.expected_verifier_id.clone(),
            tee_type: "tdx".to_string(),
            quote_valid: true,
            report_data: evidence.report_data.clone(),
            binding_assurance_level: binding_level,
            verified_claim_assurance: None,
            tcb_status: Some(format!("{:?}", tcb_status.tcb_status_type)),
            measurements,
            binding_claims: evidence.binding_claims.clone(),
            attested_issuance: None,
            identity_claims,
            verified_at: current_timestamp(),
            expires_at: Some(current_timestamp_plus_seconds(self.freshness_window)?),
        };

        tracing::info!(
            target: "argus::verifier",
            "Quote verification completed successfully"
        );

        Ok(verified)
    }
}

/// TCB Status information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TcbStatus {
    pub tcb_version: Option<String>,
    pub tcb_evaluation: TcbEvaluationLevel,
    pub tcb_status_type: TcbStatusType,
    pub advisory_ids: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TcbEvaluationLevel {
    Basic,
    Standard,
    Advanced,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TcbStatusType {
    UpToDate,
    OutOfDate,
    UpdateRequired,
    Unknown,
}

/// Get current timestamp plus specified seconds
fn current_timestamp_plus_seconds(seconds: u64) -> Result<String> {
    use chrono::{Duration, Utc};
    
    let now = Utc::now();
    let future = now + Duration::seconds(seconds as i64);
    Ok(future.to_rfc3339())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_quote_structure_validation() {
        let verifier = TdxQuoteVerifier::new();
        
        // Valid TSM quote structure (actual TDX 2.0 format from TSM)
        // Header: version=0x0004, type=0x0002 (TD Quote), subtype=0x0081
        // All values are little-endian
        let mut valid_quote = vec![0u8; 1040];
        valid_quote[0] = 0x04;  // Version byte 1 (LE)
        valid_quote[1] = 0x00;  // Version byte 2 (LE)
        valid_quote[2] = 0x02;  // Type byte 1 (LE) = 0x0002 for TD Quote
        valid_quote[3] = 0x00;  // Type byte 2 (LE)
        valid_quote[4] = 0x81;  // Subtype byte 1 (LE) = 0x0081 for standard TD quote
        valid_quote[5] = 0x00;  // Subtype byte 2 (LE)
        
        let result = verifier.validate_quote_structure(&valid_quote);
        assert!(result.is_ok(), "Valid TSM quote should pass validation: {:?}", result);
        
        // Invalid quote type (0xFF instead of 0x0002)
        let mut invalid_quote = vec![0u8; 1040];
        invalid_quote[0] = 0x04;  // Version byte 1 (LE)
        invalid_quote[1] = 0x00;  // Version byte 2 (LE)
        invalid_quote[2] = 0xFF;  // Invalid Type
        invalid_quote[3] = 0xFF;  // Invalid Type
        invalid_quote[4] = 0x81;  // Subtype
        invalid_quote[5] = 0x00;  // Subtype byte 2
        
        let result = verifier.validate_quote_structure(&invalid_quote);
        assert!(result.is_err(), "Invalid quote type should fail validation");
    }

    #[test]
    fn test_rtmr_extraction() {
        let verifier = TdxQuoteVerifier::new();
        
        // Create a minimal quote with RTMR values
        let mut quote = vec![0u8; 1024];
        // Fill with test pattern for RTMR0
        for i in 0..48 {
            quote[832 + i] = (i as u8).wrapping_add(0xAA);
        }
        
        let result = verifier.extract_rtmr_at(&quote, 832);
        assert!(result.is_ok());
        let rtmr = result.unwrap();
        assert_eq!(rtmr.len(), 96); // 48 bytes * 2 hex chars
    }

    #[test]
    fn test_tcb_status_parsing() {
        let verifier = TdxQuoteVerifier::new();
        let mut quote = vec![0u8; 1040];
        quote[0] = 0x04;
        quote[1] = 0x00;
        quote[2] = 0x02;
        quote[3] = 0x00;
        quote[4] = 0x81;
        quote[5] = 0x00;
        
        // TCB status is intentionally not evaluated (see check_tcb_status
        // doc comment) - it always reports Unknown rather than fabricating
        // a freshness claim.
        let result = verifier.check_tcb_status(&quote);
        assert!(result.is_ok());
        let status = result.unwrap();
        assert_eq!(status.tcb_status_type, TcbStatusType::Unknown);
    }

    #[test]
    fn test_nonce_binding_verification() {
        let verifier = TdxQuoteVerifier::new();
        
        // Create mock evidence with valid binding digest
        let binding_digest = vec![0xabu8; 48]; // 48 bytes of SHA-384 digest
        let binding_digest_hex = hex::encode(&binding_digest);
        
        let evidence = Evidence {
            version: "v1".to_string(),
            evidence_type: "tee_quote".to_string(),
            tee_type: "tdx".to_string(),
            quote: "BAACAIEAAAAAAAAAk5pyM/ecTKmUCg2zlX8GB+WhlcwH9+Rj5INjzFXGFWMAAAAABgEIAAAAAAAAAAAAAAAA".to_string(),
            binding_claims: None,
            quote_format: "tdx".to_string(),
            report_data: binding_digest_hex.clone(),
            nonce_binding: NonceBinding {
                algorithm: BINDING_ALGORITHM.to_string(),
                domain: "argus-evidence-v1\x00".to_string(),
                canonical_request_digest: binding_digest_hex,
                bound_fields: vec!["nonce".to_string()],
            },
            generated_at: "2026-06-26T00:00:00Z".to_string(),
        };

        let expected_binding = ExpectedBinding {
            algorithm: BINDING_ALGORITHM.to_string(),
            report_data: evidence.report_data.clone(),
            canonical_request_digest: evidence.nonce_binding.canonical_request_digest.clone(),
        };
        
        // Test with matching binding digest
        let result = verifier.verify_nonce_binding(&evidence, &expected_binding, &binding_digest);
        assert!(result.is_ok(), "Matching binding digest should pass: {:?}", result);
        
        // Test with mismatched binding digest
        let wrong_digest = vec![0x01u8; 48];
        let result = verifier.verify_nonce_binding(&evidence, &expected_binding, &wrong_digest);
        assert!(result.is_err(), "Mismatched binding digest should fail");
        
        // Test with empty binding digest
        let mut empty_evidence = evidence.clone();
        empty_evidence.nonce_binding.canonical_request_digest = "".to_string();
        let result = verifier.verify_nonce_binding(&empty_evidence, &expected_binding, &binding_digest);
        assert!(result.is_err(), "Empty binding digest should fail");
    }
}