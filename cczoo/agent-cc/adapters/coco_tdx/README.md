# Run AI Agents in Confidential Containers with Intel TDX

This guide shows how to deploy AI agent workloads in Intel TDX confidential
VMs with Confidential Containers (CoCo). OpenClaw and NanoBot are two example
agents; the same deployment pattern can be adapted to other containerized
agents that can reach their model provider from the guest.

The host needs Intel TDX support, `/dev/kvm`, `/dev/vhost-vsock`, Docker, and
outbound access to the image registry and model API endpoint.

## Deployment guide

### 1. Prepare the CoCo TDX environment

Run this section once before deploying either OpenClaw or NanoBot. The
`docker run` command starts the Asterinas-maintained CoCo container; the
workload containers are launched later as Kubernetes Pods inside its TDX
runtime.

On the **host**, start the CoCo container with an interactive shell:

```bash
# Override these defaults if the cluster uses different Service or Pod CIDRs.
export K8S_SERVICE_CIDR="${K8S_SERVICE_CIDR:-10.96.0.0/12}"
export K8S_POD_CIDR="${K8S_POD_CIDR:-10.244.0.0/16}"
DOCKER_BRIDGE_CIDR="$(docker network inspect bridge \
  --format '{{(index .IPAM.Config 0).Subnet}}')"

# Keep loopback, Docker bridge, and Kubernetes traffic off the proxy.
export NO_PROXY="localhost,127.0.0.1,::1,$DOCKER_BRIDGE_CIDR,$K8S_SERVICE_CIDR,$K8S_POD_CIDR"
export no_proxy="$NO_PROXY"
export COCO_CONTAINER="${COCO_CONTAINER:-asterinas-coco-tdx}"

docker pull asterinas/coco:0.18.0-20260603
docker run -it \
  --name "$COCO_CONTAINER" \
  --privileged \
  --cgroupns host \
  --device /dev/kvm \
  --device /dev/vhost-vsock \
  --tmpfs /var/lib/containerd/tmpmounts:rw,size=8g \
  --tmpfs /var/lib/containerd-nydus:rw,size=8g \
  -e HTTP_PROXY -e HTTPS_PROXY -e NO_PROXY \
  -e http_proxy -e https_proxy -e no_proxy \
  asterinas/coco:0.18.0-20260603 bash
```

Inside the **CoCo container**, select its Kubernetes configuration:

```bash
export KUBECONFIG=/etc/kubernetes/super-admin.conf
```

Then bootstrap Kubernetes and verify the node and Linux TDX RuntimeClass:

```bash
# Init Kubernetes env
/opt/coco/setup-coco-k8s.sh
kubectl get nodes
kubectl get runtimeclass kata-qemu-tdx-linux
```

Keep Terminal A attached to the CoCo container. In Terminal B on the host, run
`docker build`, `skopeo copy`, and `docker exec`. Set `COCO_CONTAINER` to the
same container name used in Terminal A:

```bash
export COCO_CONTAINER="${COCO_CONTAINER:-asterinas-coco-tdx}"
```

Before deploying an agent, configure the guest registry mirror with an
address reachable from a TDX guest. Run this on the **host** from the
repository root:

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
the mirror. The Linux TDX handler uses the nydus snapshotter for this
guest-pull configuration; the 8 GiB tmpfs mounts provide working space for
the image-pull path.

If a Pod remains in `ContainerCreating` or a forced termination leaves a TDX
sandbox behind, follow the recovery steps in
[troubleshooting.md](troubleshooting.md#pod-remains-containercreating) before
creating another Pod.

### 2. Deploy the OpenClaw example

#### 2.1 Prepare the image on the host

Run the image build and registry push on the **host**:

```bash
cd cczoo/agent-cc/adapters/OpenClaw
docker build -f Dockerfile.coco-tdx \
  -t docker.io/library/openclaw-coco-tdx:latest .

# Push the image to the local registry used by the guest mirror.
# Keep the guest-facing mirror address separate from this host-side push address.
export REGISTRY_PUSH_ADDRESS="${REGISTRY_PUSH_ADDRESS:-127.0.0.1:5000}"
skopeo copy --dest-tls-verify=false \
  docker-daemon:docker.io/library/openclaw-coco-tdx:latest \
  docker://$REGISTRY_PUSH_ADDRESS/library/openclaw-coco-tdx:latest
```

This image is based on `openclaw-flat:latest`. Its Dockerfile replaces the
external SQLite read-only preparation path with OpenClaw's in-process
implementation, avoiding a file rename sequence unsupported by Asterinas.

#### 2.2 Create OpenClaw Secrets

Run these commands inside the **CoCo container**:

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

And verify with:

```bash
kubectl config current-context
kubectl get secret agent-api-key openclaw-gateway-token
```

#### 2.3 Deploy OpenClaw

Run this from Terminal B on the **host**. Set `OPENCLAW_PROXY_URL` only when
the TDX guest needs an outbound proxy. The proxy address must be resolvable
from the guest.

```bash
export COCO_CONTAINER="${COCO_CONTAINER:-asterinas-coco-tdx}"
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

`--model` sets OpenClaw's default model. The value above uses OpenClaw's
`openrouter/<provider>/<model>` format: `openrouter` selects the OpenRouter
integration, and `nvidia/nemotron-3.5-lightning:free` is the OpenRouter model
slug. `:free` model availability and identifiers may change over time.

#### 2.4 Verify the OpenClaw gateway

Run the verification commands inside the **CoCo container**:

```bash
kubectl wait --for=condition=Ready pod/openclaw-coco-tdx-gateway --timeout=10m
kubectl exec -it openclaw-coco-tdx-gateway -- sh -lc \
  'node /app/dist/index.js agent \
    --message "Hello, please check the TDX status and confirm that you are running inside a TDX virtual machine." --json'
```

#### 2.5 Optional: TC API trust plane and signed image

The TC API `POST /api/deploy-launch` endpoint launches Docker containers and
does not use the Kubernetes Kata RuntimeClass. For the deployment above, retain
the Kubernetes launcher and use the same Trustee/KBS trust plane to verify the
OpenClaw image inside the guest:

```bash
OPENCLAW_PROXY_URL="${PROXY_URL:-${HTTPS_PROXY:-${https_proxy:-}}}" \
  bash cczoo/agent-cc/adapters/OpenClaw/scripts/run-signed-images-trustee.sh
```

The helper signs the registry digest, publishes only the Cosign public key and
a deny-by-default policy to Trustee, installs the separate
`kata-qemu-tdx-linux-signed` guest-pull RuntimeClass, and invokes the normal
OpenClaw launcher. The signing key remains on the host. The existing
`kata-qemu-tdx-linux` path is left unchanged.

This flow succeeds only when the Kata guest image includes signed-image
verification support. The helper treats a Ready Pod without a Trustee
attestation or resource request as a failure; a RuntimeClass annotation alone
is not proof that the image policy was enforced.

### 3. Deploy the NanoBot example

NanoBot demonstrates a smaller OpenAI-compatible chat workload using the same
Linux guest runtime and CoCo TDX foundation as OpenClaw.

#### 3.1 Create the API Secret

Inside the **CoCo container**, create the Secret in the CoCo Kubernetes
cluster. Enter the API key only at the prompt. The command stores it in a
temporary shell variable and pipes it into `nano-bot-api-key`, so the value is
not written to the command line or shell history:

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

In Terminal B on the **host**, export `COCO_CONTAINER`, then run this command
from the repository root while Terminal A remains attached to the CoCo
container:

```bash
docker exec -i -e KUBECONFIG=/etc/kubernetes/super-admin.conf \
  "$COCO_CONTAINER" bash -s -- \
  --image docker.io/library/nano_bot:2.0 \
  --secret nano-bot-api-key \
  --api-address https://openrouter.ai/api/v1 \
  --model minimax/minimax-m3:free \
  < cczoo/agent-cc/adapters/coco_tdx/run_openai_workload.sh
```

Use the command above when the TDX guest has direct API access. When a proxy
is required, export its address in the host terminal and pass it into the CoCo
container explicitly. The proxy must be resolvable and reachable from the TDX
guest:

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

If only one terminal is available, detach it from the interactive container
with `Ctrl-p`, then `Ctrl-q` (do not press `Ctrl-c`). The container keeps
running and the terminal returns to the host shell, where it can run the same
`docker exec` command.

If the repository is mounted inside the CoCo container, run the entrypoint
directly there instead of using `docker exec`:

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

#### 3.3 Verify NanoBot

Run the probe inside the **CoCo container**:

```bash
printf 'Reply with exactly: TDX guest connectivity confirmed.\nquit\n' |
  kubectl exec -i openai-workload-kata-qemu-tdx -- \
  /usr/local/bin/tdx-chat-bot.rb
```

A successful run prints the requested confirmation. A `401` means the Secret
or key is invalid. A `404` can mean that the selected model is no longer
available; inspect the response body before changing credentials.

## Reference

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

## Adapt the guide to other agents and models

The deployment foundation is not tied to OpenClaw or NanoBot. To add another
agent, provide a container image, select a compatible TDX RuntimeClass, inject
credentials through Kubernetes Secrets, and account for the guest's storage
and network constraints.

The NanoBot client speaks the OpenAI Chat Completions protocol. OpenAI,
OpenRouter, vLLM, Ollama-compatible gateways, and similar providers can be
selected with a model profile when they expose that protocol.

OpenClaw is an agent runtime, not a model provider. Its deployment uses its
own image, gateway token, workspace storage, and startup/readiness probe.

Providers that do not implement OpenAI-compatible chat need a provider adapter
or gateway translating their native API to this contract. Keep that
translation outside the TDX deployment script so changing a provider does not
change confidential VM, registry, or attestation setup.
