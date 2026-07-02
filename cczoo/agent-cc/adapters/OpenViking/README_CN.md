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
| [scripts/openviking_service.py](scripts/openviking_service.py) | 工作 Python 实现 |
| [scripts/launch_openviking_via_tc_api.sh](scripts/launch_openviking_via_tc_api.sh) | 构建、推送并通过 tc-api 启动 OpenViking workload |
| [configs/docker-compose.tc-api.yml](configs/docker-compose.tc-api.yml) | tc-api + registry + Argus Provider 栈，用于真实 Docker 启动流程 |
| [configs/Dockerfile.tc-api-workload](configs/Dockerfile.tc-api-workload) | 用于 tc-api 管理的 OpenViking workload 容器镜像 |
| [configs/openviking-launch-payload.json](configs/openviking-launch-payload.json) | tc-api 部署的启动 payload |

## 集成点

### 1. Trust Gate 验证

OpenViking 实现了 verify-skill trust gate，OpenClaw 在上下文传输前调用：

```rust
// 示例：OpenViking trust gate 实现
use argus::{TdxQuoteVerifier, AttestationContext};

pub struct OpenVikingTrustGate {
    verifier: TdxQuoteVerifier,
    policy: TrustPolicy,
}

impl OpenVikingTrustGate {
    /// 在允许上下文访问前验证 OpenClaw
    pub async fn verify_caller(&self, caller_evidence: &AttestationEvidence) -> Result<bool> {
        // 验证调用者的 TDX quote
        self.verifier
            .verify_quote(&caller_evidence.tdx_quote)
            .await?;

        // 检查 TCB 状态
        if caller_evidence.tcb_status != TcbStatus::UpToDate {
            tracing::warn!("Caller TCB is not up to date");
            return Ok(false);
        }

        // 验证 nonce 绑定以确保新鲜度
        if !self.verify_nonce_binding(&caller_evidence.binding_digest) {
            tracing::warn!("Caller nonce binding verification failed");
            return Ok(false);
        }

        // 根据信任策略评估
        self.policy
            .evaluate(&caller_evidence.claims)
            .await
    }

    /// 根据验证结果允许或拒绝上下文传输
    pub async fn evaluate_context_transfer(
        &self,
        caller: &AttestationEvidence,
        context_id: &str,
    ) -> Result<ContextTransferDecision> {
        let is_trusted = self.verify_caller(caller).await?;

        if is_trusted {
            Ok(ContextTransferDecision::Allow {
                context_id: context_id.to_string(),
                verified_claims: caller.claims.clone(),
            })
        } else {
            Ok(ContextTransferDecision::Deny {
                reason: "Caller verification failed trust policy".to_string(),
            })
        }
    }
}
```

### 2. 上下文网关操作

OpenViking 暴露的上下文操作均基于证明：

| 操作 | 描述 | 需要证明 |
|------|------|----------|
| `observe` | 读取上下文元数据（不物化） | 是 |
| `recall` | 物化上下文以供处理 | 是 |
| `commit` | 存储带证明绑定的上下文 | 是 |
| `privacy_restore` | 恢复加密上下文 | 是 |

### 3. 隐私恢复操作

OpenViking 支持隐私恢复操作：

```rust
// 示例：隐私恢复操作
pub async fn privacy_restore(
    &self,
    caller: &AttestationEvidence,
    context_id: &str,
) -> Result<EncryptedContext> {
    // 验证调用者
    if !self.verify_caller(caller).await? {
        return Err(GatewayError::AccessDenied {
            reason: "Caller verification failed".to_string(),
        });
    }

    // 执行隐私恢复
    let encrypted_context = self.storage
        .get_encrypted(context_id)
        .await?;

    Ok(encrypted_context)
}
```

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

> **注意**：Demo 模式（`openviking_service.py`）在内存中运行，无真实 TDX quote。
> 要进行生产或完整证明验证，请使用 `run_openclaw_openviking_e2e.sh`。

### 2. tc-api 管理模式

通过 tc-api 管理的 Docker 启动路径运行时，Argus claims 才能带出 tc-api 元数据：

1. `configs/docker-compose.tc-api.yml`：启动本地 registry、tc-api，以及 Argus Evidence Provider
2. `configs/Dockerfile.tc-api-workload`：打包 `openviking_service.py --serve` 成真正的 service workload 镜像
3. `scripts/launch_openviking_via_tc_api.sh`：构建镜像、推送到本地 registry，并提交 deploy-launch 请求

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

**完整端到端测试请参考 [OpenClaw Scripts README](../../OpenClaw/scripts/README.md)**

该文档包含：
- 前置条件检查
- 环境验证步骤
- 构建说明
- 完整 e2e 测试运行命令

## Provider 一侧环境变量示例

```bash
cd /home/siyuan/confidential-computing-zoo/cczoo/agent-cc/core/argus
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