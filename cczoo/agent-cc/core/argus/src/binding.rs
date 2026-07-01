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

//! Service Runtime Binding - Local integration layer
//!
//! Exposes local runtime metadata to Evidence Engine.

use crate::types::*;
use anyhow::Result;
use async_trait::async_trait;
use std::collections::HashMap;

/// Service runtime binding trait for local metadata collection.
#[async_trait]
pub trait ServiceRuntimeBinding: Send + Sync {
    /// Return the local logical service identifier.
    async fn service_name(&self) -> Result<String>;

    /// Return stable service identifier from deployment domain.
    async fn service_id(&self) -> Result<Option<String>>;

    /// Return resolved image digest (sha256:...).
    async fn image_digest(&self) -> Result<Option<String>>;

    /// Return canonical executable digest when observable.
    async fn executable_digest(&self) -> Result<Option<String>>;

    /// Return local runtime facts binding target endpoint to workload instance.
    async fn runtime_binding(&self, target_uri: &str) -> Result<RuntimeBindingContext>;

    /// Return locally accessible service credentials when available.
    async fn service_credentials(&self) -> Result<Option<ServiceCredentials>>;
}

/// Local service runtime binding implementation.
///
/// Reads from environment variables and local filesystem metadata
/// that would be populated by a container runtime or orchestrator.
pub struct LocalServiceRuntimeBinding {
    // Configuration values from environment
    config: HashMap<String, String>,
}

impl LocalServiceRuntimeBinding {
    pub fn new() -> Self {
        Self {
            config: std::env::vars().collect(),
        }
    }
}

impl Default for LocalServiceRuntimeBinding {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl ServiceRuntimeBinding for LocalServiceRuntimeBinding {
    async fn service_name(&self) -> Result<String> {
        Ok(self
            .config
            .get("ARGUS_SERVICE_NAME")
            .cloned()
            .or_else(|| self.config.get("HOSTNAME").cloned())
            .unwrap_or_else(|| "unknown".to_string()))
    }

    async fn service_id(&self) -> Result<Option<String>> {
        Ok(self.config.get("ARGUS_SERVICE_ID").cloned())
    }

    async fn image_digest(&self) -> Result<Option<String>> {
        let digest = self.config.get("ARGUS_IMAGE_DIGEST").cloned();
        if let Some(ref d) = digest {
            if !d.starts_with("sha256:") {
                return Ok(Some(format!("sha256:{}", d)));
            }
            return Ok(Some(d.clone()));
        }
        Ok(None)
    }

    async fn executable_digest(&self) -> Result<Option<String>> {
        Ok(self.config.get("ARGUS_EXECUTABLE_DIGEST").cloned())
    }

    async fn runtime_binding(&self, target_uri: &str) -> Result<RuntimeBindingContext> {
        use std::time::{SystemTime, UNIX_EPOCH};

        let pid = std::process::id();
        let start_time = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs()
            .to_string();

        let container_id = self.config.get("CONTAINER_ID").or_else(|| self.config.get("HOSTNAME")).cloned();
        let pod_uid = self.config.get("POD_UID").cloned();
        let namespace = self.config.get("NAMESPACE").cloned();
        let vm_instance_id = self.config.get("VM_INSTANCE_ID").cloned();

        // Try to read cgroup path
        let cgroup_path = std::fs::read_to_string("/proc/self/cgroup")
            .ok()
            .and_then(|content| {
                content
                    .lines()
                    .find(|line| line.starts_with("0:"))
                    .map(|line| line.split(':').last().unwrap_or("").trim().to_string())
            });

        Ok(RuntimeBindingContext {
            endpoint: target_uri.to_string(),
            owning_pid: pid,
            process_start_time: start_time,
            container_id,
            pod_uid,
            vm_instance_id,
            namespace,
            cgroup_path,
        })
    }

    async fn service_credentials(&self) -> Result<Option<ServiceCredentials>> {
        let spiffe_id = self.config.get("SPIFFE_ID").cloned();
        let cert_path = self.config.get("CERT_CHAIN_PATH");
        let token_path = self.config.get("SERVICE_TOKEN_PATH");

        let certificate_chain_pem = cert_path.and_then(|path| {
            std::fs::read_to_string(path)
                .ok()
                .map(|content| content.lines().map(|l| l.to_string()).collect())
        });

        let token = token_path.and_then(|path| std::fs::read_to_string(path).ok().map(|t| t.trim().to_string()));

        if spiffe_id.is_some() || certificate_chain_pem.is_some() || token.is_some() {
            return Ok(Some(ServiceCredentials {
                spiffe_id,
                certificate_chain_pem,
                token,
            }));
        }
        Ok(None)
    }
}

/// Mock service runtime binding for testing.
pub struct MockServiceRuntimeBinding {
    service_name: String,
    service_id: Option<String>,
    instance_id: String,
}

impl MockServiceRuntimeBinding {
    pub fn new(
        service_name: impl Into<String>,
        service_id: Option<String>,
        instance_id: impl Into<String>,
    ) -> Self {
        Self {
            service_name: service_name.into(),
            service_id,
            instance_id: instance_id.into(),
        }
    }
}

impl Default for MockServiceRuntimeBinding {
    fn default() -> Self {
        Self {
            service_name: "test-service".to_string(),
            service_id: Some("test-id-001".to_string()),
            instance_id: "test-instance-001".to_string(),
        }
    }
}

#[async_trait]
impl ServiceRuntimeBinding for MockServiceRuntimeBinding {
    async fn service_name(&self) -> Result<String> {
        Ok(self.service_name.clone())
    }

    async fn service_id(&self) -> Result<Option<String>> {
        Ok(self.service_id.clone())
    }

    async fn image_digest(&self) -> Result<Option<String>> {
        Ok(Some("sha256:abc123def456789012345678901234567890123456789012345678901234abcd".to_string()))
    }

    async fn executable_digest(&self) -> Result<Option<String>> {
        Ok(Some("sha256:def456789012345678901234567890123456789012345678901234567890abc".to_string()))
    }

    async fn runtime_binding(&self, target_uri: &str) -> Result<RuntimeBindingContext> {
        Ok(RuntimeBindingContext {
            endpoint: target_uri.to_string(),
            owning_pid: 12345,
            process_start_time: "1718000000".to_string(),
            container_id: Some("test-container-001".to_string()),
            pod_uid: Some("test-pod-uid-001".to_string()),
            vm_instance_id: None,
            namespace: Some("default".to_string()),
            cgroup_path: Some("/docker/test".to_string()),
        })
    }

    async fn service_credentials(&self) -> Result<Option<ServiceCredentials>> {
        Ok(Some(ServiceCredentials {
            spiffe_id: Some("spiffe://test.trust.domain/test-service".to_string()),
            certificate_chain_pem: None,
            token: None,
        }))
    }
}