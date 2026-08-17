# OpenClaw 适配器

本文介绍 OpenClaw 在 Intel TDX 环境中的容器部署、工具沙箱，以及与可信服务
的集成方式。

> **推荐的生产基线：** 对于本地 Ollama 和 LUKS 加密状态存储的原生 TDVM
> 部署，请参考 [OpenClaw 机密计算最佳实践指南](../../best-practices/README_CN.md)
> 和 [OpenClaw-CC 原生部署指南](../../../openclaw-cc/README.md)。

## 部署模式

| 模式 | 信任边界 | 能力 | 适用场景 |
| --- | --- | --- | --- |
| 原生 TDVM | 整个 TDVM | TDX 内存保护和原生 LUKS 状态存储 | 推荐的生产基线 |
| 容器沙箱 | 单个 TDVM；Docker 隔离工具容器 | 为工具执行创建短生命周期沙箱容器 | 不可信工具或 shell 工作负载 |
| TC-API 生命周期 | 单个 TDVM；Docker 与 TC-API | 构建/发布证据和基于证明的启动 | 可验证的构建到运行时流程 |

同一个 TDVM 内的容器共享内核和硬件信任边界。除非使用 Confidential
Containers（CoCo）或 Kata TDX，否则容器不构成独立硬件 TEE。

## 容器沙箱

从仓库根目录构建并启动仅绑定 loopback 主机端口的 Gateway：

```bash
cd cczoo/agent-cc/adapters/OpenClaw/scripts
bash run-sbx.sh --bind loopback
```

脚本使用持久化 Docker volume 保存 Gateway 配置和 workspace。未提供 token
时会生成一个；请在本地 UI 中输入，不要把 token 放入 URL、源码或日志。
默认容器名为 `openclaw-gateway`。

Gateway 可以在短生命周期的 `openclaw-sandbox:bookworm-slim` 容器中执行工具。
访问 Docker socket 等同于对 TDVM Docker daemon 的 root 级控制，因此只应授予
可信 Gateway 进程。

## 将 Ollama 配置为主模型

此连接器配置 OpenClaw 调用本地 Ollama，不执行 Argus 验证，也不会使模型访问
自动具备证明门控。请将 Ollama 模型文件保存在已挂载的 LUKS 卷中：

```bash
cd cczoo/agent-cc/adapters/OpenClaw/scripts
./run_ollama_luks.sh pull llama3.2
```

为了让 Gateway 容器访问宿主机服务、同时避免 Ollama 监听所有宿主机网卡，
请将 Ollama 绑定到 Docker bridge 地址，而不是 `0.0.0.0`：

```bash
DOCKER0_IP="$(ip -4 -o addr show dev docker0 | awk 'NR == 1 { split($4, a, "/"); print a[1] }')"
if [[ -z "$DOCKER0_IP" ]]; then
  echo "docker0 没有 IPv4 地址" >&2
  exit 1
fi
OLLAMA_HOST="${DOCKER0_IP}:11434" ./run_ollama_luks.sh serve
```

请在独立终端保持 `serve` 运行。在另一个终端重新获取 bridge 地址并配置
已启动的 Gateway：

```bash
cd cczoo/agent-cc/adapters/OpenClaw/scripts
DOCKER0_IP="$(ip -4 -o addr show dev docker0 | awk 'NR == 1 { split($4, a, "/"); print a[1] }')"
[[ -n "$DOCKER0_IP" ]] || { echo "docker0 没有 IPv4 地址" >&2; exit 1; }
export OPENCLAW_CONTAINER=openclaw-gateway
export OLLAMA_BASE_URL="http://${DOCKER0_IP}:11434"
export OLLAMA_CONTAINER_BASE_URL=http://host.docker.internal:11434
export OLLAMA_MODEL=llama3.2
./connect_openclaw_ollama.sh
```

`run-sbx.sh` 会为容器添加 `host.docker.internal:host-gateway` 映射。如果使用
其他 Gateway 容器或 Docker 网络，请设置实际的 `OPENCLAW_CONTAINER` 和
`OLLAMA_CONTAINER_BASE_URL`。绑定到 `docker0` 可限制对该 bridge 的暴露，但
bridge 上的其他可信容器仍可能访问未提供认证的 Ollama API；必要时使用防火墙
或专用网络进一步限制访问。

连接器会检查 Ollama 是否就绪、目标模型是否已安装、Gateway 容器是否可连通，
随后更新 provider 配置并重启 OpenClaw。`run_ollama_luks.sh` 要求 LUKS 卷已
挂载，并将模型保存在该卷下；需要加密存储时，不要改用普通的
`ollama pull` 或 `ollama serve`。

## TC-API 构建到运行时生命周期

TC-API 提供构建、发布和启动接口，可用于签名制品、SBOM 和运行时证明流程。
前置条件和 API 详情请参考 [TC-API 快速入门](../../core/tc_api/README.md)。
TC-API 的启动接口必须保持固定且受 allowlist 限制；不要传入调用方可控的
Docker 命令字符串。

## OpenViking 集成状态

OpenViking 官方镜像启动脚本目前会 fail-closed，因为 TC-API 启动路径使用
host network，且缺少仅 loopback 端口暴露以及经过路径校验的配置/数据卷挂载
参数。因此，之前的一键端到端流程暂不可用；当前限制请参考
[OpenViking 适配器指南](../OpenViking/README_CN.md)。
`connect_openclaw_openviking.sh` 不是 workload 启动器，只连接已经运行的服务。

## 安全边界

1. `/var/run/docker.sock` 可控制 TDVM 的 Docker daemon，只应授权给可信进程。
2. TD 内的容器共享内核和 TDX 信任边界；容器隔离不能替代最小权限、沙箱或策略控制。
3. 不要将 API token 或签名密钥存入镜像、源码、命令历史或日志。应在运行时注入
   短期凭据，或将凭据保存在加密密钥存储中。
4. 本地服务应绑定 loopback 或专用可信网络；不要默认认为容器或 host-network
   启动只对 loopback 开放。

## 相关文档

- [OpenClaw 容器保护](openclaw_container_protection_CN.md)
- [OpenViking 适配器](../OpenViking/README_CN.md)
- [Ollama 适配器](../Ollama/README.md)
- [Argus](../../core/argus/README.md)
- [TC-API](../../core/tc_api/README.md)
- [Trusted Log (TLog)](../../core/tlog/README.md)
- [OpenClaw 最佳实践](../../best-practices/README_CN.md)
