# Confidential AI Solution Demo 

---
## 1. Overview 

**Objective**: Enable privacy-preserving LLM inference workflows with confidential computing VM 
**Design Principles**:
- Confidentiality: Ensure models and user data are not exposed outside of confidential VM
- Integrity: Guarantee the LLM inference environment(e.g., framework, models, UI) is untampered and verifiable. 

## 2. System Architecture 

### Core Components

### Workflow

## 3. Required Software Components

| Component                  | Version       | Purpose                                                                                                   |
| -------------------------- | ------------- | --------------------------------------------------------------------------------------------------------- |
| **Ollama**                 |               | Framework for running language models on confidential VMs                                                 |
| **DeepSeek-R1**            |               | High performance reasoning model for inference service                                                    |
| **open-webui**             | `v0.5.20`     | Self-hosted AI interface for user-interaction, running on the same confidential VM to simplify deployment |
| **Cofidential AI(cc-zoo)** |               | Patches and compoents from cc-zoo                                                                         |
| **Attestation Service**    |               |                                                                                                           |
## 4. Build and Setup Instructions

### 4.1 Download AI Modle
Here we use deepseek-llm-7b-chat model, please refer to the [guide](https://www.modelscope.cn/models/deepseek-ai/deepseek-llm-7b-chat) to download the model.


### 4.2 Install ollama
Please refer to [ollama installation guide](https://github.com/ollama/ollama/blob/main/docs/linux.md).

### 4.3 Build openwebui
xxx
xxx

### 4.4 Run openwebui
- Run ollama + AI model
xxx
- Run openwebui
xxx

- Configure `Attestation Service`
xxx
- Check Attestation status


### Prerequisites:
- Hardware: Intel Xeon with TDX features
- Software: (1) Host/Guest OS with TDX support (2)Install TDX remote attestation DCAP packages
Please refer to [Intel TDX Enabling Guide](https://cc-enabling.trustedservices.intel.com/intel-tdx-enabling-guide/01/introduction/index.html).

## 5. Implemenation Detials
### Measurement 
### Remote Attestation
