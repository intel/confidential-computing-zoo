# OpenClaw Agent 示例

本目录包含一个示例适配器，演示 OpenClaw 如何与 Agent-CC 集成作为运行时信任验证框架。

## 概述

OpenClaw Agent 是一个在 Intel TDX 虚拟机中运行的 AI agent 运行时，它利用 Agent-CC 的核心服务进行可信的 agent-to-service 通信。

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

## 快速开始

```bash
# 一键真实 quote 路径：compose 栈 + tc-api launch + real Guard + OpenClaw。
cd ../../OpenViking/examples
export TC_API_IDENTITY_TOKEN=<sigstore-identity-token>
./run_openclaw_openviking_e2e.sh
```

如果 OpenViking workload 已经在 `:8010` 健康运行，可以追加
`SKIP_LAUNCH=1` 复用现有 workload，跳过 tc-api launch。

对于真实的 tc-api + Docker 路径，现在可以直接使用 OpenViking 示例目录下的
`docker-compose.tc-api.yml` 和 `launch_openviking_via_tc_api.sh`。新的
`run_openclaw_openviking_e2e.sh` 已经把这条路径与 real-verifier Guard
启动和 OpenClaw 最终验证串成一个脚本。

该示例会调用本地 Argus Guard 的 `POST /ra/v1/verify` 接口，验证目标服务，
并把 Guard 返回的 `report_data` 当作本地 secret release 和上下文存储的绑定值。

## 验证状态

截至 2026-06-29，已经真实验证：

- 交互式 Sigstore 登录下的 tc-api `deploy-launch` 成功，并拉起了运行中的
    OpenViking workload，监听 `http://127.0.0.1:8010`。
- Argus provider 已能返回带 tc-api 元数据的 claims，包括 `launch_id`、
    `image_digest` 和 `transparency_log_id`。
- Argus provider 已通过 tc-api `POST /v1/attestation` 生成真实 TDX quote，
    不再回退到 mock evidence。
- Guard 已在不设置 `ARGUS_ALLOW_MOCK_VERIFIER=1` 的 real verifier 模式下
    成功接受 provider 返回的 quote。
- `openclaw_agent.py` 已真实完成以下端到端链路：
    OpenClaw -> Guard -> Provider -> OpenViking `POST /verify/caller` ->
    `POST /context` -> `GET /context/{id}/metadata` -> `GET /context/{id}`。

## 运行前提

- OpenClaw 一侧可访问本地 Argus Guard：`http://localhost:8007`
- OpenViking 一侧单独运行 Argus Evidence Provider，并且 Guard 能访问到它
- 如果希望走真实 quote 路径，需要当前机器具备 Intel TDX 和 TSM 支持

## 真实双侧部署步骤

```bash
# 在 OpenViking 示例目录一键拉起 compose、launch workload、启动 real Guard，并执行 OpenClaw。
cd ../../OpenViking/examples
export TC_API_IDENTITY_TOKEN=<sigstore-identity-token>
./run_openclaw_openviking_e2e.sh
```

## 预期输出

```text
OpenClaw Agent - Agent-CC Integration Example

[1] Verifying OpenViking through Argus Guard...
    TCB Status: UpToDate
    Service Name: openviking-cmem
    Workload ID: openviking-cmem
    Launch ID: launch-...
    Image Digest: sha256:...
    Rekor UUID: ...
    Transparency Log ID: ...
    RTMR0: ...

[2] Creating attestation context...
[3] Retrieving attestation-gated secret...
[4] Storing context with attestation binding...
[5] Retrieving context with binding verification...
```

当前仓库里的 live TSM 路径在 quote 结构校验和请求绑定校验通过后会返回
`TCB Status: UpToDate`，便于上层默认策略继续执行。但这还不代表已经完成
基于 collateral 的 TCB 新鲜度判定。

上面这些额外元数据行只有在 OpenViking 一侧通过 tc-api 管理的 Docker / launch
路径启动时才会出现。单独执行 `python3 openviking_service.py --serve` 仍然可以
返回证明结果，但如果 tc-api 没有跟踪这个 workload，就不会带出 `image_digest`、
`launch_id`、`Rekor UUID` 这类 tc-api 相关字段。

## 基于 tc-api 的 OpenViking 部署

如果希望在 Argus claims 中带出 `image_digest`、`launch_id` 和 Rekor 标识，
OpenViking 一侧需要通过 tc-api 或其他 Docktap 管理的 Docker 路径启动，而不是
只运行 Python demo。

1. 在 OpenViking 一侧启动 tc-api。
2. 通过 `POST /api/deploy-launch` 启动 OpenViking workload，并把 `metadata.workload_id` 设为 `openviking-cmem`。
3. 为 sidecar/provider 进程设置 `ARGUS_SERVICE_ID=openviking-cmem` 和 `TC_API_WORKLOAD_ID=openviking-cmem`，让 Argus 按 workload ID 查询 tc-api，而不是按 provider 自己的 container ID 查询。
4. 在 OpenClaw 一侧把 Guard 的 `EVIDENCE_ENDPOINT` 指向这个 provider：`http://<openviking-provider-host>:8008`。

Provider 一侧示例环境变量：

```bash
export ARGUS_WORKLOAD_IDENTITY=openviking-cmem
export ARGUS_SERVICE_ID=openviking-cmem
export TC_API_WORKLOAD_ID=openviking-cmem
export TC_API_URL=http://127.0.0.1:8000
./start_argus.sh start-provider
```

## 实现文件

| 文件 | 描述 |
|------|-------------|
| [openclaw_agent.py](openclaw_agent.py) | 工作 Python 实现 |
| [README.md](README.md) | 英文文档 |
| [README_CN.md](README_CN.md) | 中文文档 |