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

//! Integration tests for EvidenceFetcherHttp
//!
//! Tests the HTTP-based evidence fetcher against a mock Evidence Provider.

mod integration_test_helpers;

use argus::{EvidenceFetcher, engine::EvidenceFetcherHttp};
use argus::types::{EvidenceRequest, GuardContext, TargetService};

/// Test that EvidenceFetcherHttp can fetch evidence from a running provider
#[tokio::test]
async fn test_evidence_fetcher_http_fetches_successfully() {
    // Create mock provider
    let provider = std::sync::Arc::new(integration_test_helpers::MockEvidenceProvider::new());
    let addr = integration_test_helpers::start_test_server(provider.clone()).await;

    // Create fetcher pointing to our mock server
    let fetcher = EvidenceFetcherHttp::new(format!("http://127.0.0.1:{}", addr.port()));

    // Build a test request
    let target = TargetService::new("test-service", "https://test.local");
    let context = GuardContext::new("test-caller", vec![]);

    let request = EvidenceRequest {
        version: "v1".to_string(),
        nonce: "test-nonce-12345".to_string(),
        caller_id: context.caller_id.clone(),
        target: Some(target.clone()),
        requested_claims: context.requested_claims.clone(),
        profile_digest: None,
    };

    // Fetch evidence
    let result = fetcher.request_evidence(&request).await;
    assert!(result.is_ok(), "Expected successful fetch, got: {:?}", result.err());

    let evidence = result.unwrap();
    assert_eq!(evidence.version, "v1");
    assert_eq!(evidence.tee_type, "tdx");
}

/// Test that EvidenceFetcherHttp handles HTTP errors gracefully
#[tokio::test]
async fn test_evidence_fetcher_http_handles_errors() {
    // Create mock provider that returns errors
    let provider = std::sync::Arc::new(
        integration_test_helpers::MockEvidenceProvider::new().with_error(),
    );
    let addr = integration_test_helpers::start_test_server(provider.clone()).await;

    // Create fetcher pointing to our mock server
    let fetcher = EvidenceFetcherHttp::new(format!("http://127.0.0.1:{}", addr.port()));

    // Build a test request
    let target = TargetService::new("test-service", "https://test.local");
    let context = GuardContext::new("test-caller", vec![]);

    let request = EvidenceRequest {
        version: "v1".to_string(),
        nonce: "test-nonce-12345".to_string(),
        caller_id: context.caller_id.clone(),
        target: Some(target.clone()),
        requested_claims: context.requested_claims.clone(),
        profile_digest: None,
    };

    // Fetch evidence - should fail due to mock error
    let result = fetcher.request_evidence(&request).await;
    assert!(result.is_err(), "Expected error due to mock server error");
}

/// Test that EvidenceFetcherHttp handles connection failures
#[tokio::test]
async fn test_evidence_fetcher_http_connection_failure() {
    // Create fetcher pointing to a non-running server
    let fetcher = EvidenceFetcherHttp::new("http://127.0.0.1:99999");

    // Build a test request
    let target = TargetService::new("test-service", "https://test.local");
    let context = GuardContext::new("test-caller", vec![]);

    let request = EvidenceRequest {
        version: "v1".to_string(),
        nonce: "test-nonce-12345".to_string(),
        caller_id: context.caller_id.clone(),
        target: Some(target.clone()),
        requested_claims: context.requested_claims.clone(),
        profile_digest: None,
    };

    // Fetch evidence - should fail due to connection refused
    let result = fetcher.request_evidence(&request).await;
    assert!(result.is_err(), "Expected connection failure error");
}

/// Test that EvidenceFetcherHttp correctly sends request data
#[tokio::test]
async fn test_evidence_fetcher_http_sends_correct_request() {
    // Create mock provider
    let provider = std::sync::Arc::new(integration_test_helpers::MockEvidenceProvider::new());
    let addr = integration_test_helpers::start_test_server(provider.clone()).await;

    // Create fetcher pointing to our mock server
    let fetcher = EvidenceFetcherHttp::new(format!("http://127.0.0.1:{}", addr.port()));

    // Build a test request with specific values
    let target = TargetService::new("my-special-service", "https://special.local");
    let context = GuardContext::new("special-caller", vec![]);

    let request = EvidenceRequest {
        version: "v1".to_string(),
        nonce: "unique-nonce-67890".to_string(),
        caller_id: context.caller_id.clone(),
        target: Some(target.clone()),
        requested_claims: context.requested_claims.clone(),
        profile_digest: None,
    };

    // Fetch evidence
    let _ = fetcher.request_evidence(&request).await;

    // Verify the server received the correct request
    let last_request = provider.get_last_request().await;
    assert!(
        last_request.is_some(),
        "Expected server to have received a request"
    );

    let received = last_request.unwrap();
    assert_eq!(received.version, "v1");
    assert_eq!(received.caller_id, "special-caller");
    assert_eq!(
        received.target.as_ref().unwrap().service_name,
        "my-special-service"
    );
}

/// Test endpoint URL generation
#[tokio::test]
async fn test_evidence_fetcher_http_endpoint_url() {
    let fetcher = EvidenceFetcherHttp::new("http://localhost:8006");
    assert_eq!(fetcher.endpoint_url(), "http://localhost:8006/ra/v1/evidence");

    let fetcher2 = EvidenceFetcherHttp::new("http://localhost:8006/");
    assert_eq!(fetcher2.endpoint_url(), "http://localhost:8006/ra/v1/evidence");

    let fetcher3 = EvidenceFetcherHttp::new("http://peer:9000");
    assert_eq!(fetcher3.endpoint_url(), "http://peer:9000/ra/v1/evidence");
}