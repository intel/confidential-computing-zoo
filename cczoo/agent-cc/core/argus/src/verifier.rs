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

//! RA Adapter - Verifier abstraction layer
//!
//! Encapsulates TDX verifier-specific protocols and normalization.

use crate::errors::Result;
use crate::types::*;
use async_trait::async_trait;
use crate::tdx_verifier::TdxQuoteVerifier;

/// RA Adapter for TDX quote verification.
pub struct RaAdapter {
    verifier: TdxQuoteVerifier,
}

impl RaAdapter {
    pub fn new() -> Self {
        Self {
            verifier: TdxQuoteVerifier::new(),
        }
    }

    pub fn with_intel_ca_cert(cert_pem: &[u8]) -> Self {
        Self {
            verifier: TdxQuoteVerifier::new().with_intel_ca_cert(cert_pem),
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
        options: &VerificationOptions,
    ) -> Result<VerifiedClaims> {
        self.verifier
            .verify_evidence(evidence, expected_binding, options)
            .await
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
            tcb_status: Some("Unknown".to_string()),
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::RaVerifier;

    #[tokio::test]
    async fn production_adapter_rejects_short_forged_quote() {
        let evidence = Evidence {
            version: "v1".to_string(),
            evidence_type: "tee_quote".to_string(),
            tee_type: "tdx".to_string(),
            quote: encode_quote(&[0u8; 100]),
            binding_claims: None,
            quote_format: "tdx".to_string(),
            report_data: hex::encode([0u8; 48]),
            nonce_binding: NonceBinding::default(),
            generated_at: chrono::Utc::now().to_rfc3339(),
        };

        let result = RaAdapter::new()
            .verify_evidence(
                &evidence,
                &ExpectedBinding::default(),
                &VerificationOptions::default(),
            )
            .await;

        assert!(result.is_err());
    }
}