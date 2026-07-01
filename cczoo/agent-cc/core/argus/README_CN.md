# Argus

Argus 是一个应用于机密计算环境中的 agent-to-service（A2S）通信的运行时信任验证框架。

它的职责很窄：在调用方向对端服务发送敏感数据之前，Argus 获取该对端的证据，通过外部证明或身份系统验证证据，并评估调用方本地的策略以决定是否继续调用。

当前文档范围：Argus v1 仅针对 A2S 指定。服务到服务的触发、缓存和推广语义有意排除在当前草案之外。

## 状态

Argus v1 已经用 Rust 实现，并在真实的 Intel TDX 硬件上完成了端到端验证：

- `argus-evidence-provider`（服务侧）：通过 Linux TSM/configfs 接口（`/sys/kernel/config/tsm/report/`）生成真实的 TDX quote，可选地通过 TC-API 补充服务元数据。
- `argus-guard`（调用方侧）：获取证据，校验 quote 结构、签名和 nonce 绑定，并评估策略给出 ALLOW/DENY 决策。
- 两个二进制都从本 crate 通过 `cargo build --release` 构建，也可以通过 `Dockerfile` 打包成单个 Docker 镜像用于容器化部署。
- 已经与 [OpenClaw](../../adapters/OpenClaw) 和 [OpenViking](../../adapters/OpenViking) 适配器以及 `core/tc-api` 一起完成端到端验证，验证脚本见 `adapters/OpenViking/examples/run_openclaw_openviking_e2e.sh`。
- TCB/collateral（基于 PCCS 的新鲜度校验）在 v1 中被有意排除在范围之外——原因见 [设计决策](./docs/design-decisions.md)。

## 文档

- [快速开始](./docs/quickstart.md)：在本地或通过 Docker 构建、运行并冒烟测试 Argus。
- [架构](./docs/architecture.md)：系统模型、信任边界、部署模式、治理边界和 v1 MVP。
- [API 契约](./docs/api.md)：证据请求和响应、验证者契约、配置文件模型、策略模型和诊断面。
- [配置参考](./docs/configuration.md)：环境变量和运行时配置参考。
- [部署指南](./docs/deployment.md)：生产部署选项，包括 Docker 和 systemd。
- [设计决策](./docs/design-decisions.md)：范围决策，包括为什么 TCB/collateral 校验在 v1 中不在范围内。
- [测试和验证](./docs/tests.md)：一致性向量、谓词验证、治理回归测试、推广策略和 MVP 验证。
- [故障排除](./docs/troubleshooting.md)：常见问题和解决方案。

## Argus 涵盖的内容

Argus 标准化的内容：

- 调用方信任执行
- 服务方证据生产
- 验证者标准化声明
- 配置文件驱动的授权决策
- 配置文件、收集器和引用值的治理感知失败关闭行为

Argus 不要求仓库本身拥有每个治理系统。只要满足文档中描述的契约，配置文件发布、收集器 PKI 和引用值包分发可以由外部系统提供。

## 推荐 V1 路径

V1 的推荐基线路径是：

1. 调用方侧的 SDK 模式。
2. 服务侧的直接 `/ra/v1/evidence` 端点。
3. 用于引用和 report-data 验证的 Trustee 或等效验证者。
4. 本地加载或从简单治理包加载的静态签名配置文件。
5. 基本路径中不需要服务网格权威连接或策略权威运行时收集器要求。

此路径旨在首先关闭协议循环，然后根据配置文件扩展到网格、收集器密集型和更自动化的治理集成。

## 如何使用此仓库

如果您正在将 Argus 集成到调用方或服务中：

1. 从 [快速开始](./docs/quickstart.md) 开始构建并冒烟测试二进制文件。
2. 阅读 [架构](./docs/architecture.md) 了解范围和部署假设。
3. 在实现任何端点、验证者适配器、配置文件加载器或策略引擎之前，请阅读 [API 契约](./docs/api.md)。
4. 使用 [测试和验证](./docs/tests.md) 作为一致性向量、拒绝原因和推广行为的验收标准。
5. 如果服务无法启动或证明失败，请查阅 [故障排除](./docs/troubleshooting.md)。

`src/` 下的 Rust 实现就是实际交付的技术栈：`argus-evidence-provider` 和 `argus-guard` 二进制，通过 `cargo build --release` 或提供的 `Dockerfile` 构建。这里没有单独的 Python 原型——本 crate 就是参考实现。

## 仓库布局

```text
argus/
├── README.md
├── README_CN.md
├── Cargo.toml / Cargo.lock
├── Dockerfile
├── docker-compose.yml
├── start_argus.sh          # build/validate/start/stop/status/test 辅助脚本
├── src/
│   ├── lib.rs
│   ├── binding.rs          # 运行时绑定上下文（endpoint、pid、container id 等）
│   ├── crypto_verifier.rs  # tdx_verifier.rs 使用的签名/证书校验辅助逻辑
│   ├── engine.rs           # 调用方侧 ArgusEngine（fetch -> verify -> policy -> decision）
│   ├── errors.rs
│   ├── policy.rs           # 策略评估器
│   ├── tc_api_client.rs    # 可选的 TC-API 元数据/quote 客户端
│   ├── tdx_verifier.rs     # TDX quote 结构/签名/nonce 绑定校验
│   ├── types.rs
│   ├── verifier.rs         # RaAdapter（RaVerifier trait 实现）
│   ├── bin/
│   │   ├── evidence_provider.rs   # argus-evidence-provider HTTP 服务
│   │   └── guard.rs               # argus-guard HTTP 服务
│   └── service/
│       └── engine.rs      # 服务侧 EvidenceEngine（quote 生成、TC-API 元数据）
├── tests/                  # 集成和单元测试套件
├── test-fixtures/
└── docs/
    ├── architecture.md
    ├── api.md
    ├── tests.md
    ├── quickstart.md
    ├── configuration.md
    ├── deployment.md
    ├── design-decisions.md
    └── troubleshooting.md
```

## 快速开始

```bash
# 构建 Argus
cargo build --release

# 为 Evidence Provider 注入稳定的 workload identity
export ARGUS_WORKLOAD_IDENTITY=openviking-cmem

# 验证环境
./start_argus.sh validate

# 启动服务
./start_argus.sh start

# 运行一次真实验证链路
./start_argus.sh test
```

现在推荐通过 `ARGUS_WORKLOAD_IDENTITY` 为 Evidence Provider 注入真实且稳定的
workload identity。`ARGUS_SERVICE_NAME`、`SERVICE_NAME` 和 `K_SERVICE` 仍可作为
兼容输入，但 Argus 不再把 `HOSTNAME` 当作有效的服务身份来源。

## 安全保证

当前 Argus 在已验证路径上提供这些具体保护能力：

- 通过调用方生成的 nonce 和 `report_data` 绑定，降低重放风险。
- 把调用方请求、返回的 `BindingClaims` 和证据里的 `report_data` 绑定到同一条链路上。
- 当证据获取或验证失败时，在调用方侧失败关闭。
- 抽取 RTMR 和 TCB 状态，供上层策略进一步收紧访问控制。
- 将调用方信任执行与服务端证据生成分离，避免应用代码直接控制证明流程。

当前边界也需要明确：默认请求路径已经能对 live TSM quote 做结构校验和请求绑定校验，
但尚未在 Guard 的主路径里完成完整的 Intel collateral / certificate-chain 验证。
因此，当前实现更准确的表述是“请求绑定的 TDX 证据验证”，而不是“完整 PKI 远程证明验证”。
详见 [设计决策](./docs/design-decisions.md) 了解完整原因和路线图。

## 后续计划

最自然的后续工作是：

1. 按照 [设计决策](./docs/design-decisions.md) 中的路线图，把 collateral 感知的 TCB 校验（PCCS/QVL）接入 Guard 的主验证路径。
2. 为 `ProfileBody`、`ProfileEnvelope` 等契约创建机器可读的 schema。
3. 按照 [测试和验证](./docs/tests.md) 为规范化、内置谓词和拒绝原因分类添加一致性向量。