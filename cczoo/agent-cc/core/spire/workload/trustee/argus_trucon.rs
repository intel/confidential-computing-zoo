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

//! Trustee integration for TruCon workload history verification.
//!
//! `prepare` checks untrusted request fields before TDX verification.
//! After the TDX verifier authenticates the Quote and its REPORTDATA binding,
//! `appraise` verifies the referenced history and adds server-owned TruCon claims.
use crate::{HashAlgorithm, Tee};
use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use std::{path::Path, process::Stdio, time::Duration};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWriteExt},
    process::Command,
};

static SLOTS: tokio::sync::Semaphore = tokio::sync::Semaphore::const_new(4);

// Stage only lookup references and runtime data here. They become usable for
// appraisal only after the calling AS path verifies TDX and REPORTDATA.
pub fn prepare(
    tee: &Tee,
    evidence: &Value,
    runtime: &Value,
    algorithm: &HashAlgorithm,
) -> Result<Option<Value>> {
    let references = evidence.get("rekor_entry_ids");
    let workload = runtime.get("protocol").and_then(Value::as_str) == Some("argus.workload.tdx");
    if !workload && references.is_none() {
        return Ok(None);
    }
    if *tee != Tee::Tdx || !workload || algorithm.digest(b"").len() != 48 {
        bail!("TruCon evidence requires TDX and SHA-384 bound workload runtime_data");
    }
    let refs = references
        .and_then(Value::as_array)
        .context("missing Rekor reference list")?;
    if !(2..=4096).contains(&refs.len()) {
        bail!("invalid Rekor reference count");
    }
    let mut seen = std::collections::HashSet::new();
    for reference in refs {
        let s = reference
            .as_str()
            .context("Rekor reference must be a string")?;
        let index = (1..64).contains(&s.len()) && s.bytes().all(|c| c.is_ascii_digit());
        let uuid = matches!(s.len(), 64 | 80)
            && s.bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c));
        if !(index || uuid) || !seen.insert(s) {
            bail!("invalid or duplicate Rekor reference");
        }
    }
    Ok(Some(
        json!({"rekor_entry_ids": refs, "runtime_data": runtime}),
    ))
}

fn protected(path: &Path) -> Result<()> {
    let meta = std::fs::symlink_metadata(path)?;
    if !meta.is_file() {
        bail!("verifier/config must be regular files");
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if meta.uid() != 0 || meta.mode() & 0o022 != 0 {
            bail!("verifier/config must be root-owned without group/other write");
        }
    }
    Ok(())
}

async fn bounded(mut stream: impl AsyncRead + Unpin, limit: u64) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    (&mut stream)
        .take(limit + 1)
        .read_to_end(&mut bytes)
        .await?;
    if bytes.len() as u64 > limit {
        bail!("TruCon verifier output exceeds limit");
    }
    Ok(bytes)
}

pub async fn appraise(request: Option<&Value>, claims: &mut Value, tee_class: &str) -> Result<()> {
    // Never retain an input or preexisting verdict under our reserved namespace.
    claims
        .as_object_mut()
        .context("TEE claims must be an object")?
        .remove("trucon");
    let Some(request) = request else {
        return Ok(());
    };
    if tee_class != "cpu" {
        bail!("TruCon requires TDX CPU claims");
    }
    let mut request = request.clone();
    // RTMR2 comes from authenticated TDX claims, never from a caller's supplied
    // history, runtime data, or claimed verification result.
    request["rtmr2"] = claims
        .pointer("/quote/body/rtmr_2")
        .context("authenticated RTMR2 is missing")?
        .clone();
    let bytes = serde_json::to_vec(&request)?;
    if bytes.len() > 524288 {
        bail!("TruCon request exceeds size limit");
    }
    let executable =
        std::env::var("ARGUS_TRUCON_VERIFIER").context("TruCon verifier is not configured")?;
    let config =
        std::env::var("ARGUS_TRUCON_CONFIG").context("TruCon trust configuration is missing")?;
    if !Path::new(&executable).is_absolute() || !Path::new(&config).is_absolute() {
        bail!("verifier paths must be absolute");
    }
    protected(Path::new(&executable))?;
    protected(Path::new(&config))?;
    // Queueing and subprocess work share the same budget. Clearing the
    // environment prevents inherited proxy/Python settings changing verification.
    let result = tokio::time::timeout(Duration::from_secs(50), async {
        let _permit = SLOTS.acquire().await?;
        let mut child = Command::new(&executable)
            .arg(&config)
            .env_clear()
            .env("PATH", "/usr/bin:/bin")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true)
            .spawn()
            .context("start TruCon verifier")?;
        let mut stdin = child.stdin.take().context("verifier stdin")?;
        let stdout = child.stdout.take().context("verifier stdout")?;
        let stderr = child.stderr.take().context("verifier stderr")?;
        let write = async {
            stdin.write_all(&bytes).await?;
            drop(stdin);
            Ok::<(), anyhow::Error>(())
        };
        // Drain both output pipes while writing input so a full pipe cannot
        // deadlock the child; kill_on_drop also covers timeout/error exits.
        let (_, output, errors) =
            tokio::try_join!(write, bounded(stdout, 16384), bounded(stderr, 4096))?;
        let status = child.wait().await?;
        if !status.success() {
            bail!(
                "TruCon verifier rejected evidence: {}",
                String::from_utf8_lossy(&errors)
            );
        }
        let value: Value = serde_json::from_slice(&output).context("invalid verifier result")?;
        if value.get("verified") != Some(&Value::Bool(true)) {
            bail!("TruCon verifier did not affirm evidence");
        }
        Ok::<Value, anyhow::Error>(value)
    })
    .await
    .context("TruCon verifier timeout")??;
    claims["trucon"] = result;
    Ok(())
}
