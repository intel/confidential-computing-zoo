# Upstream provenance

- Upstream: [spiffe/spiffe-helper](https://github.com/spiffe/spiffe-helper).
- Base release: [v0.11.0](https://github.com/spiffe/spiffe-helper/tree/v0.11.0).
- Source archive: [v0.11.0 tarball](https://codeload.github.com/spiffe/spiffe-helper/tar.gz/refs/tags/v0.11.0).
- Source archive SHA-256: `124b009c0dc737c5e5f7afd11eed4fe41b0ac9b98e98fc51cd1a49b38b3e6090`.

This directory contains the Helper runtime and its required packages, with
the upstream Apache-2.0 [LICENSE](LICENSE) retained. It embeds a subset of the
release; upstream CI, image-publishing machinery, examples and test assets
are not part of this runtime distribution.

Argus adds opt-in Broker configuration, PID-instance subscription, atomic
credential publication, progress/watchdog handling, local AuthZ, an Agent HCL
merge command and an mTLS service probe with explicit header/environment
bindings. Local operational events use structured JSON fields. Broker support
uses go-spiffe and the adjacent [workload module](../../workload/README.md). Ordinary Helper
operation continues through the upstream Workload API path.

Rebases must preserve the upstream license and review local changes against
the tagged release. Build and deployment instructions are maintained in the
[workload guide](../../workload/README.md).
