## Why

Docktap 的每次 Docker 操作（pull/create/start/stop/rm）都需要一个有效的 OIDC identity token 来完成 Sigstore keyless 签名。由于 oauth2.sigstore.dev/auth 签发的 token 有效期只有 60 秒，用户在交互式场景下（尤其是 agent 场景）操作间隔超过 1 分钟就会被 attestation gate 拦截，必须重新登录。当前的 lifecycle grant 只覆盖单容器的 start/stop/rm 且仅 120 秒，无法根本解决问题。

## What Changes

- **新增 session delegation 机制**：用户登录后在 OIDC token 有效期内创建一条链上 delegation 事件（签名由 Fulcio 证书背书），后续 Docker 操作使用 chain owner key 直签 DSSE envelope 并提交 Rekor（使用 intoto entry type，verifier 为裸公钥 PEM），不再依赖 OIDC token。
- **新增 delegation API endpoint**：`POST /api/docktap/delegate`，在 OIDC token 有效期内消费 token 并创建 delegation 链上事件。
- **修改 attestation gate 逻辑**：从检查 `has_reusable_identity_token()` 改为检查是否存在有效的 session delegation。
- **修改 submit_operation 签名路径**：新增 owner key 直签路径，当存在有效 delegation 时绕过 Fulcio，直接用 owner key 签署 DSSE envelope 并构建 intoto proposed entry 提交 Rekor。
- **修改验证逻辑**：新增 delegation-aware 的 signer identity 验证——delegation 事件的 signer 必须匹配 policy，后续事件的 signer（owner key）只需由 delegation 声明的 delegatee 匹配且在 scope/TTL 内。
- **delegation 存储**：在现有 `/dev/shm` SQLite 中新增 delegation 表，per-chain，TTL-only 过期（不支持主动撤销）。
- **DSSE 签名算法约束**：owner key 签署 DSSE envelope 时使用 ECDSA P-384 + SHA-256（Rekor 服务端验证要求），owner_authorization 继续使用 P-384 + SHA-384。

## Capabilities

### New Capabilities
- `session-delegation`: 定义 delegation 事件的 predicate 结构、链上语义（event_type `session.delegation`、per-chain、predicateType 复用 `trusted-log.dev/v1`）、TTL 管理、scope 约束、存储模型。
- `owner-key-dsse-signing`: 定义使用 chain owner key 直接签署 DSSE envelope 的流程，包括 DSSE PAE 构建、ECDSA P-384 + SHA-256 签名、intoto proposed entry 构建、Rekor 提交。
- `delegation-verification`: 定义 delegation-aware 的链验证逻辑——分层 signer identity 检查、delegation chain 追溯、scope/TTL 验证。

### Modified Capabilities
- `docktap-trucon-commit`: submit_operation 新增 owner key 直签路径，delegation_id 字段加入 predicate。
- `chain-root-owner-attestation`: owner key 的用途从"仅 owner_authorization"扩展到"DSSE envelope 签名 + Rekor 提交"。

## Impact

- **tc_api/docktap/trucon_client.py**: submit_operation 新增 delegation 检查和 owner key 签名路径。
- **tc_api/docktap/proxy/docker_proxy.py**: attestation gate 从 token 检查改为 delegation 检查；lifecycle grant 机制被 session delegation 取代。
- **tc_api/sigstore_baseline.py**: owner key 复用于 DSSE 签名（新增 SHA-256 签名函数）。
- **tlog-rekor/adapter.py**: 新增 owner key signed intoto entry 构建和提交方法。
- **tc_api/tlog_client.py**: verify_record 新增 `_annotate_delegation_verification`；`_extract_signer_identity` 允许裸公钥（返回 None 时走 delegation 路径）。
- **tc_api/trucon/app.py**: `/commit` 端点新增 delegation 准入检查。
- **tc_api/trucon/database.py**: 新增 delegation 表。
- **tc_api/main.py**: 新增 `POST /api/docktap/delegate` endpoint。
- **Rekor 兼容性**：已通过 demo 验证 public Rekor 接受裸公钥 PEM 作为 dsse/intoto entry verifier（logIndex 1523234106）。
- **Open Question**: 多 agent 实例共享同一条链时，delegation 和 owner key 的分发模型待设计。当前假设单 agent per chain。
