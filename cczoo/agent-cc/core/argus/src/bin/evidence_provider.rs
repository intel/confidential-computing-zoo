//! Evidence Provider binary
//!
//! Runs the Argus Evidence Provider service as an HTTP server.
//! Provides TDX quote generation and evidence endpoints for attestation.

use argus::types::*;
use argus::binding::LocalServiceRuntimeBinding;
use argus::service::EvidenceEngine;
use argus::tc_api_client::TcApiClient;
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

#[derive(Clone)]
struct AppState {
    engine: Arc<EvidenceEngine>,
    tc_api_client: Option<Arc<TcApiClient>>,
}

async fn health_handler() -> &'static str {
    "OK"
}

async fn evidence_handler(
    State(state): State<AppState>,
    Json(request): Json<EvidenceRequest>,
) -> Result<Json<Evidence>, StatusCode> {
    // If TC-API client is configured, create engine with it
    let evidence = if let Some(ref tc_api) = state.tc_api_client {
        let engine = EvidenceEngine::with_tc_api_client(
            Arc::new(LocalServiceRuntimeBinding::new()),
            (*tc_api).clone(),
        );
        engine.handle_evidence_request(&request).await.map_err(|e| {
            tracing::error!("Failed to generate evidence: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?
    } else {
        state.engine.handle_evidence_request(&request).await.map_err(|e| {
            tracing::error!("Failed to generate evidence: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?
    };

    Ok(Json(evidence))
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt::init();

    // Get configuration from environment
    let host = std::env::var("HOST").unwrap_or_else(|_| "0.0.0.0".to_string());
    let port: u16 = std::env::var("PORT")
        .unwrap_or_else(|_| "8006".to_string())
        .parse()
        .unwrap_or(8006);
    let tc_api_url = std::env::var("TC_API_URL")
        .unwrap_or_else(|_| "http://localhost:8000".to_string());

    // Create runtime binding
    let runtime = Arc::new(LocalServiceRuntimeBinding::new());

    // Create TC-API client if URL is configured
    let tc_api_client = if tc_api_url != "disabled" {
        Some(Arc::new(TcApiClient::new(&tc_api_url)))
    } else {
        None
    };

    // Create evidence engine
    let engine = Arc::new(EvidenceEngine::new(runtime));

    // Create app state
    let state = AppState {
        engine,
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
        .route("/ra/v1/evidence", post(evidence_handler))
        .with_state(state)
        .layer(cors);

    // Parse address
    let addr: SocketAddr = format!("{}:{}", host, port)
        .parse()
        .expect("Failed to parse address");

    tracing::info!("Argus Evidence Provider starting on {}", addr);
    tracing::info!("Evidence endpoint: POST /ra/v1/evidence");
    tracing::info!("Health endpoint: GET /health");

    // Start server
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}