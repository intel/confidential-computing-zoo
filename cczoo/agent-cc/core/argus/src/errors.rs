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

//! Error types for Argus v1
//!
//! Provides structured error types for evidence fetching, verification,
//! and policy evaluation.

use thiserror::Error;

/// Result type alias using ArgusError
pub type Result<T> = std::result::Result<T, ArgusError>;

/// Main error type for Argus operations.
#[derive(Debug, Error)]
pub enum ArgusError {
    // =============================================================================
    // Evidence Fetch Errors
    // =============================================================================
    
    /// Failed to connect to peer Evidence Provider
    #[error("Evidence fetch failed: connection refused to {endpoint}")]
    EvidenceFetchConnectionFailed {
        endpoint: String,
        #[source]
        source: Option<std::io::Error>,
    },
    
    /// Evidence request failed with HTTP error status
    #[error("Evidence request failed with status {status} from {endpoint}")]
    EvidenceFetchHttpError {
        endpoint: String,
        status: u16,
        body: String,
    },
    
    /// Evidence request timed out
    #[error("Evidence request timed out after {timeout}s to {endpoint}")]
    EvidenceFetchTimeout {
        endpoint: String,
        timeout: u64,
    },
    
    /// Failed to parse evidence response
    #[error("Failed to parse evidence response from {endpoint}: {reason}")]
    EvidenceParseError {
        endpoint: String,
        reason: String,
    },
    
    // =============================================================================
    // Verification Errors
    // =============================================================================
    
    /// Quote validation failed
    #[error("Quote validation failed: {reason}")]
    QuoteValidationFailed {
        reason: String,
    },
    
    /// Quote is malformed or invalid encoding
    #[error("Invalid quote encoding: {reason}")]
    QuoteInvalidEncoding {
        reason: String,
    },
    
    /// Binding mismatch between expected and actual
    #[error("Binding mismatch: expected {expected}, got {actual}")]
    BindingMismatch {
        expected: String,
        actual: String,
    },
    
    /// TCB status check failed
    #[error("TCB status check failed: {status}")]
    TcbStatusFailed {
        status: String,
    },
    
    /// Measurement verification failed
    #[error("Measurement verification failed for {measurement}: expected {expected}, got {actual}")]
    MeasurementMismatch {
        measurement: String,
        expected: String,
        actual: String,
    },
    
    // =============================================================================
    // Policy Evaluation Errors
    // =============================================================================
    
    /// Policy evaluation resulted in deny
    #[error("Policy denied: {reason}")]
    PolicyDenied {
        reason: String,
    },
    
    /// Required claim is missing
    #[error("Missing required claim: {claim_path}")]
    MissingRequiredClaim {
        claim_path: String,
    },
    
    /// Identity conflict detected
    #[error("Identity conflict: service name mismatch")]
    IdentityConflict,
    
    // =============================================================================
    // Request Construction Errors
    // =============================================================================
    
    /// Failed to build evidence request
    #[error("Failed to build evidence request: {reason}")]
    RequestBuildFailed {
        reason: String,
    },
    
    /// Invalid request parameters
    #[error("Invalid request: {reason}")]
    InvalidRequest {
        reason: String,
    },
    
    // =============================================================================
    // General Errors
    // =============================================================================
    
    /// Unsupported verifier or TEE type
    #[error("Unsupported: {feature}")]
    Unsupported {
        feature: String,
    },
    
    /// Operation timed out
    #[error("Operation timed out after {timeout}s")]
    Timeout {
        timeout: u64,
    },
    
    /// Internal error
    #[error("Internal error: {context}")]
    Internal {
        context: String,
    },
}

impl ArgusError {
    /// Create an evidence fetch connection error
    pub fn evidence_fetch_connection_failed(endpoint: impl Into<String>) -> Self {
        Self::EvidenceFetchConnectionFailed {
            endpoint: endpoint.into(),
            source: None,
        }
    }
    
    /// Create an evidence fetch HTTP error
    pub fn evidence_fetch_http_error(endpoint: impl Into<String>, status: u16, body: impl Into<String>) -> Self {
        Self::EvidenceFetchHttpError {
            endpoint: endpoint.into(),
            status,
            body: body.into(),
        }
    }
    
    /// Create an evidence fetch timeout error
    pub fn evidence_fetch_timeout(endpoint: impl Into<String>, timeout: u64) -> Self {
        Self::EvidenceFetchTimeout {
            endpoint: endpoint.into(),
            timeout,
        }
    }
    
    /// Create a quote validation error
    pub fn quote_validation_failed(reason: impl Into<String>) -> Self {
        Self::QuoteValidationFailed {
            reason: reason.into(),
        }
    }
    
    /// Create a binding mismatch error
    pub fn binding_mismatch(expected: impl Into<String>, actual: impl Into<String>) -> Self {
        Self::BindingMismatch {
            expected: expected.into(),
            actual: actual.into(),
        }
    }
    
    /// Create a measurement mismatch error
    pub fn measurement_mismatch(
        measurement: impl Into<String>,
        expected: impl Into<String>,
        actual: impl Into<String>,
    ) -> Self {
        Self::MeasurementMismatch {
            measurement: measurement.into(),
            expected: expected.into(),
            actual: actual.into(),
        }
    }
    
    /// Create a policy denied error
    pub fn policy_denied(reason: impl Into<String>) -> Self {
        Self::PolicyDenied {
            reason: reason.into(),
        }
    }
    
    /// Create a missing required claim error
    pub fn missing_required_claim(claim_path: impl Into<String>) -> Self {
        Self::MissingRequiredClaim {
            claim_path: claim_path.into(),
        }
    }
    
    /// Create an invalid request error
    pub fn invalid_request(reason: impl Into<String>) -> Self {
        Self::InvalidRequest {
            reason: reason.into(),
        }
    }
    
    /// Create an unsupported feature error
    pub fn unsupported(feature: impl Into<String>) -> Self {
        Self::Unsupported {
            feature: feature.into(),
        }
    }
    
    /// Create an internal error
    pub fn internal(context: impl Into<String>) -> Self {
        Self::Internal {
            context: context.into(),
        }
    }
    
    /// Check if this is a retryable error
    pub fn is_retryable(&self) -> bool {
        matches!(
            self,
            Self::EvidenceFetchTimeout { .. } |
            Self::EvidenceFetchConnectionFailed { .. }
        )
    }
    
    /// Get the error code for logging and monitoring
    pub fn error_code(&self) -> &'static str {
        match self {
            Self::EvidenceFetchConnectionFailed { .. } => "E001",
            Self::EvidenceFetchHttpError { .. } => "E002",
            Self::EvidenceFetchTimeout { .. } => "E003",
            Self::EvidenceParseError { .. } => "E004",
            Self::QuoteValidationFailed { .. } => "E005",
            Self::QuoteInvalidEncoding { .. } => "E006",
            Self::BindingMismatch { .. } => "E007",
            Self::TcbStatusFailed { .. } => "E008",
            Self::MeasurementMismatch { .. } => "E009",
            Self::PolicyDenied { .. } => "E010",
            Self::MissingRequiredClaim { .. } => "E011",
            Self::IdentityConflict => "E012",
            Self::RequestBuildFailed { .. } => "E013",
            Self::InvalidRequest { .. } => "E014",
            Self::Unsupported { .. } => "E015",
            Self::Timeout { .. } => "E016",
            Self::Internal { .. } => "E017",
        }
    }
}

/// Evidence-specific errors for service-side operations.
#[derive(Debug, Error)]
pub enum EvidenceError {
    /// Failed to collect local runtime facts
    #[error("Local collection failed: {reason}")]
    LocalCollectionFailed {
        reason: String,
    },
    
    /// Quote generation failed
    #[error("Quote generation failed: {reason}")]
    QuoteGenerationFailed {
        reason: String,
    },
    
    /// Unsupported claim type requested
    #[error("Unsupported claim type: {claim_type}")]
    UnsupportedClaim {
        claim_type: String,
    },
    
    /// Binding construction failed
    #[error("Binding construction failed: {reason}")]
    BindingConstructionFailed {
        reason: String,
    },
    
    /// Operation timed out
    #[error("Operation timed out after {timeout}s")]
    Timeout {
        timeout: u64,
    },
}

impl EvidenceError {
    /// Get the error code for logging
    pub fn error_code(&self) -> &'static str {
        match self {
            Self::LocalCollectionFailed { .. } => "EV001",
            Self::QuoteGenerationFailed { .. } => "EV002",
            Self::UnsupportedClaim { .. } => "EV003",
            Self::BindingConstructionFailed { .. } => "EV004",
            Self::Timeout { .. } => "EV005",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_codes() {
        let err = ArgusError::evidence_fetch_connection_failed("http://localhost:8006");
        assert_eq!(err.error_code(), "E001");
        
        let err = ArgusError::quote_validation_failed("empty quote");
        assert_eq!(err.error_code(), "E005");
        
        let err = ArgusError::policy_denied("insufficient assurance level");
        assert_eq!(err.error_code(), "E010");
    }
    
    #[test]
    fn test_retryable_errors() {
        let timeout_err = ArgusError::EvidenceFetchTimeout {
            endpoint: "http://localhost:8006".to_string(),
            timeout: 30,
        };
        assert!(timeout_err.is_retryable());
        
        let http_err = ArgusError::EvidenceFetchHttpError {
            endpoint: "http://localhost:8006".to_string(),
            status: 500,
            body: "Internal server error".to_string(),
        };
        assert!(!http_err.is_retryable());
    }
    
    #[test]
    fn test_evidence_error_codes() {
        let err = EvidenceError::QuoteGenerationFailed {
            reason: "TDX not available".to_string(),
        };
        assert_eq!(err.error_code(), "EV002");
    }
}