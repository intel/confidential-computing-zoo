# OpenClaw and NanoBot on CoCo with Intel TDX

These examples run OpenClaw and an OpenAI-compatible NanoBot chat workload
inside an Intel TDX confidential VM:

```text
Kubernetes -> Kata QEMU TDX -> Asterinas guest -> kata-agent/CDH -> workload
```

Use this directory when the target machine already has the official CoCo
environment with the TDX RuntimeClass.

## Quick start

The commands below are split between the real host and the CoCo container.

### 1. Setup CoCo TDX environment

Run this section once before deploying either OpenClaw or NanoBot. The
`docker run` command starts the Asterinas-maintained CoCo container; the
workload containers are launched later as Kubernetes Pods inside its TDX
runtime.

The target host needs Linux Intel TDX, `/dev/kvm`, `/dev/vhost-vsock`, Docker,
and outbound access to the image registry and API endpoint. The earlier
CoCo/TDX validation recorded in this repository used
`asterinas/coco:0.18.0-20260603`.

On the real host, start the CoCo container with an interactive shell:

```bash
# Keep Kubernetes, Docker-network, and CoCo-internal traffic off the proxy.
export NO_PROXY=localhost,127.0.0.1,::1,172.16.0.0/12,10.96.0.0/12,10.244.0.0/16
export no_proxy="$NO_PROXY"
export COCO_CONTAINER="${COCO_CONTAINER:-asterinas-coco-tdx}"

docker pull asterinas/coco:0.18.0-20260603
docker run -it \
  --name "$COCO_CONTAINER" \
  --privileged \
  --cgroupns host \
  --device /dev/kvm \
  --device /dev/vhost-vsock \
  --tmpfs /var/lib/containerd-tmpmounts:rw,size=8g \
  --tmpfs /var/lib/containerd-nydus:rw,size=8g \
  -e HTTP_PROXY -e HTTPS_PROXY -e NO_PROXY \
  -e http_proxy -e https_proxy -e no_proxy \
  asterinas/coco:0.18.0-20260603 bash
```

Run only one CoCo container on a host. Do not start a second container with a
different name: the containers share host TDX/KVM and runtime resources, and
parallel instances can leave the guest API endpoint or QEMU sandboxes
unusable. Keep this container running for the entire Kubernetes workload
lifecycle. If it is forcibly terminated, start a fresh container and rerun
`/opt/coco/setup-coco-k8s.sh` before creating another TDX Pod.

Inside the CoCo container, configure and bootstrap Kubernetes:

```bash
export KUBECONFIG=/etc/kubernetes/super-admin.conf
```

### 1.1 Bootstrap and check the runtime

```bash
# Init Kubernetes env
/opt/coco/setup-coco-k8s.sh
kubectl get nodes
kubectl get runtimeclass kata-qemu-tdx-asterinas
```

Keep this terminal attached to the CoCo container. Run host-side commands such
as `docker build`, `skopeo copy`, and `docker exec` from a second host terminal.
In every host terminal, set `COCO_CONTAINER` to the running container name. For
example, use `asterinas-coco-official` for an existing container, or
`asterinas-coco-tdx` for the container started above:

```bash
export COCO_CONTAINER=asterinas-coco-official
```

The guest registry mirror must also be configured with a guest-reachable
address before either workload pulls an image:

```bash
cd <workdir>
REGISTRY_ADDRESS="$(docker network inspect bridge \
  --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}'):5000"
CONTAINER_NAME="$COCO_CONTAINER" \
  REGISTRY_ADDRESS="$REGISTRY_ADDRESS" \
  LINUX_INITRD=/opt/coco/prebuilt/asterinas-coco/kata-containers-initrd.img \
  bash cczoo/agent-cc/adapters/nano_bot/scripts/configure_guest_registry_mirror.sh
```

The script repacks the initramfs, so create a new workload Pod after changing
the mirror. The 8 GiB tmpfs mounts are required by the guest-pull and nydus
paths used by the OpenClaw image.

For the Asterinas TDX handler, use the native containerd snapshotter. The
handler's runtime and image-platform entries must both contain
`snapshotter = "native"`; nydus is not supported for TDX cleanup in this
flow and can leave later Pods stuck in `ContainerCreating`.

If a forced Pod deletion or Docker termination leaves a TDX sandbox stuck in
`ContainerCreating`, stop creating Pods and recover the runtime first. The
containerd temporary directory must exist after any manual cleanup:

```bash
docker exec "$COCO_CONTAINER" bash -lc \
  'mkdir -p /var/lib/containerd/tmpmounts /var/lib/containerd-nydus \
          /var/lib/containerd-tmpmounts'
```

Restart the dedicated CoCo container only after deleting the failed workload,
and run `/opt/coco/setup-coco-k8s.sh` inside it. Do not remove
`/var/lib/containerd`, and do not share runtime state with
`asterinas-coco-official`. Verify `kubectl get nodes` is `Ready` before
deploying again. The Asterinas CoCo image used here can retain stale TDX
shims/QEMU processes after a forced termination; when that happens, a fresh
CoCo container is required before retrying.

### 2. OpenClaw on CoCo TDX

Use the CoCo container, Kubernetes control plane, RuntimeClass, guest
registry mirror, and proxy setup described below. The OpenClaw-specific image,
gateway token, Pod manifest, and deployment script remain in `../OpenClaw/`.

#### 2.1 Prepare the image on the host

Run the image build and registry push on the real host:

```bash
cd cczoo/agent-cc/adapters/OpenClaw
docker build -f Dockerfile.coco-smoke \
  -t docker.io/library/openclaw-coco-smoke:patched .

# Push the image to the local registry used by the guest mirror.
# Keep the guest-facing mirror address separate from this host-side push address.
export REGISTRY_PUSH_ADDRESS="${REGISTRY_PUSH_ADDRESS:-127.0.0.1:5000}"
skopeo copy --dest-tls-verify=false \
  docker-daemon:docker.io/library/openclaw-coco-smoke:patched \
  docker://$REGISTRY_PUSH_ADDRESS/library/openclaw-coco-smoke:patched
```

The guest still uses the image reference
`docker.io/library/openclaw-coco-smoke:patched`; the configured guest mirror
rewrites that reference to the registry address reachable from the TDX VM.
Configure or repair the mirror before deploying either workload when the CoCo
container's Docker network has changed.

#### 2.2 Create OpenClaw Secrets

Run these commands inside the CoCo container with the CoCo cluster context:

```bash
read -rsp 'OPENAI_API_KEY: ' OPENAI_API_KEY
printf '%s' "$OPENAI_API_KEY" |
  kubectl create secret generic agent-api-key \
    --from-file=OPENAI_API_KEY=/dev/stdin \
    --dry-run=client -o yaml | kubectl apply -f -
unset OPENAI_API_KEY

read -rsp 'OPENCLAW_GATEWAY_TOKEN: ' OPENCLAW_GATEWAY_TOKEN
printf '%s' "$OPENCLAW_GATEWAY_TOKEN" |
  kubectl create secret generic openclaw-gateway-token \
    --from-file=OPENCLAW_GATEWAY_TOKEN=/dev/stdin \
    --dry-run=client -o yaml | kubectl apply -f -
unset OPENCLAW_GATEWAY_TOKEN
```

Run this section in the terminal attached to the CoCo container, not in a host
terminal using the host's default Kubernetes context. Verify with:

```bash
kubectl config current-context
kubectl get secret agent-api-key openclaw-gateway-token
```

#### 2.3 Deploy OpenClaw

Run this from a second host terminal. The script itself runs inside the CoCo
container so that it uses the CoCo Kubernetes cluster, RuntimeClass, and
containerd. Set `OPENCLAW_PROXY_URL` only when the TDX guest needs an outbound
proxy; the value must be resolvable from the guest.

> **Note on RuntimeClass & Storage:**
> - In standard Kata CoCo TDX setups, use `--runtime-class kata-qemu-tdx-linux`
>   (default in `run-coco-tdx.sh`). The Linux TDX guest runtime provides full
>   POSIX support for Node.js runtime and networking.
> - Kata TDX guests with `shared_fs = "none"` cannot mount arbitrary host directories
>   or multiple nested `emptyDir` volumes. A single memory-backed `emptyDir` mounted
>   at `/dev/shm` ensures all state (`/dev/shm/openclaw-state`) and cache
>   (`/dev/shm/openclaw-cache`) remain encrypted in confidential guest RAM without
>   triggering virtio-fs or virtio-block hotplug timeouts.

```bash
export COCO_CONTAINER="${COCO_CONTAINER:-asterinas-coco-official}"
export OPENCLAW_PROXY_URL="${PROXY_URL:-${HTTPS_PROXY:-${https_proxy:-}}}"
docker exec -i \
  -e KUBECONFIG=/etc/kubernetes/super-admin.conf \
  -e OPENCLAW_PROXY_URL="$OPENCLAW_PROXY_URL" \
  "$COCO_CONTAINER" bash -s -- \
  --api-secret agent-api-key \
  --gateway-secret openclaw-gateway-token \
  --runtime-class kata-qemu-tdx-linux \
  --model openrouter/nvidia/nemotron-3.5-lightning:free \
  < cczoo/agent-cc/adapters/OpenClaw/scripts/run-coco-tdx.sh
```

#### 2.4 Verify the OpenClaw gateway

Run the verification commands inside the CoCo container:

```bash
kubectl wait --for=condition=Ready pod/openclaw-coco-tdx-gateway --timeout=10m
kubectl exec -it openclaw-coco-tdx-gateway -- sh -lc \
  'node /app/dist/index.js agent \
    --message "Hello, please check the TDX status and confirm that you are running inside a TDX virtual machine." --json'
```

### 3. NanoBot on CoCo TDX

The following steps deploy the standalone `nano_bot` OpenAI-compatible
workload using the same CoCo TDX foundation.

#### 3.1 Create the API Secret

Create the Secret against the Kubernetes cluster inside the CoCo container.
Do not replace a placeholder in this command with the API key. Run it in a
real terminal and enter the actual key when prompted. The key is stored in the
temporary `OPENAI_API_KEY` shell variable, then piped into the Kubernetes
Secret named `nano-bot-api-key`; it is not written into the command line or
shell history:

```bash
read -rsp 'OPENAI_API_KEY: ' OPENAI_API_KEY
printf '%s' "$OPENAI_API_KEY" |
  kubectl create secret generic nano-bot-api-key \
    --from-file=OPENAI_API_KEY=/dev/stdin \
    --dry-run=client -o yaml | kubectl apply -f -
unset OPENAI_API_KEY
kubectl get secret nano-bot-api-key
```

#### 3.2 Configure and run the workload

Open a second host terminal while the interactive CoCo container session is
running. Export `COCO_CONTAINER` in that terminal, then run the command from
the repository root:

```bash
docker exec -i -e KUBECONFIG=/etc/kubernetes/super-admin.conf \
  "$COCO_CONTAINER" bash -s -- \
  --image docker.io/library/nano_bot:2.0 \
  --secret nano-bot-api-key \
  --api-address https://openrouter.ai/api/v1 \
  --model minimax/minimax-m3:free \
  < cczoo/agent-cc/adapters/coco_tdx/run_openai_workload.sh
```

The command above is ready to copy when the TDX guest has direct API access.
For a proxy, export the address once in the host terminal and pass it into the
CoCo container explicitly. The value can come from the host's existing proxy
configuration; it must also be resolvable and reachable from the TDX guest:

```bash
export WORKLOAD_PROXY_URL="${PROXY_URL:-${HTTPS_PROXY:-${https_proxy:-}}}"
docker exec -i \
  -e KUBECONFIG=/etc/kubernetes/super-admin.conf \
  -e PROXY_URL="$WORKLOAD_PROXY_URL" "$COCO_CONTAINER" bash -s -- \
  --image docker.io/library/nano_bot:2.0 \
  --secret nano-bot-api-key \
  --api-address https://openrouter.ai/api/v1 \
  --model minimax/minimax-m3:free \
  --proxy "$WORKLOAD_PROXY_URL" \
  < cczoo/agent-cc/adapters/coco_tdx/run_openai_workload.sh
```

Leave `WORKLOAD_PROXY_URL` empty and omit `--proxy` when the guest has direct
API access. If you need to pin the Pod to a node, add `--node-name
<real-node-name>` after replacing the placeholder with the actual Kubernetes
node name.

If you only have one host terminal, detach from the interactive container with
`Ctrl-p`, then `Ctrl-q` (do not press `Ctrl-c`). The container keeps running;
execute the same `docker exec` command from the host shell after detaching.

If the repository is mounted inside the CoCo container, run the entrypoint
directly there instead and do not use `docker exec`:

```bash
bash /path/to/coco_tdx/run_openai_workload.sh \
  --image docker.io/library/nano_bot:2.0 \
  --secret nano-bot-api-key \
  --api-address https://openrouter.ai/api/v1 \
  --model minimax/minimax-m3:free
```

The script creates the Pod, waits for `Ready`, and prints a probe command.

For repeatable provider changes, copy
[model-profile.env.example](model-profile.env.example) to an untracked local
file and pass it with `--model-config`. It contains only endpoint, model,
Secret reference, proxy, and TLS settings; it never contains the API key.

#### 3.3 Run the probe

```bash
printf 'Reply with exactly: TDX guest connectivity confirmed.\nquit\n' |
  kubectl exec -i openai-workload-kata-qemu-tdx -- \
  /usr/local/bin/tdx-chat-bot.rb
```

A successful run prints the requested confirmation. A `401` means the Secret
or key is invalid. A `404` can mean that the selected model is no longer
available; inspect the response body before changing credentials.

## Files

- [run_openai_workload.sh](run_openai_workload.sh): NanoBot deployment
  entrypoint; accepts machine-specific values as options or environment
  variables.
- [openai-workload-kata-qemu-tdx.yaml](openai-workload-kata-qemu-tdx.yaml):
  minimal proxy-free example manifest.
- [model-profile.env.example](model-profile.env.example): provider profile
  template for replacing endpoint/model without editing deployment logic.
- [deployment.md](deployment.md): host preparation, CoCo setup, registry,
  proxy, initramfs, and migration checklist.
- [troubleshooting.md](troubleshooting.md): diagnosis by layer and recovery
  commands.
- [OpenClaw adapter](../OpenClaw/): OpenClaw image, scripts, and manifest used
  by the deployment steps above.

## Security notes

The example uses a Kubernetes Secret for the API key, but the local image
registry and image-pull path may still be unauthenticated depending on the
chosen setup. Treat the CoCo container, registry, initramfs, and proxy as part
of the trusted deployment boundary. Add image signing, attestation policy,
registry authentication, and TLS CA provisioning before production use.

## Other agents and models

The default image is `nano_bot`, but it is only an example workload, not the
model abstraction.
The client speaks the OpenAI Chat Completions protocol, so OpenAI, OpenRouter,
vLLM, Ollama-compatible gateways, and similar providers can be selected with a
model profile when they expose that protocol.

OpenClaw is an agent/workload runtime, not a model provider. Its CoCo TDX
deployment is documented below in this guide; it uses its own image, gateway
token, workspace volumes, and startup/readiness probe.

Providers that do not implement OpenAI-compatible chat need a provider adapter
or gateway translating their native API to this contract. Keep that
translation outside the TDX deployment script so changing a provider does not
change confidential VM, registry, or attestation setup.
