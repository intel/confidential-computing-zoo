# Ollama Adapter: Local LLM Service for Confidential Agents

Ollama provides a lightweight runtime and standard OpenAI-compatible API (`/v1`) for open-source large language models, enabling seamless integration with agents such as OpenClaw and Hermes Agent.

Deploying Ollama inside an Intel TDX confidential virtual machine (TDVM) keeps model weight decryption, inference computation, and prompt context entirely within hardware-encrypted memory, eliminating the exposure of sensitive prompts and data to external commercial cloud APIs.

---

## 1. Deployment Modes & Trust Boundaries

| Mode | Trust Boundary | Status | Recommended Use Case |
| --- | --- | --- | --- |
| **Native Single-TD (Recommended)** | Ollama and Agent run in the same TDVM, communicating over `127.0.0.1` loopback. | ✅ Fully validated (supports Qwen 2.5 1.5B / 7B, etc.). | Primary baseline for production and evaluation; minimal attack surface. |
| **Host Ollama for TD containers** | Ollama runs on the TDVM host and is bound to the `docker0` address so containers in the same TD can reach it. | ✅ `ollama-td.sh setup docker` | Agents or tool stacks that already run in Docker. |
| **Single-TD Container + TC-API** | Ollama container image is signed, encrypted, and launched after remote attestation via TC-API. | 🚧 Dockerfile available; end-to-end TC-API flow pending integration. | Enterprise pipelines requiring verifiable build-to-runtime supply chain integrity. |
| **Cross-TD Distributed Service** | Agent TD and Ollama TD are physically separated, connected via Argus attested channels. | 🚧 Architectural roadmap (depends on Argus mesh). | Centralized model inference clusters or multi-tenant agent deployments. |

---

## 2. Prerequisites

- **Hardware/Guest**: Linux guest operating system supporting Intel TDX (verify presence of `/dev/tdx_guest`).
- **Dependencies**: `systemd`, `curl`, `bash`.
- **System Resources**:
  - `qwen2.5:1.5b`: Minimum 4 GB available RAM, 2 GB disk.
  - `qwen2.5:7b`: Minimum 16 GB available RAM, 8 GB disk.

---

## 3. Native Single-TD Deployment (Quick Start)

### Method 1: Using the Automated `ollama-td.sh` Script (Recommended)

The repository provides an automated management script at [scripts/ollama-td.sh](./scripts/ollama-td.sh) tailored for TD environments. It automatically installs Ollama, configures systemd, and binds the API strictly to loopback:

```bash
cd cczoo/agent-cc/adapters/Ollama

# 1. Install Ollama, bind to 127.0.0.1:11434, and pull model (e.g., qwen2.5:7b)
./scripts/ollama-td.sh setup local qwen2.5:7b

# 2. Check service status and pulled models
./scripts/ollama-td.sh status local

# 3. Test OpenAI-compatible API connectivity
./scripts/ollama-td.sh test local
```

*Common script commands:*
- `./scripts/ollama-td.sh start | stop`: Start or stop the systemd service
- `./scripts/ollama-td.sh pull <model>`: Pull an additional model

### Method 2: Offline / Mirror Model Import (For Restricted Network Environments)

If network constraints prevent pulling directly from the official Ollama registry, GGUF weights can be downloaded from ModelScope or local mirrors and imported into Ollama:

```bash
# 1. Download Qwen2.5-1.5B-Instruct GGUF weights (~1.12 GB) and verify SHA-256
curl -fL 'https://modelscope.cn/models/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/master/qwen2.5-1.5b-instruct-q4_k_m.gguf' \
  -o qwen2.5-1.5b-instruct-q4_k_m.gguf

printf '%s  %s\n' \
  '6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e' \
  'qwen2.5-1.5b-instruct-q4_k_m.gguf' | sha256sum -c -

# 2. Create Modelfile
cat > Modelfile <<'EOF'
FROM ./qwen2.5-1.5b-instruct-q4_k_m.gguf
PARAMETER num_ctx 16384
PARAMETER temperature 0.2
EOF

# 3. Create the local model in Ollama
ollama create qwen2.5:1.5b-validation -f Modelfile

# 4. Test inference
curl -fsS http://127.0.0.1:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5:1.5b-validation","prompt":"Hello, please respond with: TDX Ollama works!","stream":false}'
```

---

## 4. Host Ollama for Containers in the TD

If the agent runs inside a Docker container within the same TDVM, bind the host Ollama service to the `docker0` bridge:

```bash
# Bind Ollama to docker0 bridge
./scripts/ollama-td.sh setup docker qwen2.5:7b

# Test connectivity from inside container
docker run --rm --add-host=host.docker.internal:host-gateway \
  curlimages/curl:latest -fsS http://host.docker.internal:11434/api/tags
```

The containerized agent accesses Ollama at `http://host.docker.internal:11434/v1`.

---

## 5. Agent Integration

Ollama's local API does not enforce authentication; any placeholder API key (such as `ollama`) can be supplied.

### OpenClaw Configuration

Add the provider in OpenClaw's configuration file (`.openclaw.json`):

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

### Hermes Agent Configuration

Configure provider settings in `$HERMES_HOME/config.yaml`:

```yaml
model:
  provider: custom
  base_url: http://127.0.0.1:11434/v1
  default: qwen2.5:7b
```

---

## 6. TC-API Container Lifecycle (Advanced)

The repository provides [Dockerfile.tc-api](./Dockerfile.tc-api) to bake pre-pulled models into an image and launch `ollama serve` at container startup.

Submitting the build through TC-API produces a signed, SBOM-attested image that can be launched conditionally on TDX remote attestation. See the [TC-API Documentation](../../core/tc_api/README.md) for complete details.

---

## 7. Security Best Practices

> [!WARNING]
> 1. **Do Not Expose to Public Networks**: Ollama's local API has no built-in authentication. Never bind to `0.0.0.0`; bind only to `127.0.0.1` or controlled internal container bridge addresses.
> 2. **At-Rest Protection**: Model weights and caches reside on local disk. If weights contain proprietary IP, locate the models directory (`~/.ollama/models`) on a LUKS-encrypted volume.
> 3. **Cross-TD Attestation**: For distributed setups where Ollama runs in a separate TD, use Argus with mutual remote attestation to verify the model endpoint identity before sending sensitive prompts.
