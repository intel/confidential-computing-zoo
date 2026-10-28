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

[Dockerfile.openviking](configs/Dockerfile.openviking)固定
`ENTRYPOINT ["openviking-server"]`、清空继承的 CMD，并以 UID/GID
`10001:10001` 运行应用。共享启动工具使用镜像的 `USER`，TC API 无须加入
应用专用的用户处理逻辑。构建后的实际 image config ID 用于部署配置的
`approved.image_config_digest`；它与 registry manifest digest、基础镜像
digest 是不同的值。镜像内容发生变化时，包括用户、环境变量或健康检查，
必须重新构建并批准新的 image config ID。

显式 Docker 健康检查从 `OPENVIKING_CONFIG_FILE` 指向的配置文件读取
`server.port`，不携带 API key，访问 `http://127.0.0.1:<port>/health`。
配置缺失或不可读、端口非法、HTTP 检查失败时，容器会被标记为不健康。
该检查只反映应用存活，不验证工作负载认证、API-key 授权或 Embedding/VLM
可用性，也不替代独立的 Helper/NGINX 就绪检查。

## 准备应用配置和加密数据

先将专用 LUKS 文件系统挂载到 `/srv/openviking`，再创建以下路径。配置受保护的
workload 配置时，应记录该 LUKS 后端设备的 UUID，并填入
`workload.data_luks_uuid`。TC-API profile 会在启动前检查数据路径对应的挂载和
device-mapper LUKS UUID；无法验证时会 fail-closed。工作负载运行期间应保持挂载：

```bash
findmnt --noheadings --output SOURCE,FSTYPE --mountpoint /srv/openviking
sudo install -d -o root -g root -m 0700 /srv/openviking
sudo install -d -o 10001 -g 10001 -m 0700 /srv/openviking/data
sudo install -o root -g 10001 -m 0640 configs/ov.conf.example /srv/openviking/ov.conf
```

对于 `findmnt` 显示的 mapper 设备，使用 `cryptsetup status <mapper>` 确认其
后端 LUKS 设备，再用 `cryptsetup luksUUID <backing-device>` 获取期望 UUID。
不要填 mapper 名称或文件系统 UUID。

参考 [ov.conf.example](configs/ov.conf.example)，填写
`/srv/openviking/ov.conf` 中的 root API key、Embedding 和 VLM 的 provider、
model、endpoint、密钥，以及所选 Embedding 模型的输出维度。保留配置文件的
root 所有权及组 `10001` 的读取权限（`0640`），应用不应拥有或修改该只读
配置文件。数据目录须允许容器内 UID/GID `10001:10001` 写入。上述属主示例
适用于未启用 user-namespace remapping 的 Docker；启用映射时，应使用对应
的宿主机映射 ID。审查完成后，将配置文件的准确 SHA-256 以 `sha256:<hex>`
格式填入 `approved.config_digest`。
运行时观察值仍须与批准配置匹配。

已有工作目录应先停止工作负载，再将数据文件属主迁移到应用账号后切换镜像。
创建数据目录的命令不会修改目录内已有文件的属主。

替换 `ov.conf.example` 中所有占位符，包括 root API key、Embedding/VLM provider、
endpoint、model 和 API key。root key 仅保留在服务端，客户端应使用专用 User API
Key。不要提交完成后的配置文件，也不要将其打包进镜像。将配置文件准确的
SHA-256 以 `sha256:<hex>` 格式填入 `approved.config_digest`。

示例部署会将应用配置与声明的监听端口和数据路径进行核对，并保持以下对应关系：

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

容器使用只读 rootfs、Docker bridge 网络、无 capabilities 和受限 `/tmp`，
仅发布 NGINX TLS 端口。业务容器不挂载 TDX 设备、SPIRE socket 或 SVID 私钥。
镜像设置 `HOME=/var/lib/openviking` 和
`XDG_CACHE_HOME=/var/lib/openviking/.cache`，使用户状态与缓存写入数据挂载；
`TMPDIR=/tmp` 使用受限临时挂载，`PYTHONDONTWRITEBYTECODE=1` 避免在已安装
Python 模块旁写入字节码。若修改 `data_path`，须在 `workload.environment`
中显式将 `HOME` 和 `XDG_CACHE_HOME` 改为该可写挂载内的路径。
宿主机上的 NGINX、Provider 和 Helper 继续使用各自的服务权限；应用用户变化
不改变这些组件的账号或进入 network namespace 的方式。

## 部署与验证

按照[工作负载证明部署指南](../../core/spire/workload/README.md)构建/安装运行时，
并配置 Trustee、SPIRE 与 TC-API。严格的 root-owned `environment.json` 必须包含
已批准的 image config ID、配置摘要、TDX measurements、精确的客户端 SPIFFE ID
以及 OpenViking 宿主机/容器路径。

将 TC-API 的 `ARGUS_WORKLOAD_CONFIG` 指向受保护的 workload export。如果 TC-API
运行在容器中，应只读挂载该文件，并将 `config_host_path` 与 `data_host_path`
以 Docker host 使用的相同路径提供给容器。还需将 Docker host 的 `/proc`、
`/run/docker.pid` 和 `/sys` 只读挂载到配置中的 `docker_host_proc_path`、
`docker_host_pid_path` 和 `docker_host_sysfs_dev_block_path` 对应位置，不能
指向 TC-API 自身隔离的容器 namespace。示例
[TC-API Compose 文件](configs/docker-compose.tc-api.yml)已包含这些挂载。请求通过
`workload_attestation_profile=nginx-spiffe` 选择 profile；该 profile 从受保护的
export 派生 Docker 参数和环境变量，并拒绝任意命令覆盖。

依次使用手册中的 `workload.py launch`、`register`、`preflight`、`start`。
登记必须定位到一个实际监听进程，核对批准的 executable、镜像和配置摘要以及
当前 launch。启动中断后使用 `resume-launch` 查询或完成原来的操作，不重新
创建替代容器。
`approved.executable` 须填写在可信客户机上观察到的实际监听进程
`/proc/<pid>/exe` 解析路径，不要从示例推断 Python 次版本。升级解释器时，
应同时审查该路径和新的 image config ID。

```bash
sudo --preserve-env=TC_API_BEARER_TOKEN,TC_API_IDENTITY_TOKEN \
  python3 /opt/argus-workload/scripts/workload.py launch \
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
