# Deployment reference

This document contains the details deliberately kept out of the quick-start
README. It is written for moving the example to another Linux host.

## Deployment boundaries

There are four independently configured network/runtime boundaries:

1. The real host, which starts Docker and provides TDX, KVM, and the registry.
2. The CoCo container, which runs Kubernetes, containerd, and Nydus.
3. The Kata QEMU TDX VM, which boots the Linux guest and `kata-agent`.
4. The workload container, which runs `nano_bot` or OpenClaw and calls the API.

A proxy or DNS fix at one boundary does not automatically apply to the others.
The guest agent needs proxy kernel parameters before the workload exists; the
workload needs proxy environment variables after it starts.

## Per-host variables

Keep these values outside git. Set them in a local shell or deployment system:

```bash
export COCO_CONTAINER=<container-name>
export IMAGE_REF=docker.io/library/nano_bot:2.0
export API_ADDRESS=https://openrouter.ai/api/v1
export MODEL=minimax/minimax-m3:free
export PROXY_URL=http://<guest-resolvable-proxy>:<port>  # empty if direct
export NODE_NAME=<optional-node-name>
```

The deployment entrypoint also accepts a provider profile. Start from
`model-profile.env.example`, keep the copy outside git, and select it with:

```bash
./run_openai_workload.sh --model-config /path/to/model-profile.env
```

The supported profile keys are `MODEL_API_ADDRESS`, `MODEL_NAME`,
`MODEL_API_KEY_SECRET`, `MODEL_API_KEY_SECRET_KEY`, `MODEL_PROXY_URL`,
`MODEL_NO_PROXY`, and `MODEL_TLS_VERIFY`. Profile files are parsed as simple
`KEY=VALUE` data; shell code is not evaluated. Explicit command-line options
override profile values.

The proxy hostname must resolve inside the TDX guest. A hostname that resolves
only in the host's `/etc/hosts` will fail in the guest. Prefer a routable IP or
DNS name; test it from a running Pod before diagnosing the API key.

## CoCo container checklist

Inside the CoCo container:

```bash
export KUBECONFIG=/etc/kubernetes/super-admin.conf
kubectl get nodes -o wide
kubectl get runtimeclass kata-qemu-tdx-linux
pgrep -af 'containerd|containerd-nydus'
findmnt /var/lib/containerd-nydus
findmnt /var/lib/containerd/tmpmounts
```

Both temporary paths must exist and have enough space for the image. For this
example, 2 GiB is a practical starting point:

```bash
mkdir -p /var/lib/containerd-nydus /var/lib/containerd/tmpmounts
mountpoint -q /var/lib/containerd-nydus || \
  mount -t tmpfs -o size=2G tmpfs /var/lib/containerd-nydus
mountpoint -q /var/lib/containerd/tmpmounts || \
  mount -t tmpfs -o size=2G tmpfs /var/lib/containerd/tmpmounts
```

Do not start a second containerd using the same socket, state directory, or
root directory. Restarting the CoCo container removes mounts unless they were
provided as Docker `--tmpfs` options.

## Registry and image

The image reference, registry repository, and guest mirror must agree. For a
local Docker registry, publish the normalized repository used by Docker:

```text
docker.io/library/nano_bot:2.0
registry-address/library/nano_bot:2.0
```

The registry address used by the guest must be reachable from the guest, while
the push address can be `127.0.0.1` when the registry runs on the host. Do not
send a local registry address through an outbound proxy.

For a plain HTTP development registry, configure the guest mirror as insecure.
For HTTPS, use a certificate whose SAN covers the guest-visible registry name
and install its CA in the initramfs. Do not use an unauthenticated HTTP
registry outside an isolated development network.

## Guest initramfs

CDH reads `/etc/registry-configuration.toml` from the Kata initramfs. Editing
`/opt/coco/config/cdh/registry-configuration.toml` alone does not change a new
VM. Inspect and repack the exact initramfs selected by the Linux TDX runtime:

```bash
INITRD=/opt/coco/prebuilt/asterinas-coco/kata-containers-initrd.img
WORKDIR=$(mktemp -d)
gzip -dc "$INITRD" | cpio -idmu --quiet -D "$WORKDIR"
cat "$WORKDIR/etc/registry-configuration.toml"
rm -rf "$WORKDIR"
```

Back up the initramfs before repacking. Keep its archive format and every file
except the intended registry configuration unchanged. After repacking, create
a new Pod; an existing VM retains its old initramfs.

The related helper [../nano_bot/scripts/configure_guest_registry_mirror.sh](../nano_bot/scripts/configure_guest_registry_mirror.sh)
can stage this change. Review its transport and address values for the target
host before running it.

## Guest agent proxy

The workload's `HTTP_PROXY` does not help image pulling because image pulling
happens before the workload starts. Add these tokens to the existing
`kernel_params` in the Linux TDX runtime TOML:

```text
agent.https_proxy=<proxy-url>
agent.no_proxy=<localhost-and-cluster-addresses>
```

Preserve all existing kernel parameters. Do not replace the official TOML with
a hand-written minimal file. Confirm the new QEMU command line and guest
`AgentConfig` after the next VM starts.

## Secret and deployment

Create the Secret in the CoCo cluster, not the host's unrelated Kubernetes
context. Then run the entrypoint from the CoCo container or stream it into the
container from the host:

```bash
docker exec -i "$COCO_CONTAINER" bash -s -- \
  --image "$IMAGE_REF" \
  --secret nano-bot-api-key \
  --api-address "$API_ADDRESS" \
  --model "$MODEL" \
  ${PROXY_URL:+--proxy "$PROXY_URL"} \
  ${NODE_NAME:+--node-name "$NODE_NAME"} \
  < cczoo/agent-cc/adapters/coco_tdx/run_openai_workload.sh
```

When shell array handling makes optional arguments awkward, enter the CoCo
container and invoke the script directly. The entrypoint supports
`--namespace`, `--node-name`, `--proxy`, `--no-proxy`, and size overrides. It
waits for `Ready` and prints events on failure.

## Moving to another machine

Before deployment, verify:

- The host has TDX enabled and the required device nodes.
- The CoCo image version is a tested set of kernel, initrd, Kata, containerd,
  and Nydus artifacts.
- RuntimeClass `kata-qemu-tdx-linux` points to the active Linux TDX handler,
  whose runtime and image-platform entries use the nydus snapshotter.
- The API Secret exists in the CoCo cluster namespace.
- The image repository and architecture are available from the guest.
- The guest initramfs mirror uses the new machine's reachable address.
- The guest agent proxy and workload proxy are configured independently.
- Both tmpfs paths are mounted after every runtime/container restart.
- Only one runtime stack owns the configured containerd socket.
- The chosen model is currently listed as free by the API provider.

The checked-in YAML is intentionally proxy-free. Prefer the script for real
deployments because it avoids copying host-specific node and proxy values into
the repository.

## Provider compatibility

The current workload contract is the OpenAI Chat Completions API. A provider
profile changes only the endpoint, model, Secret reference, proxy, and TLS
settings. It does not change the TDX VM or image-pull path.

For a native provider with another protocol, place an OpenAI-compatible gateway
or a provider adapter beside the workload. Do not add provider-specific logic
to the Linux TDX runtime setup. This keeps model replacement independent from
confidential VM deployment.

## OpenClaw as a workload

OpenClaw is not interchangeable with the default image by changing
`MODEL_NAME`. It is
an agent runtime with its own gateway, token, ports, workspace, image, and
readiness check. Reuse the CoCo/TDX host preparation and image/registry rules,
then follow [the OpenClaw adapter](../../OpenClaw/README.md) for its workload
deployment. A future shared workload launcher should consume an image,
command, environment Secret references, and readiness probe as inputs; this
nano_bot launcher deliberately remains focused on the current image contract.
