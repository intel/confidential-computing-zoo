//! TC-API Client - Client for querying TC-API service metadata
//!
//! This module provides a client for querying service metadata from the TC-API
//! server. It is used by the EvidenceEngine to fetch service information for
//! generating binding claims during TDX attestation.

use crate::types::*;
use anyhow::{Context, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::Duration;

/// TC-API client for querying service metadata
#[derive(Clone)]
pub struct TcApiClient {
    client: Client,
    base_url: String,
    auth_token: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ServiceMetadataQuery {
    pub container_id: Option<String>,
    pub workload_id: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ServiceMetadataResponse {
    pub workload_id: String,
    pub container_id: Option<String>,
    pub launch_id: Option<String>,
    pub image_digest: Option<String>,
    pub service_name: Option<String>,
    pub created_at: Option<String>,
    pub last_seen_at: Option<String>,
}

impl TcApiClient {
    /// Create a new TC-API client
    pub fn new(base_url: impl Into<String>) -> Self {
        Self {
            client: Client::builder()
                .timeout(Duration::from_secs(10))
                .build()
                .expect("Failed to create HTTP client"),
            base_url: base_url.into(),
            auth_token: None,
        }
    }

    /// Set the authentication token
    pub fn with_auth_token(self, token: impl Into<String>) -> Self {
        Self {
            auth_token: Some(token.into()),
            ..self
        }
    }

    /// Query service metadata by container ID
    pub async fn query_by_container(&self, container_id: &str) -> Result<ServiceMetadataResponse> {
        let query = ServiceMetadataQuery {
            container_id: Some(container_id.to_string()),
            workload_id: None,
        };
        self.query_metadata(&query).await
    }

    /// Query service metadata by workload ID
    pub async fn query_by_workload_id(&self, workload_id: &str) -> Result<ServiceMetadataResponse> {
        let query = ServiceMetadataQuery {
            container_id: None,
            workload_id: Some(workload_id.to_string()),
        };
        self.query_metadata(&query).await
    }

    async fn query_metadata(&self, query: &ServiceMetadataQuery) -> Result<ServiceMetadataResponse> {
        let url = format!("{}/api/service-metadata/workload/query", self.base_url);

        let mut request = self.client.post(&url).json(query);

        if let Some(ref token) = self.auth_token {
            request = request.header("Authorization", format!("Bearer {}", token));
        }

        let response = request.send().await?.error_for_status().with_context(|| {
            format!("Failed to query service metadata: {}", url)
        })?;

        response.json().await.context("Failed to parse service metadata response")
    }
}

/// Trait for fetching service metadata from TC-API
#[async_trait]
pub trait ServiceMetadataFetcher: Send + Sync {
    /// Fetch service metadata for the current service
    async fn fetch_metadata(&self) -> Result<ServiceMetadataResponse>;
}

/// TC-API based service metadata fetcher
pub struct TcApiServiceMetadataFetcher {
    client: Arc<TcApiClient>,
    container_id: String,
}

impl TcApiServiceMetadataFetcher {
    /// Create a new TC-API service metadata fetcher
    pub fn new(client: Arc<TcApiClient>, container_id: impl Into<String>) -> Self {
        Self {
            client,
            container_id: container_id.into(),
        }
    }
}

#[async_trait]
impl ServiceMetadataFetcher for TcApiServiceMetadataFetcher {
    async fn fetch_metadata(&self) -> Result<ServiceMetadataResponse> {
        self.client.query_by_container(&self.container_id).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_client_creation() {
        let client = TcApiClient::new("http://localhost:8000");
        assert_eq!(client.base_url, "http://localhost:8000");
    }

    #[tokio::test]
    async fn test_client_with_auth() {
        let client = TcApiClient::new("http://localhost:8000")
            .with_auth_token("test-token");
        assert!(client.auth_token.is_some());
    }
}