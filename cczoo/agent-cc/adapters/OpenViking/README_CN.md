# OpenViking 适配器

本文档目录是 Agent-CC 适配器的 OpenViking 入口点。

它代表了将 OpenViking 作为机密内存控制平面服务在 Agent-CC 模型中运行的服务侧集成路径。该适配器旨在使用 `core/` 中的共享核心服务，而不是在本地重新实现信任、构建或证明流程。

## 概述

OpenViking 是一个机密内存控制平面服务，提供基于证明的上下文存储和检索。它通过信任门机制与 OpenClaw agent 配合工作。

## 当前范围

- 使用 OpenViking 作为 Agent-CC 端到端验证的参考服务工作负载。
- 将 OpenViking 机密内存操作连接到共享的 TC-API 验证路径。
- 重用共享信任基础设施进行上下文网关操作。

在真实双侧部署中，OpenViking 运行在服务侧，并与 Argus Evidence Provider
部署在同一侧；OpenClaw 则保留自己的本地 Guard，并通过远端 provider
端点拉取 OpenViking 的证据。

## 示例

- **[OpenViking Service 示例](examples/README_CN.md)** - 完整的集成示例，展示：
  - 服务侧 provider + 调用侧 guard 的双侧部署
  - 信任门验证实现
  - 上下文网关操作（观察、召回、提交）
  - 隐私恢复操作
  - Docker Compose 配置

## 相关核心服务

- [`../../core/tc-api/`](../../core/tc-api/) 用于可信构建、发布、启动和验证编排
- [`../../core/tlog/`](../../core/tlog/) 用于不可篡改签名的运行时证据和摘要规则
- [`../../core/trust-service/`](../../core/trust-service/) 用于部署流程使用的证明支持服务
- [`../../core/argus/`](../../core/argus/) 用于 TDX 引用验证

## OpenClaw 集成

OpenViking 通过验证技能信任门与 OpenClaw 配合工作：

- OpenClaw 在发送上下文之前调用本地验证技能
- 验证技能验证 OpenViking 或网关证据
- 当验证失败或不可用时，拒绝上下文传输

详情请参阅 [OpenViking 可信上下文门规范](../../openspec/specs/openviking-trusted-context-gate/spec.md)。

## 状态

此适配器目前作为文档和集成入口点。随着适配器路径的扩展，这里将添加具体的 OpenViking 特定部署资产。

## 开始使用

1. 阅读 [`examples/README_CN.md`](examples/README_CN.md) 获取完整的集成示例。
2. 阅读 [`../../README_CN.md`](../../README_CN.md) 了解顶层 Agent-CC 架构和端到端场景。
3. 阅读 [`../../openspec/specs/openviking-trusted-context-gate/spec.md`](../../openspec/specs/openviking-trusted-context-gate/spec.md) 了解信任门规范。