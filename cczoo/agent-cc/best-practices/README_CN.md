<div align="right">
  <a href="./README.md">English</a>
</div>

# OpenClaw 机密计算部署最佳实践指南

本指南提供在 Intel TDX（Trust Domain Extensions）机密虚拟机（TDVM）中部署与运行 Agentic AI 工作负载（以 OpenClaw 为参考 Agent）的端到端实施指引与架构最佳实践。

---

## 1. 架构概览与信任模型

AI Agent 系统在运行期会处理高敏感的用户输入、推理过程、工具凭据与持久记忆。在机密计算环境中部署 Agent，可实现跨数据生命周期的纵深防御：

- **使用中数据保护（Data in Use）**：基于 Intel TDX 硬件内存加密，隔离宿主机、云厂商虚拟化管理程序及邻居 VM，防止内存窥视与篡改。
- **静态数据保护（Data at Rest）**：Agent 的配置文件、会话历史与长期记忆持久化于加密卷（LUKS），且仅在通过度量证明的 TD 内部解锁。
- **传输中数据保护（Data in Transit）**：敏感模型推理与工具调用限制在 TD 本地回环（Loopback）通信；跨信任域交互则强制实施基于远程证明绑定的 mTLS 通道。
- **可验证证据（Verifiable Evidence）**：通过硬件根 TDX Quote 与签名透明日志（TLog），向外部验证方提供不可篡改的系统启动与运行完整性证明。

### 目标架构图

```mermaid
flowchart LR
    User[用户 / 消息平台] -->|TLS| Gateway[OpenClaw Gateway]
    subgraph TD[Intel TDX TDVM 信任边界]
        Gateway --> Agent[OpenClaw Agent 核心]
        Agent --> Tools[工具执行 / 沙箱]
        Gateway --> State[配置 / 会话 / 记忆]
        Agent -->|本地回环: 127.0.0.1:11434| Ollama[本地 Ollama 模型服务]
    end
    State --- Disk[(LUKS 加密卷)]
    TD --> Evidence[TDX Quote / TLog 证据]
    Agent -.->|跨 TD: 基于证明的 mTLS (Argus)| Remote[远端模型 / RAG 知识库]
```

### 部署形态对比

| 部署形态 | 信任边界特征 | 适用场景与推荐度 |
| --- | --- | --- |
| **形态一：单 TD 协同部署（推荐起步）** | OpenClaw 与 Ollama 部署于同一 TDVM，通过 `127.0.0.1` 本地回环通信。 | **基线生产与评估首选**：最小化网络攻击面，模型推理免于网络暴露，自包含信任边界。 |
| **形态二：TD 内容器沙箱部署** | OpenClaw Gateway 运行于 TD 容器内，工具执行派生临时沙箱容器。 | **高风险工具执行场景**：在 TD 内部提供应用级进程与文件系统隔离。 |
| **形态三：跨 TD 分布式服务** | Agent 与 LLM/RAG 分布于不同 TDVM，通过 Argus 建立证明绑定的安全通道。 | **多租户与企业级集群**：模型或向量数据库作为中心化安全服务共享时使用。 |

---

## 2. 端到端部署流程（单 TD 推荐实践）

以下步骤详细演示如何在单个 Intel TDX TDVM 内落地完成 OpenClaw 与本地 Ollama 的协同加固部署。

### 步骤 1：TDVM 环境检查

登录 Intel TDX 虚拟机，确认机密计算硬件设备与环境就绪：

```bash
# 检查 TDX 设备节点
ls -l /dev/tdx_guest

# 检查 TDX 证明依赖包
dpkg -l | grep -E "sgx|tdx"
```

### 步骤 2：创建并挂载加密状态卷

Agent 的配置、会话记忆与 API 凭据不得以明文留在宿主可访问的普通磁盘上。在 TD 内创建并挂载 LUKS 加密虚拟文件系统：

请从仓库根目录执行。第一个参数是容量，第二个参数是镜像路径。

```bash
cd cczoo/openclaw-cc/luks_tools
export VFS_SIZE=10G
export VIRTUAL_FS=/root/vfs
./create_encrypted_vfs.sh "${VFS_SIZE}" "${VIRTUAL_FS}"

# 使用上面打印出的 LOOP_DEVICE，例如 /dev/loop0。
export LOOP_DEVICE=/dev/loop0
mkdir -p /home/encrypted_storage
./mount_encrypted_vfs.sh "${LOOP_DEVICE}" format
```

将 OpenClaw 指向该挂载点。这些路径与 [OpenClaw-CC 原生部署指南](../../openclaw-cc/README_CN.md) 一致：

```bash
export OPENCLAW_STATE_DIR=/home/encrypted_storage/.openclaw
export OPENCLAW_CONFIG_PATH=/home/encrypted_storage/.openclaw/openclaw.json
mkdir -p "$OPENCLAW_STATE_DIR"
```

### 步骤 3：部署本地模型服务（Ollama）

为保障推理上下文完全留在机密内存中，在同一 TDVM 内快速部署 Ollama 模型服务：

```bash
cd cczoo/agent-cc/adapters/Ollama

# 安装 Ollama 并绑定至本地回环接口 (127.0.0.1:11434)
./scripts/ollama-td.sh setup local qwen2.5:7b

# 验证本地 OpenAI-compatible API 健康状态
./scripts/ollama-td.sh test local
```

*注：如资源有限或用于轻量测试，可选用 `qwen2.5:1.5b`。*

### 步骤 4：安装并配置 OpenClaw

在 TDVM 内安装 OpenClaw，并将其模型提供方配置为本地 Ollama：

1. **安装 OpenClaw**：
   ```bash
   curl -fsSL https://openclaw.ai/install.sh | bash
   ```

2. **配置 `$OPENCLAW_CONFIG_PATH`**：
   ```json
   {
     "models": {
       "providers": {
         "local-ollama": {
           "baseUrl": "http://127.0.0.1:11434/v1",
           "apiKey": "ollama",
           "api": "openai-completions",
           "models": ["qwen2.5:7b"]
         }
       },
       "default": "local-ollama/qwen2.5:7b"
     }
   }
   ```

3. **启动 OpenClaw Gateway**：
   ```bash
   openclaw gateway run --config "$OPENCLAW_CONFIG_PATH"
   ```

### 步骤 5：验证运行状态与证明证据

完成部署后，验证系统处于可信硬件保护中：

```bash
cd cczoo/openclaw-cc/tdx_utility
python3 -m pip install ./
cd ../cc_tdx_skills/get_td_quote/scripts
python3 setup.py build_ext --inplace
python3 print_tdx_quote.py

# 确认状态目录挂载于加密卷之上
df -h "$OPENCLAW_STATE_DIR"
```

---

## 3. 安全最佳实践检查清单

| 安全域 | 最佳实践措施 | 原理与防范风险 |
| --- | --- | --- |
| **网络暴露面** | Ollama 严格绑定至 `127.0.0.1:11434`，严禁绑定 `0.0.0.0`。 | Ollama 本地 API 默认无认证机制，回环绑定限制仅允许 TD 内部进程交互。 |
| **凭据安全** | 平台 Token、API Key 等敏感凭据在 TD 内交互式录入配置文件。 | 杜绝将凭据固化进 Dockerfile、镜像层、shell 历史记录或代码仓库。 |
| **静态数据持久化** | 所有的配置、会话记录和长短期记忆必须落在 LUKS 挂载目录中。 | 防止宿主机通过快照提取、磁盘镜像离线分析泄露数据。 |
| **最小特权原则** | OpenClaw 与 Ollama 建议运行于独立的非 root 普通用户。 | 降低 TD guest OS 内部潜在的提权与逃逸风险。 |
| **工具沙箱化** | 当 Agent 启用终端代码执行类工具时，建议开启容器沙箱隔离。 | 限制模型自主生成的不可信代码影响 Agent 主进程或篡改宿主文件系统。 |

---

## 4. 生产演进与高级模式

对于企业级多租户或分布式场景，系统可按以下路径平滑演进：

1. **TC-API 自动化镜像管理与可信启动**：
   - 使用 TC-API 构建带签名、带 SBOM 的不可篡改容器镜像。
   - 启动阶段执行远程证明策略校验，校验通过后再从 KBS 动态释放解密密钥。
   - *演进方向*：扩展 TC-API 启动接口以支持受控的运行时敏感参数注入与加密持久卷挂载。

2. **基于 Argus 的跨 TD 证明服务网格**：
   - 当 LLM 或向量数据库部署在独立 TDVM 时，普通 TLS 无法抵御对端身份伪造。
   - 引入 **Argus** 可信服务框架，在建立 mTLS 的同时交换硬件 TDX Quote，确保请求仅发往经过度量证明的合规后端。

---

## 5. 相关参考与扩展文档

- [OpenClaw Adapter 指南](../adapters/OpenClaw/README_CN.md) - 容器沙箱与 TC-API 构建启动流
- [OpenClaw-CC TDVM 原生部署](../../openclaw-cc/README_CN.md) - TDX 原生深度部署与度量技能
- [Ollama Adapter 指南](../adapters/Ollama/README_CN.md) - Ollama 脚本、离线模型导入及配置
- [Hermes Agent Adapter 指南](../adapters/Hermes/README_CN.md) - 另一类主流 Agent 框架的 TDX 适配指引
- [TC-API 架构与参考](../core/tc_api/README.md) - 可信构建至运行时的控制平面说明
