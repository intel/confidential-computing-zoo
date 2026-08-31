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

//! TDX Node Evidence Provider binary.
//!
//! The Provider serves the guest-local SPIRE Agent over a Unix domain socket.
//! It binds the fixed Agent identity, the Server challenge, and the Agent proof
//! key into TDX REPORTDATA, then returns the raw Quote produced by Linux TSM.
//! Quote appraisal remains in the Server-side Trustee path, and SPIRE remains
//! responsible for issuing the Agent SVID.

use anyhow::{anyhow, bail, Context, Result};
use axum::{
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::post,
    Json, Router,
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha384};
use std::{
    ffi::{OsStr, OsString},
    path::{Path, PathBuf},
    sync::Arc,
};
use tdx_quote::{tsm::TsmInstanceQuoteGenerator, QuoteError, ReportData};

const DEFAULT_SOCKET_PATH: &str = "/run/argus/evidence-provider.sock";
const DEFAULT_TSM_REPORT_ROOT: &str = "/sys/kernel/config/tsm/report";

// Keep these values byte-for-byte aligned with the Go NodeAttestor protocol.
const NODE_BINDING_DOMAIN: &[u8] = b"argus.node.tdx.reportdata";
const NODE_AGENT_ID: &[u8] = b"spiffe://argus.local/spire/agent/argus_tdx/openviking-node";

/// Runtime paths for the guest-local socket and Linux TSM report interface.
#[derive(Debug, PartialEq, Eq)]
struct Config {
    socket_path: PathBuf,
    tsm_report_root: PathBuf,
}

impl Config {
    fn parse(args: impl IntoIterator<Item = OsString>) -> Result<Self> {
        let mut socket_path = PathBuf::from(DEFAULT_SOCKET_PATH);
        let mut tsm_report_root = PathBuf::from(DEFAULT_TSM_REPORT_ROOT);
        let mut args = args.into_iter();

        while let Some(argument) = args.next() {
            match argument.as_os_str() {
                value if value == OsStr::new("--socket-path") => {
                    socket_path = PathBuf::from(
                        args.next()
                            .ok_or_else(|| anyhow!("--socket-path requires a value"))?,
                    );
                }
                value if value == OsStr::new("--tsm-report-root") => {
                    tsm_report_root = PathBuf::from(
                        args.next()
                            .ok_or_else(|| anyhow!("--tsm-report-root requires a value"))?,
                    );
                }
                _ => bail!("unknown argument: {:?}", argument),
            }
        }

        Ok(Self {
            socket_path,
            tsm_report_root,
        })
    }
}

/// Inputs that the SPIRE Agent requires the Quote to bind.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct NodeEvidenceRequest {
    nonce: String,
    proof_public_key: String,
}

/// Verifier-neutral raw TDX Quote returned to the SPIRE Agent.
#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
struct NodeEvidenceResponse {
    evidence_type: String,
    quote_format: String,
    quote: String,
}

/// Isolates hardware Quote generation from the HTTP contract and its tests.
trait QuoteSource: Send + Sync {
    fn generate_quote(&self, report_data: &ReportData) -> Result<Vec<u8>, QuoteError>;
}

impl QuoteSource for TsmInstanceQuoteGenerator {
    fn generate_quote(&self, report_data: &ReportData) -> Result<Vec<u8>, QuoteError> {
        self.generate_quote_bytes(report_data)
    }
}

#[derive(Clone)]
struct AppState {
    quote_source: Arc<dyn QuoteSource>,
}

#[derive(Debug)]
enum ProviderError {
    InvalidRequest(String),
    Quote(QuoteError),
    QuoteTask(tokio::task::JoinError),
}

impl IntoResponse for ProviderError {
    fn into_response(self) -> Response {
        match self {
            Self::InvalidRequest(message) => (StatusCode::BAD_REQUEST, message).into_response(),
            Self::Quote(error) => {
                tracing::error!("TDX quote generation failed: {error}");
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "TDX quote generation failed",
                )
                    .into_response()
            }
            Self::QuoteTask(error) => {
                tracing::error!("TDX quote task failed: {error}");
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "TDX quote generation failed",
                )
                    .into_response()
            }
        }
    }
}

fn decode_fixed_32(field: &str, encoded: &str) -> Result<[u8; 32], ProviderError> {
    let decoded = URL_SAFE_NO_PAD
        .decode(encoded)
        .map_err(|_| ProviderError::InvalidRequest(format!("{field} is not base64url-no-pad")))?;
    decoded
        .try_into()
        .map_err(|_| ProviderError::InvalidRequest(format!("{field} must decode to 32 bytes")))
}

fn append_lp16(buffer: &mut Vec<u8>, value: &[u8]) {
    buffer.extend_from_slice(&(value.len() as u16).to_be_bytes());
    buffer.extend_from_slice(value);
}

/// Build the frozen Node binding shared with the Server NodeAttestor.
///
/// The first 48 REPORTDATA bytes are SHA-384 over length-prefixed domain and
/// Agent ID values followed by the 32-byte nonce and proof public key. The
/// `ReportData` type zero-fills the remaining 16 bytes required by TDX.
fn node_report_data(nonce: &[u8; 32], proof_public_key: &[u8; 32]) -> ReportData {
    let mut runtime_data = Vec::with_capacity(
        2 + NODE_BINDING_DOMAIN.len()
            + 2
            + NODE_AGENT_ID.len()
            + nonce.len()
            + proof_public_key.len(),
    );
    append_lp16(&mut runtime_data, NODE_BINDING_DOMAIN);
    append_lp16(&mut runtime_data, NODE_AGENT_ID);
    runtime_data.extend_from_slice(nonce);
    runtime_data.extend_from_slice(proof_public_key);

    let digest = Sha384::digest(runtime_data);
    ReportData::from_digest(&digest).expect("SHA-384 digest fits in TDX REPORTDATA")
}

/// Generate one fresh Quote for a Server-authored Node challenge.
async fn node_evidence_handler(
    State(state): State<AppState>,
    Json(request): Json<NodeEvidenceRequest>,
) -> Result<Json<NodeEvidenceResponse>, ProviderError> {
    let nonce = decode_fixed_32("nonce", &request.nonce)?;
    let proof_public_key = decode_fixed_32("proof_public_key", &request.proof_public_key)?;
    let report_data = node_report_data(&nonce, &proof_public_key);
    let quote_source = state.quote_source;
    // TSM configfs I/O is blocking, so keep it off the async HTTP worker.
    let quote = tokio::task::spawn_blocking(move || quote_source.generate_quote(&report_data))
        .await
        .map_err(ProviderError::QuoteTask)?
        .map_err(ProviderError::Quote)?;

    Ok(Json(NodeEvidenceResponse {
        evidence_type: "tdx_quote".to_string(),
        quote_format: "tdx".to_string(),
        quote: URL_SAFE_NO_PAD.encode(quote),
    }))
}

/// Expose only the Node Evidence API used by the SPIRE Agent plugin.
fn router(quote_source: Arc<dyn QuoteSource>) -> Router {
    Router::new()
        .route("/node-evidence", post(node_evidence_handler))
        .with_state(AppState { quote_source })
}

/// Removes only the socket created by this Provider when the listener exits.
#[cfg(unix)]
struct SocketGuard(PathBuf);

#[cfg(unix)]
impl Drop for SocketGuard {
    fn drop(&mut self) {
        use std::io;
        use std::os::unix::fs::FileTypeExt;

        match std::fs::symlink_metadata(&self.0) {
            Ok(metadata) if metadata.file_type().is_socket() => {
                if let Err(error) = std::fs::remove_file(&self.0) {
                    tracing::error!(path = %self.0.display(), %error, "remove Provider socket failed");
                }
            }
            Ok(_) => {}
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => {
                tracing::error!(path = %self.0.display(), %error, "inspect Provider socket during cleanup failed");
            }
        }
    }
}

/// Bind the protected guest-local socket, replacing a stale socket only.
#[cfg(unix)]
fn bind_socket(path: &Path) -> Result<(tokio::net::UnixListener, SocketGuard)> {
    use std::io;
    use std::os::unix::fs::{FileTypeExt, PermissionsExt};

    match std::fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_socket() => std::fs::remove_file(path)
            .with_context(|| format!("remove stale socket {}", path.display()))?,
        Ok(_) => bail!("socket path exists and is not a socket: {}", path.display()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => return Err(error.into()),
    }

    let listener = tokio::net::UnixListener::bind(path)
        .with_context(|| format!("bind Unix socket {}", path.display()))?;
    let guard = SocketGuard(path.to_path_buf());
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o660))
        .with_context(|| format!("set Unix socket permissions on {}", path.display()))?;
    Ok((listener, guard))
}

/// Wait for either interactive shutdown or the service manager's terminate signal.
#[cfg(unix)]
async fn shutdown_signal() -> std::io::Result<()> {
    let mut terminate = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    tokio::select! {
        result = tokio::signal::ctrl_c() => result,
        _ = terminate.recv() => Ok(()),
    }
}

/// Serve HTTP/1 connections over the Provider's Unix domain socket.
#[cfg(unix)]
async fn serve(config: Config) -> Result<()> {
    use hyper::server::conn::http1;
    use hyper_util::{rt::TokioIo, service::TowerToHyperService};

    let quote_source = Arc::new(TsmInstanceQuoteGenerator::with_path(config.tsm_report_root));
    let app = router(quote_source);
    let (listener, _socket_guard) = bind_socket(&config.socket_path)?;
    tracing::info!(socket = %config.socket_path.display(), "TDX Evidence Provider listening");

    let shutdown = shutdown_signal();
    tokio::pin!(shutdown);
    loop {
        tokio::select! {
            accepted = listener.accept() => {
                let (stream, _) = accepted?;
                let service = TowerToHyperService::new(app.clone());
                tokio::spawn(async move {
                    if let Err(error) = http1::Builder::new()
                        .serve_connection(TokioIo::new(stream), service)
                        .await
                    {
                        tracing::error!("UDS HTTP connection failed: {error}");
                    }
                });
            }
            result = &mut shutdown => {
                result?;
                break;
            }
        }
    }

    Ok(())
}

#[cfg(unix)]
#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    serve(Config::parse(std::env::args_os().skip(1))?).await
}

#[cfg(not(unix))]
fn main() -> Result<()> {
    bail!("argus-tdx-evidence-provider requires Unix domain sockets")
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::Body,
        http::{Request, StatusCode},
    };
    use base64::Engine as _;
    use http_body_util::BodyExt;
    use std::sync::Mutex;
    use tower::ServiceExt;

    struct RecordingQuoteSource {
        quote: Vec<u8>,
        report_data: Mutex<Option<[u8; 64]>>,
    }

    impl QuoteSource for RecordingQuoteSource {
        fn generate_quote(&self, report_data: &ReportData) -> Result<Vec<u8>, QuoteError> {
            *self.report_data.lock().unwrap() = Some(*report_data.as_aligned_bytes());
            Ok(self.quote.clone())
        }
    }

    struct FailingQuoteSource;

    impl QuoteSource for FailingQuoteSource {
        fn generate_quote(&self, _report_data: &ReportData) -> Result<Vec<u8>, QuoteError> {
            Err(std::io::Error::new(std::io::ErrorKind::NotFound, "TSM unavailable").into())
        }
    }

    fn request(body: serde_json::Value) -> Request<Body> {
        Request::builder()
            .method("POST")
            .uri("/node-evidence")
            .header("content-type", "application/json")
            .body(Body::from(serde_json::to_vec(&body).unwrap()))
            .unwrap()
    }

    #[tokio::test]
    async fn node_evidence_returns_raw_tdx_quote_bound_to_nonce_and_proof_key() {
        let quote_source = Arc::new(RecordingQuoteSource {
            quote: vec![0xde, 0xad, 0xbe, 0xef],
            report_data: Mutex::new(None),
        });
        let nonce: [u8; 32] = std::array::from_fn(|index| index as u8);
        let proof_public_key: [u8; 32] = std::array::from_fn(|index| (index + 32) as u8);

        let response = router(quote_source.clone())
            .oneshot(request(serde_json::json!({
                "nonce": URL_SAFE_NO_PAD.encode(nonce),
                "proof_public_key": URL_SAFE_NO_PAD.encode(proof_public_key),
            })))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = response.into_body().collect().await.unwrap().to_bytes();
        assert_eq!(
            serde_json::from_slice::<NodeEvidenceResponse>(&body).unwrap(),
            NodeEvidenceResponse {
                evidence_type: "tdx_quote".to_string(),
                quote_format: "tdx".to_string(),
                quote: "3q2-7w".to_string(),
            }
        );

        let report_data = quote_source.report_data.lock().unwrap().unwrap();
        assert_eq!(
            hex::encode(report_data),
            "1f827005b702f0f5faeba4839f30bbf3b39846ccb6c4dfb3366c70a215a74181e99b7f441be8d5d4ea984c114643237100000000000000000000000000000000"
        );
    }

    #[tokio::test]
    async fn node_evidence_rejects_unknown_request_fields() {
        let response = router(Arc::new(RecordingQuoteSource {
            quote: vec![1],
            report_data: Mutex::new(None),
        }))
        .oneshot(request(serde_json::json!({
            "nonce": URL_SAFE_NO_PAD.encode([0x11; 32]),
            "proof_public_key": URL_SAFE_NO_PAD.encode([0x22; 32]),
            "workload": "not-part-of-node-evidence"
        })))
        .await
        .unwrap();

        assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
    }

    #[tokio::test]
    async fn node_evidence_requires_unpadded_base64url_with_exact_lengths() {
        let app = router(Arc::new(RecordingQuoteSource {
            quote: vec![1],
            report_data: Mutex::new(None),
        }));
        let padded_nonce = base64::engine::general_purpose::URL_SAFE.encode([0x11; 32]);

        let padded_response = app
            .clone()
            .oneshot(request(serde_json::json!({
                "nonce": padded_nonce,
                "proof_public_key": URL_SAFE_NO_PAD.encode([0x22; 32]),
            })))
            .await
            .unwrap();
        assert_eq!(padded_response.status(), StatusCode::BAD_REQUEST);

        let short_response = app
            .oneshot(request(serde_json::json!({
                "nonce": URL_SAFE_NO_PAD.encode([0x11; 31]),
                "proof_public_key": URL_SAFE_NO_PAD.encode([0x22; 32]),
            })))
            .await
            .unwrap();
        assert_eq!(short_response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn node_evidence_fails_when_tsm_quote_generation_fails() {
        let response = router(Arc::new(FailingQuoteSource))
            .oneshot(request(serde_json::json!({
                "nonce": URL_SAFE_NO_PAD.encode([0x11; 32]),
                "proof_public_key": URL_SAFE_NO_PAD.encode([0x22; 32]),
            })))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
    }

    #[tokio::test]
    async fn provider_exposes_only_the_node_evidence_route() {
        let app = router(Arc::new(RecordingQuoteSource {
            quote: vec![1],
            report_data: Mutex::new(None),
        }));

        let health = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(health.status(), StatusCode::NOT_FOUND);

        let generic_evidence = app
            .oneshot(
                Request::builder()
                    .uri("/evidence")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(generic_evidence.status(), StatusCode::NOT_FOUND);
    }

    #[test]
    fn config_uses_frozen_runtime_defaults() {
        assert_eq!(
            Config::parse(Vec::<OsString>::new()).unwrap(),
            Config {
                socket_path: PathBuf::from(DEFAULT_SOCKET_PATH),
                tsm_report_root: PathBuf::from(DEFAULT_TSM_REPORT_ROOT),
            }
        );
    }
}
