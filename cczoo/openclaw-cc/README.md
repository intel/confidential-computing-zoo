<div align="right">
  <a href="./README_CN.md">中文版</a>
</div>

# OpenClaw-CC(Confidential Computing) Demo Solution

Cloud-deployed AI agents differ from “single-shot” AI workloads: they run continuously, connect to user-facing channels (e.g., Discord/WhatsApp/WeChat/Web), invoke tools/skills, and maintain user context and long-term memory as well as other sensitive data like user tokens or credentials for accessing diversified services. This broadens the attack surface and concentrates high-value data at the agent runtime where it exists as data-in-use.

Confidential computing is critical because it protects in-use data from privileged infrastructure threats (host OS, hypervisor, and cloud operators). It enables securing user sensitive data by running software components inside hardware-enforced trusted execution environments (TEEs), which are isolated from the host environment. This document outlines the architecture,and threat model for a typical agent system (OpenClaw), discusses how confidential computing mitigates risks, and provides a practical solution to prevent data leaks with AI agents use case.

This demo is based on OpenClaw, an open-source AI framework that coordinates users, language models, tools, and long-term memory. But the principles discussed here can be applied to other agent frameworks with similar architectures and threat profiles.

## 1. OpenClaw Overview and Threat Model

OpenClaw is a personal AI assistant that can run locally or in the cloud. In practice, agent-style assistants are often deployed in the cloud to provide 24×7 availability and reliable integration with internet-facing services such as WhatsApp, Discord, WeChat, and web APIs. Acting as an autonomous agent, OpenClaw bridges users and downstream systems by monitoring channel messages and orchestrating model and tool calls.

### 1.1 Architecture and data flow

![OpenClaw Architecture](./images/openclaw-arch.png)

1. Users interact with OpenClaw through a channel service, which forwards messages to the agent runtime (orchestrator).
2. The orchestrator maintains session state, applies policy and security controls, and coordinates calls to the model service for inference. As needed, it retrieves and updates long-term context in the memory service and invokes external tool/skill services using guarded inputs and credentials.
3. User context and conversation history can also be persisted into storage as long-term memory, enabling continuity and personalization across sessions.

In OpenClaw workflows, agent runtime continuously process and retain sensitive context—including user histories, enterprise documents, retrieved knowledge fragments, and external system responses. These long-lived context assets are reused in downstream decisions, so a runtime compromise can expose far more than a single query. At the same time, pluggable services make both sensitive user interactive data and context knowledge model weights high-value targets, particularly in cloud environments. The multi-tenant clound operation increases exposure to privileged infrastructure threats, misconfigurations, as well as broad access to retained data (e.g., memory logs, configuration files, scripts, and backups).

As OpenClaw and similar agentic AI frameworks move to the cloud, shared-infrastructure deployments increase the risk of runtime data leakage, exposing sensitive data and user context state. Even with TLS for data-in-transit and encryption for data-at-rest, privileged host OS or hypervisor-level attackers may still access runtime memory, revealing prompts, intermediate states, and service API tokens. Dynamic tool or services invocation further amplifies risk, as compromised services or tools in the workflow can be induced to take unauthorized real-world actions.

Traditional sandboxing mechanisms, such as OS-level containers and VM isolation—primarily mitigate internal threats between co-located processes or tenants. However, these measures provide limited protection against privileged attackers (e.g., host administrators, hypervisors, or compromised cloud operation environments) in cloud. They also lack effective guarantees that the agent runtime and its sensitive assets remain untampered throughout the whole lifecycle.

Securing Agent-AI requires protecting the entire inference–memory–retrieval–action pipeline, where data-in-use confidentiality remains the most significant challenge. Long-term memory and continual learning provide persistent knowledge and adaptability, but they also intensify requirements for data governance, consent, and secure deletion, especially in today’s multi-tenant environments that lack strong in-use isolation. Achieving trustworthy execution requires hardware-enforced isolation, remote attestation, and full lifecycle data management to close gaps left by traditional sandboxing and runtime protections.

### 1.2 Threat areas

- **Runtime context (data in use)**: privileged infrastructure access (memory inspection/debugging), prompt/tool injection, and multi-tenant/session bleed.
- **Long-term memory (data at rest)**: memory stores become high-value data lakes; production data reused for offline evaluation/prompt tuning/training expands exposure and complicates consent.
- **Secrets and skill permissions**: credential leakage (API keys/OAuth tokens/cookies), and plugin/supply-chain risks that introduce new exfiltration paths.
- **Cloud-specific threat surface**: metadata/control-plane exposure, shared infrastructure risks (memory, io, storage and network), and hypervisor-level attacks.

## 2. Confidential Computing and Mitigations

### 2.1 Confidential computing

Agent risk concentrates in data-in-use: runtime context, tool-call parameters/results, intermediate states, memory retrieval outputs, and credentials appear briefly in plaintext during orchestration. Confidential computing (TEEs) places sensitive execution and data inside hardware-enforced isolation so that even cloud admins, the host OS, and the hypervisor cannot directly read plaintext inside the enclave.

With remote attestation, upstream services (e.g., channels and key management systems) can verify workload identity and policy before releasing sensitive data such as conversation keys or skill tokens.

### 2.2 OpenClaw Confidential Computing  Solution (OpenClaw-CC)

To mitigate privileged infrastructure threats in multi-tenant cloud environments, the OpenClaw runtime can be deployed inside a hardware-enforced Trusted Execution Environment (TEE), such as a TDVM. This ensures that even the host OS, hypervisor, or cloud operator cannot directly inspect plaintext runtime memory. By isolating orchestration logic, policy enforcement, and memory handling inside the secure exeuction environment, OpenClaw-CC achieves strong confidentiality guarantees across the full inference–retrieval–action pipeline, closing the primary gap left by traditional VM or container isolation.

![OpenClaw-CC Architecture](./images/openclaw-cc.png)

In addition, OpenClaw-CC can leverages remote attestation or attestation-bound secure channels to establish trust before releasing sensitive data. Upstream services components, such as channel services, model providers, and secret/token brokers, can verify that the OpenClaw-CC runtimeis running inside an secure environment with an expected measurement before provisioning credentials or long-term memory keys.

Persistent storage is protected with encryption at rest, e.g. LUKS based encryption disk, with encryption keys managed inside the TEE, as well as its integrity attested while mouting with TEE.

Together, TDX based TEE isolation, remote attestation, and encrypted data persistence provide an end-to-end confidential computing architecture that prevents runtime data leakage and strengthens OpenClaw’s resilience against privileged cloud attacking risks.

### 2.3 Mitigations

This subsection focuses on how Intel TDX based TEE reduce exposure to privileged infrastructure threats while data is being processed.

| Risk area              | Examples of issues                                    | Intel TDX benefits                                                                 |
| ---------------------- | ----------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Runtime                | Memory inspection, runtime data leaks                 | Run core processes in TEE; keep in-memory data encrypted; attest runtime integrity |
| Long-term memory       | Residual data in backups; exposure during rehydration | Encrypt memory; decrypt only inside TEE; attest runtime integrity                  |
| Secrets & permissions  | API keys/tokens/cookies stolen                        | Use secrets only inside TEE; attestation-gated key release                         |
| Prompt/tool misuse     | Unintended tool calls or unsafe responses             | Protect sensitive intermediate data from host access via TEE                       |
| Plugins & supply chain | Malicious or vulnerable extensions                    | Attest runtime and plugin integrity                                                |


Intel TDX based TEE significantly reduce privileged infrastructure exposure for in-use data. Beyond data-in-use protection, complementary engineering measures remain important—for example: least-privilege permissions, tool/policy allowlists etc. That is out of scope for this document.

## 3. OpenClaw-CC Demo Solution

### 3.1 Data at rest protection

Create an encrypted directory to store OpenClaw configuration files, ensuring at rest data security.

Create a LUKS block file and bind it to a free loop device:

```BASH
# Debian/Ubuntu
apt install -y cryptsetup

# CentOS
yum install -y cryptsetup

git clone https://github.com/intel/confidential-computing-zoo.git
cd confidential-computing-zoo/cczoo/openclaw-cc/luks_tools
export VFS_SIZE=10G  # Adjust size as needed
export VIRTUAL_FS=/home/vfS
./create_encrypted_vfs.sh ${VFS_SIZE} ${VIRTUAL_FS}
```

According to the loop device number output by the above command (such as `/dev/loop0`), create the `LOOP_DEVICE` environment variable to bind the loop device:

```BASH
export LOOP_DEVICE=<the binded loop device>
```

On first execution, the block loop device needs to be formatted as ext4:

```BASH
mkdir /home/encrypted_storage
./mount_encrypted_vfs.sh ${LOOP_DEVICE} format
```

**To secure OpenClaw's at rest data by storing configuration and state directories (sessions, logs, caches) in an encrypted location, configure these environment variables:**

```BASH
# State directory for mutable data (sessions, logs, caches).
export OPENCLAW_STATE_DIR="/home/encrypted_storage"
# Config path for OpenClaw.
export OPENCLAW_CONFIG_PATH="/home/encrypted_storage"
```

### 3.2 Install OpenClaw

Install dependencies and OpenClaw:

```shell
# Debian/Ubuntu
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
apt install -y nodejs

# CentOS
curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash -
dnf install -y nodejs cmake

npm install -g pnpm

# Install OpenClaw
cd <work dir>
git clone https://github.com/openclaw/openclaw.git
cd openclaw
pnpm install
pnpm setup
source /root/.bashrc
pnpm link --global
openclaw onboard --install-daemon
```

## 4. Conclusion and Future Work

OpenClaw-CC demonstrates a robust approach to confidential computing, leveraging TDX based TEEs and attestation to mitigate risks of deploying OpenClaw in multi-tenant infrastructure. By incorporating these technologies, OpenClaw-CC enhances data protection throughout its architecture, from runtime context to long-term memory management. The demo solution showcases practical implementations of these principles, providing a valuable reference for organizations or individuals seeking to adopt confidential computing practices.

This demo is still an early-stage prototype, primarily aimed at exploring how confidential computing techniques can address critical data leakage challenges for OpenClaw likely agent workloads. Future work will focus on expanding support for Docker-based deployments with TEEs, integrating a trusted build-to-deploy process, and further strengthening the services execution environment. Feedback and contributions from the community are welcome to help refine this solution.