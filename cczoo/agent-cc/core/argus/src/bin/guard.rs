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

//! Guard binary
//!
//! Runs the Argus Guard HTTP server for caller-side verification.
//! Provides REST endpoints for target verification requests.

use argus::{
    types::*,
    engine::{EvidenceFetcher, EvidenceFetcherHttp, RaVerifier, PolicyEvaluatorTrait},
    verifier::RaAdapter,
    policy::PolicyEvaluator,
};
use anyhow::{bail, Result};
use axum::{
    extract::{DefaultBodyLimit, State},
    http::{header::AUTHORIZATION, HeaderMap, StatusCode},
    routing::{get, post},
    Json, Router,
};
use std::net::SocketAddr;
use std::sync::Arc;

/// Application state for the Guard HTTP server
#[derive(Clone)]
struct GuardAppState {
    evidence_fetcher: Arc<EvidenceFetcherHttp>,
    ra_adapter: Arc<RaAdapter>,
    policy_evaluator: Arc<dyn PolicyEvaluatorTrait>,
    api_token: Option<Arc<str>>,
}

const MAX_BATCH_SIZE: usize = 32;
const MAX_REQUEST_BODY_BYTES: usize = 1024 * 1024;

fn authorize(headers: &HeaderMap, expected_token: Option<&str>) -> Result<(), StatusCode> {
    let Some(expected_token) = expected_token else {
        return Ok(());
    };
    let supplied_token = headers
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "));

    if supplied_token == Some(expected_token) {
        Ok(())
    } else {
        Err(StatusCode::UNAUTHORIZED)
    }
}

/// Health check response
#[derive(serde::Serialize)]
struct HealthResponse {
    status: String,
    version: String,
}

/// Verification request from caller
#[derive(serde::Deserialize)]
pub struct VerifyRequest {
    pub target: TargetService,
    pub caller_id: String,
    pub requested_claims: Option<Vec<RequestedClaim>>,
    pub verification_options: Option<VerificationOptions>,
    pub profile_digest: Option<String>,
}

/// Verification response
#[derive(serde::Serialize)]
pub struct VerifyResponse {
    pub decision: String,
    pub reason: Option<String>,
    pub claims: Option<VerifiedClaims>,
}

/// Guard context from request
impl From<&VerifyRequest> for GuardContext {
    fn from(req: &VerifyRequest) -> Self {
        GuardContext {
            caller_id: req.caller_id.clone(),
            requested_claims: req.requested_claims.clone().unwrap_or_default(),
            verification_options: req.verification_options.clone().unwrap_or_default(),
        }
    }
}

/// Health check handler
async fn health_handler() -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "OK".to_string(),
        version: "v1".to_string(),
    })
}

/// Verification handler - POST /ra/v1/verify
async fn verify_handler(
    State(state): State<GuardAppState>,
    headers: HeaderMap,
    Json(request): Json<VerifyRequest>,
) -> Result<Json<VerifyResponse>, StatusCode> {
    authorize(&headers, state.api_token.as_deref())?;

    // Build guard context from request
    let context = GuardContext::from(&request);

    // Build evidence request
    let evidence_request = EvidenceRequest {
        version: "v1".to_string(),
        nonce: generate_nonce(),
        caller_id: request.caller_id.clone(),
        target: Some(request.target.clone()),
        requested_claims: context.requested_claims.clone(),
        profile_digest: request.profile_digest.clone(),
    };

    // Fetch evidence from peer
    let evidence = state
        .evidence_fetcher
        .request_evidence(&evidence_request)
        .await
        .map_err(|e| {
            tracing::error!("Evidence fetch failed: {}", e);
            StatusCode::BAD_GATEWAY
        })?;

    // Build expected binding for verification
    let binding_claims = evidence
        .binding_claims
        .as_ref()
        .ok_or(StatusCode::UNPROCESSABLE_ENTITY)?;
    let expected_binding =
        ExpectedBinding::from_request_and_claims(&evidence_request, binding_claims);

    // Verify evidence
    let verified_claims = state
        .ra_adapter
        .verify_evidence(&evidence, &expected_binding, &context.verification_options)
        .await
        .map_err(|e| {
            tracing::error!("Verification failed: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    // Evaluate policy
    let decision = state
        .policy_evaluator
        .evaluate_policy(&request.target, &verified_claims, &context)
        .await;

    // Convert decision to response
    let response = match decision {
        GuardDecision::Allow(claims) => VerifyResponse {
            decision: "ALLOW".to_string(),
            reason: None,
            claims: Some(claims),
        },
        GuardDecision::Deny { reason, claims } => VerifyResponse {
            decision: "DENY".to_string(),
            reason: Some(format!("{:?}", reason)),
            claims,
        },
    };

    Ok(Json(response))
}

/// Batch verification request
#[derive(serde::Deserialize)]
pub struct BatchVerifyRequest {
    pub requests: Vec<VerifyRequest>,
}

/// Batch verification response
#[derive(serde::Serialize)]
pub struct BatchVerifyResponse {
    pub results: Vec<VerifyResponse>,
}

/// Batch verification handler - POST /ra/v1/verify/batch
async fn batch_verify_handler(
    State(state): State<GuardAppState>,
    headers: HeaderMap,
    Json(request): Json<BatchVerifyRequest>,
) -> Result<Json<BatchVerifyResponse>, StatusCode> {
    authorize(&headers, state.api_token.as_deref())?;
    if request.requests.is_empty() || request.requests.len() > MAX_BATCH_SIZE {
        return Err(StatusCode::PAYLOAD_TOO_LARGE);
    }

    let mut results = Vec::with_capacity(request.requests.len());

    for req in request.requests {
        // Build guard context from request
        let context = GuardContext::from(&req);

        // Build evidence request
        let evidence_request = EvidenceRequest {
            version: "v1".to_string(),
            nonce: generate_nonce(),
            caller_id: req.caller_id.clone(),
            target: Some(req.target.clone()),
            requested_claims: context.requested_claims.clone(),
            profile_digest: req.profile_digest.clone(),
        };

        // Fetch evidence
        let evidence = match state.evidence_fetcher.request_evidence(&evidence_request).await {
            Ok(e) => e,
            Err(e) => {
                tracing::error!("Evidence fetch failed: {}", e);
                results.push(VerifyResponse {
                    decision: "ERROR".to_string(),
                    reason: Some(format!("Evidence fetch failed: {}", e)),
                    claims: None,
                });
                continue;
            }
        };

        // Build expected binding
        let Some(binding_claims) = evidence.binding_claims.as_ref() else {
            results.push(VerifyResponse {
                decision: "ERROR".to_string(),
                reason: Some("Evidence did not contain binding claims".to_string()),
                claims: None,
            });
            continue;
        };
        let expected_binding =
            ExpectedBinding::from_request_and_claims(&evidence_request, binding_claims);

        // Verify evidence
        let verified_claims = match state
            .ra_adapter
            .verify_evidence(&evidence, &expected_binding, &context.verification_options)
            .await
        {
            Ok(c) => c,
            Err(e) => {
                tracing::error!("Verification failed: {}", e);
                results.push(VerifyResponse {
                    decision: "ERROR".to_string(),
                    reason: Some(format!("Verification failed: {}", e)),
                    claims: None,
                });
                continue;
            }
        };

        // Evaluate policy
        let decision = state
            .policy_evaluator
            .evaluate_policy(&req.target, &verified_claims, &context)
            .await;

        // Convert decision to response
        let response = match decision {
            GuardDecision::Allow(claims) => VerifyResponse {
                decision: "ALLOW".to_string(),
                reason: None,
                claims: Some(claims),
            },
            GuardDecision::Deny { reason, claims } => VerifyResponse {
                decision: "DENY".to_string(),
                reason: Some(format!("{:?}", reason)),
                claims,
            },
        };

        results.push(response);
    }

    Ok(Json(BatchVerifyResponse { results }))
}

/// Configuration for the Guard server
#[derive(Clone)]
pub struct GuardConfig {
    pub host: String,
    pub port: u16,
    pub evidence_endpoint: String,
    pub policy_type: PolicyType,
}

/// Policy type for evaluation
#[derive(Clone, Copy, Debug, Default)]
pub enum PolicyType {
    #[default]
    AllowAll,
    Strict,
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt::init();

    // Get configuration from environment
    let host = std::env::var("HOST").unwrap_or_else(|_| "127.0.0.1".to_string());
    let port: u16 = std::env::var("PORT")
        .unwrap_or_else(|_| "8007".to_string())
        .parse()
        .unwrap_or(8007);
    let evidence_endpoint = std::env::var("EVIDENCE_ENDPOINT")
        .unwrap_or_else(|_| "http://localhost:8006".to_string());
    let intel_ca_cert_path = std::env::var("INTEL_CA_CERT_PATH")
        .map_err(|_| anyhow::anyhow!("INTEL_CA_CERT_PATH is required"))?;
    let intel_ca_cert = std::fs::read(&intel_ca_cert_path)?;
    
    let api_token = std::env::var("ARGUS_API_TOKEN")
        .ok()
        .filter(|token| !token.is_empty())
        .map(Arc::<str>::from);
    if host != "127.0.0.1" && host != "::1" && host != "localhost" && api_token.is_none() {
        bail!("ARGUS_API_TOKEN is required when Guard listens on a non-loopback address");
    }

    // Create evidence fetcher with peer endpoint
    let evidence_fetcher = Arc::new(EvidenceFetcherHttp::new(&evidence_endpoint));

    // Create RA adapter
    let ra_adapter = Arc::new(RaAdapter::with_intel_ca_cert(&intel_ca_cert));

    // Production policy fails closed on insufficient assurance, invalid quotes, and identity mismatch.
    let policy_evaluator: Arc<dyn PolicyEvaluatorTrait> = Arc::new(PolicyEvaluator::new());

    // Create app state
    let state = GuardAppState {
        evidence_fetcher,
        ra_adapter,
        policy_evaluator,
        api_token,
    };

    // Build router
    let app = Router::new()
        .route("/health", get(health_handler))
        .route("/ra/v1/verify", post(verify_handler))
        .route("/ra/v1/verify/batch", post(batch_verify_handler))
        .with_state(state)
        .layer(DefaultBodyLimit::max(MAX_REQUEST_BODY_BYTES));

    // Parse address
    let addr: SocketAddr = format!("{}:{}", host, port)
        .parse()
        .expect("Failed to parse address");

    tracing::info!("Argus Guard starting on {}", addr);
    tracing::info!("Verification endpoint: POST /ra/v1/verify");
    tracing::info!("Batch verification endpoint: POST /ra/v1/verify/batch");
    tracing::info!("Health endpoint: GET /health");
    tracing::info!("Evidence endpoint: {}", evidence_endpoint);
    
    // Start server
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}