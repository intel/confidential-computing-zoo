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

//! Argus Engine - Caller-side trust orchestration
//!
//! Implements the main facade for end-to-end target verification.

use crate::errors::{ArgusError, Result};
use crate::types::*;
use anyhow::{anyhow, Context};
use async_trait::async_trait;
use reqwest::Client;
use std::collections::BTreeMap;
use std::sync::Arc;
use std::time::Duration;

/// Evidence request builder for constructing requests.
pub struct EvidenceRequestBuilder;

impl EvidenceRequestBuilder {
    pub fn new() -> Self {
        Self {}
    }

    /// Build an evidence request from target and context.
    pub async fn build_evidence_request(
        &self,
        target: &TargetService,
        context: &GuardContext,
    ) -> Result<EvidenceRequest> {
        Ok(EvidenceRequest {
            version: "v1".to_string(),
            nonce: generate_nonce(),
            caller_id: context.caller_id.clone(),
            target: Some(target.clone()),
            requested_claims: context.requested_claims.clone(),
            profile_digest: None,
        })
    }
}

impl Default for EvidenceRequestBuilder {
    fn default() -> Self {
        Self::new()
    }
}

/// HTTP-based evidence fetcher for SDK mode.
pub struct EvidenceFetcherHttp {
    client: Client,
    endpoint_base: String,
}

impl EvidenceFetcherHttp {
    /// Create a new HTTP evidence fetcher with the given endpoint base URL.
    pub fn new(endpoint_base: impl Into<String>) -> Self {
        Self {
            client: Client::builder()
                .timeout(Duration::from_secs(30))
                .connect_timeout(Duration::from_secs(10))
                .build()
                .expect("Failed to create HTTP client"),
            endpoint_base: endpoint_base.into(),
        }
    }

    /// Get the evidence endpoint URL.
    pub fn endpoint_url(&self) -> String {
        format!("{}/ra/v1/evidence", self.endpoint_base.trim_end_matches('/'))
    }
}

impl Default for EvidenceFetcherHttp {
    fn default() -> Self {
        Self::new("http://localhost:8006".to_string())
    }
}

#[async_trait]
impl EvidenceFetcher for EvidenceFetcherHttp {
    async fn request_evidence(&self, request: &EvidenceRequest) -> Result<Evidence> {
        self.fetch_evidence(request).await
    }
}

impl EvidenceFetcherHttp {
    /// Fetch evidence from the peer Evidence Provider via HTTP POST.
    async fn fetch_evidence(&self, request: &EvidenceRequest) -> Result<Evidence> {
        let url = self.endpoint_url();
        
        tracing::debug!(
            target: "argus::engine",
            "Fetching evidence from peer: {}",
            url
        );
        
        let response = match self.client.post(&url).json(request).send().await {
            Ok(resp) => resp,
            Err(e) => {
                tracing::error!(
                    target: "argus::engine",
                    "Evidence fetch connection failed: {}: {}",
                    url, e
                );
                return Err(ArgusError::evidence_fetch_connection_failed(&url));
            }
        };

        // Check for HTTP errors
        if !response.status().is_success() {
            let status = response.status().as_u16();
            let body = response.text().await.unwrap_or_default();
            tracing::error!(
                target: "argus::engine",
                "Evidence request failed with status {}: {}",
                status, body
            );
            return Err(ArgusError::evidence_fetch_http_error(&url, status, &body));
        }

        // Parse the evidence response
        let evidence: Evidence = match response.json().await {
            Ok(evidence) => evidence,
            Err(e) => {
                tracing::error!(
                    target: "argus::engine",
                    "Failed to parse evidence response: {}",
                    e
                );
                return Err(ArgusError::EvidenceParseError {
                    endpoint: url,
                    reason: e.to_string(),
                });
            }
        };

        tracing::debug!(
            target: "argus::engine",
            "Received evidence: version={}, tee_type={}, quote_format={}",
            evidence.version, evidence.tee_type, evidence.quote_format
        );

        Ok(evidence)
    }

    /// Generate mock evidence for testing or fallback when peer is unavailable.
    /// 
    /// This method creates a mock Evidence response for testing purposes when
    /// no peer Evidence Provider is available. In production, use fetch_evidence()
    /// to request real evidence from a running Evidence Provider.
    pub async fn mock_evidence(&self, request: &EvidenceRequest) -> Result<Evidence> {
        self.build_mock_evidence(request).await
    }

    /// Internal helper to build mock evidence.
    async fn build_mock_evidence(&self, request: &EvidenceRequest) -> Result<Evidence> {
        // Build mock binding claims
        let binding_claims = BindingClaims {
            assurance_level: BindingAssuranceLevel::L2,
            service_identity: BindingIdentityClaims {
                service_name: "peer-service".to_string(),
                service_id: Some("peer-id-001".to_string()),
                instance_id: "peer-instance-001".to_string(),
                instance_scope: "pod".to_string(),
                image_digest: Some("sha256:peerimage123".to_string()),
                executable_digest: None,
                spiffe_id: Some("spiffe://test.trust.domain/peer-service".to_string()),
            },
            runtime_binding: RuntimeBindingContext {
                endpoint: request.target.as_ref().map(|t| t.target_uri.clone()).unwrap_or_default(),
                owning_pid: 99999,
                process_start_time: "1718000000".to_string(),
                container_id: Some("peer-container".to_string()),
                pod_uid: Some("peer-pod-uid".to_string()),
                vm_instance_id: None,
                namespace: Some("default".to_string()),
                cgroup_path: Some("/docker/peer".to_string()),
            },
            claim_support: BTreeMap::new(),
            verifier_validated_support: None,
            provider_claim_assurance: BTreeMap::new(),
        };

        // Compute binding digest
        let canonical_request = request.to_canonical_bytes();
        let canonical_binding = binding_claims.to_canonical_bytes();
        let digest = compute_binding_digest(&canonical_request, &canonical_binding);

        // Generate mock quote (placeholder)
        let quote_bytes = vec![0x42u8; 64];
        let quote_b64 = encode_quote(&quote_bytes);

        Ok(Evidence {
            version: "v1".to_string(),
            evidence_type: "tee_quote".to_string(),
            tee_type: "tdx".to_string(),
            quote: quote_b64,
            binding_claims: Some(binding_claims),
            quote_format: "tdx".to_string(),
            report_data: encode_report_data(&digest),
            nonce_binding: NonceBinding {
                algorithm: BINDING_ALGORITHM.to_string(),
                domain: "argus-evidence-v1\x00".to_string(),
                canonical_request_digest: hex::encode(&digest),
                bound_fields: vec![
                    "nonce".to_string(),
                    "caller_id".to_string(),
                    "target".to_string(),
                    "requested_claims".to_string(),
                    "profile_digest".to_string(),
                ],
            },
            generated_at: current_timestamp(),
        })
    }
}

/// Public caller-facing engine for end-to-end target verification.
///
/// Orchestrates evidence retrieval, TDX verifier calls, policy evaluation,
/// and allow or deny decisions.
pub struct ArgusEngine {
    fetcher: Arc<dyn EvidenceFetcher>,
    ra_adapter: Arc<dyn RaVerifier>,
    policy: Arc<dyn PolicyEvaluatorTrait>,
    request_builder: EvidenceRequestBuilder,
}

#[async_trait]
pub trait EvidenceFetcher: Send + Sync {
    async fn request_evidence(&self, request: &EvidenceRequest) -> Result<Evidence>;
}

#[async_trait]
pub trait RaVerifier: Send + Sync {
    async fn verify_evidence(
        &self,
        evidence: &Evidence,
        expected_binding: &ExpectedBinding,
        options: &VerificationOptions,
    ) -> Result<VerifiedClaims>;
}

#[async_trait]
pub trait PolicyEvaluatorTrait: Send + Sync {
    async fn evaluate_policy(
        &self,
        target: &TargetService,
        claims: &VerifiedClaims,
        context: &GuardContext,
    ) -> GuardDecision;
}

impl ArgusEngine {
    /// Create a new ArgusEngine with default components.
    pub fn new() -> Self {
        Self::with_components(
            Arc::new(EvidenceFetcherHttp::default()),
            Arc::new(crate::verifier::RaAdapter::new()),
            Arc::new(crate::policy::PolicyEvaluator::new()),
        )
    }

    /// Create an ArgusEngine with custom components.
    pub fn with_components(
        fetcher: Arc<dyn EvidenceFetcher>,
        ra_adapter: Arc<dyn RaVerifier>,
        policy: Arc<dyn PolicyEvaluatorTrait>,
    ) -> Self {
        Self {
            fetcher,
            ra_adapter,
            policy,
            request_builder: EvidenceRequestBuilder::new(),
        }
    }

    /// Verify a target service and return allow or deny decision.
    ///
    /// 1. Build evidence request
    /// 2. Fetch target evidence
    /// 3. Verify evidence through RA adapter
    /// 4. Evaluate policy
    /// 5. Return decision
    pub async fn verify_target(
        &self,
        target: &TargetService,
        context: &GuardContext,
    ) -> Result<GuardDecision> {
        // Step 1: Build evidence request
        let request = self.request_builder.build_evidence_request(target, context).await?;

        // Step 2: Fetch evidence
        let evidence = self.fetcher.request_evidence(&request).await?;

        // Step 3: Verify evidence
        let expected_binding = ExpectedBinding {
            algorithm: BINDING_ALGORITHM.to_string(),
            report_data: evidence.report_data.clone(),
            canonical_request_digest: String::new(),
        };

        let verified_claims = self
            .ra_adapter
            .verify_evidence(&evidence, &expected_binding, &context.verification_options)
            .await?;

        // Step 4: Evaluate policy
        let decision = self.policy.evaluate_policy(target, &verified_claims, context).await;

        Ok(decision)
    }
}

impl Default for ArgusEngine {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_verify_target_returns_decision() {
        // Use mock evidence fetcher for testing
        let fetcher = MockEvidenceFetcher::new();
        let engine = ArgusEngine::with_components(
            Arc::new(fetcher),
            Arc::new(crate::verifier::RaAdapter::new()),
            Arc::new(crate::policy::AllowAllPolicyEvaluator::new()),
        );
        let target = TargetService::new("test", "https://test.local");
        let context = GuardContext::new("test-caller", vec![]);

        let decision = engine.verify_target(&target, &context).await;
        assert!(decision.is_ok());
    }
}

/// Mock evidence fetcher for testing without a running peer.
pub struct MockEvidenceFetcher {
    endpoint_base: String,
}

impl MockEvidenceFetcher {
    pub fn new() -> Self {
        Self {
            endpoint_base: "http://localhost:8006".to_string(),
        }
    }
}

impl Default for MockEvidenceFetcher {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl EvidenceFetcher for MockEvidenceFetcher {
    async fn request_evidence(&self, request: &EvidenceRequest) -> Result<Evidence> {
        // Use the same mock implementation as EvidenceFetcherHttp
        EvidenceFetcherHttp::new(&self.endpoint_base)
            .mock_evidence(request)
            .await
    }
}