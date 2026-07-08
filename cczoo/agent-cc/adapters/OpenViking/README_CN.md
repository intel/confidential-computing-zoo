# OpenViking Service 示例

本目录包含一个示例适配器，演示 OpenViking 如何与 Agent-CC 集成作为机密 Agent memory 服务。

## 概述

OpenViking 是专为 AI 智能体设计的开源上下文数据库，提供基于证明的上下文存储和检索。本示例展示 OpenViking 如何使用 Agent-CC 的核心服务进行可信上下文传输。

## 上下文网关操作

OpenViking 暴露的上下文操作均基于证明：

| 操作 | 描述 | 需要证明 |
|------|------|----------|
| `observe` | 读取上下文元数据（不物化） | 是 |
| `recall` | 物化上下文以供处理 | 是 |
| `commit` | 存储带证明绑定的上下文 | 是 |
| `privacy_restore` | 恢复加密上下文 | 是 |

## OpenClaw 集成

OpenViking 通过 verify-skill trust gate 与 OpenClaw 配合工作：

- OpenClaw 在发送上下文前调用本地 verify skill
- Verify skill 验证 OpenViking 或网关证明
- 当验证失败或不可用时，上下文传输被拒绝

详见 [OpenViking Trusted Context Gate 规范](../../openspec/specs/openviking-trusted-context-gate/spec.md)。

## 部署模式

### 1. Python Demo 模式

`openviking_service.py` 提供内存态演示，用于验证 trust-gate 流程：

```bash
# 内存态演示（自动退出）
python3 scripts/openviking_service.py

# HTTP 服务模式
python3 scripts/openviking_service.py --serve
```

> **注意**：Demo 模式（`openviking_service.py`）在内存中运行，无真实 TDX quote。
> 要进行端到端测试，请参考 [OpenClaw 到服务保护指南](../OpenClaw/openclaw_to_service_protection_CN.md)。

### 2. tc-api 管理模式

通过 tc-api 管理的 Docker 启动路径运行时，Argus claims 才能带出 tc-api 元数据：

1. `configs/docker-compose.tc-api.yml`：启动本地 registry、tc-api，以及 Argus Evidence Provider
2. `configs/Dockerfile.tc-api-workload`：打包 `openviking_service.py --serve` 成真正的 service workload 镜像
3. `scripts/launch_openviking.sh`：构建镜像、推送到本地 registry，并提交 deploy-launch 请求

### 2.1 LUKS 落盘保护（暂缓支持）

`openviking_service.py` 可以将 context 持久化到 `OPENVIKING_DATA_DIR`，但
tc-api 有意拒绝任意 Docker 命令覆盖。目前尚未实现结构化且经过路径校验的
LUKS 数据卷挂载 API，因此 `launch_openviking.sh` 在默认
`OPENVIKING_USE_LUKS=1` 时会安全地拒绝启动。仅可在非生产测试中设置
`OPENVIKING_USE_LUKS=0`；此模式使用容器自身存储，不提供静态数据加密。
在受限挂载 API 实现前，不要传入 `dockercmd` 或声称数据已加密落盘。

仅非生产测试时，可从仓库根目录运行：

```bash
cd cczoo/agent-cc/adapters/OpenViking/scripts
OPENVIKING_USE_LUKS=0 ./launch_openviking.sh
```

OpenViking 本身不启动 Argus Evidence Provider。预期流程是只在
OpenViking 一侧使用 `ARGUS_WORKLOAD_IDENTITY=openviking-cmem` 启动 provider，
而 OpenClaw 一侧运行自己的本地 Guard，并通过 `EVIDENCE_ENDPOINT` 指向
这个远端 provider。

如果希望在 Argus claims 中带出 `image_digest`、`launch_id` 和 Rekor 标识符，
provider 还需要设置 `ARGUS_SERVICE_ID` 和 `TC_API_WORKLOAD_ID`，并且
这两个值必须与 tc-api 为 OpenViking Docker workload 分配或接收的 workload ID 一致。

可运行示例默认采用 `STRICT_MODE=false`。在当前 live TSM 路径下，只要
quote 结构校验和请求绑定校验通过，Argus 就会返回 `TCB Status: UpToDate`。
这个状态可以满足示例里的默认策略流转，但它仍然不代表已经完成
collateral-backed 的 TCB 新鲜度判定。

## 运行步骤

**完整端到端测试请参考 [OpenClaw 到服务保护指南](../OpenClaw/openclaw_to_service_protection_CN.md)**

该文档包含：
- 前置条件检查
- 环境验证步骤
- 构建说明
- 完整 e2e 测试运行命令

## Provider 一侧环境变量示例

```bash
cd <work_dir>/confidential-computing-zoo/cczoo/agent-cc/core/argus
export ARGUS_WORKLOAD_IDENTITY=openviking-cmem
export ARGUS_SERVICE_ID=openviking-cmem
export TC_API_WORKLOAD_ID=openviking-cmem
export TC_API_URL=http://127.0.0.1:8000
./start_argus.sh start-provider
```

## 另请参阅

- [OpenViking Trusted Context Gate 规范](../../openspec/specs/openviking-trusted-context-gate/spec.md)
- [Argus Verifier](../../core/argus/README.md) - TDX quote 验证
- [TC-API Service](../../core/tc-api/README.md) - 构建到运行时的信任