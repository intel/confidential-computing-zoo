//! Policy Evaluator - Caller-side policy evaluation
//!
//! Evaluates normalized verifier output against caller policy.

use crate::errors::{ArgusError, Result};
use crate::types::*;
use anyhow::Context;
use async_trait::async_trait;

pub use crate::engine::PolicyEvaluatorTrait;

/// Policy evaluator for caller-side policy evaluation.
pub struct PolicyEvaluator {
    policy: AuthorizationSubjectPolicy,
}

impl PolicyEvaluator {
    pub fn new() -> Self {
        Self {
            policy: AuthorizationSubjectPolicy {
                kind: AuthorizationSubjectKind::Workload,
                proxy_mode: ProxyPolicyMode::Ignore,
                composite_requirements: vec![CompositeRequirement {
                    claim_path: "service_identity.service_name".to_string(),
                    required_level: BindingAssuranceLevel::L2,
                }],
            },
        }
    }

    pub fn with_policy(policy: AuthorizationSubjectPolicy) -> Self {
        Self { policy }
    }

    fn compare_assurance(
        &self,
        actual: BindingAssuranceLevel,
        required: BindingAssuranceLevel,
    ) -> std::cmp::Ordering {
        actual.cmp(&required)
    }

    fn check_required_claims(&self, claims: &VerifiedClaims) -> Vec<String> {
        let mut missing = Vec::new();

        for req in &self.policy.composite_requirements {
            if let Some(ref binding_claims) = claims.binding_claims {
                let field = req.claim_path.strip_prefix("service_identity.").unwrap_or(&req.claim_path);
                match field {
                    "service_name" => {
                        if binding_claims.service_identity.service_name.is_empty() {
                            missing.push(req.claim_path.clone());
                        }
                    }
                    "instance_id" => {
                        if binding_claims.service_identity.instance_id.is_empty() {
                            missing.push(req.claim_path.clone());
                        }
                    }
                    _ => {}
                }
            } else if req.claim_path.starts_with("service_identity.") {
                missing.push(req.claim_path.clone());
            }
        }

        missing
    }
}

impl Default for PolicyEvaluator {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl crate::engine::PolicyEvaluatorTrait for PolicyEvaluator {
    async fn evaluate_policy(
        &self,
        target: &TargetService,
        claims: &VerifiedClaims,
        context: &GuardContext,
    ) -> GuardDecision {
        tracing::debug!(
            target: "argus::policy",
            "Starting policy evaluation"
        );

        // Step 1: Check binding assurance level
        let min_level = self
            .policy
            .composite_requirements
            .iter()
            .map(|r| r.required_level)
            .max()
            .unwrap_or(BindingAssuranceLevel::L2);

        if self.compare_assurance(claims.binding_assurance_level, min_level) == std::cmp::Ordering::Less
        {
            tracing::warn!(
                target: "argus::policy",
                "Policy denied: insufficient binding assurance level"
            );
            return GuardDecision::Deny {
                reason: DenyReason::PolicyRejected,
                claims: Some(claims.clone()),
            };
        }

        // Step 2: Verify required claim paths
        let missing = self.check_required_claims(claims);
        if !missing.is_empty() {
            tracing::warn!(
                target: "argus::policy",
                "Policy denied: missing required claims"
            );
            return GuardDecision::Deny {
                reason: DenyReason::MissingRequiredClaim,
                claims: Some(claims.clone()),
            };
        }

        // Step 3: Check service name matches target
        if let Some(ref binding_claims) = claims.binding_claims {
            let actual_name = &binding_claims.service_identity.service_name;
            if !actual_name.is_empty() && actual_name != &target.service_name {
                // Case-insensitive check
                if actual_name.to_lowercase() != target.service_name.to_lowercase() {
                    tracing::warn!(
                        target: "argus::policy",
                        "Policy denied: identity conflict"
                    );
                    return GuardDecision::Deny {
                        reason: DenyReason::IdentityConflict,
                        claims: Some(claims.clone()),
                    };
                }
            }
        }

        // Step 4: Check quote validity
        if !claims.quote_valid {
            tracing::warn!(
                target: "argus::policy",
                "Policy denied: quote invalid"
            );
            return GuardDecision::Deny {
                reason: DenyReason::QuoteInvalid,
                claims: Some(claims.clone()),
            };
        }

        // Step 5: All checks passed
        tracing::info!(
            target: "argus::policy",
            "Policy evaluation passed"
        );
        GuardDecision::Allow(claims.clone())
    }
}

/// Permissive policy evaluator for testing.
/// Always returns Allow.
pub struct AllowAllPolicyEvaluator;

impl AllowAllPolicyEvaluator {
    pub fn new() -> Self {
        Self
    }
}

impl Default for AllowAllPolicyEvaluator {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl crate::engine::PolicyEvaluatorTrait for AllowAllPolicyEvaluator {
    async fn evaluate_policy(
        &self,
        _target: &TargetService,
        claims: &VerifiedClaims,
        _context: &GuardContext,
    ) -> GuardDecision {
        GuardDecision::Allow(claims.clone())
    }
}

/// Restrictive policy evaluator.
/// Always returns Deny for any policy evaluation.
pub struct DenyAllPolicyEvaluator;

impl DenyAllPolicyEvaluator {
    pub fn new() -> Self {
        Self
    }
}

impl Default for DenyAllPolicyEvaluator {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl crate::engine::PolicyEvaluatorTrait for DenyAllPolicyEvaluator {
    async fn evaluate_policy(
        &self,
        _target: &TargetService,
        claims: &VerifiedClaims,
        _context: &GuardContext,
    ) -> GuardDecision {
        GuardDecision::Deny {
            reason: DenyReason::PolicyRejected,
            claims: Some(claims.clone()),
        }
    }
}

/// Configuration for a composite policy requirement.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CompositeRequirementConfig {
    pub claim_path: String,
    pub required_level: BindingAssuranceLevel,
}

/// Policy configuration file format.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct PolicyConfig {
    /// Minimum required assurance level.
    #[serde(default)]
    pub min_assurance_level: BindingAssuranceLevel,
    /// List of composite requirements.
    #[serde(default)]
    pub composite_requirements: Vec<CompositeRequirementConfig>,
    /// Service name filter (optional).
    #[serde(default)]
    pub allowed_service_names: Vec<String>,
    /// Instance ID filter (optional).
    #[serde(default)]
    pub allowed_instance_ids: Vec<String>,
}

impl Default for PolicyConfig {
    fn default() -> Self {
        Self {
            min_assurance_level: BindingAssuranceLevel::L2,
            composite_requirements: vec![],
            allowed_service_names: vec![],
            allowed_instance_ids: vec![],
        }
    }
}

/// File-based configurable policy evaluator.
/// Loads policy configuration from a YAML file.
pub struct ConfigurablePolicyEvaluator {
    config: PolicyConfig,
}

impl ConfigurablePolicyEvaluator {
    /// Create a new evaluator with the given configuration.
    pub fn with_config(config: PolicyConfig) -> Self {
        Self { config }
    }

    /// Load configuration from a YAML file.
    pub fn from_file(path: impl AsRef<std::path::Path>) -> anyhow::Result<Self> {
        let content = std::fs::read_to_string(path.as_ref())
            .context(format!("Failed to read policy config from {:?}", path.as_ref()))?;
        let config: PolicyConfig = serde_yaml::from_str(&content)
            .context("Failed to parse policy config YAML")?;
        Ok(Self { config })
    }

    /// Load configuration from a YAML string.
    pub fn from_str(yaml: &str) -> anyhow::Result<Self> {
        let config: PolicyConfig = serde_yaml::from_str(yaml)
            .context("Failed to parse policy config YAML")?;
        Ok(Self { config })
    }

    fn check_service_name_allowed(&self, service_name: &str) -> bool {
        if self.config.allowed_service_names.is_empty() {
            return true;
        }
        self.config.allowed_service_names.iter()
            .any(|name| name.eq_ignore_ascii_case(service_name))
    }

    fn check_instance_id_allowed(&self, instance_id: &str) -> bool {
        if self.config.allowed_instance_ids.is_empty() {
            return true;
        }
        self.config.allowed_instance_ids.iter()
            .any(|id| id == instance_id)
    }
}

impl Default for ConfigurablePolicyEvaluator {
    fn default() -> Self {
        Self {
            config: PolicyConfig::default(),
        }
    }
}

#[async_trait]
impl crate::engine::PolicyEvaluatorTrait for ConfigurablePolicyEvaluator {
    async fn evaluate_policy(
        &self,
        target: &TargetService,
        claims: &VerifiedClaims,
        context: &GuardContext,
    ) -> GuardDecision {
        // Check binding assurance level
        if claims.binding_assurance_level < self.config.min_assurance_level {
            return GuardDecision::Deny {
                reason: DenyReason::PolicyRejected,
                claims: Some(claims.clone()),
            };
        }

        // Check service name filter
        if let Some(ref binding_claims) = claims.binding_claims {
            if !self.check_service_name_allowed(&binding_claims.service_identity.service_name) {
                return GuardDecision::Deny {
                    reason: DenyReason::IdentityConflict,
                    claims: Some(claims.clone()),
                };
            }

            // Check instance ID filter
            if !self.check_instance_id_allowed(&binding_claims.service_identity.instance_id) {
                return GuardDecision::Deny {
                    reason: DenyReason::IdentityConflict,
                    claims: Some(claims.clone()),
                };
            }
        }

        // Delegate to base PolicyEvaluator for composite requirements
        let base = PolicyEvaluator::new();
        base.evaluate_policy(target, claims, context).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_allow_all_policy_evaluator() {
        let evaluator = AllowAllPolicyEvaluator::new();
        let claims = VerifiedClaims {
            binding_assurance_level: BindingAssuranceLevel::L1,
            binding_claims: None,
            quote_valid: true,
            verifier_kind: VerifierKind::Trustee,
            verifier_id: "test-verifier".to_string(),
            tee_type: "tdx".to_string(),
            report_data: "test-report-data".to_string(),
            verified_claim_assurance: None,
            tcb_status: None,
            measurements: ExportMeasurementClaims::default(),
            attested_issuance: None,
            identity_claims: None,
            verified_at: "2024-01-01T00:00:00Z".to_string(),
            expires_at: None,
        };
        let target = TargetService::new("test", "https://test.local");
        let context = GuardContext::new("test", vec![]);

        let decision = evaluator.evaluate_policy(&target, &claims, &context).await;
        assert!(matches!(decision, GuardDecision::Allow(_)));
    }

    #[tokio::test]
    async fn test_deny_all_policy_evaluator() {
        let evaluator = DenyAllPolicyEvaluator::new();
        let claims = VerifiedClaims {
            binding_assurance_level: BindingAssuranceLevel::L2,
            binding_claims: None,
            quote_valid: true,
            verifier_kind: VerifierKind::Trustee,
            verifier_id: "test-verifier".to_string(),
            tee_type: "tdx".to_string(),
            report_data: "test-report-data".to_string(),
            verified_claim_assurance: None,
            tcb_status: None,
            measurements: ExportMeasurementClaims::default(),
            attested_issuance: None,
            identity_claims: None,
            verified_at: "2024-01-01T00:00:00Z".to_string(),
            expires_at: None,
        };
        let target = TargetService::new("test", "https://test.local");
        let context = GuardContext::new("test", vec![]);

        let decision = evaluator.evaluate_policy(&target, &claims, &context).await;
        assert!(matches!(decision, GuardDecision::Deny { reason: DenyReason::PolicyRejected, .. }));
    }

    #[tokio::test]
    async fn test_configurable_policy_from_str() {
        let yaml = r#"
min_assurance_level: L2
allowed_service_names:
  - my-service
  - other-service
"#;
        let evaluator = ConfigurablePolicyEvaluator::from_str(yaml).unwrap();
        assert_eq!(evaluator.config.min_assurance_level, BindingAssuranceLevel::L2);
        assert_eq!(evaluator.config.allowed_service_names.len(), 2);
    }

    #[tokio::test]
    async fn test_configurable_policy_service_name_filter() {
        let yaml = r#"
min_assurance_level: L1
allowed_service_names:
  - allowed-service
"#;
        let evaluator = ConfigurablePolicyEvaluator::from_str(yaml).unwrap();
        
        // Service name in allowed list
        assert!(evaluator.check_service_name_allowed("allowed-service"));
        assert!(evaluator.check_service_name_allowed("ALLOWED-SERVICE")); // case insensitive
        
        // Service name not in allowed list
        assert!(!evaluator.check_service_name_allowed("other-service"));
    }

    #[tokio::test]
    async fn test_configurable_policy_empty_allow_list() {
        let yaml = r#"
min_assurance_level: L1
"#;
        let evaluator = ConfigurablePolicyEvaluator::from_str(yaml).unwrap();
        
        // Empty allow list means all service names are allowed
        assert!(evaluator.check_service_name_allowed("any-service"));
        assert!(evaluator.check_service_name_allowed("another-service"));
    }

    #[tokio::test]
    async fn test_policy_config_default() {
        let config = PolicyConfig::default();
        assert_eq!(config.min_assurance_level, BindingAssuranceLevel::L2);
        assert!(config.composite_requirements.is_empty());
        assert!(config.allowed_service_names.is_empty());
        assert!(config.allowed_instance_ids.is_empty());
    }
}