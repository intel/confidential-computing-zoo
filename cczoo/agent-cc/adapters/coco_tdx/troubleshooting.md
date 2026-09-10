# Troubleshooting

Diagnose from the outside in: Kubernetes events, Kata/QEMU startup, guest
image pull, then the workload API request.

## First checks

```bash
export KUBECONFIG=/etc/kubernetes/super-admin.conf
POD=openai-workload-kata-qemu-tdx
kubectl get pod "$POD" -o wide
kubectl describe pod "$POD"
kubectl get events --field-selector involvedObject.name="$POD" \
  --sort-by=.lastTimestamp
```

Inspect only the current VM's logs. Shared `/tmp/console.log` and
`/tmp/qemu-serial.log` may contain output from an older sandbox:

```bash
ps -eo pid,stat,cmd | grep -E 'containerd-shim-kata-v2|qemu-system-x86_64' | grep -v grep
tail -120 /tmp/qemu-serial.log
tail -120 /tmp/console.log
```

## Pod remains Pending

Check that a node is Ready and that the Pod has a schedulable node. For a
single-node development host, pass `--node-name <node>` to the entrypoint. A
Pod's `spec.nodeName` cannot be patched after creation; delete and recreate it.

## Pod remains ContainerCreating

This usually means Kata guest boot or CDH image pull is waiting. Check:

1. `/var/lib/containerd-nydus` and `/var/lib/containerd/tmpmounts` are mounted
   and have free space.
2. The active RuntimeClass is `kata-qemu-tdx-linux`.
3. The QEMU command line contains `confidential-guest-support=tdx`, the
  expected Linux guest kernel, and the expected initramfs.
4. The guest `AgentConfig` contains the intended agent proxy.
5. The registry mirror is present inside the selected initramfs.
6. The guest can route to the mirror and the mirror transport is correct.

The fact that the image exists in host containerd does not prove that guest
pull works. With guest pull enabled, CDH retrieves the image independently.

## `tmpmounts` missing or no space

Create/remount both tmpfs paths in the CoCo container. A container restart can
remove manually-created mounts. Supply them as Docker `--tmpfs` mounts when
starting a reusable CoCo container.

If forced Pod deletion or Docker termination leaves a TDX sandbox stuck, stop
creating Pods and delete the failed workload before recovering the runtime.
Ensure the containerd temporary directories exist after manual cleanup:

```bash
docker exec "$COCO_CONTAINER" bash -lc \
  'mkdir -p /var/lib/containerd/tmpmounts /var/lib/containerd-nydus'
```

Restart the dedicated CoCo container, then run
`/opt/coco/setup-coco-k8s.sh` inside it. Do not remove
`/var/lib/containerd`, and do not share runtime state between CoCo containers.
Verify that `kubectl get nodes` reports `Ready` before deploying again.

The Asterinas CoCo image can retain stale TDX shims or QEMU processes after a
forced termination. If they remain after the recovery steps above, replace
the CoCo container with a fresh one before retrying.

## Registry errors

- `library/nano_bot not found`: publish the normalized `library/nano_bot`
  repository and use the matching image reference.
- `unexpected EOF` or schema errors: use a Docker/OCI Schema 2 image and
  disable legacy Schema 1 compatibility on a development registry.
- `no route to host`: the guest cannot reach the configured mirror address.
- TLS/CA errors: install the registry CA in the initramfs and use a certificate
  SAN matching the address used by the guest.
- `403` while pushing: push through the host's loopback registry address so a
  corporate proxy does not intercept the local registry request.

## Proxy or DNS errors

The proxy must be configured both in the Linux guest-agent kernel parameters
and in the workload environment. A host `/etc/hosts` entry is not visible in
the TDX guest. Use a guest-resolvable proxy hostname or IP.

A direct connectivity check from a running Pod:

```bash
kubectl exec "$POD" -- ruby -rsocket -e \
  's=TCPSocket.new("<proxy-host>", <proxy-port>); puts "connected"; s.close'
```

Keep Kubernetes service, Pod, Docker bridge, registry, loopback, and proxy-local
CIDRs in `NO_PROXY` as appropriate for the target network.

## `kubectl exec` returns `nodes/proxy Forbidden`

This is API Server to kubelet RBAC, not a TDX boot failure. Confirm the Pod is
already `Running`, then inspect the cluster's `system:kubelet-api-admin` role
and binding for `kube-apiserver-kubelet-client`. Grant only the minimum
`nodes/proxy` permission required by the cluster's administration policy.

## Chat API failures

Interpret the HTTP status before replacing credentials:

- `401`: key is missing, invalid, expired, revoked, or belongs to the wrong
  provider.
- `403`: key is recognized but lacks permission, quota, or account access.
- `404`: endpoint path or model slug is unavailable. Free model slugs change;
  query `/api/v1/models` and select a current `:free` model.
- `429`: provider rate limit or quota, not a TDX failure.
- DNS/proxy connection errors: fix guest networking first.

Never print the Secret value when debugging. Check only metadata:

```bash
kubectl get secret nano-bot-api-key
```

## Guest reboots or powers down

Use the complete Linux TDX runtime TOML derived from the official baseline and
preserve its required `kernel_params`. A short replacement often omits
required Kata/TDX parameters. Also verify `/dev/kvm`, `/dev/vhost-vsock`, TDX
kernel support, QGS, and firmware on the host.

## RuntimeClass mismatch

This deployment uses the Linux guest kernel and `kata-qemu-tdx-linux` for both
OpenClaw and NanoBot. If a Pod references another RuntimeClass, delete and
recreate it with `kata-qemu-tdx-linux`; `runtimeClassName` cannot be changed on
an existing Pod.
