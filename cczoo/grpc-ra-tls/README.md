# gRPC RA-TLS

This solution presents an enhanced [gRPC](https://grpc.io/) (Remote Procedure Call) framework to 
guarantee security during transmission and runtime via two-way 
[RA-TLS](https://arxiv.org/pdf/1801.05863) 
(Intel SGX Remote Attestation with Transport Layer Security) based on 
[TEE](https://en.wikipedia.org/wiki/Trusted_execution_environment) (Trusted Execution Environment).


## Introduction

[gRPC](https://grpc.io/) is a modern, open source, high-performance remote procedure call (RPC) 
framework that can run anywhere. It enables client and server applications to communicate 
transparently, and simplifies the building of connected systems. For securing gRPC connections, the 
SSL/TLS authentication mechanisms is built-in to gRPC.

Transport Layer Security ([TLS](https://en.wikipedia.org/wiki/Transport_Layer_Security)) The 
successor of the now-deprecated Secure Sockets Layer (SSL), is a cryptographic protocol designed to 
provide communications security over a computer network. The current version is 
[TLS 1.3](https://datatracker.ietf.org/doc/html/rfc8446) defined in August 2018. During the TLS 
handshake procedure, the public key certificates are used for key exchange. The public key 
certificate is [X.509](https://en.wikipedia.org/wiki/X.509) format. It is either signed by a 
certificate authority (CA) or is self-signed for binding an identity to a public key. 

RA-TLS integrates Intel SGX remote attestation with the establishment of a standard TLS (v1.3) 
connection. Remote attestation is performed during the connection setup by embedding the attestation 
evidence into the endpoints TLS public key certificate.

In the gRPC TLS handshake phase, the certificates is generated and verified as 
following.

| Generate X.509 certificate | Verify X.509 certificate |
| ------------ | ------------ |
| 1. Generate the RSA key pair <br> 2. Generate the X.509 certificate with the RSA key pair <br> 3. Embed the hash of RSA public key into SGX quote report signed by the [attestation key](https://download.01.org/intel-sgx/dcap-1.0.1/docs/Intel_SGX_ECDSA_QuoteGenReference_DCAP_API_Linux_1.0.1.pdf) <br> 4. Embed the quote report into X.509 as a v3 extension <br> 5. Self-sign the X.509 certificate | 1. Verify the X.509 certificate by the default gRPC TLS procedure <br> 2. Parse the quote report from the X.509 extension <br> 3. Verify the quote report by the Intel DCAP interface <br> 4. Compare the hash of X.509 certificate with the hash embedded in the quote reprot <br> 5. Compare the enclave's identity embedded in the quote report against the expected identity |

This solution supports the two-way RA-TLS verification between gRPC server and client. It means 
client and server both need to generate the certificates and verify each other.


## Trust execution environment
Intel SGX technology offers hardware-based memory encryption that isolates specific application code
 and data in memory. This solution provides the different gRPC framework running on different LibOS 
 (Gramine or Occlum).  

 - [Gramine](https://github.com/gramineproject/gramine) (formerly called Graphene) is a lightweight 
 library OS Based on Intel SGX technology, designed to run a single application with minimal host 
 requirements. 

 - [Occlum](https://github.com/occlum/occlum) (In progress)


## Build and installation

Currently, we only support building and installation from the source code. It will generate a docker 
images for developing the gRPC RA-TLS application.

1. Build TEE docker image

   - On Gramine

        Refer to cczoo/common/docker/gramine/README.md

        ```bash
        cd cczoo/common/docker/gramine/
        ./build_docker_image.sh
        ```

   - On Occlum

        Occlum provides the docker image in docker registry, no need to build it by self.

        ```bash
        docker pull occlum/occlum:0.26.3-ubuntu18.04
        ```

2. Build gRPC RA-TLS docker image based on TEE docker image

   - On Gramine

        ```bash
        cd cczoo/grpc-ra-tls/docker/gramine/
        ./build_docker_image.sh
        ```


## Config the remote attestation

For saving the expected measurement values of remote application enclave, we create a json template 
as following. It is loaded in gRPC server or client initialization.

Refer to `cczoo/grpc-ra-tls/docker/grpc/common/dynamic_config.json`

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
In Gramine examples, the mr_enclave and mr_signer are automatically parsed in `build.sh`.

Refer to `cczoo/grpc-ra-tls/docker/gramine/gramine/CI-Examples/grpc/cpp/ratls/build.sh`

```bash
function get_env() {
    gramine-sgx-get-token -s grpc.sig -o /dev/null | grep $1 | awk -F ":" '{print $2}' | xargs
}

function generate_json() {
    cd ${RUNTIME_TMP_PATH}/$1
    jq ' .sgx_mrs[0].mr_enclave = ''"'`get_env mr_enclave`'" | .sgx_mrs[0].mr_signer = ''"'`get_env 
    mr_signer`'" ' ${GRPC_PATH}/dynamic_config.json > ${RUNTIME_TMP_PATH}/$2/dynamic_config.json
    cd -
}
```

For isv_prod_id and isv_svn value, please refer to the values defined in libOS configuration files. 
In Gramine, it is defined in the template file.


## Run examples

- Gramine

   Refer to `cczoo/grpc-ra-tls/docker/gramine/README.md`

   Prepare the docker container

   ```bash
   cd cczoo/grpc-ra-tls/docker
   
   #start and enter the docker container
   ./start_container.sh ${pccs_service_ip}
   
   #Run the aesm service
   /root/start_aesm_service.sh
   ```

   Run the cpp example

   ```bash
   cd /gramine/CI-Examples/grpc/cpp/ratls
   ./build.sh

   #Run the server
   cd runtime/server
   gramine-sgx grpc -host=localhost:50051 -config=dynamic_config.json &

   #Run the client
   cd runtime/client
   gramine-sgx grpc -host=localhost:50051 -config=dynamic_config.json
   ```

   Run the python example

   ```bash
   cd /gramine/CI-Examples/grpc/python/ratls
   ./build.sh

   #Run the server
   gramine-sgx python -u server.py -host localhost:50051 -config dynamic_config.json &

   #Run the client
   gramine-sgx python -u client.py -host localhost:50051 -config dynamic_config.json
   ```

## How to develop the gRPC applications with RA-TLS

If you are familiar with gRPC TLS development, the only deference is using `SGX credentials` APIs to
 replace `insecure credentials` APIs.

Please refer to the examples for makefile and build script modifications.

- c++

    Server side:

    Refer to `cczoo/grpc-ra-tls/docker/grpc/v1.38.1/examples/cpp/ratls/server.cc`

    ```c++
    std::shared_ptr<grpc::ServerCredentials> creds = nullptr;
    if (sgx) {
        creds = std::move(grpc::sgx::TlsServerCredentials("dynamic_config.json"));
    } else {
        creds = std::move(grpc::InsecureServerCredentials());
    }
    ```

    Client side:

    Refer to `cczoo/grpc-ra-tls/docker/grpc/v1.38.1/examples/cpp/ratls/client.cc`

    ```c++
    std::shared_ptr<grpc::ChannelCredentials> creds = nullptr;
    if (sgx) {
        creds = std::move(grpc::sgx::TlsCredentials("dynamic_config.json"));
    } else {
        creds = std::move(grpc::InsecureChannelCredentials());
    }
    ```

- python

    Server side:

    Refer to `cczoo/grpc-ra-tls/docker/grpc/v1.38.1/examples/python/ratls/server.py`

    ```python
    if sgx:
        cred = grpc.sgxratls_server_credentials(config_json=args.config)
        server.add_secure_port(args.target, cred)
    else:
        server.add_insecure_port(args.target)
    ```

    Client side:

    Refer to `cczoo/grpc-ra-tls/docker/grpc/v1.38.1/examples/python/ratls/client.py`

    ```python
    if sgx:
        cred = grpc.sgxratls_channel_credentials(config_json=args.config)
        channel = grpc.secure_channel(args.target, cred)
    else:
        channel = grpc.insecure_channel(args.target)
    ```
