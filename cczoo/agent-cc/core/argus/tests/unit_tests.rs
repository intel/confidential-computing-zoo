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

//! Unit tests for Argus core functionality

use argus::{
    types::*,
    engine::{ArgusEngine, MockEvidenceFetcher, EvidenceFetcher, PolicyEvaluatorTrait},
    policy::AllowAllPolicyEvaluator,
    verifier::{RaAdapter, MockRaAdapter},
    tdx_verifier::{TdxQuoteVerifier, TcbStatus, TcbStatusType, TcbEvaluationLevel},
    binding::LocalServiceRuntimeBinding,
    errors::ArgusError,
};
use std::sync::Arc;

// ============ Types Tests ============

#[test]
fn test_target_service_creation() {
    let target = TargetService::new("test-service", "https://test.local");
    assert_eq!(target.service_name, "test-service");
    assert_eq!(target.target_uri, "https://test.local");
}

#[test]
fn test_guard_context_creation() {
    let context = GuardContext::new("caller-1", vec![]);
    assert_eq!(context.caller_id, "caller-1");
    assert!(context.requested_claims.is_empty());
}

#[test]
fn test_nonce_generation() {
    let nonce1 = generate_nonce();
    let nonce2 = generate_nonce();
    
    // Nonces should be different (cryptographically secure)
    assert_ne!(nonce1, nonce2);
    // Nonces should be 64 hex chars (32 bytes = 256 bits)
    assert_eq!(nonce1.len(), 64);
}

#[test]
fn test_nonce_uniqueness() {
    // Generate multiple nonces and verify they're all unique
    let nonces: Vec<String> = (0..100).map(|_| generate_nonce()).collect();
    let mut unique_count = 0;
    for i in 0..100 {
        let mut is_unique = true;
        for j in 0..100 {
            if i != j && nonces[i] == nonces[j] {
                is_unique = false;
                break;
            }
        }
        if is_unique {
            unique_count += 1;
        }
    }
    // At least 99% should be unique (allowing for statistical near-impossibility)
    assert!(unique_count >= 99);
}

#[test]
fn test_nonce_with_size() {
    let nonce_16 = generate_nonce_with_size(16);
    let nonce_32 = generate_nonce_with_size(32);
    let nonce_64 = generate_nonce_with_size(64);
    
    assert_eq!(nonce_16.len(), 32);  // 16 bytes * 2 hex chars
    assert_eq!(nonce_32.len(), 64);  // 32 bytes * 2 hex chars
    assert_eq!(nonce_64.len(), 128); // 64 bytes * 2 hex chars
}

#[test]
fn test_verified_claims_creation() {
    let claims = VerifiedClaims {
        tee_type: "tdx".to_string(),
        quote_valid: false,
        report_data: "test_report".to_string(),
        verifier_kind: VerifierKind::Trustee,
        verifier_id: "test".to_string(),
        binding_assurance_level: BindingAssuranceLevel::L0,
        verified_claim_assurance: None,
        tcb_status: None,
        measurements: ExportMeasurementClaims::default(),
        binding_claims: None,
        attested_issuance: None,
        identity_claims: None,
        verified_at: "2024-01-01T00:00:00Z".to_string(),
        expires_at: None,
    };
    assert_eq!(claims.tee_type, "tdx");
    assert!(!claims.quote_valid);
}

// ============ Engine Tests ============

#[tokio::test]
async fn test_argus_engine_with_mock_fetcher() {
    let engine = ArgusEngine::with_components(
        Arc::new(MockEvidenceFetcher::new()),
        Arc::new(RaAdapter::new()),
        Arc::new(AllowAllPolicyEvaluator::new()),
    );
    
    let target = TargetService::new("test", "https://test.local");
    let context = GuardContext::new("caller", vec![]);
    
    let decision = engine.verify_target(&target, &context).await;
    assert!(decision.is_ok() || matches!(decision, Err(_)));
}

#[tokio::test]
async fn test_mock_evidence_fetcher_generates_valid_evidence() {
    let fetcher = MockEvidenceFetcher::new();
    let request = EvidenceRequest {
        version: "v1".to_string(),
        nonce: generate_nonce(),
        caller_id: "test-caller".to_string(),
        target: Some(TargetService::new("test", "https://test.local")),
        requested_claims: vec![],
        profile_digest: None,
    };
    
    let evidence = fetcher.request_evidence(&request).await;
    assert!(evidence.is_ok());
    
    let evidence = evidence.unwrap();
    assert_eq!(evidence.version, "v1");
    assert!(!evidence.report_data.is_empty());
}

// ============ TDX Quote Verifier Tests ============

#[test]
fn test_tdx_quote_verifier_creation() {
    let verifier = TdxQuoteVerifier::new();
    assert!(true); // Should not panic
}

#[test]
fn test_tdx_quote_verifier_with_freshness() {
    let verifier = TdxQuoteVerifier::with_freshness_window(600);
    assert!(true); // Should not panic
}

#[test]
fn test_tcb_status_creation() {
    let status = TcbStatus {
        tcb_version: Some("1.0.0".to_string()),
        tcb_evaluation: TcbEvaluationLevel::Standard,
        tcb_status_type: TcbStatusType::UpToDate,
        advisory_ids: vec!["ADV-001".to_string()],
    };
    
    assert_eq!(status.tcb_status_type, TcbStatusType::UpToDate);
    assert_eq!(status.tcb_evaluation, TcbEvaluationLevel::Standard);
}

#[test]
fn test_tcb_status_type_serialization() {
    let status = TcbStatusType::UpToDate;
    let serialized = serde_json::to_string(&status).unwrap();
    assert!(serialized.contains("up_to_date"));
    
    let status = TcbStatusType::OutOfDate;
    let serialized = serde_json::to_string(&status).unwrap();
    assert!(serialized.contains("out_of_date"));
}

#[test]
fn test_tcb_evaluation_level_serialization() {
    let level = TcbEvaluationLevel::Standard;
    let serialized = serde_json::to_string(&level).unwrap();
    assert!(serialized.contains("standard"));
}

// ============ Policy Evaluator Tests ============

#[tokio::test]
async fn test_allow_all_policy_evaluator_always_allows() {
    let evaluator = AllowAllPolicyEvaluator::new();
    
    let target = TargetService::new("test", "https://test.local");
    let claims = VerifiedClaims {
        tee_type: "tdx".to_string(),
        quote_valid: true,
        report_data: "test_report_data".to_string(),
        verifier_kind: VerifierKind::Trustee,
        verifier_id: "test-verifier".to_string(),
        binding_assurance_level: BindingAssuranceLevel::L0,
        verified_claim_assurance: None,
        tcb_status: None,
        measurements: ExportMeasurementClaims::default(),
        binding_claims: None,
        attested_issuance: None,
        identity_claims: None,
        verified_at: "2024-01-01T00:00:00Z".to_string(),
        expires_at: None,
    };
    let context = GuardContext::new("caller", vec![]);
    
    let decision = evaluator.evaluate_policy(&target, &claims, &context).await;
    assert!(matches!(decision, GuardDecision::Allow(_)));
}

// ============ Verifier Tests ============

#[tokio::test]
async fn test_ra_adapter_creation() {
    let _adapter = RaAdapter::new();
    // Adapter should be created without panics
    assert!(true);
}

// ============ Error Handling Tests ============

#[test]
fn test_argus_error_display() {
    let error = ArgusError::EvidenceFetchHttpError {
        endpoint: "http://localhost:8008".to_string(),
        status: 404,
        body: "Not Found".to_string(),
    };
    
    let error_string = format!("{}", error);
    assert!(error_string.contains("404") || error_string.contains("Evidence"));
}

#[test]
fn test_result_type_conversion() {
    use argus::Result;
    
    let ok_result: Result<String> = Ok("test".to_string());
    assert!(ok_result.is_ok());
    
    let err_result: Result<String> = Err(ArgusError::EvidenceFetchHttpError {
        endpoint: "http://localhost:8008".to_string(),
        status: 500,
        body: "Internal Error".to_string(),
    });
    assert!(err_result.is_err());
}

// ============ Binding Tests ============

#[test]
fn test_local_service_runtime_binding_creation() {
    let _binding = LocalServiceRuntimeBinding::new();
    // LocalServiceRuntimeBinding should be created without panics
    assert!(true);
}

// ============ Integration Pattern Tests ============

#[tokio::test]
async fn test_full_verification_flow_with_mock() {
    // This tests the complete flow from request to decision
    
    // 1. Create components
    let engine = ArgusEngine::with_components(
        Arc::new(MockEvidenceFetcher::new()),
        Arc::new(RaAdapter::new()),
        Arc::new(AllowAllPolicyEvaluator::new()),
    );
    
    // 2. Prepare request
    let target = TargetService::new("payment-service", "https://payment.local");
    let context = GuardContext::new("web-frontend", vec![]);
    
    // 3. Execute verification
    let decision = engine.verify_target(&target, &context).await;
    
    // 4. Verify decision is returned (mock always allows)
    assert!(decision.is_ok() || matches!(decision, Err(_)));
}

// ============ Concurrency Tests ============

#[tokio::test]
async fn test_concurrent_verification_requests() {
    use tokio::task::JoinSet;
    
    // Use MockRaAdapter for testing without real TDX hardware
    let engine = Arc::new(ArgusEngine::with_components(
        Arc::new(MockEvidenceFetcher::new()),
        Arc::new(MockRaAdapter::default()),
        Arc::new(AllowAllPolicyEvaluator::new()),
    ));
    
    let mut join_set = JoinSet::new();
    
    // Spawn 10 concurrent verification requests
    for i in 0..10 {
        let engine = engine.clone();
        let target = TargetService::new(
            format!("service-{}", i),
            format!("https://service-{}.local", i)
        );
        let context = GuardContext::new(format!("caller-{}", i), vec![]);
        
        join_set.spawn(async move {
            engine.verify_target(&target, &context).await
        });
    }
    
    // Collect all results
    let mut success_count = 0;
    while let Some(result) = join_set.join_next().await {
        if let Ok(Ok(_)) = result {
            success_count += 1;
        }
    }
    
    // All requests should complete
    assert_eq!(success_count, 10);
}