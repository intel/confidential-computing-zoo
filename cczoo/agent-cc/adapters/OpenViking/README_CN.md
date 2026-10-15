# OpenViking Workload Attestation 适配

本目录提供 `openviking-cmem` 的镜像与配置。部署由共享的
[工作负载认证工具](../../core/spire/workload/README.md)管理：先核验当前监听实例与
经过认证的生命周期历史，再由 SPIRE Server CA 签发独立的工作负载
X.509-SVID。NGINX 由 TDX 客户机内的受信组件管理，运行于业务容器之外，
使用该实例的身份提供 NGINX 服务入口，并将请求转发到已登记的后端。
请求需要通过 mTLS、客户端 SPIFFE ID 精确授权和 OpenViking 的 API-key 授权。

## 镜像

以 `cczoo/agent-cc/adapters/OpenViking` 为工作目录，使用已批准的官方基础镜像
digest 构建薄镜像：

```bash
export OPENVIKING_BASE='ghcr.io/volcengine/openviking@sha256:<approved-base-digest>'
export OPENVIKING_IMAGE='registry:5000/openviking:<approved-release>'
docker build --build-arg OPENVIKING_BASE="$OPENVIKING_BASE" \
  -f configs/Dockerfile.openviking -t "$OPENVIKING_IMAGE" .
docker push "$OPENVIKING_IMAGE"
docker image inspect "$OPENVIKING_IMAGE" --format '{{.Id}}'
```

[Dockerfile.openviking](configs/Dockerfile.openviking)固定
`ENTRYPOINT ["openviking-server"]` 并清空继承的 CMD。构建后的实际 image config
ID 用于部署配置的 `approved.image_config_digest`；它与 registry manifest
digest、基础镜像 digest 是不同的值。

## 应用配置

配置文件与可写数据使用 TDX 客户机内两个独立的容器宿主路径：

```bash
sudo install -d -m 0700 /srv/openviking /srv/openviking/data
sudo install -m 0600 configs/ov.conf.example /srv/openviking/ov.conf
```

填写 [ov.conf.example](configs/ov.conf.example) 中的 root API key、Embedding
和 VLM 的 provider、model、endpoint、密钥，以及所选 Embedding 模型的输出
维度，并确保应用运行账号可以写入数据目录。审查完成后，将配置文件的准确
SHA-256 以 `sha256:<hex>` 格式填入 `approved.config_digest`。
运行时观察值仍须与批准配置匹配。

示例与统一部署配置保持以下对应关系：

| OpenViking / TDX 客户机设置 | Workload 部署设置 |
|---|---|
| `server.host = 127.0.0.1` | 由同一 network namespace 内的 NGINX 访问业务监听端口 |
| `server.port = 1933` | `workload.listen_port = 1933` |
| 宿主机 `/srv/openviking/ov.conf` | `config_host_path`；只读挂载到 `config_path = /etc/openviking/ov.conf` |
| `OPENVIKING_CONFIG_FILE=/etc/openviking/ov.conf` | `config_env = OPENVIKING_CONFIG_FILE`，`workload.environment` 中同名变量的值与配置路径一致 |
| `storage.workspace = /var/lib/openviking` | `data_path = /var/lib/openviking`；宿主机可写目录为 `data_host_path = /srv/openviking/data` |
| NGINX TLS 端口 `1943` | `tls_port = 1943`，`published_port = 1943` |

部署示例在 `workload.config_json_checks` 中显式声明
上述 OpenViking 字段校验，在 `workload.environment` 中设置
`PYTHONDONTWRITEBYTECODE=1` 和 `OPENVIKING_WITH_BOT=0`。共享启动与认证代码
按声明执行，不识别 OpenViking 专用字段。

容器使用只读 rootfs、独立 bridge network namespace、无 capabilities 和受限
`/tmp`，仅发布 NGINX TLS 端口。业务容器不挂载 TDX 设备、SPIRE socket 或
SVID 私钥。

## 部署与业务访问

按[部署手册](../../core/spire/workload/README.md)构建、安装认证组件，配置
Trustee policy 和 SPIRE entries，并向 TC API 提供 `ARGUS_WORKLOAD_CONFIG`。
使用 `nginx-spiffe` workload attestation profile，由受保护配置生成
挂载和环境变量；该模式拒绝任意启动命令覆盖。

依次使用手册中的 `workload.py launch`、`register`、`preflight`、`start`。
登记必须定位到一个实际监听进程，核对批准的 executable、镜像和配置摘要以及
当前 launch。启动中断后使用 `resume-launch` 查询或完成原来的操作，不重新
创建替代容器。

客户端使用有效 SVID、私钥与信任 bundle 访问 `https://<guest>:1943`，其完整
SPIFFE ID 必须在精确 allowlist 中，同时验证配置中的目标 SPIFFE ID。
OpenViking 自身的 API-key 授权继续生效。客户端应使用 OpenViking 用户 API key，
root API key 保留在服务端。认证工具的 `verify` 使用提供的
客户端凭据检查当前身份交付和一次已授权业务请求。示例的 `business_headers`
将 `X-API-Key` 显式映射到 `OPENVIKING_API_KEY`；通过 sudo 运行 `verify` 时需
显式保留该变量。直接运行客户端探针时传入
`-header-env X-API-Key=OPENVIKING_API_KEY`，探针不会隐式读取 API-key 变量。
mTLS 认证通信身份；NGINX 处理请求期间，Helper 检查已登记的进程、配置和监听端口。
普通请求不逐次执行远程证明。

停止或更换实例时，使用认证生命周期工具和现有 TC API/Docktap 操作路径。
新的 PID 实例需要独立登记与准入，即使逻辑 SPIFFE ID 沿用原值。同一有效
订阅内的 SVID 更新复用准入；新订阅需要重新取证。凭据清理、SVID 续期和
本地监督的边界见[架构说明](../../core/spire/workload/ARCHITECTURE.md)。
