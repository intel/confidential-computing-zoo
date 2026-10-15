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

//! Independent Linux observation and the workload JCS/SHA-384 binding.
use anyhow::{bail, Context, Result};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use serde_json::Value;
use sha2::{Digest, Sha256, Sha384};
use std::{collections::BTreeMap, fs, io::Read, path::Path};
use tdx_quote::ReportData;
pub mod trucon;

pub type Target = BTreeMap<String, String>;
pub const PROTOCOL: &str = "argus.workload.tdx";
const FIELDS: &[&str] = &[
    "agent_id",
    "boot_id",
    "config_digest",
    "config_env",
    "config_path",
    "container_id",
    "executable",
    "image_config_digest",
    "launch_id",
    "listen_port",
    "net_namespace",
    "pid",
    "pid_namespace",
    "policy_id",
    "rootfs_read_only",
    "start_time",
    "workload_id",
];

fn decimal(s: &str) -> bool {
    !s.starts_with('0') && !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit())
}
fn hex(s: &str, n: usize) -> bool {
    s.len() == n
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn digest(s: &str) -> bool {
    s.strip_prefix("sha256:").is_some_and(|v| hex(v, 64))
}
// Keep this schema aligned with the Go protocol: string-only ASCII values and
// sorted keys make the same target hash identically in each language.
pub fn validate(t: &Target) -> Result<()> {
    if t.len() != FIELDS.len() || FIELDS.iter().any(|f| !t.contains_key(*f)) {
        bail!("invalid target schema");
    }
    if t.values()
        .any(|v| v.bytes().any(|b| !(32..=126).contains(&b)))
    {
        bail!("target values must be printable ASCII");
    }
    super::validate_agent_id(&t["agent_id"])?;
    let key = t["config_env"].as_bytes();
    if key.is_empty()
        || key.len() > 128
        || !(key[0].is_ascii_alphabetic() || key[0] == b'_')
        || !key.iter().all(|b| b.is_ascii_alphanumeric() || *b == b'_')
    {
        bail!("invalid configuration environment variable");
    }
    if t["rootfs_read_only"] != "true" {
        bail!("invalid node or filesystem binding");
    }
    let boot = &t["boot_id"];
    if boot.len() != 36
        || [8, 13, 18, 23].iter().any(|i| boot.as_bytes()[*i] != b'-')
        || !hex(&boot.replace('-', ""), 32)
    {
        bail!("invalid boot ID");
    }
    if !hex(&t["container_id"], 64)
        || !digest(&t["image_config_digest"])
        || !digest(&t["config_digest"])
    {
        bail!("actual image/config digests required");
    }
    for f in ["pid", "start_time", "listen_port"] {
        if !decimal(&t[f]) {
            bail!("invalid decimal {f}");
        }
    }
    let pid = t["pid"].parse::<i32>()?;
    let port = t["listen_port"].parse::<u16>()?;
    if pid <= 0 || port == 0 {
        bail!("invalid PID or port");
    }
    for f in ["workload_id", "policy_id", "launch_id"] {
        let v = &t[f];
        if v.is_empty()
            || v.len() > 128
            || !v
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"_.-".contains(&b))
        {
            bail!("invalid {f}");
        }
    }
    for (f, prefix) in [("pid_namespace", "pid:["), ("net_namespace", "net:[")] {
        if !t[f]
            .strip_prefix(prefix)
            .and_then(|s| s.strip_suffix(']'))
            .is_some_and(decimal)
        {
            bail!("invalid namespace");
        }
    }
    for f in ["config_path", "executable"] {
        let p = &t[f];
        if !p.starts_with('/')
            || p == "/"
            || p.ends_with('/')
            || p.split('/')
                .skip(1)
                .any(|s| s.is_empty() || s == "." || s == "..")
        {
            bail!("invalid target path");
        }
    }
    Ok(())
}
pub fn runtime_data(t: &Target, nonce: &str) -> Result<Target> {
    validate(t)?;
    let decoded = URL_SAFE_NO_PAD.decode(nonce)?;
    if decoded.len() != 32 || URL_SAFE_NO_PAD.encode(decoded) != nonce {
        bail!("invalid nonce");
    }
    let mut data = t.clone();
    data.insert("nonce".into(), nonce.into());
    data.insert("protocol".into(), PROTOCOL.into());
    Ok(data)
}
pub fn report_data(data: &Target) -> Result<ReportData> {
    let mut target = data.clone();
    let nonce = target.remove("nonce").context("missing nonce")?;
    if target.remove("protocol").as_deref() != Some(PROTOCOL) {
        bail!("invalid protocol");
    }
    runtime_data(&target, &nonce)?;
    // Sorted keys + ASCII string values give identical RFC 8785 JSON in Rust/Go/Trustee.
    Ok(ReportData::from_digest(&Sha384::digest(
        serde_json::to_vec(data)?,
    ))?)
}
fn bounded(path: impl AsRef<Path>, max: u64) -> Result<Vec<u8>> {
    let mut v = Vec::new();
    fs::File::open(path)?.take(max + 1).read_to_end(&mut v)?;
    if v.len() as u64 > max {
        bail!("input exceeds limit");
    }
    Ok(v)
}
// Restrict Docker mount destinations and keep declared configuration/executable
// paths outside the writable data and /tmp paths. Guest root and Docker metadata
// remain trusted; these checks do not measure writable data or process memory.
fn validate_mounts(c: &Value, t: &Target, data_path: &Path) -> Result<()> {
    for key in ["config_path", "executable"] {
        let path = Path::new(&t[key]);
        if path.starts_with(data_path) || path.starts_with("/tmp") {
            bail!("configuration or executable overlaps a writable mount");
        }
    }
    let mounts = c["Mounts"].as_array().context("missing mounts")?;
    for mount in mounts {
        let dest = mount["Destination"].as_str().context("invalid mount")?;
        if dest != t["config_path"]
            && Path::new(dest) != data_path
            && !(dest == "/tmp" && mount["Type"] == "tmpfs")
        {
            bail!("unapproved workload mount");
        }
        if dest == t["config_path"] && mount["RW"] != false {
            bail!("configuration mount must be read-only");
        }
    }
    if !mounts
        .iter()
        .any(|m| m["Destination"].as_str() == Some(&t["config_path"]) && m["RW"] == false)
    {
        bail!("missing read-only configuration mount");
    }
    Ok(())
}
#[cfg(not(target_os = "linux"))]
pub fn load_and_check(_: &Path, _: &Path) -> Result<Target> {
    bail!("Workload evidence requires Linux");
}
#[cfg(target_os = "linux")]
pub fn load_and_check(path: &Path, data_path: &Path) -> Result<Target> {
    use std::{os::unix::fs::MetadataExt, process::Command};
    // The registration is a protected observation record, not a substitute for
    // observing Docker and /proc again when a fresh Quote is requested.
    let meta = fs::symlink_metadata(path)?;
    if !meta.is_file() || meta.uid() != 0 || meta.mode() & 0o022 != 0 {
        bail!("target registration must be root-owned and protected");
    }
    let parent = fs::metadata(path.parent().context("registration parent required")?)?;
    if parent.uid() != 0 || parent.mode() & 0o022 != 0 {
        bail!("registration directory must be root-owned and protected");
    }
    let t: Target = serde_json::from_slice(&bounded(path, 32768)?)?;
    validate(&t)?;
    // Re-observe Docker's content ID instead of accepting the registration's
    // image digest alone. Docker and the guest root collecting it remain trusted.
    let out = Command::new("timeout")
        .args(["10s", "docker", "inspect", &t["container_id"]])
        .output()?;
    if !out.status.success() || out.stdout.len() > 1 << 20 {
        bail!("docker inspect failed");
    }
    let values: Vec<Value> = serde_json::from_slice(&out.stdout)?;
    if values.len() != 1 {
        bail!("expected one container");
    }
    let c = &values[0];
    if c["Id"].as_str() != Some(&t["container_id"])
        || c["Image"].as_str() != Some(&t["image_config_digest"])
        || c["State"]["Running"] != true
        || c["HostConfig"]["ReadonlyRootfs"] != true
        || c["HostConfig"]["Privileged"] != false
        || c["Config"]["Labels"]["io.trucon.launch-id"].as_str() != Some(&t["launch_id"])
        || c["Config"]["Labels"]["io.trucon.workload-id"].as_str() != Some(&t["workload_id"])
    {
        bail!("container differs from registration");
    }
    let init = c["State"]["Pid"]
        .as_u64()
        .context("missing container PID")?;
    let env = c["Config"]["Env"]
        .as_array()
        .context("missing workload environment")?;
    // The config-path key is declared per application. Require the same binding
    // in Docker's startup environment and in the actual server process below.
    let prefix = format!("{}=", t["config_env"]);
    let values: Vec<_> = env
        .iter()
        .filter_map(Value::as_str)
        .filter(|e| e.starts_with(&prefix))
        .collect();
    if values.len() != 1 || values[0] != format!("{}{}", prefix, t["config_path"]) {
        bail!("workload configuration path is not active");
    }
    if c["HostConfig"]["NetworkMode"] == "host" || c["HostConfig"]["PidMode"] == "host" {
        bail!("isolated container namespaces required");
    }
    validate_mounts(c, &t, data_path)?;
    let pid = &t["pid"];
    let root = format!("/proc/{pid}");
    let process_env = bounded(format!("{root}/environ"), 1 << 20)?;
    let bindings: Vec<_> = process_env
        .split(|b| *b == 0)
        .filter(|e| e.starts_with(prefix.as_bytes()))
        .collect();
    let expected = format!("{}{}", prefix, t["config_path"]);
    if bindings.len() != 1 || bindings[0] != expected.as_bytes() {
        bail!("process configuration environment differs from registration");
    }
    if fs::read_to_string("/proc/sys/kernel/random/boot_id")?.trim() != t["boot_id"] {
        bail!("boot changed");
    }
    let stat = fs::read_to_string(format!("{root}/stat"))?;
    let fields: Vec<_> = stat
        .rsplit_once(") ")
        .context("invalid process stat")?
        .1
        .split_whitespace()
        .collect();
    if fields.len() < 20 || fields[0] == "Z" || fields[0] == "X" || fields[19] != t["start_time"] {
        bail!("process incarnation changed");
    }
    for (f, n) in [("pid_namespace", "pid"), ("net_namespace", "net")] {
        if fs::read_link(format!("{root}/ns/{n}"))?.to_str() != Some(&t[f])
            || fs::read_link(format!("/proc/{init}/ns/{n}"))?
                != fs::read_link(format!("{root}/ns/{n}"))?
        {
            bail!("namespace changed");
        }
    }
    if fs::read_link(format!("{root}/exe"))?.to_str() != Some(&t["executable"])
        || !fs::read_to_string(format!("{root}/cgroup"))?.contains(&t["container_id"])
    {
        bail!("process/container binding changed");
    }
    // Hash the file visible inside this process's mount namespace, including
    // the read-only configuration bind mount checked above.
    let config = bounded(format!("{root}/root{}", t["config_path"]), 4 << 20)?;
    if format!("sha256:{}", hex::encode(Sha256::digest(config))) != t["config_digest"] {
        bail!("configuration changed");
    }
    if listener_pid(pid, &t["listen_port"], &t["pid_namespace"])? != *pid {
        bail!("target is not the unique loopback listener");
    }
    Ok(t)
}
#[cfg(target_os = "linux")]
fn listener_pid(anchor: &str, port: &str, namespace: &str) -> Result<String> {
    // /proc/<pid>/net is namespace-wide. Match the loopback socket inode to
    // exactly one process's FDs instead of treating the anchor PID as its owner.
    let expected = port.parse::<u16>()?;
    let mut sockets = Vec::new();
    for proto in ["tcp", "tcp6"] {
        for line in fs::read_to_string(format!("/proc/{anchor}/net/{proto}"))?
            .lines()
            .skip(1)
        {
            let f: Vec<_> = line.split_whitespace().collect();
            if f.len() < 10 || f[3] != "0A" {
                continue;
            }
            let (addr, p) = f[1].split_once(':').context("invalid tcp row")?;
            if u16::from_str_radix(p, 16)? != expected {
                continue;
            }
            if proto != "tcp" || addr != "0100007F" {
                bail!("workload must listen only on IPv4 loopback");
            }
            sockets.push(format!("socket:[{}]", f[9]));
        }
    }
    if sockets.len() != 1 {
        bail!("expected exactly one service socket");
    }
    let mut owners = Vec::new();
    for e in fs::read_dir("/proc")?.flatten() {
        let pid = e.file_name().to_string_lossy().into_owned();
        if !decimal(&pid) {
            continue;
        }
        if fs::read_link(e.path().join("ns/pid"))
            .ok()
            .and_then(|p| p.to_str().map(str::to_owned))
            .as_deref()
            != Some(namespace)
        {
            continue;
        }
        let Ok(fds) = fs::read_dir(e.path().join("fd")) else {
            continue;
        };
        if fds.flatten().any(|fd| {
            fs::read_link(fd.path())
                .ok()
                .and_then(|p| p.to_str().map(str::to_owned))
                .as_deref()
                == Some(&sockets[0])
        }) {
            owners.push(pid);
        }
    }
    if owners.len() != 1 {
        bail!("listener is shared or absent");
    }
    Ok(owners.remove(0))
}
