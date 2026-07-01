# OpenClaw 适配器

本文档目录是 Agent-CC 适配器的 OpenClaw 入口点。

它代表了在 Agent-CC 模型中运行 OpenClaw 的部署侧集成路径，无需进行侵入性的框架修改。该适配器旨在使用 `core/` 中的共享核心服务，而不是在本地重新实现信任、构建或证明流程。

## 当前范围

- 使用 OpenClaw 作为 Agent-CC 端到端验证的参考 agent 工作负载。
- 将 OpenClaw 运行时部署连接到共享的 TC-API 构建、启动和验证路径。
- 重用共享信任基础设施，如可信日志记录、基于证明的受控密钥释放和加密存储助手。

在真实双侧部署中，OpenClaw 运行在调用方一侧，并搭配本地 Argus Guard；
OpenViking 一侧则暴露远端 Argus Evidence Provider，供这个 Guard 通过
`EVIDENCE_ENDPOINT` 拉取证据。

## 示例

- **[OpenClaw Agent 示例](examples/README_CN.md)** - 完整的集成示例，展示：
  - 本地 Guard + 远端 provider 的双侧部署
  - 基于证明的受控密钥释放
  - 加密上下文存储
  - Docker Compose 配置

## 相关核心服务

- [`../../core/tc-api/`](../../core/tc-api/) 用于可信构建、发布、启动和验证编排
- [`../../core/tlog/`](../../core/tlog/) 用于不可篡改签名的运行时证据和摘要规则
- [`../../core/trust-service/`](../../core/trust-service/) 用于部署流程使用的证明支持服务
- [`../../core/argus/`](../../core/argus/) 用于 TDX 引用验证

## 状态

此适配器目前作为文档和集成入口点。随着适配器路径的扩展，这里将添加具体的 OpenClaw 特定部署资产。

## 开始使用

1. 阅读 [`examples/README_CN.md`](examples/README_CN.md) 获取完整的集成示例。
2. 阅读 [`../../README_CN.md`](../../README_CN.md) 了解顶层 Agent-CC 架构和端到端场景。
3. 阅读 [`../../core/tc-api/README_CN.md`](../../core/tc-api/README_CN.md) 了解从构建到运行时的可信控制路径。
4. 如果需要证明服务容器设置，请阅读 [`../../core/trust-service/README_CN.md`](../../core/trust-service/README_CN.md)。