# RA-TLS Enhanced gRPC

This solution presents an enhanced [gRPC](https://grpc.io/) (Google Remote Procedure Call) framework to
guarantee security during transmission and runtime via two-way
[RA-TLS](https://arxiv.org/pdf/1801.05863)
(Remote Attestation with Transport Layer Security) based on
[TEE](https://en.wikipedia.org/wiki/Trusted_execution_environment) (Trusted Execution Environment).


## Introduction

[gRPC](https://grpc.io/) is a modern, open source, high-performance remote procedure call (RPC)
framework that can run anywhere. It enables client and server applications to communicate
transparently and simplifies the building of connected systems. For securing gRPC connections, the
SSL/TLS authentication mechanisms are built-in to gRPC. gRPC is designed to work with a variety of authentication mechanisms, making it easy to use gRPC to communicate with other systems.

Transport Layer Security ([TLS](https://en.wikipedia.org/wiki/Transport_Layer_Security)), the
successor of the now-deprecated Secure Sockets Layer (SSL), is a cryptographic protocol designed to
provide communications security over a computer network. The current version is
[TLS 1.3](https://datatracker.ietf.org/doc/html/rfc8446) defined in August 2018.

gRPC RA-TLS integrates TEE and Intel® RA-TLS technology, and establishes a standard TLS (v1.3)
connection in the TEE based on the gRPC TLS/SSL mechanism. The TEE guarantees code and data loaded inside to be
protected with respect to confidentiality and integrity in runtime.

During the TLS handshake procedure, the public key certificates are used for key exchange. The
public key certificate is [X.509](https://en.wikipedia.org/wiki/X.509) format. The public key certificate is either signed
by a certificate authority (CA) or is self-signed for binding an identity to a public key.

Remote attestation is performed during the connection setup by embedding the attestation evidence
into the endpoints TLS public key certificate.

![](img/tls-v13-handshake.svg)

In the gRPC TLS handshake phase, the certificates are generated and verified as follows.

| Generate X.509 certificate | Verify X.509 certificate |
| ------------ | ------------ |
| 1. Generate the RSA key pair <br> 2. Generate the X.509 certificate with the RSA key pair <br> 3. Embed the hash of RSA public key into SGX/TDX quote report signed by the [attestation key](https://download.01.org/intel-sgx/dcap-1.0.1/docs/Intel_SGX_ECDSA_QuoteGenReference_DCAP_API_Linux_1.0.1.pdf) <br> 4. Embed the quote report into X.509 as a v3 extension <br> 5. Self-sign the X.509 certificate | 1. Verify the X.509 certificate by the default gRPC TLS procedure <br> 2. Parse the quote report from the X.509 extension <br> 3. Verify the quote report by the Intel DCAP interface <br> 4. Compare the hash of X.509 certificate with the hash embedded in the quote report <br> 5. Compare the enclave's identity embedded in the quote report against the expected identity |

This solution supports two-way RA-TLS verification between the gRPC server and client, which means the
client and server both need to generate certificates and verify each other.


## Prerequisites
### Docker Engine
Docker Engine is an open-source containerization technology for building and containerizing your applications.
Please follow this [guide](https://docs.docker.com/engine/install/ubuntu/#install-using-the-convenience-script)
to install Docker engine. It is recommended to use a data disk of at least 128GB for the docker daemon data directory. This [guide](https://docs.docker.com/config/daemon/#daemon-data-directory) describes how to configure the docker daemon data directory. If behind a proxy server, please refer to this [guide](https://docs.docker.com/config/daemon/systemd/) for configuring the docker daemon proxy settings.

### CCZoo Source:
```
   git clone https://github.com/intel/confidential-computing-zoo.git
   cczoo_base_dir=$PWD/confidential-computing-zoo
```

## RA-TLS Enhanced gRPC for TDX

[Intel® Trust Domain Extensions](https://www.intel.com/content/www/us/en/developer/tools/trust-domain-extensions/overview.html) (Intel® TDX) is Intel's newest confidential computing technology. This hardware-based trusted execution environment (TEE) facilitates the deployment of trust domains (TD), which are hardware-isolated virtual machines (VM) designed to protect sensitive data and applications from unauthorized access.

### Azure (TDX)

1. Build container.
```
cd ${cczoo_base_dir}/cczoo/grpc-ra-tls/azure_tdx
./build_docker_image.sh
```

NOTE: To specify the proxy server, set the `http_proxy` and `https_proxy` variables prior to the call to build_docker_image.sh, for example:
      
```
http_proxy=http://proxyserver:port https_proxy=http://proxyserver:port ./build_docker_image.sh
```

2. Start example RA-TLS Enhanced gRPC server.

Modify the Networking settings of the Azure DCesv5 VM (designated as the gRPC server) to add an inbound port rule for TCP port 8500. From the server VM, start the gRPC RA-TLS container. From the container, modify `/etc/azure_tdx_config.json` to specify your [Intel Trust Authority](https://www.intel.com/content/www/us/en/security/trust-authority.html) API key: `"api_key": "your project amber api key"`.

```bash
cd ${cczoo_base_dir}/cczoo/grpc-ra-tls/azure_tdx
image_id=grpc-ra-tls:azure_tdx_latest
container_id=$(./start_container.sh ${image_id})
container_ipaddr=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' ${container_id})
docker exec -it -e container_ipaddr=${container_ipaddr} ${container_id} bash

vi /etc/azure_tdx_config.json
```

Run the C++ server OR the Python server:

For C++:
```bash
cd /grpc/v1.38.1/examples/cpp/ratls/build
pkill server
pkill python3
./server --host=${container_ipaddr}:8500 &
```

For Python:
```bash
cd /grpc/v1.38.1/examples/python/ratls/build
pkill server
pkill python3
python3 server.py --host=${container_ipaddr}:8500 &
```

3. Start example RA-TLS Enhanced gRPC client.

From an Azure DCesv5 VM designated as the client, start the gRPC RA-TLS container, specifying the server VM's public IP address (replace `x.x.x.x`). From the container, modify `/etc/azure_tdx_config.json` to specify your [Intel Trust Authority](https://www.intel.com/content/www/us/en/security/trust-authority.html) API key: `"api_key": "your project amber api key"`.

```bash
cd ${cczoo_base_dir}/cczoo/grpc-ra-tls/azure_tdx
image_id=grpc-ra-tls:azure_tdx_latest
server_public_ipaddr=x.x.x.x
container_id=$(./start_container.sh ${image_id})
docker exec -it -e server_public_ipaddr=${server_public_ipaddr} ${container_id} bash

vi /etc/azure_tdx_config.json
```

Run the C++ client OR the Python client:

For C++:
```bash
cd /grpc/v1.38.1/examples/cpp/ratls/build
./client --host=${server_public_ipaddr}:8500
```
Observe the following expected output: `Greeter received: Hello a Hello b`
    
For Python:
```bash
cd /grpc/v1.38.1/examples/python/ratls/build
python3 client.py --host=${server_public_ipaddr}:8500
```
Observe the following expected output: `Greeter received: Hello a Hello b`

### Other Cloud Deployments (TDX)

The following steps for for cloud deployments other than Azure. Please refer to `cczoo/grpc-ra-tls/tdx/README.md` for more details.

1. Build container.

First, build the base container. Refer to `cczoo/common/docker/tdx/README.md` for more details.
```
cd ${cczoo_base_dir}/cczoo/common/docker/tdx
base_image=centos:8
image_tag=tdx-dev:dcap1.15-centos8-latest
./build_docker_image.sh ${base_image} ${image_tag}
```

Then build the RA-TLS Enhanced gRPC container:
```bash
cd ${cczoo_base_dir}/cczoo/grpc-ra-tls/tdx
base_image=tdx-dev:dcap1.15-centos8-latest
image_tag=grpc-ratls-dev:tdx-dcap1.15-centos8-latest
./build_docker_image.sh ${base_image} ${image_tag}
```

2. Start the RA-TLS Enhanced gRPC container.

From the TDX guest OS:

```bash
cd ${cczoo_base_dir}/cczoo/grpc-ra-tls/tdx

# Start and enter the docker container
image_tag=grpc-ratls-dev:tdx-dcap1.15-centos8-latest
./start_container.sh ${pccs_service_ip} ${image_tag}

# Run the aesm service
/root/start_aesm_service.sh
```

3. Build and run the example gRPC server/client (C++)

```bash
cd ${GRPC_PATH}/examples/cpp/ratls
./build.sh
cd build

pkill server
pkill python3

# Run the server
./server &

# Run the client
./client
```

4. Build and run the example gRPC server/client (Python)

```bash
cd ${GRPC_PATH}/examples/python/ratls
./build.sh
cd build

pkill server
pkill python3

# Run the server
python3 -u ./server.py &

# Run the client
python3 -u ./client.py
```

## RA-TLS Enhanced gRPC for SGX (Gramine)

[Gramine](https://github.com/gramineproject/gramine) (formerly called Graphene) is a lightweight library OS, designed to run a single application with minimal host requirements. Gramine can run applications in an isolated environment with benefits comparable to running a complete OS in a virtual machine -- including guest customization, ease of porting to different OSes, and process migration.
 
### Azure (Gramine)

1. Configure Azure DCsv3 VM.

From an Azure DCsv3 VM, run the following script to install the Intel SGX DCAP dependencies and the Azure DCAP Client:
```
cd ${cczoo_base_dir}/cczoo/grpc-ra-tls/gramine
sudo ./setup_azure_vm.sh
```

Verify the Intel Architectural Enclave Service Manager is active (running):
``` 
sudo systemctl status aesmd
```

2. Build base container.

```
cd ${cczoo_base_dir}/cczoo/common/docker/gramine
./build_docker_image.azure.sh
```
NOTE: To specify the proxy server, set the `http_proxy` and `https_proxy` variables prior to the call to build_docker_image.azure.sh, for example:
      
```
http_proxy=http://proxyserver:port https_proxy=http://proxyserver:port ./build_docker_image.azure.sh
```

3. Build the RA-TLS Enhanced gRPC container. Replace `<BASE_IMAGE>` with the name:tag of the base container built from step 2, for example, `gramine-sgx-dev-azure:latest`
```
cd ${cczoo_base_dir}/cczoo/grpc-ra-tls/gramine
./build_docker_image.azure.sh <BASE_IMAGE>
```
NOTE: To specify the proxy server, set the `http_proxy` and `https_proxy` variables prior to the call to build_docker_image.azure.sh, for example:
      
```
http_proxy=http://proxyserver:port https_proxy=http://proxyserver:port ./build_docker_image.azure.sh <BASE_IMAGE>
```

4. Start the RA-TLS Enhanced gRPC container.

From the Azure DCsv3 VM, start the container. Replace `<IMAGE_ID>` with the image ID of the grpc-ratls-dev-azure container. 

```bash
cd ${cczoo_base_dir}/cczoo/grpc-ra-tls/gramine
./start_container.azure.sh <IMAGE_ID>
```

5. Build and run the example gRPC server/client (C++)

From the RA-TLS Enhanced gRPC container:
```bash
cd ${GRAMINEDIR}/CI-Examples/grpc/cpp/ratls
./build.sh
pkill loader
./run.sh server &
./run.sh client
```
Observe the following expected output: `Greeter received: Hello a Hello b`

6. Build and run the example gRPC server/client (Python)

From the RA-TLS Enhanced gRPC container:
```bash
cd ${GRAMINEDIR}/CI-Examples/grpc/python/ratls
./build.sh
pkill loader
./run.sh server &
./run.sh client
```
Observe the following expected output: `Greeter received: Hello a Hello b`

### Other Cloud Deployments (Gramine)
The following steps are for cloud deployments other than Azure. Please refer to `cczoo/grpc-ra-tls/gramine/README.md` for more details.

1. Build container.

First, build the base container:
```
cd ${cczoo_base_dir}/cczoo/common/docker/gramine
base_image=ubuntu:20.04
image_tag=gramine-sgx-dev:v1.2-ubuntu20.04-latest
./build_docker_image.sh ${base_image} ${image_tag}
```

Then build the RA-TLS Enhanced gRPC container:
```bash
cd ${cczoo_base_dir}/cczoo/grpc-ra-tls/gramine
base_image=gramine-sgx-dev:v1.2-ubuntu20.04-latest
image_tag=grpc-ratls-dev:graminev1.2-ubuntu20.04-latest
./build_docker_image.sh ${base_image} ${image_tag}
```

2. Start the RA-TLS Enhanced gRPC container, and from the container, start the AESM service.

```bash
cd ${cczoo_base_dir}/cczoo/grpc-ra-tls/gramine
image_tag=grpc-ratls-dev:graminev1.2-ubuntu20.04-latest
./start_container.sh ${pccs_service_ip} ${image_tag}

/root/start_aesm_service.sh
```

3. Build and run the example gRPC server/client (C++)

From the RA-TLS Enhanced gRPC container:
```bash
cd ${GRAMINEDIR}/CI-Examples/grpc/cpp/ratls
./build.sh
pkill loader
./run.sh server &
./run.sh client
```
Observe the following expected output: `Greeter received: Hello a Hello b`

4. Build and run the example gRPC server/client (Python)

From the RA-TLS Enhanced gRPC container:
```bash
cd ${GRAMINEDIR}/CI-Examples/grpc/python/ratls
./build.sh
pkill loader
./run.sh server &
./run.sh client
```
Observe the following expected output: `Greeter received: Hello a Hello b`

## RA-TLS Enhanced gRPC for SGX (Occlum)

[Occlum](https://github.com/occlum/occlum) is a memory-safe, multi-process library OS (LibOS) for Intel SGX. As a LibOS, it enables legacy applications to run on SGX with little or even no modifications of source code, thus protecting the confidentiality and integrity of user workloads transparently.

1. First, build the base container. Please refer to `cczoo/common/docker/occlum/README.md` for more details.
```
docker pull occlum/occlum:0.26.3-ubuntu20.04
cd ${cczoo_base_dir}/cczoo/common/docker/occlum
base_image=occlum/occlum:0.26.3-ubuntu20.04
image_tag=occlum-sgx-dev:0.26.3-ubuntu20.04-latest
./build_docker_image.sh ${base_image} ${image_tag}
```

Then build the RA-TLS Enhanced gRPC container:
```bash
cd ${cczoo_base_dir}/cczoo/grpc-ra-tls/occlum
base_image=occlum-sgx-dev:0.26.3-ubuntu20.04-latest
image_tag=grpc-ratls-dev:occlum0.26.3-ubuntu20.04-latest
./build_docker_image.sh ${base_image} ${image_tag}
```

2. Start the RA-TLS Enhanced gRPC container.
```bash
cd ${cczoo_base_dir}/cczoo/grpc-ra-tls/occlum

#start and enter the docker container
image_tag=grpc-ratls-dev:occlum0.26.3-ubuntu20.04-latest
./start_container.sh ${pccs_service_ip} ${image_tag}
```

3. Build and run the example gRPC server/client.

[LibRATS](https://github.com/inclavare-containers/librats) is optional to replace the
default RA-TLS SDK which is to generate and verify hardware quotes.

```bash
export SGX_RA_TLS_SDK=LIBRATS

cd ${OCCLUM_PATH}/demos/ra_tls

./prepare_and_build_package.sh
./build_occlum_instance.sh

cd ${OCCLUM_PATH}/demos/ra_tls

#Run the server
./run.sh server &

#Run the client
./run.sh client
```

## Information About SGX Measurements

The json template `cczoo/grpc-ra-tls/grpc/common/dynamic_config.json` is used to store the expected SGX measurement values of the remote application.
This file is loaded during the example RA-TLS Enhanced gRPC server/client initialization.

```json
{
    "verify_mr_enclave": "on",
    "verify_mr_signer": "on",
    "verify_isv_prod_id": "on",
    "verify_isv_svn": "on",
    "sgx_mrs": [
        {
            "mr_enclave": "",
            "mr_signer": "",
            "isv_prod_id": "0",
            "isv_svn": "0"
        }
    ],
}
```
The mr_enclave and mr_signer values are automatically parsed by `cczoo/grpc-ra-tls/gramine/CI-Examples/grpc/cpp/ratls/build.sh` (`get_env()` and `generate_json()`).


## How to develop the gRPC applications with RA-TLS

If you are familiar with gRPC TLS development, the only difference is using `SGX credentials` APIs to
 replace `insecure credentials` APIs.

Please refer to the examples for makefile and build script modifications.

### C++

#### Credentials Verify Options
- Two-way RA-TLS: GRPC_RA_TLS_TWO_WAY_VERIFICATION
- One-Way RA-TLS (Verify Server): GRPC_RA_TLS_SERVER_VERIFICATION
- One-Way RA-TLS (Verify Client): GRPC_RA_TLS_CLIENT_VERIFICATION

#### Server Side
Refer to `cczoo/grpc-ra-tls/grpc/v1.38.1/examples/cpp/ratls/server.cc` as an example.

```c++
std::shared_ptr<grpc::ServerCredentials> creds = nullptr;
if (sgx) {
    creds = std::move(grpc::sgx::TlsServerCredentials(args.config, GRPC_RA_TLS_TWO_WAY_VERIFICATION));
} else {
    creds = std::move(grpc::InsecureServerCredentials());
}
```

#### Client Side
Refer to `cczoo/grpc-ra-tls/grpc/v1.38.1/examples/cpp/ratls/client.cc` as an example.

```c++
std::shared_ptr<grpc::ChannelCredentials> creds = nullptr;
if (sgx) {
    creds = std::move(grpc::sgx::TlsCredentials(args.config, GRPC_RA_TLS_TWO_WAY_VERIFICATION));
} else {
    creds = std::move(grpc::InsecureChannelCredentials());
}
```

### Python

#### Credentials Verify Options
- Two-way RA-TLS: verify_option="two-way"
- One-Way RA-TLS (Verify Server): verify_option="server"
- One-Way RA-TLS (Verify Client): verify_option="client"

#### Server Side
Refer to `cczoo/grpc-ra-tls/grpc/v1.38.1/examples/python/ratls/server.py` as an example.

```python
if sgx:
    cred = grpc.sgxratls_server_credentials(config_json=args.config, verify_option="two-way")
    server.add_secure_port(args.target, cred)
else:
    server.add_insecure_port(args.target)
```

#### Client Side
Refer to `cczoo/grpc-ra-tls/grpc/v1.38.1/examples/python/ratls/client.py` as an example.

```python
if sgx:
    cred = grpc.sgxratls_channel_credentials(config_json=args.config, verify_option="two-way")
    channel = grpc.secure_channel(args.target, cred)
else:
    channel = grpc.insecure_channel(args.target)
```

---

## Cloud Deployment

### 1. Alibaba Cloud

[Aliyun ECS](https://help.aliyun.com/product/25365.html) (Elastic Compute Service) is
an IaaS (Infrastructure as a Service) level cloud computing service provided by Alibaba
Cloud. It builds security-enhanced instance families [g7t, c7t, r7t](https://help.aliyun.com/document_detail/207734.html)
based on Intel® SGX technology to provide a trusted and confidential environment
with a higher security level.

The configuration of the ECS instance as blow:

- Instance Type  : [g7t](https://help.aliyun.com/document_detail/108490.htm#section-bew-6jv-c0k).
- Instance Kernel: 4.19.91-24
- Instance OS    : Alibaba Cloud Linux 2.1903
- Instance Encrypted Memory: 32G
- Instance vCPU  : 16
- Instance SGX PCCS Server Addr: [sgx-dcap-server.cn-hangzhou.aliyuncs.com](https://help.aliyun.com/document_detail/208095.html)

***Notice***: Please replace server link in `sgx_default_qcnl.conf` included in the Dockerfile with Aliyun PCCS server address.

### 2. Tencent Cloud

Tencent Cloud Virtual Machine (CVM) provide one instance named [M6ce](https://cloud.tencent.com/document/product/213/11518#M6ce),
which supports Intel® SGX encrypted computing technology.

The configuration of the M6ce instance as blow:

- Instance Type  : [M6ce.4XLARGE128](https://cloud.tencent.com/document/product/213/11518#M6ce)
- Instance Kernel: 5.4.119-19-0009.1
- Instance OS    : TencentOS Server 3.1
- Instance Encrypted Memory: 64G
- Instance vCPU  : 16
- Instance SGX PCCS Server: [sgx-dcap-server-tc.sh.tencent.cn](https://cloud.tencent.com/document/product/213/63353)

***Notice***: Please replace server link in `sgx_default_qcnl.conf` included in the Dockerfile with Tencent PCCS server address.

### 3. ByteDance Cloud

ByteDance Cloud (Volcengine SGX Instances) provides the instance named `ebmg2t`,
which supports Intel® SGX encrypted computing technology.

The configuration of the ebmg2t instance as blow:

- Instance Type  : `ecs.ebmg2t.32xlarge`.
- Instance Kernel: kernel-5.15
- Instance OS    : ubuntu-20.04
- Instance Encrypted Memory: 256G
- Instance vCPU  : 16
- Instance SGX PCCS Server: `sgx-dcap-server.bytedance.com`.

***Notice***: Please replace server link in `sgx_default_qcnl.conf` included in the Dockerfile with ByteDance PCCS server address.

### 4. Microsoft Azure

Microsoft Azure [DCsv3-series](https://docs.microsoft.com/en-us/azure/virtual-machines/dcv3-series) instances support Intel® SGX confidential computing technology.

The following is the configuration of the DCsv3-series instance used:

- Instance Type  : Standard_DC16s_v3
- Instance Kernel: 6.2.0-1014-azure 
- Instance OS    : Ubuntu Server 20.04 LTS - Gen2
- Instance Encrypted Memory: 64G
- Instance vCPU  : 16

Microsoft Azure [DCesv5-series](https://azure.microsoft.com/en-us/updates/confidential-vms-with-intel-tdx-dcesv5-ecesv5/) instances support Intel® TDX confidential computing technology.

The following is the configuration of the DCesv5-series instance used:

- Instance Type  : Standard_DC16es_v5
- Instance Kernel: 6.2.0-1015-azure
- Instance OS    : Ubuntu 22.04 LTS Gen 2 TDX
- Instance vCPU  : 16
  
***Notice:*** Azure DCesv5-series instances were used under private preview.
