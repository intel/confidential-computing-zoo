# OpenViking 适配器

此适配器将官方 OpenViking Server 部署为 `openviking-cmem` workload，并通过
官方插件接入 OpenClaw。

## 安全边界

容器仅发布 `127.0.0.1:1933`，所有 OpenViking 状态均保存在
`/app/.openviking`，不使用 privileged 或 host network。

## 启动前准备

明确 Embedding 和 VLM 的 provider、model、endpoint 与密钥。以
`cczoo/agent-cc/adapters/OpenViking` 为工作目录，在选定的存储挂载点创建
受限配置文件：

```bash
export OPENVIKING_LUKS_MOUNT_ROOT="<mounted-storage-path>"
export OPENVIKING_LUKS_SUBDIR=openviking
OPENVIKING_HOST_DATA_DIR="${OPENVIKING_LUKS_MOUNT_ROOT}/${OPENVIKING_LUKS_SUBDIR}"
mkdir -p "$OPENVIKING_HOST_DATA_DIR"
cp configs/ov.conf.example "$OPENVIKING_HOST_DATA_DIR/ov.conf"
chmod 700 "$OPENVIKING_HOST_DATA_DIR"
chmod 600 "$OPENVIKING_HOST_DATA_DIR/ov.conf"
```

拉取并记录经过验证的官方镜像 digest，不能使用 `latest`：

```bash
docker pull "ghcr.io/volcengine/openviking:<tested-version>"
docker image inspect "ghcr.io/volcengine/openviking:<tested-version>" \
  --format '{{index .RepoDigests 0}}'
```

部署前使用同一 digest 验证配置：

```bash
docker run --rm \
  -v "$OPENVIKING_HOST_DATA_DIR:/app/.openviking" \
  "ghcr.io/volcengine/openviking@sha256:<digest>" \
  openviking-server doctor
```

## 启动与验证

脚本使用 `configs/Dockerfile.openviking` 构建本地包装镜像并通过 TC API
启动。必须显式提供版本和固定 digest：

```bash
export OPENVIKING_VERSION="<tested-version>"
export OPENVIKING_BASE="ghcr.io/volcengine/openviking@sha256:<digest>"
(cd scripts && ./launch_openviking.sh)
```

验证服务与就绪状态：

```bash
curl -fsS http://127.0.0.1:1933/health
curl -fsS http://127.0.0.1:1933/ready
```

## 接入 OpenClaw

使用 Root Key 创建 OpenClaw 专用 User API Key，不能将 Root Key 交给
OpenClaw。确认 Gateway 的 Node.js 与 OpenClaw 版本满足官方插件要求后执行：

```bash
export OPENVIKING_API_KEY="<openclaw-user-key>"
../OpenClaw/scripts/connect_openclaw_openviking.sh
```

该脚本检查 `/health` 和 `/ready`，安装官方 OpenViking 插件，配置
`http://127.0.0.1:1933` 并显示插件状态。Gateway state 必须持久化，否则容器
重建会丢失插件及配置。
