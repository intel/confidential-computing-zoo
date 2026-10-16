# Hermes Agent Adapter

This guide provides deployment instructions and security practices for running [Hermes Agent](https://github.com/NousResearch/hermes-agent) inside an Intel TDX confidential virtual machine (TDVM).

---

## 1. Overview & Trust Model

Deploying Hermes Agent inside an Intel TDX TDVM protects user conversations, reasoning context, and credentials from external observation or tampering:

- **Confidential Memory**: Hermes execution and local model inference remain protected inside hardware-encrypted TDX memory.
- **State Protection**: Hermes configurations, credentials, session logs, and SQLite memory stores reside on an encrypted volume (LUKS) mounted inside the TD.
- **Local Loopback Inference**: Hermes connects to a co-located Ollama model service over loopback (`127.0.0.1:11434`), preventing prompts and outputs from leaving the confidential boundary.

---

## 2. Prerequisites

- An Intel TDX TDVM with `/dev/tdx_guest` available.
- A mounted LUKS-encrypted volume (e.g. at `/mnt/encrypted/hermes`) for state persistence.
- Local Ollama service running on `http://127.0.0.1:11434`. (Refer to the [Ollama Adapter Guide](../Ollama/README.md)).

---

## 3. Step-by-Step Native Deployment

### Step 1: Install Hermes Agent

Log in as a dedicated unprivileged user inside the TDVM and install Hermes:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

### Step 2: Configure Encrypted State Directory

Direct all state, database, and credential persistence to the mounted LUKS volume:

```bash
export HERMES_HOME=/mnt/encrypted/hermes
mkdir -p "$HERMES_HOME"

# Run initial setup wizard
hermes setup
```

### Step 3: Configure Ollama Model Provider

Configure Hermes to consume the co-located Ollama service via OpenAI-compatible API in `$HERMES_HOME/config.yaml`:

```yaml
model:
  provider: custom
  base_url: http://127.0.0.1:11434/v1
  default: qwen2.5:7b
```

*Note: For lightweight testing, `qwen2.5:1.5b` can be used.*

### Step 4: Configure Credentials Securely

Configure messaging platform tokens (e.g., Discord, Telegram, Slack) or API keys inside the TD:
- Use the interactive wizard: `hermes setup`
- Or save variables into `$HERMES_HOME/.env` with strict permissions:
  ```bash
  chmod 0600 "$HERMES_HOME/.env"
  ```

> **Security Warning**: Never hardcode credentials into Dockerfiles, commit them to git, or pass them via unencrypted command-line flags.

### Step 5: Launch Hermes Agent

Run Hermes in interactive CLI mode:
```bash
HERMES_HOME=/mnt/encrypted/hermes hermes
```

Or run the messaging gateway daemon:
```bash
HERMES_HOME=/mnt/encrypted/hermes hermes gateway run
```

---

## 4. Systemd Service Management (Optional)

To keep the Hermes gateway running persistently as a user service:

1. Create the systemd user service file:
   ```ini
   # ~/.config/systemd/user/hermes-gateway.service
   [Unit]
   Description=Hermes Agent Gateway
   RequiresMountsFor=/mnt/encrypted/hermes

   [Service]
   Type=simple
   Environment=HERMES_HOME=/mnt/encrypted/hermes
   ExecStart=%h/.local/bin/hermes gateway run
   Restart=on-failure
   RestartSec=5

   [Install]
   WantedBy=default.target
   ```

2. Enable and start the service:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now hermes-gateway.service
   ```

---

## 5. Verification & Operational Notes

- **Verified Baseline**: Local text inference has been validated in an Intel TDX TDVM connecting to local Ollama with `qwen2.5:1.5b`.
- **Context Length**: When using Ollama, confirm the effective context window with `ollama ps`. A context size of 32,768 tokens is recommended for stable operation.
- **Hardware Attestation**: Install `cczoo/openclaw-cc/tdx_utility`, then run `python3 setup.py build_ext --inplace` and `python3 print_tdx_quote.py` in `cczoo/openclaw-cc/cc_tdx_skills/get_td_quote/scripts/`.

---

## 6. Container Execution & Future Roadmap

Containerizing Hermes under TC-API requires container command overrides (to execute `hermes gateway run` instead of the interactive CLI) and dynamic persistent volume mounting. Support for these capabilities is tracked on the TC-API roadmap.

---

## 7. Security Boundaries

- **TD Boundary**: A TDVM protects runtime memory from external host or hypervisor access. It does not defend against compromised dependencies or unauthorized actions executed inside the guest OS.
- **Terminal Tool Privileges**: Hermes terminal execution tools can perform powerful shell actions. Enforce least-privilege permissions and restrict access to the file system and sensitive network endpoints.
- **External API Traffic**: If configuring an external model provider instead of local Ollama, prompt and context data will leave the TD boundary over the internet.

---

## 8. References

- [Hermes Agent Upstream Repository](https://github.com/NousResearch/hermes-agent)
- [Hermes Agent Installation Documentation](https://hermes-agent.nousresearch.com/docs/getting-started/installation)
- [Hermes Agent Provider Configuration](https://hermes-agent.nousresearch.com/docs/integrations/providers)
- [Ollama Adapter Guide](../Ollama/README.md)
