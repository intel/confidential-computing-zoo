//! Argus v1 - Application-non-invasive runtime trust verification framework
//!
//! This library provides Intel TDX quote verification for agent-to-service
//! communication. It enables callers to verify that peer services run in
//! expected Intel TDX trusted execution environments.
//!
//! # Core Components
//!
//! - [`ArgusEngine`] - Main facade for end-to-end target verification
//! - [`EvidenceEngine`] - Service-side evidence generation
//! - [`RaAdapter`] - TDX verifier abstraction
//! - [`PolicyEvaluator`] - Caller-side policy evaluation
//!
//! # Usage
//!
//! ```rust
//! use argus::{ArgusEngine, TargetService, GuardContext, engine::MockEvidenceFetcher, policy::AllowAllPolicyEvaluator};
//! use std::sync::Arc;
//!
//! #[tokio::main]
//! async fn main() -> anyhow::Result<()> {
//!     // Create engine with mock evidence fetcher for testing
//!     // In production, use ArgusEngine::new() with a real EvidenceFetcherHttp
//!     let engine = ArgusEngine::with_components(
//!         Arc::new(MockEvidenceFetcher::new()),
//!         Arc::new(argus::RaAdapter::new()),
//!         Arc::new(AllowAllPolicyEvaluator::new()),
//!     );
//!     let target = TargetService::new("my-service", "https://my-service.local");
//!     let context = GuardContext::new("caller-1", vec![]);
//!
//!     let decision = engine.verify_target(&target, &context).await?;
//!     println!("Decision: {:?}", decision);
//!     Ok(())
//! }
//! ```

pub mod types;
pub mod errors;
pub mod engine;
pub mod verifier;
pub mod policy;
pub mod binding;
pub mod service;
pub mod tc_api_client;

pub use errors::{ArgusError, EvidenceError, Result};
pub use types::*;
pub use engine::{ArgusEngine, EvidenceFetcher, MockEvidenceFetcher, RaVerifier, PolicyEvaluatorTrait};
pub use binding::ServiceRuntimeBinding;
pub use verifier::RaAdapter;
pub use policy::{PolicyEvaluator, AllowAllPolicyEvaluator, DenyAllPolicyEvaluator, ConfigurablePolicyEvaluator, PolicyConfig, CompositeRequirementConfig};
pub use service::EvidenceEngine;
pub use tc_api_client::{TcApiClient, ServiceMetadataFetcher, ServiceMetadataResponse};