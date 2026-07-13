# Asterinas CoCo with Intel TDX

This directory documents a reproducible deployment of the official Asterinas
Confidential Containers (CoCo) example with the TDX runtime:

```text
asterinas/coco container
  -> Kubernetes + containerd + Nydus
  -> Kata QEMU TDX sandbox
  -> Asterinas TDX guest kernel
  -> Kata guest initramfs and kata-agent
  -> guest-pull through Confidential Data Hub (CDH)
  -> Alpine workload rootfs
```

The procedure is intentionally parameterized. It does not contain a corporate
proxy URL, a host-specific IP address, a private registry address, or a
credential.

## What This Example Uses

The official TDX example uses these artifacts:

- A privileged `asterinas/coco` container.
- `/dev/kvm` and `/dev/vhost-vsock`.
- A TDX-capable host kernel and firmware.
- The Asterinas TDX guest kernel.
- A Kata guest initramfs containing `kata-agent`, CDH, and the guest tools.
- containerd with the Nydus snapshotter.
- `image_guest_pull`, which obtains the workload image from inside the guest.

It does **not** boot a Kata confidential rootfs image as the VM root disk. QEMU
boots with `-kernel` and `-initrd`; the Alpine workload rootfs is fetched later
by CDH/Nydus.

## Prerequisites

The host must provide:

- Linux with Intel TDX enabled and initialized.
- `/dev/kvm` and `/dev/vhost-vsock`.
- Docker with permission to use privileged containers.
- A working outbound network path to the required image registry, either
  directly or through an HTTP CONNECT proxy.
- Enough memory for the development container and TDX VM.

The Asterinas documentation currently uses a published `asterinas/coco` image.
Use a version whose Asterinas kernel, Kata shim, containerd, Nydus, and initrd
are a tested set. Do not mix files from unrelated CoCo image versions.

## Start the CoCo Environment

Set a version appropriate for the release being tested:

```bash
export COCO_IMAGE_VERSION=<tested-asterinas-coco-version>
```

Start the development container with the flags required by the official
Asterinas documentation:

```bash
docker run -it --rm \
  --name asterinas-coco \
  --privileged \
  --cgroupns host \
  --device /dev/kvm \
  --device /dev/vhost-vsock \
  --tmpfs /var/lib/containerd-nydus:rw,size=512m \
  asterinas/coco:"${COCO_IMAGE_VERSION}" \
  bash
```

The `/var/lib/containerd-nydus` tmpfs is important. It is temporary storage
used by the Nydus image service while preparing guest-pull images. If the
container was started without it, add the mount before starting workloads:

```bash
mkdir -p /var/lib/containerd-nydus
mountpoint -q /var/lib/containerd-nydus || \
  mount -t tmpfs -o size=512M tmpfs /var/lib/containerd-nydus
```

Inside the CoCo container, bootstrap the cluster:

```bash
/opt/coco/setup-coco-k8s.sh
```

The official setup should create the Kubernetes cluster, RuntimeClasses,
containerd configuration, Nydus snapshotter, and Asterinas runtime files.

## Configure a Network Proxy

A proxy has to be configured at more than one boundary. Host-side processes
(containerd, Nydus, and registry helpers) do not automatically configure the
`kata-agent` inside the TDX guest.

Use values from the local environment; do not commit them:

```bash
export PROXY_URL=http://<proxy-host>:<proxy-port>
export HTTP_PROXY="$PROXY_URL"
export HTTPS_PROXY="$PROXY_URL"
export http_proxy="$PROXY_URL"
export https_proxy="$PROXY_URL"
```

The host/container `NO_PROXY` should bypass Kubernetes, Docker, and local
registry networks. Adapt the CIDRs to the actual Docker and cluster networks:

```bash
export NO_PROXY_VALUE="localhost,127.0.0.1,::1,<kubernetes-service-cidr>,<pod-cidr>,<docker-network-cidr>"
export NO_PROXY="$NO_PROXY_VALUE"
export no_proxy="$NO_PROXY_VALUE"
```

Verify the proxy before debugging CoCo:

```bash
curl -sSIL -x "$PROXY_URL" --max-time 20 \
  https://registry-1.docker.io/v2/ | head
```

A `401 Unauthorized` from Docker Registry is expected and proves that HTTPS
CONNECT and registry reachability work. It is not an authentication failure
for this diagnostic.

### Pass the Proxy to the Guest Agent

The guest agent needs proxy kernel parameters in the TDX runtime configuration.
Edit the runtime configuration inside the CoCo container, preserving the
existing kernel parameters:

```bash
RUNTIME_CFG=/opt/coco/config/configuration-qemu-tdx-asterinas.toml

# Add these tokens to the existing kernel_params string.
# Use the same PROXY_URL and a no_proxy list that also bypasses local mirrors.
# agent.https_proxy=<proxy-url>
# agent.no_proxy=<local-and-cluster-addresses>
```

For example, the resulting line may contain:

```toml
kernel_params = "... agent.image_pull_timeout=3600 agent.https_proxy=<proxy-url> agent.no_proxy=localhost,127.0.0.1,<local-registry-ip>,<docker-network-cidr>,<pod-cidr> ..."
```

After a new VM boots, confirm both the QEMU command line and the agent
announcement. An old VM will continue to show the old configuration:

```bash
ps -eo pid,args | grep '[q]emu-system-x86_64'
strings /tmp/console.log | grep 'AgentConfig'
```

The announcement must contain non-empty `https_proxy` and `no_proxy` values.

## Image Registry and Initramfs Configuration

This is the most important troubleshooting detail.

CDH reads the registry configuration from the guest initramfs:

```text
/etc/registry-configuration.toml
```

Changing only this host-side file is insufficient:

```text
/opt/coco/config/cdh/registry-configuration.toml
```

That file is a staging file. It must be copied into the initramfs and the VM
must be recreated before the guest sees the change.

### Inspect the Initramfs

The Kata initramfs is a gzip-compressed `newc` archive. Inspect its registry
configuration before changing anything:

```bash
INITRD=/opt/coco/prebuilt/asterinas-coco/kata-containers-initrd.img
WORKDIR=$(mktemp -d)
cd "$WORKDIR"
gzip -dc "$INITRD" | cpio -idmu --quiet
cat etc/registry-configuration.toml
rm -rf "$WORKDIR"
```

The configuration commonly contains a mirror such as:

```toml
unqualified-search-registries = ["docker.io"]

[[registry]]
location = "docker.io"

[[registry.mirror]]
location = "<registry-address>"
```

The mirror must be reachable from the guest network and must match its
transport and trust configuration. A stale address, a mirror that is not
running, an HTTP/HTTPS mismatch, or a CA that the initramfs does not trust will
leave the Pod in `ContainerCreating` while the agent waits for CDH.

### Patch the Initramfs Safely

Back up the original before repacking. Replace only the registry configuration
and keep the rest of the initramfs unchanged:

```bash
INITRD=/opt/coco/prebuilt/asterinas-coco/kata-containers-initrd.img
STAGING=/opt/coco/config/cdh/registry-configuration.toml
BACKUP="${INITRD}.bak-$(date +%Y%m%d%H%M%S)"
WORKDIR=$(mktemp -d)

cp -a "$INITRD" "$BACKUP"
mkdir -p "$(dirname "$STAGING")"

cat > "$STAGING" <<'EOF'
unqualified-search-registries = ["docker.io"]

[[registry]]
location = "docker.io"

[[registry.mirror]]
location = "<reachable-registry-address>"
EOF

cd "$WORKDIR"
gzip -dc "$INITRD" | cpio -idmu --quiet
cp "$STAGING" etc/registry-configuration.toml
find . -print0 | cpio --null -o -H newc --quiet | gzip -9 > /tmp/kata-containers-initrd.img.new
mv /tmp/kata-containers-initrd.img.new "$INITRD"
rm -rf "$WORKDIR"
```

If the registry uses TLS, install its CA certificate in the initramfs trust
store and use a registry certificate whose SAN covers the address used by the
guest. For an HTTP development registry, the registry configuration must
explicitly mark the mirror as insecure if the CDH version requires that field.
Do not use an unauthenticated registry for production workloads.

The repository's related helper,
[`configure_guest_registry_mirror.sh`](../scripts/configure_guest_registry_mirror.sh),
implements the same staging-and-repack pattern for the nano_bot local registry.
Review its transport settings before using it with an HTTPS registry.

## Required Runtime State

Before creating the Pod, verify that exactly one official containerd owns the
configured socket and that Nydus is running:

```bash
pgrep -af 'containerd|containerd-nydus|containerd-shim-kata'
findmnt /var/lib/containerd-nydus
```

For the official runtime, also create the temporary mount directory used by
containerd/Kata:

```bash
mkdir -p /var/lib/containerd/tmpmounts
mountpoint -q /var/lib/containerd/tmpmounts || \
  mount -t tmpfs -o size=512M tmpfs /var/lib/containerd/tmpmounts
findmnt /var/lib/containerd/tmpmounts
```

Do not start a second containerd against the same root, state directory, or
Unix socket. Duplicate daemons can produce stale shims, API failures, and
misleading Pod events.

When restarting the runtime, preserve the proxy environment for host-side
processes and restore both tmpfs mounts afterwards. A container restart also
removes manually-created mounts unless they were supplied as Docker `--tmpfs`
arguments.

## Reproducible nano_bot Flow

The commands below are the recommended Asterinas path. Run the deployment
commands inside the CoCo container, but create the Kubernetes Secret from a
real SSH/TTY terminal so the key is never placed in shell history, chat, or an
agent log. The host `kubectl` context and the `kubectl` context inside CoCo are
often different clusters; the Secret must exist in the latter.

### 1. Verify the baseline and create the Secret

Inside the CoCo container:

```bash
kubectl get runtimeclass kata-qemu-tdx-asterinas
kubectl apply -f /opt/coco/manifests/alpine-kata-qemu-tdx.yaml
kubectl wait --for=condition=Ready pod/alpine-kata-qemu-tdx --timeout=10m
```

From a real SSH/TTY terminal, create the Secret in the CoCo cluster. This
example sends bytes directly to `kubectl` and does not display them:

```bash
read -rsp 'OPENAI_API_KEY: ' OPENAI_API_KEY
echo
printf '%s' "$OPENAI_API_KEY" |
  docker exec -i asterinas-coco-tdx kubectl create secret generic nano-bot-api-key \
    --from-file=OPENAI_API_KEY=/dev/stdin
unset OPENAI_API_KEY
```

Use the actual CoCo container name if it differs. Verify metadata only inside
CoCo; never use `jsonpath` on `.data.OPENAI_API_KEY`:

```bash
kubectl get secret nano-bot-api-key -o jsonpath='{.metadata.name}{"\n"}'
```

### 2. Build and publish without tc-api

The tc-api builder remains available as a separate workflow, but it is not a
prerequisite. The direct Docker path publishes a Docker Schema 2 image under
the normalized `docker.io/library/nano_bot` repository. Schema 2 matters:
older registry compatibility responses can make containerd fail during the
manifest `HEAD` request.

On the true host, start or reuse a plain-HTTP development registry and capture
the address reachable from the CoCo network:

```bash
export CONTAINER_NAME=asterinas-coco-tdx
export REGISTRY_ADDRESS="$(scripts/setup_local_registry.sh)"
```

The helper disables Registry Schema 1 compatibility for new registries. If an
old `registry:2` container is reused, recreate it with
`REGISTRY_COMPATIBILITY_SCHEMA1_ENABLED=false` while preserving its registry
data volume.

Build and push the image from the true host. The script uses `127.0.0.1` for
the push side to avoid accidentally sending a private registry address through
the corporate proxy, while the guest uses `REGISTRY_ADDRESS`:

```bash
export IMAGE_TAG=2.0
scripts/build_and_push_nano_bot_docker.sh
```

The script uses `skopeo --format v2s2` and checks the registry before pushing.
If Docker needs an outbound proxy, export the proxy variables before running
it. Do not put proxy credentials or API keys in the image.

### 3. Configure the guest and deploy

Still on the true host, configure both the host containerd mirror and the
guest initramfs. The helper must target the same CoCo container used above:

```bash
export LINUX_INITRD=/opt/coco/prebuilt/asterinas-coco/kata-containers-initrd.img
CONTAINER_NAME="$CONTAINER_NAME" \
REGISTRY_ADDRESS="$REGISTRY_ADDRESS" \
LINUX_INITRD="$LINUX_INITRD" \
  scripts/configure_guest_registry_mirror.sh
```

The mirror address in the initramfs, the containerd `hosts.toml`, and the
registry transport must agree. For the helper's plain-HTTP development mode,
the guest config contains `insecure = true` and containerd uses
`http://...`. For HTTPS, use a certificate whose SAN covers the guest-visible
address and install its CA in the initramfs instead of using `skip_verify`.

Configure the guest agent proxy separately from the workload proxy. Add
`agent.https_proxy=<proxy-url>` and an `agent.no_proxy` list containing the
local registry and cluster networks to
`configuration-qemu-tdx-asterinas.toml`, then create a new VM. A workload
`HTTP_PROXY` environment variable cannot repair image pulling that happens
before the container starts. Prefer a proxy IP or a hostname resolvable from
the guest; the host's `/etc/hosts` is not automatically visible in the TDX
guest.

Finally, send the checked deployment entrypoint from the true host into the
CoCo container. This works even when the repository is not mounted into that
container:

```bash
docker exec -i "$CONTAINER_NAME" bash -s -- \
  --image docker.io/library/nano_bot:2.0 \
  --secret nano-bot-api-key \
  --api-address https://aidemo.intel.cn/v1 \
  --model minimax-m2.7 \
  --proxy http://<guest-resolvable-proxy>:<port> \
  < cczoo/agent-cc/adapters/nano_bot/asterinas_coco/run_nano_bot_asterinas.sh
```

The script is the portable entrypoint; the checked-in YAML is only a
proxy-free example. The script checks the active Kubernetes context, RuntimeClass, Secret
metadata, initramfs mirror, and both temporary filesystems. It creates the Pod
with a Secret reference only, waits for `Ready`, and prints Pod events when
startup fails. Defaults are deliberately overridable because registry IPs,
proxy addresses, image tags, and container names are environment-specific.

Run the chat probe only after the Pod is Ready:

```bash
printf 'Reply with exactly: TDX guest connectivity confirmed.\nquit\n' |
  kubectl exec -i nano-bot-kata-qemu-tdx-asterinas -- \
    /usr/local/bin/tdx-chat-bot.rb
```

### Why the original run took many iterations

The failures were independent and crossed four boundaries:

| Symptom | Root cause | Preventive check |
| --- | --- | --- |
| Secret not found | Secret was created against the host API endpoint, not the CoCo cluster | `kubectl get secret` inside CoCo |
| `172.17.0.1` or `unexpected EOF` | Stale host-side mirror; guest and host registry configs were not the same layer | Inspect initramfs and `/etc/containerd/certs.d/docker.io/hosts.toml` |
| `library/nano_bot` not found | Registry repository path did not match Docker's normalized `docker.io/library/...` name | Publish to `library/nano_bot` and use the normalized image reference |
| Schema/manifest pull errors | Registry returned Schema 1 to containerd `HEAD` requests | Registry Schema 1 disabled and `skopeo --format v2s2` |
| `tmpmounts` missing or full | Runtime restart removed the mount, or 512 MiB was insufficient for Ruby layers | Mount both tmpfs paths before deployment; use at least 2 GiB for this image |
| Ruby `openai` LoadError | Flattening with `docker import` dropped `GEM_HOME`/Bundler metadata | Use the native Docker build; avoid ad-hoc flattening |
| Proxy hostname resolution failure | Guest DNS could not resolve the host-only proxy name | Use a guest-resolvable proxy IP/name and configure agent/workload proxy separately |
| Linux rootfs `ENOENT` | The Linux runtime script was used while validating the Asterinas path | Use `kata-qemu-tdx-asterinas` and this Asterinas entrypoint |

The Linux script under `../scripts/repro_linux_coco_tdx.sh` is intentionally
not part of this flow. It targets `kata-qemu-tdx-linux` and requires a Linux
guest kernel plus matching runtime configuration.

## Run the Official TDX Example

Use the bundled manifest supplied by the CoCo image:

```bash
export KUBECONFIG=/etc/kubernetes/super-admin.conf
kubectl apply -f /opt/coco/manifests/alpine-kata-qemu-tdx.yaml
kubectl wait --for=condition=Ready pod/alpine-kata-qemu-tdx --timeout=10m
```

If OpenAPI discovery is unavailable while the API server is recovering, use
`--validate=false`; this skips client-side schema discovery and does not skip
server-side validation:

```bash
kubectl apply --validate=false \
  -f /opt/coco/manifests/alpine-kata-qemu-tdx.yaml
```

Verify the workload and guest:

```bash
kubectl get pod alpine-kata-qemu-tdx -o wide
kubectl exec alpine-kata-qemu-tdx -- cat /etc/alpine-release
kubectl exec alpine-kata-qemu-tdx -- cat /proc/cmdline
```

Expected results include:

- Pod status `1/1 Running`.
- An Alpine release such as `3.22.x`.
- A cmdline containing `agent.https_proxy` when a proxy is configured.
- A QEMU command line containing `-machine ... confidential-guest-support=tdx`.
- QEMU arguments containing both `-kernel` and `-initrd`.

## Debugging by Layer

### Pod stays in `ContainerCreating`

Inspect events first:

```bash
kubectl describe pod alpine-kata-qemu-tdx
kubectl get events --sort-by=.lastTimestamp
```

Then inspect only the current VM's console log. Old `/tmp/console.log` content
can belong to a previous sandbox and lead to incorrect conclusions:

```bash
strings /tmp/console.log | grep -Ei \
  'AgentConfig|pull image|sending pull|error|failed|timeout|started|completed'
```

### `stat /var/lib/containerd/tmpmounts: no such file or directory`

Create the directory and mount the required tmpfs. This is a host/container
runtime prerequisite, not a guest image problem.

### CDH waits after `sending pull image request`

Check, in order:

1. The guest's `AgentConfig` has the intended proxy.
2. The guest initramfs registry configuration points to the intended mirror.
3. The mirror address is reachable from the guest network.
4. The mirror transport matches its configuration (`http` versus `https`).
5. The initramfs contains the required CA certificate for TLS.
6. The image has the requested architecture and OCI/Docker manifest format.

The fact that the image is present in host containerd is not enough. With
`use_local_image_pull = false`, the guest pulls the image independently.

### `unexpected EOF` from kubectl or Kubernetes API

Usually check proxy bypasses first. Kubernetes service, Pod, Docker bridge,
and loopback addresses should not be sent through an outbound proxy. Also
verify that only one API server/containerd stack is active.

### `kubectl exec` returns `nodes/proxy Forbidden`

This is a Kubernetes API-to-kubelet RBAC issue after the Pod is already running.
It is separate from TDX boot and guest-pull. Compare the cluster's existing
`system:kubelet-api-admin` role and its bindings before changing RBAC. Avoid
broad permanent permissions in production merely to make a diagnostic command
work.

### QEMU boots but the guest immediately powers down

Check that the runtime configuration was derived from the complete official
TOML. Do not replace it with a short hand-written file. Preserve required
Kata settings and only change the kernel, initrd, and intended kernel
parameters.

### TDX or QEMU failures

Verify:

```bash
ls -l /dev/kvm /dev/vhost-vsock
cat /sys/firmware/tdx_enabled 2>/dev/null || true
dmesg | grep -i tdx
systemctl status qgsd.service 2>/dev/null || true
```

The exact TDX checks differ by host kernel and distribution. A successful
Asterinas guest announcement proves that the VM reached kata-agent; it does
not by itself prove that the workload image pull completed.

## Rootfs and Integrity Notes

There are two different rootfs concepts in this flow:

1. **Guest boot environment**: `kata-containers-initrd.img`, supplied to QEMU
   with `-initrd`. It contains the Asterinas-compatible guest userspace,
   kata-agent, CDH, certificates, and registry configuration.
2. **Workload rootfs**: Alpine's rootfs, obtained by CDH/Nydus through
   `image_guest_pull` after the VM has booted.

The official flow does not pass a Kata confidential rootfs image as a QEMU
root disk. The current flow also does not automatically provide an independent
measurement or signature verification step for the initramfs. TDX protects the
confidential VM after launch, but operators must add an appropriate measured
boot, attestation, signed-artifact verification, or equivalent supply-chain
control if initramfs integrity is a security requirement.

## Cleanup

Delete the workload after testing:

```bash
kubectl delete pod alpine-kata-qemu-tdx --ignore-not-found
```

Stop any temporary local registry created for testing. Keep initramfs backups
until the deployment has been validated, then manage them according to the
artifact retention policy.

## Reference

- [Asterinas: Using Asterinas as a Confidential Containers Guest Kernel](https://asterinas.github.io/book/kernel/vm-based-containers/coco.html)
- [Parent nano_bot CoCo/TDX README](../README.md)
- [Guest registry mirror helper](../scripts/configure_guest_registry_mirror.sh)
