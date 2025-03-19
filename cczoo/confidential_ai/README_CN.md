<div align="right">
  <a href="./README.md">English</a>
</div>

# Confidential AI 方案演示 

---
## 1. 概述 

**目标**: 通过机密计算虚拟机展示隐私保护的大语言模型推理工作流程

**设计原则**:
- 机密性: 确保模型与用户数据仅在机密计算虚拟机（Confidential VM）的加密安全边界内处理，​禁止明文暴露到外部环境。
- 完整性: 保障大语言模型推理服务运行环境各组件（推理服务框架、模型文件、交互界面等）的代码与配置防篡改，支持第三方审计验证流程。

## 2. 系统架构 

![System Deployment Architecture](./images/Deployment%20Architecture.png)

### 部署组件

#### 1. 客户端
终端用户访问大语言模型服务的交互界面（UI），负责 ​发起会话、验证远端模型服务环境可信性，并与后端模型服务进行安全通信。

#### 2. 远程证明服务
基于云端的远程证明服务，用于验证模型推理服务环境的安全状态，包括：平台可信计算基（TCB, Trusted Computing Base）以及推理模型服务环境，如服务框架、模型参数、运行依赖、配置等的可信性。

#### 3. 机密虚拟机 (TDVM)
- **open-webui:**  
    运行于机密虚拟机内部的 Web 交互接口，通过 RESTful API 接收用户模型服务请求。
- **模型服务:**  
    处理模型推理服务请求的模型服务框架。
- **可信服务:**  
    提供执行环境可信性证明的安全服务模块

**基于Intel TDX的机密虚拟机**
+ 基于硬件的可信执行环境，满足机密计算需要的内存密态隔离和权限隔离多种保护能力，确保用户数据和模型参数的机密性保护
+ 支持异构机密计算能力，配合支持机密计算的AI加速器实现对模型处理的安全高效加速。

### 工作流程

![Confidential AI Workflow](./images/Confidential%20AI%20Flow.png)

#### 1. 服务启动及度量流程

- **运行环境度量:**  
    平台TCB模块针对运行模型服务的运行环境进行完整性度量，度量结果存储在位于TCB中的TDX Module中。

#### 2. 推理会话初始化阶段

- **新建会话:**  
    客户端 (浏览器) 向`open-webui`发起新的会话请求。

#### 3. 远程证明阶段

- **证明请求:**  
    客户端发起会话请求时，会向服务后端同时请求一个证明模型运行环境的可信性证明(TDX quote)，该证明可以用来验证远程服务环境的可信性，包含用户会话管理服务 `open-webui` 和模型服务 (`ollama + DeepSeek`)。
    
- **证明产生:**  
    `open-webui` 服务后端将将用户会话创建过程中的证明请求转发至​基于Intel TDX的机密计算虚拟机（Confidential VM）​ 可信服务模块（TSM）​。该模块通过协调底层TDX Module与宿主机操作系统（Host OS）上运行的证明生成服务，生成包含完整证书链的​TDX证明（TDX Quote）​。

    
- **证明验证:**  
    客户端将接收到的证明（Quote）提交至远程证明服务（Attestation Service）​进行验证。证明服务通过验证该次证明的有效性（包括数字签名、证书链及安全策略），返回证明结果，确认远端模型服务环境的安全性状态与完整性。

#### 4. 机密大模型推理服务阶段

- **远程证明成功:** 客户端可以 ​充分信任远端模型服务，因为其运行在​高度安全且可信的模式 下。这种保证意味着，对于终端用户而言，数据泄露的风险极低（尽管任何系统都存在一定程度的风险）。

- **远程证明失败:** 证明服务将返回错误信息，表明远程证明失败。此时，用户或者系统或选择中止进一步服务请求，或在 有效提示安全风险的情况下继续提供服务，但是此时远端模型服务可能存在数据安全风险。


## 3. 软件组件

| Component                  | Version       | Purpose                                                                                                   |
| -------------------------- | ------------- | --------------------------------------------------------------------------------------------------------- |
| **Ollama**                 |  `v0.5.7`     | Framework for running language models on confidential VMs                                                 |
| **DeepSeek-R1**            |               | High performance reasoning model for inference service                                                    |
| **open-webui**             | `v0.5.20`     | Self-hosted AI interface for user-interaction, running on the same confidential VM to simplify deployment |
| **Cofidential AI(cc-zoo)** |               | Patches and compoents from cc-zoo                                                                         |
| **Attestation Service**    |               |                                                                                                           |
## 4. 构建和安装指南

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

## 5. 安全原理概述
### Measurement

Intel Trust Domain Extensions (TDX) enhances virtual machine security by isolating them within hardware-protected Trust Domains (TDs). During the boot process, the TDX module records the state of the TD guest using two primary registers:

- **Build Time Measurement Register (MRTD):** Captures measurements related to the guest VM's initial configuration and boot block image.
    
- **Runtime Measurement Registers (RTMR):** Records measurements of the initial state, kernel image, command-line options, and other runtime services and parameters as needed. 
    

These measurements ensure the integrity of the TD and the running application throughout its lifecycle. For this solution demo, the measurements of model services and parameters, including those associated with the Ollama and DeepSeek models, as well as the open-webui web framework can be reflected in the RTMRs. 

### Remote Attestation

Remote attestation in TDX provides cryptographic proof of a TD's integrity and authenticity to remote parties. The process involves several key steps:

+ **Quote Generation and Retrieval:**
    1. The client requests the `open-webui` to provide proof of the remote services' integrity.
    2. The backend of `open-webui` communicates with the Trusted Service to retrieve the measurement report signed with the platform's TCB certificate. The report includes MRTD and RTMRs reflecting the current integrity status of the running model serving environment. This signed measurement report is known as the quote.
+ **Quote Verification:** The client sends the quote to a trusted attestation service to verify it against predefined policies, establishing trust with the model service before processing sensitive information.
    

By integrating these measurement and attestation mechanisms, the Confidential AI service provides a robust framework for verifying the integrity and authenticity of remote model serving services, which is crucial for protecting data security and privacy.
