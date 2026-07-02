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

## 实现文件

| 文件 | 描述 |
|------|-------------|
| [scripts/openclaw_agent.py](scripts/openclaw_agent.py) | 工作 Python 实现 |
| [scripts/run_openclaw_openviking_e2e.sh](scripts/run_openclaw_openviking_e2e.sh) | 一键真实 quote e2e 运行脚本 |
| [README.md](README.md) | 英文文档 |
| [README_CN.md](README_CN.md) | 中文文档 |

## 集成点

### 1. Evidence Provider 集成

OpenClaw 通过 Agent-CC Evidence Provider 获取 TDX 证明证据：

```rust
// 示例：为 OpenClaw 运行时获取证明证据
use argus::EvidenceFetcher;

pub struct OpenClawEvidenceProvider {
    evidence_endpoint: String,
}

impl OpenClawEvidenceProvider {
    pub fn new() -> Self {
        Self {
            evidence_endpoint: std::env::var("EVIDENCE_ENDPOINT")
                .unwrap_or_else(|_| "http://localhost:8008".to_string()),
        }
    }

    /// 获取 OpenClaw 运行时证明的 TDX quote
    pub async fn fetch_runtime_attestation(&self) -> Result<AttestationEvidence> {
        let evidence = EvidenceFetcher::new(&self.evidence_endpoint)
            .with_service_identity("openclaw-agent")
            .fetch_evidence()
            .await?;
        
        Ok(AttestationEvidence {
            quote: evidence.tdx_quote,
            runtime_measurements: evidence.rtmr_values,
            tcb_status: evidence.tcb_status,
        })
    }
}
```

### 2. 基于证明的 Secret 释放

OpenClaw 仅在证明验证成功后检索 secrets：

```rust
// 示例：基于证明的 API key 检索
use argus::{AttestationContext, SecretStore};

pub struct OpenClawSecretManager {
    secret_store: SecretStore,
}

impl OpenClawSecretManager {
    /// 仅在证明通过时获取 API key
    pub async fn get_api_key(&self, key_id: &str) -> Result<String> {
        let attestation = AttestationContext::new()
            .with_minimum_assurance_level("L2")
            .verify()
            .await?;

        if !attestation.is_trusted() {
            return Err(AgentError::AttestationFailed {
                reason: "OpenClaw runtime attestation verification failed".to_string(),
            });
        }

        self.secret_store
            .get_secret(key_id, &attestation)
            .await
    }
}
```

### 3. 加密上下文存储

OpenClaw 使用 Agent-CC 的加密存储来保存敏感上下文：

```rust
// 示例：带证明绑定的加密上下文存储
use argus::{EncryptedStorage, AttestationBinding};

pub struct OpenClawContextManager {
    storage: EncryptedStorage,
}

impl OpenClawContextManager {
    /// 带证明绑定存储上下文
    pub async fn store_context(
        &self,
        context_id: &str,
        context_data: &[u8],
        binding: &AttestationBinding,
    ) -> Result<()> {
        self.storage
            .store_encrypted(context_id, context_data, binding)
            .await
    }

    /// 仅在证明匹配时检索上下文
    pub async fn retrieve_context(
        &self,
        context_id: &str,
        expected_binding: &AttestationBinding,
    ) -> Result<Vec<u8>> {
        let context = self.storage
            .retrieve_encrypted(context_id, expected_binding)
            .await?;

        Ok(context)
    }
}
```

## 配置

### 环境变量

```bash
# OpenClaw Agent 配置
AGENT_SERVICE_NAME=openclaw-agent
AGENT_INSTANCE_ID=openclaw-instance-001

# Evidence Provider
EVIDENCE_ENDPOINT=http://localhost:8008

# Guard Service（用于服务间证明）
GUARD_ENDPOINT=http://localhost:8007
BINDING_ASSURANCE_LEVEL=L2

# 加密存储
ENCRYPTED_VFS_PATH=/mnt/encrypted
```

### Docker Compose 示例

```yaml
# filepath: docker-compose.yml
services:
  openclaw-agent:
    image: openclaw:latest-tdx
    environment:
      HOST: 0.0.0.0
      PORT: 8009
      EVIDENCE_ENDPOINT: http://argus-evidence-provider:8008
      GUARD_ENDPOINT: http://argus-guard:8007
      BINDING_ASSURANCE_LEVEL: L2
      ENCRYPTED_VFS_PATH: /mnt/encrypted
    volumes:
      - encrypted_vfs:/mnt/encrypted
    depends_on:
      - argus-evidence-provider
      - argus-guard
    devices:
      - /dev/tdx_guest:/dev/tdx_guest
    cap_add:
      - SYS_ADMIN
    security_opt:
      - seccomp:unconfined

  argus-evidence-provider:
    image: argus-evidence-provider:latest
    environment:
      HOST: 0.0.0.0
      PORT: 8008
      RUST_LOG: info
    volumes:
      - tsm_socket:/var/run/tsm

  argus-guard:
    image: argus-guard:latest
    environment:
      HOST: 0.0.0.0
      PORT: 8007
      EVIDENCE_ENDPOINT: http://argus-evidence-provider:8008
      BINDING_ASSURANCE_LEVEL: L2
      RUST_LOG: info

volumes:
  encrypted_vfs:
```

## 验证流程

```
1. OpenClaw 在 TDVM 中启动
         │
         ▼
2. 从 TSM 获取 TDX Quote
         │
         ▼
3. 发送到 Evidence Provider
         │
         ▼
4. Argus 验证 quote 结构
         │
         ▼
5. Argus 验证 nonce 绑定
         │
         ▼
6. Argus 检查 TCB 状态
         │
         ▼
7. 返回证明证据
         │
         ▼
8. OpenClaw 使用证据进行：
   - 服务证明
   - Secret 检索
   - 加密存储访问
```

## 运行示例

### 前置条件

- OpenClaw 一侧：Argus Guard 可访问 `http://localhost:8007`
- OpenViking 一侧：Argus Evidence Provider 可从 Guard 主机访问
- 如果需要真实 quote 路径，需要启用 TSM 的 Intel TDX 平台

### 构建和运行

```bash
# 在 OpenClaw 一侧，只启动 Argus Guard 并指向 OpenViking 一侧的 provider。
cd ../../../core/argus
export EVIDENCE_ENDPOINT=http://<openviking-provider-host>:8008
./start_argus.sh start-guard

# 返回同一主机上的 OpenClaw 示例。
cd ../../../adapters/OpenClaw/scripts

# 可选：覆盖 OpenClaw 验证的逻辑目标
export TARGET_SERVICE_NAME=openviking-cmem
export TARGET_URI=https://<openviking-service-host>

# 运行调用方侧验证演示
python3 openclaw_agent.py
```

在 OpenViking 一侧，单独启动 provider：

```bash
cd ../../../core/argus
export ARGUS_WORKLOAD_IDENTITY=openviking-cmem
./start_argus.sh start-provider
```

## 预期输出

```bash
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

在当前 live TSM 路径上，Argus 在 quote 结构和请求绑定验证通过后报告
`TCB Status: UpToDate`。这足以满足示例的默认策略流程，但仍然不代表
已完成基于 collateral 的 TCB 新鲜度评估。

上述额外元数据行仅在 OpenViking 一侧通过 tc-api 管理的 Docker 路径启动时
才会出现。直接运行 `python3 openviking_service.py --serve` 仍可返回证明证据，
但除非 tc-api 正在跟踪服务 workload，否则 image digest、launch ID 和
Rekor UUID 等 tc-api 特定字段将为空。

## 基于 tc-api 的 OpenViking 部署

要在 Argus claims 中显示 `image_digest`、`launch_id` 和 Rekor 标识符，
OpenViking 一侧需要通过 tc-api 或其他 Docktap 管理的 Docker 路径启动，
而不是仅直接运行 Python demo。

1. 在 OpenViking 一侧启动 tc-api。
2. 通过 `POST /api/deploy-launch` 启动 OpenViking workload，并将
   `metadata.workload_id` 设置为 `openviking-cmem`。
3. 使用 `ARGUS_SERVICE_ID=openviking-cmem` 和 `TC_API_WORKLOAD_ID=openviking-cmem`
   启动 sidecar/provider 进程，以便 Argus 按 workload ID 而非其自己的
   container ID 查询 tc-api。
4. 将 OpenClaw 一侧的 Guard 指向该 provider：
   `EVIDENCE_ENDPOINT=http://<openviking-provider-host>:8008`。

Provider 一侧环境变量示例：

```bash
export ARGUS_WORKLOAD_IDENTITY=openviking-cmem
export ARGUS_SERVICE_ID=openviking-cmem
export TC_API_WORKLOAD_ID=openviking-cmem
export TC_API_URL=http://127.0.0.1:8000
./start_argus.sh start-provider
```

## 另请参阅

- [OpenClaw Adapter](../README.md) - 主适配器文档
- [Argus Verifier](../../core/argus/README.md) - TDX quote 验证
- [TC-API Service](../../core/tc-api/README.md) - 构建到运行时的信任

## 快速开始

### 前置条件

运行完整 e2e 测试前，确保：
- Intel TDX 启用平台（`/dev/tdx_guest`）
- TSM configfs 位于 `/sys/kernel/config/tsm/report/`
- 已安装 Docker & docker-compose
- 已构建 Argus 二进制（见 [core/argus README](../../core/argus/README.md)）
- 设置 TC-API identity token（`TC_API_IDENTITY_TOKEN` 或 `TC_API_BEARER_TOKEN`）

### 步骤 1: 验证环境

```bash
cd /home/siyuan/confidential-computing-zoo/cczoo/agent-cc/core/argus
./start_argus.sh validate
```

预期输出：
```
[INFO] Validating environment...
[INFO] TDX device found at /dev/tdx_guest
[INFO] TSM configfs found
```

### 步骤 2: 构建 Argus（如未构建）

```bash
cd /home/siyuan/confidential-computing-zoo/cczoo/agent-cc/core/argus
cargo build --release
```

### 步骤 3: 运行完整端到端测试

```bash
# 一键真实 quote 路径：compose 栈 + tc-api launch + real Guard + OpenClaw。
cd /home/siyuan/confidential-computing-zoo/cczoo/agent-cc/adapters/OpenClaw/scripts
export TC_API_IDENTITY_TOKEN=<sigstore-identity-token>
./run_openclaw_openviking_e2e.sh
```

该脚本：
1. 启动 Docker Compose 栈（registry + tc-api + argus-provider）
2. 通过 tc-api 启动 OpenViking workload
3. 以 real-verifier 模式启动 argus-guard
4. 运行带完整 TDX 证明的 OpenClaw 验证

### 跳过 workload 启动（如已运行）

如果 OpenViking workload 已在 `:8010` 健康运行，可以追加
`SKIP_LAUNCH=1` 复用现有 workload，跳过 tc-api launch：

```bash
SKIP_LAUNCH=1 ./run_openclaw_openviking_e2e.sh
```

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