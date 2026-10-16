<div align="right">
  <a href="./README_CN.md">中文版</a>
</div>

# OpenClaw Confidential Computing Best Practices Guide

This guide provides an end-to-end deployment guide and architectural best practices for running Agentic AI workloads (using OpenClaw as the reference agent) within Intel TDX (Trust Domain Extensions) confidential virtual machines (TDVMs).

---

## 1. Architectural Overview & Trust Model

Agent systems handle sensitive user prompts, internal reasoning traces, tool credentials, and persistent memories. Deploying an agent in Confidential Computing provides defense-in-depth across the data lifecycle:

- **Data in Use**: Hardware-enforced memory encryption via Intel TDX isolates agent execution and LLM inference from hypervisors, cloud operators, and neighboring VMs.
- **Data at Rest**: Persistent configuration, session history, and long-term memory reside on an encrypted volume (LUKS) unlocked strictly inside the attested TD.
- **Data in Transit**: Sensitive model queries and tool executions run over local loopback inside the TD, or over attestation-authenticated mTLS when crossing trust boundaries.
- **Verifiable Evidence**: The deployment posture is provable to remote verifiers via hardware-rooted TDX Quotes and transparency logs.

### Target Architecture

```mermaid
flowchart LR
    User[User / Client] -->|TLS| Gateway[OpenClaw Gateway]
    subgraph TD[Intel TDX TDVM Trust Boundary]
        Gateway --> Agent[OpenClaw Agent Core]
        Agent --> Tools[Tool Execution / Sandbox]
        Gateway --> State[Config / Sessions / Memory]
        Agent -->|Loopback: 127.0.0.1:11434| Ollama[Local Ollama LLM]
    end
    State --- Disk[(LUKS Encrypted Volume)]
    TD --> Evidence[TDX Quote / TLog Evidence]
    Agent -.->|Cross-TD: Attested mTLS (Argus)| Remote[Remote Services / RAG]
```

### Deployment Patterns

| Deployment Pattern | Trust Boundary | Recommended Use Case |
| --- | --- | --- |
| **Pattern 1: Single-TD Co-location (Recommended)** | OpenClaw Agent and Ollama LLM share a single TDVM; communicate over loopback (`127.0.0.1`). | **Production baseline & evaluation**: Minimal attack surface, zero network exposure for inference, self-contained trust boundary. |
| **Pattern 2: Container Sandbox in TD** | OpenClaw Gateway runs in a TD container; tool executions spawn in temporary sandboxed containers. | **High tool-risk scenarios**: Isolates risky tool executions from agent core while remaining inside the TD. |
| **Pattern 3: Cross-TD / Distributed Services** | Agent and LLM/RAG reside in separate TDVMs, connected via attestation-bound secure channels (Argus). | **Multi-tenant / Enterprise clusters**: When LLM or knowledge base is shared across multiple agents. |

---

## 2. End-to-End Deployment Walkthrough (Single-TD Baseline)

The following step-by-step workflow implements the recommended **Single-TD Co-location** deployment pattern.

### Step 1: Verify the TDVM Environment

Log in to the Intel TDX guest and ensure the confidential computing hardware interface is available:

```bash
# Verify TDX guest device exists
ls -l /dev/tdx_guest

# Ensure TDX attestation tools / quote libraries are installed
dpkg -l | grep -E "sgx|tdx"
```

### Step 2: Set Up Encrypted Storage for Agent State

Agent configurations, conversation history, and API tokens must be protected at rest. Create and mount a LUKS-encrypted virtual filesystem inside the TD:

Run these commands from the repository root. The first argument is the volume size, and the second is the image path.

```bash
cd cczoo/openclaw-cc/luks_tools
export VFS_SIZE=10G
export VIRTUAL_FS=/root/vfs
./create_encrypted_vfs.sh "${VFS_SIZE}" "${VIRTUAL_FS}"

# Use the LOOP_DEVICE printed above, for example /dev/loop0.
export LOOP_DEVICE=/dev/loop0
mkdir -p /home/encrypted_storage
./mount_encrypted_vfs.sh "${LOOP_DEVICE}" format
```

Point OpenClaw at that mounted volume. These are the same paths used by the [OpenClaw-CC native guide](../../openclaw-cc/README.md):

```bash
export OPENCLAW_STATE_DIR=/home/encrypted_storage/.openclaw
export OPENCLAW_CONFIG_PATH=/home/encrypted_storage/.openclaw/openclaw.json
mkdir -p "$OPENCLAW_STATE_DIR"
```

### Step 3: Deploy Local Model Service (Ollama)

To keep model inference entirely within the confidential memory boundary, deploy Ollama locally inside the same TDVM:

```bash
cd cczoo/agent-cc/adapters/Ollama

# Install Ollama and bind to local loopback (127.0.0.1:11434)
./scripts/ollama-td.sh setup local qwen2.5:7b

# Test that the local OpenAI-compatible endpoint is healthy
./scripts/ollama-td.sh test local
```

*Note: For lightweight testing or resource-constrained environments, `qwen2.5:1.5b` can be used.*

### Step 4: Install and Configure OpenClaw

Install OpenClaw natively inside the TDVM, configuring it to consume the local Ollama service:

1. **Install OpenClaw**:
   ```bash
   curl -fsSL https://openclaw.ai/install.sh | bash
   ```

2. **Configure Provider in `$OPENCLAW_CONFIG_PATH`**:
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

3. **Start the OpenClaw Gateway**:
   ```bash
   openclaw gateway run --config "$OPENCLAW_CONFIG_PATH"
   ```

### Step 5: Verify Runtime Integrity and Attestation

Verify that the system is operating within a valid hardware TCB:

```bash
cd cczoo/openclaw-cc/tdx_utility
python3 -m pip install ./
cd ../cc_tdx_skills/get_td_quote/scripts
python3 setup.py build_ext --inplace
python3 print_tdx_quote.py

# Confirm that the state directory resides on the encrypted mount
df -h "$OPENCLAW_STATE_DIR"
```

---

## 3. Security Best Practices Checklist

| Domain | Best Practice | Rationale / Verification |
| --- | --- | --- |
| **Network Exposure** | Bind Ollama exclusively to `127.0.0.1:11434`. Never expose `0.0.0.0`. | Ollama local API lacks built-in authentication; loopback binding restricts access to local TD processes. |
| **Secret Management** | Inject platform tokens and API keys interactively inside the TD into `$OPENCLAW_CONFIG_PATH`. | Never bake secrets into Docker images, shell scripts, or git repositories. |
| **State Persistence** | Store all sessions, credentials, and memory under the LUKS-mounted directory. | Protects data at rest against host-level storage inspection or snapshot extraction. |
| **Least Privilege** | Run agent and tool processes under a dedicated non-root user. | Mitigates local privilege escalation within the TD guest OS. |
| **Tool Execution** | If enabling arbitrary code execution tools, enable Docker sandbox isolation. | Prevents untrusted model-generated code from tampering with gateway state or host filesystem. |

---

## 4. Production Roadmap & Advanced Patterns

For enterprise multi-tenant deployments, the architecture evolves beyond single-TD co-location:

1. **Automated TC-API Container Lifecycle**:
   - Building signed, SBOM-tracked agent container images.
   - Enforcing launch-time remote attestation via TC-API before releasing decryption keys.
   - *Roadmap*: Extending TC-API launch requests to support dynamic runtime secret injection and encrypted persistent volume binding.

2. **Cross-TD Attested Service Composition (Argus)**:
   - When scaling LLMs, vector databases, or memory stores to dedicated TDVMs, plain TLS is insufficient.
   - Deploy **Argus** sidecars to establish mutual attestation (mTLS with TDX Quote exchange) ensuring sensitive prompts only flow to verified backend enclaves.

---

## 5. Related Guides & References

- [OpenClaw Adapter Guide](../adapters/OpenClaw/README.md) - Container sandbox and TC-API integration
- [OpenClaw-CC Native TDVM Guide](../../openclaw-cc/README.md) - Deep dive into native TDX agent deployment and skills
- [Ollama Adapter Guide](../adapters/Ollama/README.md) - Complete Ollama setup, offline import, and script usage
- [Hermes Agent Adapter Guide](../adapters/Hermes/README.md) - Alternative agent framework integration
- [TC-API Architecture & Reference](../core/tc_api/README.md) - Trusted build-to-runtime control plane
