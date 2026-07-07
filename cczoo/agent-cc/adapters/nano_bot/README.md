# CoCo + Intel TDX + nano_bot

## Overview

This project demonstrates how to run a chat-bot workload inside a Confidential Containers (CoCo) environment with Intel TDX. It shows how to deploy a Ruby-based chatbot (`nano_bot`) as a payload container within a confidential guest VM, using a custom Linux kernel instead of the default Asterinas kernel.

## Prerequisites

This project assumes you already have a **working CoCo + Kata + Intel TDX**
host stack (the "CoCo dev container", named `asterinas-coco-tdx` by default)
with:

- Docker running, with a container running the CoCo/Kata/containerd/kubelet
  stack (kubectl reachable via `docker exec <container> kubectl ...`).
- A pre-existing, working Asterinas (or other baseline) Kata runtime TOML for
  QEMU+TDX (`SOURCE_RUNTIME_CFG`), used only as a template to derive the
  Linux-kernel runtime config from - it is never modified.
- A self-compiled Linux guest kernel binary with vsock + overlayfs +
  `/dev/tdx_guest` support built in (see the sibling `linux-coco-tdx` project
  for how one was built and validated) and the matching Kata `initrd`.
- On the true host (not the CoCo dev container): `docker`, `skopeo`.

If you don't have this base stack yet, this repo isn't a starting point for
that part - it only adds nano_bot on top of an already-working CoCo/TDX/Linux
guest kernel setup.

### Getting `asterinas-coco-tdx`

This repository does not build the CoCo dev container for you. It assumes you
already have a working Asterinas CoCo development container and, by default,
expects it to be named `asterinas-coco-tdx`.

The recommended source is the official Asterinas confidential-containers
`tools/docker` workflow:

- upstream path: `https://github.com/asterinas/confidential-containers/tree/main/tools/docker`
- image family: `asterinas/coco:<version>`
- bootstrap entrypoint inside the container: `/opt/coco/setup-coco-k8s.sh`

You have two practical ways to obtain it.

#### Option 1: Start from an existing `asterinas/coco:<version>` image

If you already have access to a published `asterinas/coco:<version>` image,
start it with the same runtime requirements documented by upstream and name it
`asterinas-coco-tdx` so this repo works without extra overrides:

```bash
docker run -it --rm \
  --name asterinas-coco-tdx \
  --privileged \
  --cgroupns host \
  --device /dev/kvm \
  --device /dev/vhost-vsock \
  --tmpfs /var/lib/containerd-nydus:rw,size=512m \
  asterinas/coco:<DOCKER_IMAGE_VERSION> \
  bash
```

Then bootstrap CoCo inside the container:

```bash
/opt/coco/setup-coco-k8s.sh
```

After bootstrap, verify the baseline runtime before using this repo:

```bash
kubectl apply -f /opt/coco/manifests/alpine-kata-qemu-tdx.yaml
kubectl get pods -w
```

#### Option 2: Build the dev container from upstream `tools/docker`

If you do not already have a usable `asterinas/coco` image, build it from the
official repository:

```bash
git clone https://github.com/asterinas/confidential-containers.git
cd confidential-containers/tools/docker

DOCKER_BUILDKIT=1 docker build --progress=plain \
  --build-arg ASTERINAS_BASE_IMAGE=asterinas/asterinas:<DOCKER_IMAGE_VERSION> \
  --build-arg KATA_RELEASE_PACKAGE_URL=<asterinas-kata-release-package-url> \
  --build-arg COCO_RELEASE_PACKAGE_URL=<confidential-containers-release-package-url> \
  -t asterinas/coco:<DOCKER_IMAGE_VERSION> \
  .
```

Then start it with the same runtime flags as above:

```bash
docker run -it --rm \
  --name asterinas-coco-tdx \
  --privileged \
  --cgroupns host \
  --device /dev/kvm \
  --device /dev/vhost-vsock \
  --tmpfs /var/lib/containerd-nydus:rw,size=512m \
  asterinas/coco:<DOCKER_IMAGE_VERSION> \
  bash
```

Inside the container, bootstrap Kubernetes + CoCo:

```bash
/opt/coco/setup-coco-k8s.sh
```

The upstream image already contains the baseline files this repo expects to
build on, including:

- `/opt/coco/config/configuration-qemu-tdx-asterinas.toml`
- `/etc/containerd/conf.d/50-coco-guest-pull.toml`
- `/opt/coco/prebuilt/asterinas-coco/kata-containers-initrd.img`

If you choose a different container name, export `CONTAINER_NAME=<your-name>`
before running this repo's scripts.

## Quick Start

```bash
# 0. Make sure the upstream Asterinas CoCo dev container is already running.
#    This repo does not create it for you; see "Getting asterinas-coco-tdx"
#    above if you still need to obtain/build/bootstrap it.

# 1. Point at your existing CoCo/TDX setup (all paths are yours, not secrets,
#    but there is no universal default so you must set them).
export SOURCE_RUNTIME_CFG=/opt/coco/config/configuration-qemu-tdx-asterinas.toml
export HOST_LINUX_KERNEL=/path/to/vmlinuz-6.16.0-vsock-net-tdxguest-builtin
export LINUX_INITRD=/opt/coco/prebuilt/asterinas-coco/kata-containers-initrd.img

# 2. Tell it which OpenAI-compatible endpoint/model to use. Never commit
#    these values - they are only ever passed as environment variables.
export OPENAI_API_ADDRESS=https://api.openai.com/v1   # your endpoint
export OPENAI_API_KEY=sk-...                          # your key
export NANO_BOT_MODEL=gpt-3.5-turbo                   # your model name

# 3. Only if your network requires an outbound HTTP proxy to reach the
#    endpoint above (omit entirely if you don't need one):
export PROXY_URL=http://your-proxy:port
# If your proxy does TLS interception with a self-signed CA, also set:
# export FARADAY_SSL_VERIFY=none

# 4. Run everything: builds+publishes the nano_bot image using tc-api, wires up the guest
#    registry mirror, prepares the Linux runtime config, deploys the Pod,
#    and runs a live chat test *inside* the TDX guest.
cd scripts && bash repro_linux_coco_tdx.sh
```

### Expected Output

During a healthy run, the script should print log phases like these:

```text
[2026-07-03 19:30:41] Starting CoCo + TDX + nano_bot flow.
[2026-07-03 19:30:43] Building/publishing the nano_bot image via a local registry.
[2026-07-03 19:30:48] Deploying CoCo TDX workload.
[2026-07-03 19:34:51] Workload deployed successfully.
==========================================
VM TEE Startup Capture (Step 1)
==========================================
==========================================
Workload Startup Verification (Step 7)
==========================================
NAME                           READY   STATUS    RESTARTS   AGE
nano-bot-kata-qemu-tdx-linux   1/1     Running   0          32s
==========================================
nano_bot Workload (Step 7 Extended)
==========================================
--- Probe Pod Log (node-local fallback) ---
... http=200
SUCCESS: Chat bot is running inside the TDX guest VM (pod: nano-bot-kata-qemu-tdx-linux)!
         Model: Qwen3.5-35B-A3B
[2026-07-03 19:41:03] Done. CoCo + TDX + nano_bot flow completed.
```

Treat the run as successful when all of the following are true:

- the main workload Pod reaches `READY 1/1` and `STATUS Running`
- the script prints `Workload deployed successfully.`
- the final guest-side chat probe returns `http=200`
- the script ends with `SUCCESS: Chat bot is running inside the TDX guest VM`

Important nuance: in some CoCo baselines, kubelet streaming APIs are blocked.
In that case you may still see lines such as `Failed to read /etc/os-release`
or `Failed to get process list` during `Workload Startup Verification`. Those
lines do not mean the run failed if the Pod is `Running` and the probe later
returns `http=200` plus the final `SUCCESS` line.

### Key Startup Logs To Watch

- `Starting CoCo + TDX + nano_bot flow.` means the orchestration entrypoint is running.
- `Restarting containerd with updated proxy bypasses.` is the critical proxy handoff point for guest image pulls.
- `Workload deployed successfully.` means Kubernetes accepted the Pod and it reached `Ready`.
- `VM TEE Startup Capture (Step 1)` marks the guest-boot evidence section.
- `Workload Startup Verification (Step 7)` prints the Pod status table you should inspect first.
- `--- Probe Pod Log (node-local fallback) ---` is the key chat-verification section when `kubectl exec`/`logs` are blocked.
- `http=200` confirms the guest reached the OpenAI-compatible endpoint successfully.
- `SUCCESS: Chat bot is running inside the TDX guest VM` is the end-to-end success marker.

### Continue Chatting After Startup

If your environment allows `kubectl exec`, the simplest way to keep chatting
with the already-running `nano_bot` container is to launch the interactive
client that is baked into the image:

```bash
CN=asterinas-coco-tdx
POD=nano-bot-kata-qemu-tdx-linux

docker exec -it $CN kubectl exec -it $POD -- /usr/local/bin/tdx-chat-bot.rb
```

Expected interactive banner:

```text
TDX Chat Bot initialized (model: <your-model>). Type 'quit' to exit.
Enter your message:
```

If you need a shell first, enter the Pod and run the client manually:

```bash
docker exec -it $CN kubectl exec -it $POD -- /bin/bash
/usr/local/bin/tdx-chat-bot.rb
```

If `kubectl exec` is blocked by kubelet proxy policy in your environment, the
script's built-in fallback is a one-shot probe rather than a persistent REPL.
In that case, rerun the probe with a new prompt:

```bash
NANO_BOT_TEST_PROMPT='Summarize the difference between TDX and SEV in 3 bullets.' \
RUN_WORKLOAD=0 \
RESTART_CONTAINERD=0 \
APPLY_RUNTIMECLASS=0 \
bash scripts/repro_linux_coco_tdx.sh
```

`OPENAI_API_KEY` is only needed the first time (it is stored as a Kubernetes
Secret and reused after that; you can also create the secret yourself ahead
of time and never export the key as a script argument at all - see below).

## Security Overview

This implementation leverages Confidential Containers (CoCo) with Intel TDX to provide strong security isolation for the nano_bot workload. The deployment uses a per-task trust domain approach, where each workload instance operates within its own dedicated confidential environment.

### Security Features

1. **Hardware-based Isolation**: Utilizes Intel TDX hardware isolation to create a confidential guest VM that protects the workload from the host and other VMs.

2. **Memory Encryption**: All guest memory is encrypted and protected by TDX, preventing unauthorized access to sensitive data even if the host system is compromised.

3. **Remote Attestation**: The guest VM can be remotely attested to prove its integrity and configuration to external parties.

4. **Secure Image Distribution**: Images are distributed securely through CoCo's guest-pull mechanism, ensuring that container images are only accessible within the confidential environment.

### Security Approach

The implementation follows a per-task trust domain model where each nano_bot workload instance operates within its own isolated confidential environment. This approach provides several key security advantages:

- **Stronger Isolation**: Each workload instance has its own dedicated trust domain, providing stronger isolation than sharing a single trust domain among multiple workloads.
- **Independent Security Controls**: Each workload can have its own security policies and configurations, allowing for fine-grained security management.
- **Reduced Risk of Cross-Workload Compromise**: If one workload is compromised, it does not automatically lead to compromise of other workloads running on the same host.
- **Simplified Compliance**: Security auditing and compliance verification can be performed on a per-task basis, making it easier to track and validate security controls for individual workloads.

### Threat Model

The threat model considers the following attack vectors:

1. **Host-level Attacks**: Assumes the host system may be compromised or untrusted. The TDX isolation ensures that even if the host is compromised, the guest workload remains protected.

2. **VM-to-VM Attacks**: Multiple VMs on the same host are isolated from each other through TDX hardware isolation.

3. **Privilege Escalation**: The TDX environment prevents privilege escalation attacks that could compromise the guest VM.

4. **Side-channel Attacks**: While TDX provides strong memory protection, side-channel attacks remain a concern and require additional mitigations.

5. **Supply Chain Attacks**: The use of tc-api for building images provides better audit trails and security features compared to local builds, reducing the risk of supply chain compromises.

### Additional Security Considerations

- **Container Image Integrity**: The use of tc-api for building container images provides better audit trails and security features compared to local builds, reducing the risk of supply chain compromises.
- **Network Security**: The implementation follows secure networking practices with proper proxy configuration and DNS resolution handling.
- **Access Control**: All sensitive information such as API keys are handled through Kubernetes Secrets, never stored in plain text or committed to source code.
- **Resource Management**: Each workload instance is isolated in its own resource allocation, preventing one workload from affecting others through resource exhaustion.

## Status

The full flow in this repo has been verified end-to-end: the nano_bot Pod
boots inside a real TDX guest VM, the guest-side chat probe reaches a real
OpenAI-compatible endpoint and returns `http=200`, and the script finishes
with `SUCCESS: Chat bot is running inside the TDX guest VM`. When kubelet
streaming APIs are allowed, you can also `kubectl exec` into the Pod and run
`/usr/local/bin/tdx-chat-bot.rb` interactively inside the guest.

> Image encryption/decryption and remote attestation of the guest are
> intentionally out of scope here. The image is pulled unencrypted via CoCo's
> normal guest-pull mechanism, same as any other unauthenticated OCI image.

## Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│ Host                                                                    │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ CoCo dev container (kubelet + containerd + Kata shim + QEMU)    │    │
│  │  ┌────────────────────────────────────────────────────────┐    │    │
│  │  │ QEMU / Intel TDX confidential guest VM                  │    │    │
│  │  │  Linux 6.16 guest kernel (this project) + kata-agent     │    │    │
│  │  │  ┌──────────────────────────────────────────────────┐   │    │    │
│  │  │  │ nano_bot container (Debian + ruby + ruby-openai)  │   │    │    │
│  │  │  │  -> calls out to an OpenAI-compatible API          │   │    │    │
│  │  │  └──────────────────────────────────────────────────┘   │    │    │
│  │  └────────────────────────────────────────────────────────┘    │    │
│  └────────────────────────────────────────────────────────────────┘    │
│  local, unauthenticated Docker registry (only used to hand the locally  │
│  built nano_bot image to the guest's Confidential Data Hub)             │
└────────────────────────────────────────────────────────────────────────┘
```

## Verified Versions

This exact combination is what the flow above was verified against. Other
versions may work, but if you hit something odd, check this list first -
several of the [Troubleshooting](#troubleshooting) entries below are
version/config-specific quirks of this stack.

| Component | Version |
|---|---|
| Host OS | CentOS Stream 9 |
| Host kernel | `6.18.10-tdx` (TDX-enabled) |
| Host CPU | Intel Xeon 6971E+ (TDX-capable) |
| TDX module | initialized at boot (`virt/tdx: module initialized`, private KeyID range `[64, 128)`) |
| Docker (host) | 29.3.0 |
| skopeo (host) | 1.22.0 |
| CoCo dev container base image | `asterinas/coco:0.18.0-20260603` |
| CoCo dev container OS | Ubuntu 24.04.4 LTS |
| containerd (in dev container) | v2.2.1 (`containerd/v2`) |
| Kubernetes (kubeadm/kubelet/kubectl) | v1.30.14 |
| nydus-snapshotter | v0.15.10 |
| Kata `containerd-shim-kata-v2` | 3.28.0 |
| QEMU (BKC flow, `kata-qemu-tdx-linux`) | 9.2.50 (`qemu-kvm-9.2.50-8.qemu_bkc_v1.6_2025.08.05.el9`) |
| QEMU (alternate flow, `kata-qemu-tdx-linux-qemu10`) | 10.2.1 |
| Guest kernel (this project's Linux guest) | self-compiled `6.16.0` (`vmlinuz-6.16.0-vsock-net-tdxguest-builtin`, see the sibling `linux-coco-tdx` project for the build) |
| Guest rootfs (Kata `initrd`) | Alpine-based minimal rootfs bundled with the CoCo dev container |
| nano_bot container base image | `ruby:3.3.3-slim-bookworm` (Debian 12 "bookworm") |
| ruby (in nano_bot image) | 3.3.3 |
| `nano-bots` gem | 3.4.0 |
| `ruby-openai` gem | 7.4.0 |
| babashka | v1.12.218 |

The guest image is fetched by CoCo's **guest-pull** mechanism: the actual
image bytes are pulled from *inside* the TDX guest VM (by the Confidential
Data Hub). To make this work, this repository sets up a local Docker registry
that is accessible only from the CoCo dev container. The nano_bot image is
first built and pushed to this local registry, then the guest's Confidential
Data Hub pulls it from there. This approach ensures secure image delivery
within the confidential environment, independent of the host's containerd cache.

## How It Works

`scripts/repro_linux_coco_tdx.sh` orchestrates the deployment process in the following steps:

1. **Preflight** - validates the CoCo dev container is running and required
   paths/env vars are set.
2. **Copy kernel + RuntimeClass + containerd handler** into the dev
   container, namespaced as `kata-qemu-tdx-linux` so it never touches the
   existing Asterinas runtime.
3. **Derive the Linux guest runtime TOML** from a full copy of
   `SOURCE_RUNTIME_CFG` (not a hand-written minimal one - Kata's runtime
   config has many required fields that are easy to silently drop), patching
   only the `kernel` and `kernel_params` fields.
4. **Restart containerd**, after making sure `/dev/log` exists (see
   [Troubleshooting](#troubleshooting)).
5. **Apply the RuntimeClass**.
6. **Ensure the `OPENAI_API_KEY` Kubernetes Secret exists** (creates it from
   `$OPENAI_API_KEY` if missing).
7. **Build, flatten, and publish the nano_bot image** via
   `build_and_push_nano_bot_image.sh` to a local registry started by
   `setup_local_registry.sh` (skipped entirely if you set `NANO_BOT_IMAGE`
   yourself to a reference that's already pullable some other way). This script
   uses tc-api for building the image instead of the traditional Docker build process.
8. **Wire up the guest registry mirror** via
   `configure_guest_registry_mirror.sh` so the TDX guest's Confidential Data
   Hub can actually fetch that locally-built image.
9. **Render and deploy the Pod manifest** entirely from environment
   variables (no template file with placeholders left lying around, no
   secrets ever written into a committed file).
10. **Capture guest TEE boot logs and verify the workload**.
11. **Run the chat bot test**. The script verifies guest connectivity with a
  one-shot probe Pod and reads the result from node-local Pod logs. If your
  environment allows `kubectl exec`, you can also run the interactive client
  manually inside the already-running guest Pod.

## Key Components Explained

- **`repro_linux_coco_tdx.sh`**: Main orchestration script that runs the complete deployment
- **`setup_local_registry.sh`**: Sets up a local Docker registry for secure image distribution
- **`build_and_push_nano_bot_image.sh`**: Builds and publishes the nano_bot container image using tc-api
- **`configure_guest_registry_mirror.sh`**: Configures the guest's Confidential Data Hub to use the local registry
- **`tdx-chat-bot.rb`**: The actual chat bot implementation that runs inside the TDX guest
- **`containerd-60-linux-coco-tdx.toml`**: Containerd configuration for the custom Linux runtime
- **`kernel-params-linux.txt`**: Optional kernel parameters for the custom Linux kernel

## Configuration

All configuration is via environment variables. Nothing here is a secret by
itself except `OPENAI_API_KEY`, which is never written to disk in this repo
- it only ever flows into a Kubernetes Secret.

### Required Variables

| Variable | Description |
|---|---|
| `SOURCE_RUNTIME_CFG` | Path (inside the CoCo dev container) to an existing, working Kata QEMU+TDX runtime TOML, used as the template. |
| `HOST_LINUX_KERNEL` | Path (on the true host) to your compiled Linux guest kernel `vmlinuz`. |
| `LINUX_INITRD` | Path (inside the CoCo dev container) to the Kata `initrd` to boot with. |
| `OPENAI_API_ADDRESS` | Base URL of your OpenAI-compatible API, e.g. `https://api.openai.com/v1`. |
| `OPENAI_API_KEY` | Your API key. Only required the first run, or if the `nano-bot-api-key` Secret doesn't already exist. |

### Networking Configuration

| Variable | Default | Description |
|---|---|---|
| `PROXY_URL` | *(empty = no proxy)* | Outbound HTTP proxy the guest should use to reach `OPENAI_API_ADDRESS`. |
| `NO_PROXY_VALUE` | `localhost,127.0.0.1,::1,10.96.0.0/12,10.244.0.0/16,10.88.0.0/16` | Proxy bypass list. The `10.88.0.0/16` bridge range matters when the guest-visible local registry is on the container bridge, e.g. `10.88.0.1:5000`. |
| `FARADAY_SSL_VERIFY` | *(empty = verify on)* | Set to `none` only if your proxy does TLS interception with a self-signed CA. |
| `ADD_HOST_ALIASES` | `1` | Auto-resolves the hostnames in `OPENAI_API_ADDRESS`/`PROXY_URL` on the *host* and injects them as Pod `hostAliases`. Useful if the cluster has no working in-cluster DNS (see [Troubleshooting](#troubleshooting)). |

### nano_bot / Image Configuration

| Variable | Default | Description |
|---|---|---|
| `NANO_BOT_MODEL` | `gpt-3.5-turbo` | Chat model name sent to the API. |
| `API_KEY_SECRET_NAME` | `nano-bot-api-key` | Name of the Kubernetes Secret holding the API key. |
| `API_KEY_SECRET_KEY` | `OPENAI_API_KEY` | Key within that Secret. |
| `NANO_BOT_IMAGE` | *(empty = build locally)* | If set, skip the local build/registry entirely and use this image reference directly (must already be pullable by the guest). |
| `USE_LOCAL_REGISTRY` | `1` | Whether to build+publish the image via a local registry when `NANO_BOT_IMAGE` is unset. |
| `IMAGE_NAME` / `IMAGE_TAG` | `nano_bot` / `1.0` | Local image name/tag. |
| `FORCE_REBUILD_IMAGE` | `0` | Force build the image even if it already exists locally. |
| `FLATTEN_IMAGE` | `1` | Flatten to a single layer before pushing (works around a docker-in-docker `CAP_MKNOD` limitation - see [Troubleshooting](#troubleshooting)). |
| `TC_API_BASE_URL` | `http://localhost:8000` | URL of the tc-api service used for building images. |

### Container / Pod / Feature Flags

| Variable | Default |
|---|---|
| `CONTAINER_NAME` | `asterinas-coco-tdx` |
| `POD_NAME` | `nano-bot-kata-qemu-tdx-linux` |
| `WAIT_TIMEOUT` | `600s` |
| `INSTALL_HANDLER` / `APPLY_RUNTIMECLASS` / `RESTART_CONTAINERD` / `RUN_WORKLOAD` / `RUN_NANO_BOT_TEST` / `FORCE_RECREATE_LINUX_CFG` | `1` (set to `0` to skip that step) |

## Common Usage Patterns

```bash
# Only rebuild/redeploy the workload, skip re-touching containerd/RuntimeClass
RESTART_CONTAINERD=0 APPLY_RUNTIMECLASS=0 bash scripts/repro_linux_coco_tdx.sh

# Use an image you already pushed somewhere else, skip the local registry entirely
NANO_BOT_IMAGE=myregistry.example.com/nano_bot:1.0 bash scripts/repro_linux_coco_tdx.sh

# Create the API key Secret yourself ahead of time, then never pass the key
# to this script at all:
docker exec asterinas-coco-tdx kubectl create secret generic nano-bot-api-key \
  --from-literal=OPENAI_API_KEY=sk-...
bash scripts/repro_linux_coco_tdx.sh
```

## Manual Verification

```bash
CN=asterinas-coco-tdx

# Pod status
docker exec $CN kubectl get pod nano-bot-kata-qemu-tdx-linux -o wide

# Confirm it's really Debian + ruby inside the guest, not the host
docker exec $CN kubectl exec nano-bot-kata-qemu-tdx-linux -- cat /etc/os-release
docker exec $CN kubectl exec nano-bot-kata-qemu-tdx-linux -- ruby --version

# Preferred continuous interaction path when exec is allowed
docker exec -it $CN kubectl exec -it nano-bot-kata-qemu-tdx-linux -- /usr/local/bin/tdx-chat-bot.rb

# If exec/logs are blocked, inspect the fallback probe result from node-local logs
docker exec $CN bash -lc 'find /var/log/pods -maxdepth 2 -type d | grep nano-bot-kata-qemu-tdx-linux-chat-once | tail -n 1'

# Re-run a one-shot guest-side prompt without rebuilding or redeploying
NANO_BOT_TEST_PROMPT='Reply with exactly: TDX guest connectivity confirmed.' \
RUN_WORKLOAD=0 RESTART_CONTAINERD=0 APPLY_RUNTIMECLASS=0 \
bash scripts/repro_linux_coco_tdx.sh
```

## Troubleshooting

These are real issues hit (and fixed) while building this automation - the
scripts already handle them, but they're documented here in case you hit
variations of them.

### Common Issues

**Pod stuck in `ContainerCreating` with `Unix syslog delivery error`**
The Kata shim fails to create *any* new sandbox if `/dev/log` doesn't exist
in the CoCo dev container (e.g. its `socat` forwarder died after a
restart). `repro_linux_coco_tdx.sh` recreates it automatically before every
containerd restart; if you hit this outside the script:
```bash
docker exec $CN bash -lc '
  rm -f /dev/log
  nohup socat -u UNIX-RECVFROM:/dev/log,fork OPEN:/tmp/kata-syslog-linux.log,creat,append >/tmp/socat-devlog.out 2>&1 &
'
```

**Guest reboots ~1.5s after boot (`reboot: Power down` in the console log)**
This means `kernel_params` is missing required tokens (this happens if you
ever hand-write a "minimal" kernel_params string instead of deriving it from
the existing working config). The script derives kernel_params from
`SOURCE_RUNTIME_CFG` and only patches the handful of tokens that actually
need to differ for the Linux kernel - never write a short custom
`kernel_params` from scratch.

**`CreateContainerError` / `no space left on device` unpacking the image**
The local registry's guest-pull path uses a small tmpfs
(`/var/lib/containerd-nydus`) for scratch space during layer extraction; a
large image can exceed its default size. Increase it:
```bash
docker exec $CN mount -o remount,size=4G /var/lib/containerd-nydus
```

**`failed to convert whiteout file ... operation not permitted` pulling the image**
The CoCo dev container's own containerd/`ctr` usually lacks `CAP_MKNOD`
(common in nested docker-in-docker setups), which breaks unpacking images
that contain OCI whiteout markers (e.g. from `apt-get ... && rm -rf
/var/lib/apt/lists/*`). `build_and_push_nano_bot_image.sh` avoids this by
flattening the image to a single layer before pushing (`FLATTEN_IMAGE=1`,
the default).

**Image pull `Not authorized` / `403 Forbidden` pushing to the local registry**
If your host routes non-loopback addresses through a corporate proxy at the
OS/tool level, pushing to the registry's docker-bridge-gateway address (used
so the *guest* can reach it) can get rejected by the proxy. Push via
`127.0.0.1` instead (same registry, same storage, just reached over
loopback) - this is what `build_and_push_nano_bot_image.sh` does by default
via `PUSH_REGISTRY_ADDRESS`.

**DNS resolution fails inside the Pod for your API endpoint or proxy**
If the cluster has no working CoreDNS/kube-dns, the container's
`/etc/resolv.conf` (pointing at the cluster DNS Service IP) is a dead end.
`ADD_HOST_ALIASES=1` (the default) works around this by resolving the
relevant hostnames on the *host* (which does have working DNS) and injecting
them as Pod `hostAliases`. If DNS still fails, check the WARNING logged by
the script - it means the hostname couldn't be resolved on the host either.

**Chat request gets an SSL certificate error**
Some corporate proxies perform TLS interception with a self-signed CA, which
the guest's default trust store won't validate. Set `FARADAY_SSL_VERIFY=none`
to disable certificate verification for the chat client only (does not
affect any other component).

**`docker exec ... tee file << HEREDOC` silently writes an empty file**
`docker exec` does not attach stdin unless you pass `-i`. Any script that
pipes/heredocs content into a command run via `docker exec` must use
`docker exec -i`. This bit both the runtime-config generation and the guest
registry-mirror config generation during development; the current scripts
all use `-i` where needed.

**Two Pods of the same `kata-qemu-tdx-linux` RuntimeClass running at once**
The shared Linux runtime TOML hardcodes fixed host paths for QEMU's
console/serial/debug logs (`/tmp/console.log`, etc.), inherited from the
underlying Asterinas config. Running two sandboxes of this RuntimeClass
concurrently can make the second one fail to boot. Stick to one Pod per
Linux `kata-qemu-tdx-linux` RuntimeClass at a time (this doesn't affect the
separately-namespaced QEMU 10.2.1 RuntimeClass, if you have one).

## Security Considerations

- No proxy URL, hostname, model name, or API key is hardcoded anywhere in
  this repository - all of it is supplied via environment variables at
  runtime.
- `OPENAI_API_KEY` is stored as a Kubernetes Secret, never as a Pod env
  literal or a file in this repo.
- The local Docker registry started by this tooling is a **plain HTTP,
  unauthenticated** registry, reachable only from the CoCo dev container's
  own docker network (the docker bridge gateway address) - it should not be
  exposed beyond that, and is intended purely as a way to hand a locally
  built image to the guest's Confidential Data Hub, not as a general-purpose
  registry.
- Confidential Containers' image encryption/decryption and remote
  attestation are intentionally not used here; the guest pulls the image
  unauthenticated and unencrypted, same as it would for `docker.io/library/alpine`.

## References

- [Kata Containers](https://katacontainers.io/)
- [Intel TDX](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-trust-domain-extension.html)
- [Confidential Containers](https://confidentialcontainers.org/)
- [nano-bots](https://spec.nbots.io/)
