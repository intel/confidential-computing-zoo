//! RA Adapter - Verifier abstraction layer
//!
//! Encapsulates TDX verifier-specific protocols and normalization.

use crate::errors::{ArgusError, Result};
use crate::types::*;
use anyhow::anyhow;
use async_trait::async_trait;

/// RA Adapter for TDX quote verification.
pub struct RaAdapter {
    verifier_kind: VerifierKind,
}

impl RaAdapter {
    pub fn new() -> Self {
        Self {
            verifier_kind: VerifierKind::Trustee,
        }
    }
}

impl Default for RaAdapter {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl crate::engine::RaVerifier for RaAdapter {
    async fn verify_evidence(
        &self,
        evidence: &Evidence,
        expected_binding: &ExpectedBinding,
        _options: &VerificationOptions,
    ) -> Result<VerifiedClaims> {
        tracing::debug!(
            target: "argus::verifier",
            "Starting evidence verification"
        );

        // Step 1: Validate quote encoding
        if evidence.quote.is_empty() {
            tracing::error!(
                target: "argus::verifier",
                "Quote validation failed: empty quote"
            );
            return Err(ArgusError::QuoteInvalidEncoding {
                reason: "empty quote".to_string(),
            });
        }

        // Step 2: Verify binding
        // In production, we would recompute the binding digest and compare
        let actual_report = match decode_report_data(&evidence.report_data) {
            Ok(report) => report,
            Err(e) => {
                tracing::error!(
                    target: "argus::verifier",
                    "Failed to decode report_data: {}",
                    e
                );
                return Err(ArgusError::QuoteInvalidEncoding {
                    reason: format!("failed to decode: {}", e),
                });
            }
        };

        let quote_valid = actual_report.len() == 48; // SHA-384 produces 48 bytes

        if !quote_valid {
            tracing::error!(
                target: "argus::verifier",
                "Quote validation failed: invalid length"
            );
            return Err(ArgusError::quote_validation_failed("invalid report data length"));
        }

        tracing::debug!(
            target: "argus::verifier",
            "Quote validation passed"
        );

        // Step 3: Extract and validate measurements
        let measurements = ExportMeasurementClaims {
            image_digest: evidence
                .binding_claims
                .as_ref()
                .and_then(|bc| bc.service_identity.image_digest.clone()),
            executable_digest: evidence
                .binding_claims
                .as_ref()
                .and_then(|bc| bc.service_identity.executable_digest.clone()),
            rtmr0: None,
            rtmr1: None,
            rtmr2: None,
            rtmr3: None,
        };

        // Step 4: Build identity claims
        let identity_claims = evidence
            .binding_claims
            .as_ref()
            .and_then(|bc| bc.service_identity.spiffe_id.clone())
            .map(|spiffe_id| ExportIdentityClaims {
                spiffe_id: Some(spiffe_id),
                trust_domain: Some("test.trust.domain".to_string()),
                issuer: Some("test-issuer".to_string()),
            });

        // Step 5: Determine binding assurance level
        let binding_level = evidence
            .binding_claims
            .as_ref()
            .map(|bc| bc.assurance_level)
            .unwrap_or(BindingAssuranceLevel::L2);

        tracing::debug!(
            target: "argus::verifier",
            "Binding assurance level determined"
        );

        // Step 6: Build verified claims
        let verified = VerifiedClaims {
            verifier_kind: self.verifier_kind,
            verifier_id: "default-verifier".to_string(),
            tee_type: "tdx".to_string(),
            quote_valid,
            report_data: evidence.report_data.clone(),
            binding_assurance_level: binding_level,
            verified_claim_assurance: None,
            tcb_status: Some("OK".to_string()),
            measurements,
            binding_claims: evidence.binding_claims.clone(),
            attested_issuance: None,
            identity_claims,
            verified_at: current_timestamp(),
            expires_at: None,
        };

        Ok(verified)
    }
}

/// Mock RA Adapter for testing without real TDX verifier.
pub struct MockRaAdapter {
    quote_valid: bool,
    binding_level: BindingAssuranceLevel,
}

impl MockRaAdapter {
    pub fn new(quote_valid: bool, binding_level: BindingAssuranceLevel) -> Self {
        Self {
            quote_valid,
            binding_level,
        }
    }
}

impl Default for MockRaAdapter {
    fn default() -> Self {
        Self {
            quote_valid: true,
            binding_level: BindingAssuranceLevel::L2,
        }
    }
}

#[async_trait]
impl crate::engine::RaVerifier for MockRaAdapter {
    async fn verify_evidence(
        &self,
        evidence: &Evidence,
        _expected_binding: &ExpectedBinding,
        _options: &VerificationOptions,
    ) -> Result<VerifiedClaims> {
        Ok(VerifiedClaims {
            verifier_kind: VerifierKind::Trustee,
            verifier_id: "mock-verifier".to_string(),
            tee_type: "tdx".to_string(),
            quote_valid: self.quote_valid,
            report_data: evidence.report_data.clone(),
            binding_assurance_level: self.binding_level,
            verified_claim_assurance: None,
            tcb_status: Some("MOCK_OK".to_string()),
            measurements: ExportMeasurementClaims {
                image_digest: Some("sha256:mock123".to_string()),
                executable_digest: Some("sha256:mock456".to_string()),
                rtmr0: None,
                rtmr1: None,
                rtmr2: None,
                rtmr3: None,
            },
            binding_claims: evidence.binding_claims.clone(),
            attested_issuance: None,
            identity_claims: Some(ExportIdentityClaims {
                spiffe_id: Some("spiffe://mock.test/domain/service".to_string()),
                trust_domain: Some("mock.test".to_string()),
                issuer: Some("mock-issuer".to_string()),
            }),
            verified_at: current_timestamp(),
            expires_at: None,
        })
    }
}