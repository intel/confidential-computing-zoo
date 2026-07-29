# OpenViking 适配器

此适配器计划将官方 OpenViking Server 部署为 `openviking-cmem` workload，
并通过官方插件接入 OpenClaw。

## 当前部署状态

启动脚本会安全地拒绝部署。当前 TC-API 启动路径使用 host network，且没有
结构化参数来限制端口仅绑定到 loopback，也没有经过路径校验的配置文件和数据卷
挂载接口。因此，目前无法保证 OpenViking 仅能通过 `127.0.0.1` 访问，也无法
保证状态数据保存在预期的加密卷中。

不要通过任意 Docker 命令覆盖绕过此检查。只有在 TC-API 提供受限的 loopback
端口接口，以及配置和 LUKS 状态卷的路径校验挂载 API 后，才应启用部署。

Compose 将发布的控制平面端口绑定到 `127.0.0.1`，但 TC-API 和 Evidence
Provider 需要特权 TDX 访问，且 TC-API 挂载了宿主机 Docker socket。仅在可信
主机上运行此开发环境。

## 准备固定版本的官方镜像

包装镜像以官方 OpenViking 镜像为基础。选择经过测试的版本并解析为不可变 digest：

```bash
docker pull "ghcr.io/volcengine/openviking:<tested-version>"
docker image inspect "ghcr.io/volcengine/openviking:<tested-version>" \
  --format '{{index .RepoDigests 0}}'
```

在 [`configs/ov.conf.example`](configs/ov.conf.example) 的副本中配置 Embedding 和
VLM provider、model、endpoint 与 API key。请将该文件作为密钥处理：替换全部
占位符、限制文件权限，且不要提交或将其打包进镜像。结构化配置和存储挂载接口
尚未实现，因此准备此文件并不会启用部署。

## 启动

`scripts/launch_openviking.sh` 会校验固定的基础镜像并定义 TC-API 部署流程，但
目前会在启动基础设施或提交部署请求之前退出，因为 TC-API 启动边界无法执行
所需的网络与挂载限制。不要使用 `latest` 标签，也不要添加调用方可控的 Docker
命令来绕过此限制。

待结构化 TC-API 接口实现后，预期的调用方式为：

```bash
export OPENVIKING_VERSION="<tested-version>"
export OPENVIKING_BASE="ghcr.io/volcengine/openviking@sha256:<digest>"
./scripts/launch_openviking.sh
```

## 验证并接入 OpenClaw

安全配置的 OpenViking workload 启动后，先检查健康状态，再接入 OpenClaw：

```bash
curl -fsS http://127.0.0.1:1933/health
curl -fsS http://127.0.0.1:1933/ready
```

OpenClaw Gateway 必须满足官方插件对 Node.js 和 OpenClaw 版本的要求。请创建
专用的 User API Key；不要将 Root Key 提供给 OpenClaw。

```bash
export OPENVIKING_API_KEY="<openviking-user-key>"
../OpenClaw/scripts/connect_openclaw_openviking.sh
```

连接脚本会检查两个服务探针、安装官方 OpenViking 插件、配置
`http://127.0.0.1:1933` 并显示插件状态。Gateway state 必须持久化，以免重建后
丢失插件及其配置。
