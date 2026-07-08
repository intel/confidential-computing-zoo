# Agent-CC 适配器

Agent-CC 适配器提供了将各种工作负载集成到 TDX 可信执行环境的参考实现。

## OpenClaw 适配器

用于在 TDX 环境中部署 OpenClaw 工作负载，提供全面的容器保护。适用场景包括：

- 容器化 AI 工作负载及安全沙箱，参考[中文指南](OpenClaw/openclaw_container_protection_CN.md)
- A2S安全通信，参考[中文指南](OpenClaw/openclaw_to_service_protection_CN.md)

## 相关核心服务

- [`TC API`](../core/tc_api/README.md) - TC API 和信任链控制
- [`可信日志`](../core/tlog/README.md) - 不可变签名证据
- [`Argus`](../core/argus/README.md) - A2S安全通信