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

//! Integration test helpers for Argus HTTP components
//!
//! Provides mock servers and test utilities for testing HTTP-based
//! evidence fetching and Guard HTTP endpoints.

use argus::types::{self as types, EvidenceRequest};
use axum::{
    body::Body,
    extract::State,
    http::{Request, StatusCode},
    response::Response,
    routing::get,
    Router,
};
use http_body_util::BodyExt;
use std::sync::Arc;
use tokio::sync::RwLock;

/// Mock Evidence Provider for integration testing
pub struct MockEvidenceProvider {
    /// Whether to simulate errors
    pub simulate_error: bool,
    /// Last received evidence request
    pub last_request: Arc<RwLock<Option<EvidenceRequest>>>,
}

impl MockEvidenceProvider {
    pub fn new() -> Self {
        Self {
            simulate_error: false,
            last_request: Arc::new(RwLock::new(None)),
        }
    }

    pub fn with_error(mut self) -> Self {
        self.simulate_error = true;
        self
    }

    /// Get the last received evidence request
    pub async fn get_last_request(&self) -> Option<EvidenceRequest> {
        self.last_request.read().await.clone()
    }

    /// Create an Axum router for the mock provider
    pub fn router(self: Arc<Self>) -> Router {
        Router::new()
            .route("/health", get(health_handler))
            .route(
                "/ra/v1/evidence",
                get(evidence_get_handler).post(evidence_post_handler),
            )
            .with_state(self)
    }
}

impl Default for MockEvidenceProvider {
    fn default() -> Self {
        Self::new()
    }
}

/// Health check handler
async fn health_handler() -> StatusCode {
    StatusCode::OK
}

/// Evidence GET handler (returns mock evidence)
async fn evidence_get_handler(
    State(provider): State<Arc<MockEvidenceProvider>>,
) -> Response<Body> {
    if provider.simulate_error {
        return Response::builder()
            .status(StatusCode::INTERNAL_SERVER_ERROR)
            .body(Body::from("Internal server error"))
            .unwrap();
    }

    // Return mock evidence
    let mock_evidence = argus::Evidence {
        version: "v1".to_string(),
        evidence_type: "tee_quote".to_string(),
        tee_type: "tdx".to_string(),
        quote: "dGVzdC1xdW90ZQ==".to_string(),
        binding_claims: None,
        quote_format: "tdx".to_string(),
        report_data: "dGVzdC1yZXBvcnQtZGF0YQ==".to_string(),
        nonce_binding: types::NonceBinding {
            algorithm: "argus-evidence-v1-sha384".to_string(),
            domain: "argus-evidence-v1".to_string(),
            canonical_request_digest: "abc123".to_string(),
            bound_fields: vec!["nonce".to_string()],
        },
        generated_at: "2024-01-01T00:00:00Z".to_string(),
    };

    let body = serde_json::to_string(&mock_evidence).unwrap();
    Response::builder()
        .status(StatusCode::OK)
        .header("Content-Type", "application/json")
        .body(Body::from(body))
        .unwrap()
}

/// Evidence POST handler
async fn evidence_post_handler(
    State(provider): State<Arc<MockEvidenceProvider>>,
    request: Request<Body>,
) -> Response<Body> {
    // Store the received request
    let body = match request.collect().await {
        Ok(collected) => collected.to_bytes(),
        Err(_) => {
            return Response::builder()
                .status(StatusCode::BAD_REQUEST)
                .body(Body::from("Failed to read request body"))
                .unwrap();
        }
    };

    let evidence_request: EvidenceRequest = match serde_json::from_slice(&body) {
        Ok(req) => req,
        Err(e) => {
            return Response::builder()
                .status(StatusCode::BAD_REQUEST)
                .body(Body::from(format!("Invalid request: {}", e)))
                .unwrap();
        }
    };

    // Store for later inspection
    {
        let mut last = provider.last_request.write().await;
        *last = Some(evidence_request.clone());
    }

    if provider.simulate_error {
        return Response::builder()
            .status(StatusCode::INTERNAL_SERVER_ERROR)
            .body(Body::from("Internal server error"))
            .unwrap();
    }

    // Return mock evidence response
    let mock_evidence = argus::Evidence {
        version: "v1".to_string(),
        evidence_type: "tee_quote".to_string(),
        tee_type: "tdx".to_string(),
        quote: "dGVzdC1xdW90ZQ==".to_string(),
        binding_claims: Some(types::BindingClaims {
            assurance_level: types::BindingAssuranceLevel::L2,
            service_identity: types::BindingIdentityClaims {
                service_name: evidence_request
                    .target
                    .as_ref()
                    .map(|t| t.service_name.clone())
                    .unwrap_or_else(|| "unknown".to_string()),
                service_id: Some("test-service-id".to_string()),
                instance_id: "test-instance".to_string(),
                instance_scope: "pod".to_string(),
                image_digest: Some("sha256:test123".to_string()),
                executable_digest: None,
                spiffe_id: Some("spiffe://test.domain/test".to_string()),
            },
            runtime_binding: types::RuntimeBindingContext {
                endpoint: evidence_request
                    .target
                    .as_ref()
                    .map(|t| t.target_uri.clone())
                    .unwrap_or_default(),
                owning_pid: 12345,
                process_start_time: "1718000000".to_string(),
                container_id: Some("test-container".to_string()),
                pod_uid: Some("test-pod-uid".to_string()),
                vm_instance_id: None,
                namespace: Some("default".to_string()),
                cgroup_path: Some("/docker/test".to_string()),
            },
            claim_support: std::collections::BTreeMap::new(),
            verifier_validated_support: None,
            provider_claim_assurance: std::collections::BTreeMap::new(),
        }),
        quote_format: "tdx".to_string(),
        report_data: "dGVzdC1yZXBvcnQtZGF0YQ==".to_string(),
        nonce_binding: types::NonceBinding {
            algorithm: "argus-evidence-v1-sha384".to_string(),
            domain: "argus-evidence-v1".to_string(),
            canonical_request_digest: "abc123".to_string(),
            bound_fields: vec![
                "nonce".to_string(),
                "caller_id".to_string(),
                "target".to_string(),
            ],
        },
        generated_at: "2024-01-01T00:00:00Z".to_string(),
    };

    let body = serde_json::to_string(&mock_evidence).unwrap();
    Response::builder()
        .status(StatusCode::OK)
        .header("Content-Type", "application/json")
        .body(Body::from(body))
        .unwrap()
}

/// Start a test server on a random available port
pub async fn start_test_server(
    provider: Arc<MockEvidenceProvider>,
) -> std::net::SocketAddr {
    use tokio::net::TcpListener;
    use std::net::SocketAddr;

    let router = provider.router();

    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr: SocketAddr = listener.local_addr().unwrap();

    tokio::spawn(async move {
        let router = router.into_make_service();
        axum::serve(listener, router).await.unwrap();
    });

    addr
}