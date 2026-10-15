# OpenViking 工作负载证明适配

此适配器使用共享的工作负载证明运行时部署官方 OpenViking Server，
并对服务访问进行身份认证。

## 安全模型与状态

受支持的部署使用 TC-API `nginx-spiffe` workload profile。运行参数来自
root-owned operator 配置，而不是请求中提供的 Docker 参数。该 profile 使用
Docker bridge 网络、只读 rootfs 和只读配置挂载、独立可写数据挂载、无新增
capabilities 以及受限 `/tmp`。业务容器不会获得 TDX 设备、SPIRE socket 或
SVID 私钥。

由宿主机管理的 NGINX 使用工作负载的 X.509-SVID，并要求 mTLS、精确的客户端
SPIFFE ID allowlist，以及 OpenViking API-key 授权。Docker 会在宿主机网络接口
上发布配置的 TLS 端口，并非仅绑定 loopback。请使用网络/防火墙策略将端口限制
到可信客户端。普通请求使用已经建立的 mTLS 身份，不会逐次触发新的远程证明。

旧的 [`scripts/launch_openviking.sh`](scripts/launch_openviking.sh) 通用启动路径
仍会 fail-closed。请使用下文的工作负载证明部署方式；不要通过任意 Docker 命令
覆盖绕过安全检查。

## 构建固定版本镜像

选择经过测试的官方版本并解析其不可变基础镜像 digest：

```bash
cd cczoo/agent-cc/adapters/OpenViking
export OPENVIKING_BASE='ghcr.io/volcengine/openviking@sha256:<approved-base-digest>'
export OPENVIKING_IMAGE='registry:5000/openviking:<approved-release>'
docker build --build-arg OPENVIKING_BASE="$OPENVIKING_BASE" \
  -f configs/Dockerfile.openviking -t "$OPENVIKING_IMAGE" .
docker push "$OPENVIKING_IMAGE"
docker image inspect "$OPENVIKING_IMAGE" --format '{{.Id}}'
```

Docker image config ID（`.Id`）是 `approved.image_config_digest` 所需的值，
它不同于 registry manifest 和基础镜像 digest。包装 Dockerfile 固定 server
entrypoint 并清空继承的 command。

## 准备应用配置和加密数据

先将专用 LUKS 文件系统挂载到 `/srv/openviking`，再创建以下路径。TC-API profile
会校验配置路径并以结构化方式挂载，但不会验证底层文件系统类型。请确认挂载源
是预期的 dm-crypt 设备，并在工作负载运行期间保持挂载：

```bash
findmnt --mountpoint /srv/openviking >/dev/null || {
  echo "/srv/openviking 必须是已挂载的 LUKS 挂载点" >&2
  exit 1
}
findmnt --noheadings --output SOURCE,FSTYPE --mountpoint /srv/openviking
sudo install -d -m 0700 /srv/openviking/data
sudo install -m 0600 configs/ov.conf.example /srv/openviking/ov.conf
```

替换 `ov.conf.example` 中所有占位符，包括 root API key、Embedding/VLM provider、
endpoint、model 和 API key。root key 仅保留在服务端，客户端应使用专用 User API
Key。不要提交完成后的配置文件，也不要将其打包进镜像。将配置文件准确的
SHA-256 记录为 `approved.config_digest`。

示例部署会将应用配置与声明的监听端口和数据路径进行核对：

| OpenViking 设置 | Workload 设置 |
|---|---|
| `server.host = 127.0.0.1` | NGINX 与 workload 共享 network namespace |
| `server.port = 1933` | `workload.listen_port = 1933` |
| 宿主机 `ov.conf` | 只读挂载到 `/etc/openviking/ov.conf` |
| `OPENVIKING_CONFIG_FILE` | 必须与 `workload.config_path` 一致 |
| `storage.workspace = /var/lib/openviking` | 可写宿主机路径为 `/srv/openviking/data` |
| NGINX TLS 端口 `1943` | 配置中的 `tls_port` 和 `published_port` |

配置检查验证已声明的 JSON 字段和值类型，但不能证明应用代码会持续读取该文件。
运行时 supervisor 还会监控已登记的进程、配置摘要和监听端口。

## 部署与验证

按照[工作负载证明部署指南](../../core/spire/workload/README.md)构建/安装运行时，
并配置 Trustee、SPIRE 与 TC-API。严格的 root-owned `environment.json` 必须包含
已批准的 image config ID、配置摘要、TDX measurements、精确的客户端 SPIFFE ID
以及 OpenViking 宿主机/容器路径。

将 TC-API 的 `ARGUS_WORKLOAD_CONFIG` 指向受保护的 workload export。如果 TC-API
运行在容器中，应只读挂载该文件，并将 `config_host_path` 与 `data_host_path`
以 Docker host 使用的相同路径提供给容器。请求通过
`workload_attestation_profile=nginx-spiffe` 选择 profile；该 profile 从受保护的
export 派生 Docker 参数和环境变量，并拒绝任意命令覆盖。

在 guest 上使用部署指南中的生命周期命令：

```bash
sudo python3 /opt/argus-workload/scripts/workload.py launch \
  --config /etc/argus-workload/environment.json
sudo python3 /opt/argus-workload/scripts/workload.py register \
  --config /etc/argus-workload/environment.json
sudo python3 /opt/argus-workload/scripts/workload.py preflight \
  --config /etc/argus-workload/environment.json
sudo python3 /opt/argus-workload/scripts/workload.py start \
  --config /etc/argus-workload/environment.json
sudo --preserve-env=OPENVIKING_API_KEY \
  python3 /opt/argus-workload/scripts/workload.py verify \
  --config /etc/argus-workload/environment.json
```

客户端使用有效 SVID、私钥、信任 bundle、allowlist 中的 SPIFFE ID，以及
OpenViking User API Key 访问 `https://<guest>:1943`。Root API Key 仅保留在服务端。
操作中断后，使用原 launch ID 执行 `resume-launch`；先协调现有生命周期状态，
不要直接创建替代实例。

共享运行时支持显式的 mTLS 客户端和 API-key header。目前的
[`connect_openclaw_openviking.sh`](../OpenClaw/scripts/connect_openclaw_openviking.sh)
仅配置普通 API-key 插件客户端，不会提供 mTLS SVID/私钥，因此不能直接连接此
mTLS endpoint。将 OpenClaw 流量转发到该服务前，需先配置客户端证书集成。

## 参考

- [工作负载证明部署指南](../../core/spire/workload/README.md)
- [工作负载证明架构](../../core/spire/workload/ARCHITECTURE.md)
- [TC-API workload profile](../../core/tc_api/README.md#workload-attestation-profile)
- [OpenClaw 适配指南](../OpenClaw/openclaw_to_service_protection_CN.md)
