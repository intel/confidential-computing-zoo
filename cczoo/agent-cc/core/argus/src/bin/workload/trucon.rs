// Copyright (c) 2026 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//! Read a fixed, fully uploaded measurement history from the root-only TruCon UDS.
use anyhow::{bail, Context, Result};
use serde::Deserialize;
use std::{collections::HashSet, path::Path};

pub const DEFAULT_SOCKET: &str = "/var/run/trucon/trucon.sock";

#[derive(Debug)]
pub struct HistoryFailure(pub &'static str);
impl std::fmt::Display for HistoryFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.0)
    }
}
impl std::error::Error for HistoryFailure {}

#[derive(Debug, Deserialize, Clone, PartialEq, Eq)]
// A snapshot describes one complete, confirmed prefix. Rekor references remain
// lookup hints until Trustee authenticates their contents and replays RTMR2.
pub struct Snapshot {
    pub chain_id: String,
    pub sequence_num: usize,
    pub mr_value: String,
    pub head_log_id: String,
    pub log_ids: Vec<String>,
}

impl Snapshot {
    fn validate(&self) -> Result<()> {
        let hex = |s: &str| {
            s.bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
        };
        if self.chain_id != "default"
            || !(2..=4096).contains(&self.sequence_num)
            || self.sequence_num != self.log_ids.len()
            || self.mr_value.len() != 96
            || !hex(&self.mr_value)
            || self.log_ids.last() != Some(&self.head_log_id)
            || self.log_ids.iter().any(|id| {
                let index = (1..64).contains(&id.len()) && id.bytes().all(|c| c.is_ascii_digit());
                let uuid = matches!(id.len(), 64 | 80) && hex(id);
                !(index || uuid)
            })
            || self.log_ids.iter().collect::<HashSet<_>>().len() != self.sequence_num
        {
            bail!("invalid TruCon measurement snapshot");
        }
        Ok(())
    }
}

#[cfg(unix)]
pub fn snapshot(path: &Path) -> Result<Snapshot> {
    use std::io::{Read, Write};
    use std::os::unix::{
        fs::{FileTypeExt, MetadataExt},
        net::UnixStream,
    };
    use std::time::Duration;
    let meta = std::fs::symlink_metadata(path)?;
    if !meta.file_type().is_socket() || meta.uid() != 0 || meta.mode() & 0o077 != 0 {
        bail!("TruCon socket must be root-owned and mode 0600");
    }
    let mut stream = UnixStream::connect(path).context("connect TruCon")?;
    stream.set_read_timeout(Some(Duration::from_secs(5)))?;
    stream.set_write_timeout(Some(Duration::from_secs(5)))?;
    // The service tag selects a read-only role; the UDS gateway authenticates
    // the local peer. A caller-supplied tag alone does not grant access.
    stream.write_all(b"GET /chain-state?include_history=true HTTP/1.1\r\nHost: localhost\r\nX-TruCon-Caller-Service: argus_provider\r\nConnection: close\r\n\r\n")?;
    let mut bytes = Vec::new();
    (&mut stream).take(524289).read_to_end(&mut bytes)?;
    decode_response(&bytes)
}

#[cfg(not(unix))]
pub fn snapshot(_: &Path) -> Result<Snapshot> {
    bail!("TruCon UDS requires Linux")
}

fn decode_response(bytes: &[u8]) -> Result<Snapshot> {
    // This local gateway uses a bounded Content-Length response. Reject other
    // framing or truncated bodies instead of appraising a partial history.
    if bytes.len() > 524288 {
        bail!("TruCon response exceeds limit");
    }
    let split = bytes
        .windows(4)
        .position(|v| v == b"\r\n\r\n")
        .context("invalid HTTP response")?;
    if split > 8192 {
        bail!("TruCon headers exceed limit");
    }
    let headers = std::str::from_utf8(&bytes[..split])?;
    let mut lines = headers.split("\r\n");
    let status = lines.next().and_then(|l| l.split_whitespace().nth(1));
    let mut content_length = None;
    let mut reason = None;
    for line in lines {
        let (name, value) = line.split_once(':').context("invalid HTTP header")?;
        if name.eq_ignore_ascii_case("x-argus-reason") {
            if reason.is_some() {
                bail!("duplicate reason code");
            }
            reason = Some(value.trim());
        }
        if name.eq_ignore_ascii_case("transfer-encoding") {
            bail!("unsupported transfer encoding");
        }
        if name.eq_ignore_ascii_case("content-length") {
            if content_length.is_some() {
                bail!("duplicate content length");
            }
            content_length = Some(value.trim().parse::<usize>()?);
        }
    }
    let body = &bytes[split + 4..];
    if content_length != Some(body.len()) {
        bail!("incomplete TruCon response");
    }
    if status != Some("200") {
        let code = match (status, reason) {
            (Some("409"), Some("MUTATION_PENDING")) => "MUTATION_PENDING",
            (Some("409"), Some("HISTORY_CAPACITY")) => "HISTORY_CAPACITY",
            (Some("409"), Some("HISTORY_NOT_CONFIRMED")) => "HISTORY_NOT_CONFIRMED",
            (Some("404"), Some("HISTORY_MISSING")) => "HISTORY_MISSING",
            _ => "HISTORY_UNAVAILABLE",
        };
        return Err(HistoryFailure(code).into());
    }
    let snapshot: Snapshot = serde_json::from_slice(body)?;
    snapshot.validate()?;
    Ok(snapshot)
}
