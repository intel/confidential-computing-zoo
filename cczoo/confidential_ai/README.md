# Confidential AI Solution Demo 

---
## 1. Overview 

**Objective**: Enable privacy-preserving LLM inference workflows with confidential computing VM 

**Design Principles**:
- Confidentiality: Ensure models and user data are not exposed outside of confidential VM
- Integrity: Guarantee the LLM inference environment(e.g., framework, models, UI) is untampered and verifiable. 

## 2. System Architecture 

![System Deployment Architecture](./images/Deployment%20Architecture.png)

### Key Components

#### 1. Client
The UI interface for end users to access large language model services. It initiates sessions, verifies the remote model serving environment and interacts with backend model service.

#### 2. Attestation Service:
A cloud-based service that verifies the proofness of the remote model serving environment. It verifies the the trustworthy of the platform TCB(Trusted Computing Base)and the model serving environment and ensures that the system’s security is intact before allowing further interactions with senstive data.

#### 3. Confidential VM (TDVM)
- **open-webui:**  
    A web-based interface hosted inside the confidential VM that accepts user requests for model service via web APIs.
- **Model Service:**  
    Handles AI model inference requests securely. 
- **TSM Module:**  
    The Trusted Service Module that provides the proofness of the execution environment.

**Intel TDX based heterogeneous Confidential VM**
+ Hardware-level memory encryption and isolation for AI model and user data
+ GPU TEE support for heterogeneous confidential computing 

### Workflow

![Confidential AI Workflow](./images/Confidential%20AI%20Flow.png)

#### 1. Initialization Phase

- **New Chat Session:**  
    The client (browser) initiates a new chat session by sending a session start request to the `open-webui`.

#### 2. Attestation Phase

- **Quote Request:**  
    The client requests a TDX quote from remote model execution environment running `open-webui` and model service (`ollama + DeepSeek`).
    
- **TDX Quote Generation:**  
    The `open-webui` forwards the request to the Trusted Service Module (TSM) within the TDX Confidential VM, which generates a TDX Quote along with a certification chain, by facilitating the underlying TDX Module and the quote generation service running at host operation system.
    
- **Quote Verification:**  
    The client submits the responded quote to an external Attestation Service for verification. The Attestation Service validates the quote and returns an attestation result confirming the remote model serving environment's integrity.
    

#### 3. Trusted Model Service Flow

- **If Attestation is Successful:** The client can confidently trust the remote model service, knowing it operates in a highly secure, trusted mode. This assurance means there is low risk (every system carries some level of risk) of data leakage for the end user.

- **If Attestation Fails:** The Attestation Service returns an error message indicating the attestation failure, which halts further processing or continuing serving but with a caution that the remote model service may be at risk .


## 3. Required Software Components

| Component                  | Version       | Purpose                                                                                                   |
| -------------------------- | ------------- | --------------------------------------------------------------------------------------------------------- |
| **Ollama**                 |  `v0.5.7`     | Framework for running language models on confidential VMs                                                 |
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
4.3.1 System Requirements
- **Operating System**: Linux 
- **Python Version**: Python 3.11+
- **Node.js Version**: 20.18+

4.3.2 Development Setup Instruction
 4.3.2.1 Clone the Repository
```bash
git clone https://github.com/your-org/open-webui.git  #Replace with actual repository URL(git apply xxx.patch  添加openwebUI对TDX的支持.)
cd open-webui
```

 4.3.2.2 Install Node.js
   - Ensure Node.js ≥20.18.1 is installed:
```bash
# Install Node Version Manager (n)
sudo npm install -g n

# Install specific Node.js version
sudo npm install 20.18.1

# if meet any connect error, you can use follow way to install
# install nvm(Node Version Manager)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash

### install node with verison ID
nvm install 20.18.1

### if need change node version
nvm use 20.18.1
```
4.3.3 Install Miniconda
 - Download and install Miniconda:
```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
### while installing,you can skip reading install information by enter q, and set default choice to finish installation

```
4.3.3.1  Configure environment paths:
```bash
# Add Miniconda to PATH (replace /path/to/ with actual installation path)
export PATH="/path/to/miniconda3/bin:$PATH"   ### defaoult path is: /root/miniconda3/bin

# Initialize Conda
conda init
source ~/.bashrc

# Verify installation
conda --version
```

4.3.4 Frontend Build and Test

 4.3.4.1  Enter open-webui & Create a `.env` file:

  ```bash
  cd open-webui
  cp -RPp .env.example .env
  ```

 4.3.4.2  Update Ollama Serving Address in `.env` and Modify the `.env` file to configure the **Ollama backend URL**. This ensures that requests to `/ollama` are correctly redirected to the specified backend:

```ini
# Ollama URL for the backend to connect
OLLAMA_BASE_URL='http://ip_address:port' 

# OpenAI API Configuration (Leave empty if not used)
OPENAI_API_BASE_URL=''
OPENAI_API_KEY=''

# AUTOMATIC1111 API (Uncomment if needed)
# AUTOMATIC1111_BASE_URL="http://localhost:7860"

# Disable Tracking & Telemetry
SCARF_NO_ANALYTICS=true
DO_NOT_TRACK=true
ANONYMIZED_TELEMETRY=false
```
Ensure you replace `ip_address:port` with the actual IP address and port of your **Ollama server** if necessary.

 4.3.4.3 Build frontend server(if error occured,please goto [here](#issue_note)):
    
  ```bash
  npm run build
  ```
+ After building the frontend, copy the generated `build` directory to the backend and rename it to `frontend`:
    
    ```bash
   cp -r build ./backend/open-webui/frontend

    ```
 4.3.4.4 Backend Build and Setup

- Navigate to the backend:
    
    ```bash
    cd backend
    ```
    
- Use **Conda** for environment setup:
    
    ```bash
    conda create --name open-webui python=3.11
    conda activate open-webui
    ```

 4.3.4.5 Install python dependencies([Tips](#tips)):
    
  ```bash
  pip install -r requirements.txt -U
  ```

 4.3.4.6.1 Install TDX-quote_parse-feature enable:

  ```bash
  cd quote_generator
  python setup.py install
  ```
### 4.4 Run openwebui
- Run ollama + AI model
  ```bash
     ollama run xxxx(model name)
  ```

- Configure `Attestation Service`
  Build setps:
  ```bash
  cd confidential_ai/attestation_service/ && ./build.sh
  ```
- Check Attestation status
  ```bash
  ./attest_service
  ```
  It will start the service and wait for connection: "Starting TDX Attestation Service on port 8443..."


- Run openwebui

  1.open backend service
  ```bash
  conda create --name open-webui python=3.11
  conda activate open-webui
  cd /path/to/open-webui/backend/ && ./dev.sh
  ```
  ![backend service](./images/openwebui-backend.png)

  2.open frontend service

  ```bash
  cd utilities/tdx/restful_as/restful_tdx_att_service && ./attest_service
  ```
  ![backend service](./images/openwebui-fronted.png)

  3.open browser and goto address: https://{ip_address}:18080/(The ip address is your server ip)

  4.Example:
    get quote data and parse
    
    ![backend service](./images/parse.png)

### <h2 id="issue_note">IssueNote：</h2>
 - While building, meet with `Cannot find package `,you can try command:

 ```bash
 npm install pyodide
 ```

### <h2 id="tips">Tips：</h2>
 - Downloading packages from remote sites can be slow. To speed up the   process, you can specify a local mirror such as **Aliyun** when installing packages:

 ```bash
 pip install torch -i https://mirrors.aliyun.com/pypi/simple/
 ```

 Alternatively, you can set Aliyun as the default mirror by adding the following lines to `~/.pip/pip.conf`, suggest to this method:

 ```ini
 [global]
index-url = https://mirrors.aliyun.com/pypi/simple/
 ```



### Prerequisites:
- Hardware: Intel Xeon with TDX features
- Software: (1) Host/Guest OS with TDX support (2)Install TDX remote attestation DCAP packages
Please refer to [Intel TDX Enabling Guide](https://cc-enabling.trustedservices.intel.com/intel-tdx-enabling-guide/01/introduction/index.html).

## 5. Implemenation Detials
### Measurement 
### Remote Attestation
