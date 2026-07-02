# OpenViking Service 示例

本目录包含一个示例适配器，演示 OpenViking 如何与 Agent-CC 集成作为机密内存服务。

## 概述

OpenViking 是一个机密内存控制平面服务，提供基于证明的上下文存储和检索。本示例展示 OpenViking 如何使用 Agent-CC 的核心服务进行可信上下文传输。

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                   OpenViking Service (TDVM)                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  OpenViking Confidential Memory Control Plane               │ │
│  │  - Context Gateway                                          │ │
│  │  - Encrypted Storage                                        │ │
│  │  - Trust Policy Engine                                      │ │
│  │  - Attestation Verifier                                     │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ 基于证明的上下文传输
┌─────────────────────────────────────────────────────────────────┐
│                     Agent-CC Core Services                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Argus     │  │   TC-API    │  │  Trust      │              │
│  │  Verifier   │  │  Service    │  │  Service    │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

## 上下文网关操作

OpenViking 暴露的上下文操作均基于证明：

| 操作 | 描述 | 需要证明 |
|------|------|----------|
| `observe` | 读取上下文元数据（不物化） | 是 |
| `recall` | 物化上下文以供处理 | 是 |
| `commit` | 存储带证明绑定的上下文 | 是 |
| `privacy_restore` | 恢复加密上下文 | 是 |

## 实现文件

| 文件 | 描述 |
|------|-------------|
| [openviking_service.py](openviking_service.py) | 工作 Python 实现 |
| [Dockerfile.tc-api-workload](Dockerfile.tc-api-workload) | 用于 tc-api 管理启动路径的 OpenViking workload 镜像 |
| [docker-compose.tc-api.yml](docker-compose.tc-api.yml) | 真实 Docker 启动流程所需的 tc-api + registry + Argus Provider 编排 |
| [launch_openviking_via_tc_api.sh](launch_openviking_via_tc_api.sh) | 构建、推送并通过 tc-api 启动 OpenViking workload |

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
python3 openviking_service.py

# HTTP 服务模式
python3 openviking_service.py --serve
```

### 2. tc-api 管理模式

通过 tc-api 管理的 Docker 启动路径运行时，Argus claims 才能带出 tc-api 元数据：

1. `docker-compose.tc-api.yml`：启动本地 registry、tc-api，以及 Argus Evidence Provider
2. `Dockerfile.tc-api-workload`：打包 `openviking_service.py --serve` 成真正的 service workload 镜像
3. `launch_openviking_via_tc_api.sh`：构建镜像、推送到本地 registry，并提交 deploy-launch 请求

## 运行步骤

**完整端到端测试请参考 [OpenClaw Examples README](../../OpenClaw/examples/README.md)**

该文档包含：
- 前置条件检查
- 环境验证步骤
- 构建说明
- 完整 e2e 测试运行命令

Provider 一侧环境变量示例：

```bash
cd ../../../core/argus
export ARGUS_WORKLOAD_IDENTITY=openviking-cmem
export ARGUS_SERVICE_ID=openviking-cmem
export TC_API_WORKLOAD_ID=openviking-cmem
export TC_API_URL=http://127.0.0.1:8000
./start_argus.sh start-provider
```

关键点在于：`ARGUS_SERVICE_ID` 和 `TC_API_WORKLOAD_ID` 必须与 tc-api 在
`POST /api/deploy-launch` 时接收的 workload ID 保持一致。这样 provider 才能按
workload ID 查询 tc-api，拿到目标服务的 image digest、launch ID，以及可用的
Rekor 标识。

### 端到端步骤

1. 在 OpenViking 一侧启动控制面和 provider：

```bash
cd ../../../adapters/OpenViking/examples
docker-compose -f docker-compose.tc-api.yml up -d registry tc-api argus-provider
```

2. 导出一个 tc-api 写接口凭证。可以使用 `TC_API_IDENTITY_TOKEN` 放到请求体，
也可以使用 `TC_API_BEARER_TOKEN` 走 Authorization 头：

```bash
export TC_API_IDENTITY_TOKEN='<sigstore token>'
```

如果你不是预先导出 token，而是走交互式 Sigstore 登录，也要保持 payload 中
使用 `docker://registry:5000/openviking-cmem:latest`。`docker://localhost:5000/...`
虽然能通过格式校验，但镜像拉取发生在 tc-api 容器内部，会连不到 registry。

3. 通过 tc-api 构建并启动 OpenViking workload：

```bash
./launch_openviking_via_tc_api.sh
```

4. 在 OpenClaw 一侧，把 Guard 指向 OpenViking provider，并把目标 URI 设为
刚刚启动的 workload 监听地址：

```bash
cd ../../../core/argus
export EVIDENCE_ENDPOINT=http://<openviking-host>:8008
export ARGUS_ALLOW_MOCK_VERIFIER=1
./start_argus.sh start-guard

cd ../../../adapters/OpenClaw/examples
export TARGET_SERVICE_NAME=openviking-cmem
export TARGET_URI=http://<openviking-host>:8010
python3 openclaw_agent.py
```

如果 launch 成功，`openclaw_agent.py` 现在就应该能看到稳定的服务名，以及
来自 tc-api 的 `launch_id`、`image_digest`、透明日志相关标识等字段。

### 验证状态

截至 2026-06-29，已经真实验证：

- 交互式 tc-api `deploy-launch` 已成功完成。
- 被拉起的 OpenViking workload 已在 `8010` 端口对 `GET /health` 返回成功。
- Argus provider 返回的 evidence 已包含来自 tc-api 的 `launch_id`、
    `image_digest` 和 `transparency_log_id`。
- OpenClaw 已真实完成针对该 workload 的端到端 HTTP 调用：调用方验证、
    上下文写入、元数据观察、上下文回读。

当前边界：

- provider 侧示例仍可能回退到 mock quote。因此本次端到端验证在 OpenClaw
    一侧的 Guard 上使用了 `ARGUS_ALLOW_MOCK_VERIFIER=1`。在这条路径上，
    “只接受完整真实 quote 的 Guard 校验” 还没有完成实测验证。

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    OpenClaw Agent Runtime                        │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  OpenClaw Agent (TDVM)                                      │ │
│  │  - LLM Client                                               │ │
│  │  - Context Manager                                          │ │
│  │  - Tool Executor                                            │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │ Attestation-gated context transfer
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   OpenViking Service (TDVM)                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  OpenViking Confidential Memory Control Plane              │ │
│  │  - Context Gateway                                          │ │
│  │  - Encrypted Storage                                        │ │
│  │  - Trust Policy Engine                                      │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Agent-CC Core Services                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Argus     │  │   TC-API    │  │  Trust      │              │
│  │  Verifier   │  │  Service    │  │  Service    │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```