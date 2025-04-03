<div align="right">
  <a href="./README.md">English</a>
</div>

# Confidential AI Solution Demo 

---
## 1. Overview 
This article describes how to build a DeepSeek confidential inference service in an Alibaba Cloud heterogeneous confidential computing instance (gn8v-tee), and demonstrates how to combine the CPU TDX confidential computing security measurement authentication function to provide security authentication and privacy protection workflows for the deployed DeepSeek online inference service.
**Objective**: Demonstrate the privacy-preserving large language model inference workflow through confidential computing virtual machines

**Background**

Alibaba Cloud's heterogeneous confidential computing instance (gn8v-tee) introduces GPU into TEE (Trusted Execution Environment) based on CPU TDX confidential computing instance, which can protect data transmission between CPU and GPU and data calculation in GPU. For the construction of CPU TDX confidential computing environment and its remote attestation capability verification, please refer to[**Build TDX confidential computing environment**](https://help.aliyun.com/zh/ecs/user-guide/build-a-tdx-confidential-computing-environment)；关于异构机密计算环境的搭建请参见[**构建异构机密计算环境**](https://help.aliyun.com/zh/ecs/user-guide/build-a-tdx-confidential-computing-environment).
**Design principles**:
- Confidentiality: Ensure that models and user data are processed only within the encrypted security boundary of the confidential computing instance (TDX CPU+CC GPU), and do not expose plain text to the external environment.
- Integrity: Ensure that the code and configuration of each component of the large language model inference service operating environment (inference service framework, model files, interactive interface, etc.) are tamper-proof and support third-party audit verification processes.

# Safety Principles Overview
## Credibility Metrics
Intel Trust Domain Extensions (TDX) 
The security of the virtual machine is enhanced by isolating the virtual machine in a hardware-protected trust domain(TDs, Trusted Domains). During the boot process, the TDX module uses two main registers to record the status of the TD client.

- Build Time Measurement Register (MRTD): Capture measurements related to the initial configuration and boot image of a guest VM.

- Runtime Measurement Registers (RTMR): Record measurements of initial state, kernel images, command-line options, and other runtime services and parameters as needed.

These measurements ensure the integrity of the TD and the running application throughout its lifecycle. For this solution demonstration, measurements of model serving and kernel parameters(including those related to the Ollama and DeepSeek models and the open-webui web framework), can be reflected in the RTMR.

## Remote authentication
Remote attestation in TDX provides cryptographic authentication of the integrity and authenticity of the TD confidential virtual machine to the remote party. The process involves several key steps:
- Get TD Quote:
   i. The client requests open-webui to provide complete remote authentication services.
   ii. The open-webui backend communicates with the Trusted Service to obtain a measurement report signed with the platform TCB certificate. The report includes MRTD and RTMR, reflecting the current integrity status of the running model service environment. This signed measurement report is called Quote.
- TD Quote's certification: The client sends the quote to a trusted attestation service for verification against predefined policies and establishes trust with the model service before processing sensitive information.

## Alibaba Cloud Remote Authentication Service
Alibaba Cloud Remote Attestation Service is based on RFC 9394 - Remote ATtestation procedureS (RATS) Architecture，It can be used to verify the security status and credibility of Alibaba Cloud security-enhanced instances. This service involves the following roles:
- Attester：Users of Alibaba Cloud ECS instances need to prove the identity and credibility of the ECS instances to the relying parties.
- Relying Party：For entities that need to verify the identity and credibility of the prover, the relying party will generate an evaluation strategy based on TPM, TEE and other measurement information as benchmark data.
- Verifier：Alibaba Cloud Remote Attestation Service is responsible for comparing the evidence with the evaluation strategy and obtaining the verification result.

Alibaba Cloud Remote Attestation Service provides an API that is compatible with the OIDC standard. You can regard Alibaba Cloud Remote Attestation Service as a standard identity provider (IdP) service.

- Alibaba Cloud Remote Attestation Service issues OIDC Tokens for trusted computing instances and confidential computing instances to prove the identity of ECS instances to relying parties.
- Relying parties can verify the cryptographic validity of OIDC Tokens through OIDC's standard process.

By integrating these metrics and proof mechanisms, DeepSeek online inference service provides a powerful framework to verify the integrity and authenticity of remote model serving services, which is critical to protecting data security and privacy.

## 2. System Architecture 
The overall solution architecture design is shown in the figure:
![System Deployment Architecture](./images/DeploymentArchitecture.png)

### Deployment Components

#### 1. Client
The interactive interface (UI) through which end users access the large language model service is responsible for initiating sessions, verifying the credibility of the remote model service environment, and communicating securely with the backend model service.

#### 2. Remote Attestation Services
Based on Alibaba Cloud Remote Attestation Service, it is used to verify the security status of the model reasoning service environment, including: the platform trusted computing base (TCB, Trusted Computing Base) and the reasoning model service environment.

#### 3. Reasoning Service Components

| Component                  | Version       | Purpose                                                                                                   |
| -------------------------- | ------------- | --------------------------------------------------------------------------------------------------------- |
| **Ollama**                 |  `v0.5.7`     | Framework for running language models on confidential VMs                                                 |
| **DeepSeek-R1**            |`deepseek-r1-70b(Quantification)`| High performance reasoning model for inference service                                                    |
| **open-webui**             | `v0.5.20`     | Self-hosted AI interface for user-interaction, running on the same confidential VM to simplify deployment |
| **Cofidential AI(cc-zoo)** |   `v1.2`        | Patches and compoents from cc-zoo                                                                         |

### Workflow

![Confidential AI Workflow](./images/Confidential%20AI%20Flow.png)

#### 1. Service startup and measurement process

- **Operating environment metrics:**  
    The platform TCB module performs integrity measurement on the operating environment of the running model service, and the measurement results are stored in the TDX Module located in the TCB.

#### 2. Reasoning session initialization phase

- **New Session:**  
    The client (browser) initiates a new session request to `open-webui`.

#### 3. Remote Attestation Phase

- **Certification Request:**  
    When the client initiates a session request, it will also request a credibility certificate (TDX Quote) from the service backend to prove the credibility of the model running environment. This certificate can be used to verify the credibility of the remote service environment, including the credibility of the user session management service `open-webui` and the model service (`ollama + DeepSeek`).
    
- **Proof of Generation:**  
    The `open-webui` service backend forwards the attestation request during the user session creation process to the Confidential VM based on Intel TDX Trusted Service Module (TSM). The module generates a TDX Quote containing a complete certificate chain by coordinating the underlying TDX Module with the attestation generation service running on the host operating system (Host OS).

    
- **Proof Verification:**  
    The client submits the received quote to the remote attestation service for verification. The attestation service verifies the validity of the quote (including digital signature, certificate chain and security policy), returns the attestation result, and confirms the security status and integrity of the remote model service environment.

#### 4. Confidential large model inference service stage

- **Remote attestation success:** Clients can fully trust the remote model service because it runs in a highly secure and trusted mode. This assurance means that for end users, the risk of data leakage is extremely low (although any system has some degree of risk).

- **Remote attestation failed:** The attestation service will return an error message, indicating that the remote attestation has failed. At this point, the user or system may choose to terminate further service requests, or continue to provide services with effective warnings of security risks, but at this point the remote model service may have data security risks.


## 4. DeepSeek Confidential Inference Service Build and Installation Guide

#### Step 1: Install ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
``` 
For more information, see [**ollama Installation Guide**](https://github.com/ollama/ollama/blob/main/docs/linux.md).

#### Step 2：Download and run the deepseek model
```bash
ollama run deepseek-r1:70b
``` 

#### Step 3：Compile and install open-webui
1. Install Dependencies
```bash
# install nodejs
sudo yum install nodejs -y

# If the default installation fails, try the following steps:
# install npm
sudo yum install npm -y

# Install the specified version of nodejs
sudo npm install 20.18.1
```
Install Miniconda(Used to start the open-webui virtual environment)：
```bash
sudo wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
sudo bash Miniconda3-latest-Linux-x86_64.sh -bu
```
2. Configuring environment variables
```bash
# Set Miniconda path,Defaulte path is: /root/miniconda3/bin
export PATH="/root/miniconda3/bin:$PATH"   

# initial Conda
conda init
source ~/.bashrc

# Verify Installation
conda --version
```
3. Compile and install steps

1）Download the TDX Security Metrics plugin
```bash
cd <work_dir>
git clone https://github.com/intel/confidential-computing-zoo.git
cd confidential-computing-zoo
git checkout v1.2
```
2）get openweb-ui code
```bash
cd <work_dir>
git clone https://github.com/open-webui/open-webui.git

# checkout to tag:v0.5.20 
cd open-webui-main/
git checkout v0.5.20

# merger to CCZoo's patch，the patch enhance the functions of open-webui for TDX remote authentication
cp <work_dir>/confidential-computing-zoo/cczoo/xxxxx.patch .
git apply xxxx.patch
```
3）Create and activate the open-webui environment
```bash
conda create --name open-webui python=3.11
conda activate open-webui
```
4）Install the "Get TDX Quote" plugin
```bash
cd <work_dir>/confidential-computing-zoo/cczoo/confidential_ai/tdx_measurement_plugin/
python setup.py install

#验证安装使用
python3 -c "import quote_generator"
```
5）Compile open-webui
```bash
 # Install Dependencies
 cd <work_dir>/open-webui-main/open-webui/
 sudo npm install
 
 #Compile
 sudo npm run build
 ```
 After compilation is complete, copy the generated `build` folder to the backend directory and rename it to `frontend`:
 ```bash
 cp -r build ./backend/open-webui/frontend
 ```
 Backend service settings
 ```bash
 cd backend
vim dev.sh

#Set the service address port. The default port is 8080
PORT="${PORT:-8080}"
uvicorn open_webui.main:app --port $PORT --host 0.0.0.0 --forwarded-allow-ips '*' --reload
```
Install Python Dependencies
```bash
pip install -r requirements.txt -U
conda deactiva
```

#### Step 4：Run openwebui
1. Run ollama + DeepSeek model
```bash
ollama run deepseek-r1:70b
/bye
```
2. Alibaba Cloud Remote Attestation Service(URL:https://attest.cn-beijing.aliyuncs.com/v1/attestation) has been configured in <work_dir>/open-webui-main/open-webui/external/acs-attest-client/index.js
3. run openwebui
1) activate open-webui environment
```bash
conda activate open-webui
```
2) Enable backend services：
```bash
cd <work_dir>/open-webui-main/open-webui/backend/ && ./dev.sh
```
 ![backend service](./images/openwebui-backend.png)
3) Open browser and enter the IP address of the current heterogeneous confidential computing instance，https://{ip_address}:{port}/(Note that the IP address is replaced with the IP address of the instance where open-webui is located, and the port number is the default port 18080).
  ![backend service](./images/login.png)

4) Select a model (deepseek-r1:70b is used as an example here). You can select a model each time you create a new session window.
  ![backend service](./images/selectModel.png)
5) Each time you click the "New Chat" button, the background will automatically obtain the quote data of the TDX confidential computing environment and send it to the remote attestation service and return the authentication result. In the initial state, this icon is red. It means that the remote attestation is not completed or failed. It will be green after the remote attestation is successful.
  ![backend service](./images/attestationinfo_error.png)
6) Front-end TDX Verification (Hover the mouse over the first icon in the dialog box to see the detailed authentication information of parsing TDX Quote. If the remote attestation is successful, the icon will be marked green, and if the attestation fails, it will be marked red.
  ![backend service](./images/attestationinfo_pass.png)


### Solution security enhancement
[Using CLB to deploy HTTPS services (one-way authentication)](https://help.aliyun.com/zh/slb/classic-load-balancer/use-cases/configure-one-way-authentication-for-https-requests)
1. Open WebUI native design only supports HTTP protocol, in order to increase the security of data transmission

### <h2 id="tips">Tips：</h2>
1. When installing dependencies, you can use Alibaba Cloud's image to speed up downloading:

 ```bash
 pip install torch -i https://mirrors.aliyun.com/pypi/simple/
 ```

 Or you can set it in the `~/.pip/pip.conf` file (recommended):

 ```ini
 [global]
index-url = https://mirrors.aliyun.com/pypi/simple/
 ```
2. When compiling open-webui, if you encounter Cannot find package, you can try the following command (note that pyodide is replaced with the actual package name):
```bash
npm install pyodide
```
