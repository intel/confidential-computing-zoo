# OpenAI-compatible workload on CoCo with Intel TDX

This example runs an OpenAI-compatible chat workload inside an Intel TDX
confidential VM:

```text
Kubernetes -> Kata QEMU TDX -> Asterinas guest -> kata-agent/CDH -> nano_bot
```

Use this directory when the target machine already has the official CoCo
environment with the TDX RuntimeClass. The Linux guest-kernel flow in
`../../nano_bot/scripts/repro_linux_coco_tdx.sh` is a different runtime and is
not used here.

## Quick start

The commands below are split between the real host and the CoCo container.
Replace every value in angle brackets. Never put an API key in a repository,
manifest, command copied into chat, or shell history.

### 1. Check the host

The target host needs Linux Intel TDX, `/dev/kvm`, `/dev/vhost-vsock`, Docker,
and outbound access to the image registry and API endpoint. Start the official
Asterinas CoCo container using the release's documented command, then enter it:

```bash
docker exec -it <coco-container> bash
export KUBECONFIG=/etc/kubernetes/super-admin.conf
```

The container must contain Kubernetes, containerd, Nydus, the Asterinas TDX
kernel, and the matching Kata initramfs. Do not mix artifacts from different
CoCo releases.

### 2. Bootstrap and check the runtime

```bash
/opt/coco/setup-coco-k8s.sh
kubectl get nodes
kubectl get runtimeclass kata-qemu-tdx-asterinas
```

If the RuntimeClass does not exist, finish the release-specific Asterinas
runtime setup before continuing. See [deployment.md](deployment.md) for the
full host and CoCo-container checklist.

### 3. Create the API Secret

Create the Secret against the Kubernetes cluster inside the CoCo container.
Use a real terminal and pipe the key through stdin so it is not saved in shell
history:

```bash
read -rsp 'OPENAI_API_KEY: ' OPENAI_API_KEY
printf '%s' "$OPENAI_API_KEY" |
  kubectl create secret generic nano-bot-api-key \
    --from-file=OPENAI_API_KEY=/dev/stdin \
    --dry-run=client -o yaml | kubectl apply -f -
unset OPENAI_API_KEY
kubectl get secret nano-bot-api-key
```

### 4. Configure and run the workload

Run the checked entrypoint from the real host and stream it into the CoCo
container. This works even when the repository is not mounted there. The key
is read from the Kubernetes Secret; the script never accepts or prints it.

```bash
docker exec -i <coco-container> bash -s -- \
  --image docker.io/library/nano_bot:2.0 \
  --secret nano-bot-api-key \
  --api-address https://openrouter.ai/api/v1 \
  --model minimax/minimax-m3:free \
  --proxy http://<guest-resolvable-proxy>:<port> \
  --node-name <optional-node-name> \
  < run_openai_workload.sh
```

Omit `--proxy` when the guest can reach the API directly. Omit
`--node-name` when Kubernetes scheduling is configured correctly. The script
creates the Pod, waits for `Ready`, and prints a probe command.

The free model list changes over time. Query OpenRouter's `/api/v1/models`
endpoint and choose a current `:free` text model if this example becomes
unavailable.

For repeatable provider changes, copy
[model-profile.env.example](model-profile.env.example) to an untracked local
file and pass it with `--model-config`. It contains only endpoint, model,
Secret reference, proxy, and TLS settings; it never contains the API key.

### 5. Run the probe

```bash
printf 'Reply with exactly: TDX guest connectivity confirmed.\nquit\n' |
  kubectl exec -i openai-workload-kata-qemu-tdx -- \
  /usr/local/bin/tdx-chat-bot.rb
```

A successful run prints the requested confirmation. A `401` means the Secret
or key is invalid. A `404` can mean that the selected model is no longer
available; inspect the response body before changing credentials.

## Files

- [run_openai_workload.sh](run_openai_workload.sh): portable deployment
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

OpenClaw is an agent/workload runtime, not a model provider. It should reuse
the TDX/CoCo foundation but use its own image, ports, gateway token, workspace
volumes, and startup/readiness probe. The existing OpenClaw adapter is
documented at [../../OpenClaw/README.md](../../OpenClaw/README.md); this
OpenAI-compatible workload script intentionally does not try to start
OpenClaw.

Providers that do not implement OpenAI-compatible chat need a provider adapter
or gateway translating their native API to this contract. Keep that
translation outside the TDX deployment script so changing a provider does not
change confidential VM, registry, or attestation setup.
