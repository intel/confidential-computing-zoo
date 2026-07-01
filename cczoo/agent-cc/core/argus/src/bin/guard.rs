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
    engine::{ArgusEngine, EvidenceFetcher, EvidenceFetcherHttp, RaVerifier, PolicyEvaluatorTrait},
    verifier::RaAdapter,
    policy::AllowAllPolicyEvaluator,
    binding::ServiceRuntimeBinding,
    tc_api_client::TcApiClient,
};
use anyhow::Result;
use axum::{
    body::Body,
    extract::State,
    http::{HeaderValue, Method, StatusCode},
    response::Response,
    routing::{get, post},
    Json, Router,
};
use std::net::SocketAddr;
use std::sync::Arc;
use tower_http::cors::{Any, CorsLayer};

/// Application state for the Guard HTTP server
#[derive(Clone)]
struct GuardAppState {
    engine: Arc<ArgusEngine>,
    evidence_fetcher: Arc<EvidenceFetcherHttp>,
    ra_adapter: Arc<RaAdapter>,
    policy_evaluator: Arc<dyn PolicyEvaluatorTrait>,
    /// Optional TC-API client for Agent-side metadata (when Agent is also a TDX workload)
    tc_api_client: Option<Arc<TcApiClient>>,
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
    Json(request): Json<VerifyRequest>,
) -> Result<Json<VerifyResponse>, StatusCode> {
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
    let expected_binding = ExpectedBinding {
        algorithm: BINDING_ALGORITHM.to_string(),
        report_data: evidence.report_data.clone(),
        canonical_request_digest: evidence.nonce_binding.canonical_request_digest.clone(),
    };

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
    Json(request): Json<BatchVerifyRequest>,
) -> Result<Json<BatchVerifyResponse>, StatusCode> {
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
        let expected_binding = ExpectedBinding {
            algorithm: BINDING_ALGORITHM.to_string(),
            report_data: evidence.report_data.clone(),
            canonical_request_digest: evidence.nonce_binding.canonical_request_digest.clone(),
        };

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
    let host = std::env::var("HOST").unwrap_or_else(|_| "0.0.0.0".to_string());
    let port: u16 = std::env::var("PORT")
        .unwrap_or_else(|_| "8007".to_string())
        .parse()
        .unwrap_or(8007);
    let evidence_endpoint = std::env::var("EVIDENCE_ENDPOINT")
        .unwrap_or_else(|_| "http://localhost:8006".to_string());
    
    // TC-API configuration for Agent-side metadata (optional)
    // When AGENT_TC_API_URL is set, Guard will use local TC-API for its own identity
    // This is needed when the Agent itself is also a TDX workload requiring remote attestation
    let agent_tc_api_url = std::env::var("AGENT_TC_API_URL").ok();
    let agent_tc_api_token = std::env::var("TRUCON_SERVICE_TOKEN").ok();

    // Create TC-API client for Agent-side if configured
    let tc_api_client = if let Some(ref url) = agent_tc_api_url {
        tracing::info!("Agent TC-API configured: {}", url);
        let mut client = TcApiClient::new(url);
        if let Some(ref token) = agent_tc_api_token {
            tracing::info!("Agent TC-API auth token configured");
            client = client.with_auth_token(token);
        }
        Some(Arc::new(client))
    } else {
        tracing::info!("Agent TC-API not configured (Agent is not a TDX workload)");
        None
    };

    // Create Argus Engine
    let engine = Arc::new(ArgusEngine::new());

    // Create evidence fetcher with peer endpoint
    let evidence_fetcher = Arc::new(EvidenceFetcherHttp::new(&evidence_endpoint));

    // Create RA adapter
    let ra_adapter = Arc::new(RaAdapter::new());

    // Create policy evaluator (AllowAll for now)
    let policy_evaluator: Arc<dyn PolicyEvaluatorTrait> = Arc::new(AllowAllPolicyEvaluator::new());

    // Create app state
    let state = GuardAppState {
        engine,
        evidence_fetcher,
        ra_adapter,
        policy_evaluator,
        tc_api_client,
    };

    // Configure CORS
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(vec![Method::GET, Method::POST, Method::OPTIONS])
        .allow_headers(Any);

    // Build router
    let app = Router::new()
        .route("/health", get(health_handler))
        .route("/ra/v1/verify", post(verify_handler))
        .route("/ra/v1/verify/batch", post(batch_verify_handler))
        .with_state(state)
        .layer(cors);

    // Parse address
    let addr: SocketAddr = format!("{}:{}", host, port)
        .parse()
        .expect("Failed to parse address");

    tracing::info!("Argus Guard starting on {}", addr);
    tracing::info!("Verification endpoint: POST /ra/v1/verify");
    tracing::info!("Batch verification endpoint: POST /ra/v1/verify/batch");
    tracing::info!("Health endpoint: GET /health");
    tracing::info!("Evidence endpoint: {}", evidence_endpoint);
    
    if agent_tc_api_url.is_some() {
        tracing::info!("Agent-side TC-API: enabled (Agent is a TDX workload)");
    } else {
        tracing::info!("Agent-side TC-API: disabled (Agent is not a TDX workload)");
    }

    // Start server
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}