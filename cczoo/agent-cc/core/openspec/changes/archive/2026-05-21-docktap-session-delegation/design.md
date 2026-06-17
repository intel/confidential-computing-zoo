## Context

Docktap 当前每次 Docker 操作（pull/create/start/stop/rm）都通过 Sigstore keyless 流程签名：获取 OIDC token → Fulcio 换证书 → 签 DSSE → 提交 Rekor。oauth2.sigstore.dev/auth 的 token 有效期仅 60 秒，导致交互式和 agent 场景下操作间隔超过 1 分钟就被 attestation gate 拦截。

现有的 lifecycle grant（docker_proxy.py）是纯内存字典，120 秒 TTL，仅覆盖单容器的 start/stop/rm，无密码学约束。

chain owner key（EC P-384）已存在于 Event Log 0 中，用于 owner_authorization 签名。经 demo 验证（Rekor logIndex 1523234106），public Rekor 接受裸公钥 PEM 作为 dsse/intoto entry 的 verifier。

## Goals / Non-Goals

**Goals:**
- 用户只需在 session 开始时完成一次 OIDC 登录，后续所有 Docker 操作不再依赖 OIDC token
- Delegation 作为链上事件记录，提供可审计的授权链条
- 后续事件仍提交 Rekor（使用 intoto entry type + owner key 裸公钥），保持透明日志完整性
- 复用现有 owner key 基础设施，不引入新的密钥管理

**Non-Goals:**
- 不实现 delegation 主动撤销（TTL-only 过期）
- 不实现 cross-chain delegation（per-chain only）
- 不实现镜像/workload 级别的 scope 约束（仅操作类型 scope）
- 不实现多 agent 共享 chain 的 delegation 分发模型
- 不部署 SPIFFE/SPIRE 或私有 Fulcio/Rekor
- 不改变 ambient identity 场景的行为（有 ambient credential 时仍走 Fulcio 路径）

## Decisions

### D1: Delegation 作为链上事件（非独立 Rekor 条目）

Delegation 事件有 sequence_num，进入事件链，使用 `event_type: "session.delegation"`，predicateType 复用 `https://trusted-log.dev/v1`。

**理由**: 验证自封闭——回放一条链即可看到完整授权关系。不需要额外的 Rekor 索引/发现机制。delegation 事件走正常的 commit-intent → reserve → sign → POST /commit 路径，完全复用 TruCon sequencer。

**替代方案**: 独立 Rekor 条目（链外）——验证者需要额外查 Rekor 找 delegation bundle，需要索引约定，增加系统复杂度。

### D2: 后续事件使用 owner key 签名 DSSE + 提交 Rekor（intoto entry type）

当存在有效 delegation 且无 OIDC token 时，submit_operation 使用 chain owner key 直接签署 DSSE envelope（ECDSA P-384 + SHA-256），构建 intoto v0.0.2 proposed entry（publicKey = owner 公钥 PEM），提交 Rekor。

**理由**: intoto entry type 支持 attestation storage，Rekor 会持久化原始 payload，第三方验证者可从 Rekor 直接获取完整 Statement。dsse entry type 不支持 attestation storage（明确注释 "not implemented"）。

**签名算法约束**: DSSE envelope 签名使用 SHA-256（Rekor 服务端 verifyEnvelope 强制 `signature.LoadVerifier(key, crypto.SHA256)`）。owner_authorization 继续使用 SHA-384（不提交 Rekor）。

**替代方案**: 后续事件不上 Rekor（只提交 TruCon）——丧失公开透明日志的时间戳证明。

### D3: 复用 chain owner key 作为 delegation session key

不生成额外的 per-session 密钥对，直接使用 Event Log 0 声明的 owner key。

**理由**: owner key 已存在、已上链（公钥在 Event Log 0）、已有管理基础设施（生成、存储、加载）。验证者只需检查签名与 Event Log 0 公钥一致。

**约束**: owner key 是 chain 级别的，无法区分同一 chain 上的不同 session。当前假设单 agent per chain，多 agent 场景留作 open question。

### D4: Delegation 存储使用现有 /dev/shm SQLite

在 `/dev/shm/tc_api_queue/queue.db` 中新增 `delegations` 表。

**理由**: 复用现有存储模式（WAL mode, 0700 DAC, cross-thread access）。/dev/shm 是 tmpfs，TDX 保护内存加密，系统重启后自动清除——这是合理的安全边界。

### D5: Delegation-aware 验证逻辑

验证分层：
1. chain.init 事件：验证 signer identity + owner key 声明
2. session.delegation 事件：验证 signer identity 匹配 policy.authorized_delegators
3. 后续业务事件：signer_identity 可为 None（裸公钥无 SAN），通过 delegation_id 追溯到有效 delegation，验证 delegation scope + TTL

新增 `_annotate_delegation_verification()` 函数，与现有 `_annotate_owner_verification()` 并列。

### D6: Attestation gate 改为 delegation-aware

docker_proxy.py 的 attestation gate 从 `has_reusable_identity_token()` 改为：
1. 先检查是否有有效 OIDC token（向后兼容）
2. 如无 token，检查是否有有效 delegation（查 SQLite）
3. 都没有则拦截（428）

lifecycle grant 机制保留但降为 fallback（delegation 优先）。

### D7: Delegation 创建独立于 chain init

Delegation 通过 `POST /api/docktap/delegate` 创建，不绑定 init_chain。chain 和 delegation 有不同的生命周期——chain 是长期的，delegation 是 session 级的。

## Risks / Trade-offs

- **[攻击窗口扩大]** delegation 有效期（默认 4 小时）远大于 OIDC token（60 秒）。如果 owner key 被窃取，攻击者可在 TTL 内以该 session 身份签名。→ **缓解**: owner key 存储在 0600 权限文件中，TDX 内存加密保护；delegation TTL 可配置，高安全场景可缩短。
- **[Rekor 签名者身份缺失]** owner key 签名的事件在 Rekor 上无 SAN email/URI，`_extract_signer_identity()` 返回 None。→ **缓解**: 验证者通过 delegation chain 追溯人类身份；predicate 中的 delegation_id 提供业务层关联。
- **[SHA-256 vs SHA-384 双算法]** DSSE envelope 签名用 SHA-256（Rekor 要求），owner_authorization 用 SHA-384，增加复杂度。→ **缓解**: 两者使用场景明确分离，代码层面用不同函数封装。
- **[intoto entry 双重 base64 编码]** intoto v0.0.2 的 payload 和 sig 字段需双重 base64 编码，容易出错。→ **缓解**: adapter 中已有 `_intoto_entry_from_bundle()` 实现可参考。

## Open Questions

- **多 agent 共享 chain**: 当多个 agent 实例需要操作同一条链时，owner key 分发和 per-agent delegation 模型待设计。
- **Rekor intoto entry + 裸公钥验证**: demo 验证了 dsse entry type，intoto entry type 需在实现阶段做 spike 确认（理论上 verifyEnvelope 代码相同）。
