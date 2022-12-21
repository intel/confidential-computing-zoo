# Private Set Intersection (PSI) with Intel SGX

## Introduction
Private Set Intersection (PSI) is an application hotspot of multi-party secure computing. Its purpose is to calculate the intersection between the two parties through a secure scheme without exposing other information beyond the intersection.

There are many implementations of PSI, some of which are based on cryptographic algorithms, such as the RSA algorithm. However, the methods based on cryptography usually have problems such as slow intersection speed, complicated algorithm leads to high memory usage, and do not support multi-party intersection.

In this Private Set Intersection solution, we adopted a privacy protection computing solution based on Intel SGX technology.

### Encrypted runtime environment
Intel SGX technology offers hardware-based memory encryption that isolates specific application code and data in memory, and it allows user-level code to allocate private regions of memory, called enclaves, which are designed to be protected from processes running at higher privilege levels.

Intel SGX also helps protect against SW attacks even if OS/drivers/BIOS/VMM/SMM are compromised and helps increase protections for secrets even when attacker has full control of platform.

### Encrypted transmission and remote attestation
In the communication part of Private Set Intersection solution, we use Intel SGX Remote Attestation with Transport Layer Security (RA-TLS) technology to perform encrypted transmission and verification of program integrity. RA-TLS integrates Intel SGX remote attestation with the establishment of a standard Transport Layer Security (TLS) connection. Remote attestation is performed during the connection setup by embedding the attestation evidence into the endpoints TLS certificate.

## Privacy protection
This solution mainly contains the items listed below: 
-	Security Isolation LibOS – Gramine, an open-source project for Intel SGX, can run applications with no modification in Intel SGX. 
-	Platform Integrity - Providing Remote Attestation mechanism, so that user can gain trust in the remote Intel SGX platform.

In this solution, privacy protection is provided in the following aspects:
### Runtime security using Intel-SGX
During the intersection process, the data of each participant is stored inside the Intel SGX enclave. Intel SGX provides some assurance that no unauthorized access or memory snooping of the enclave occurs to prevent any leakage of data information.
### In-Transit security
We use the Remote Attestation with Transport Layer Security (RA-TLS) of Intel SGX technology to ensure security during transmission. This technology is proposed by Intel's security team, which combines TLS technology and remote attestation technology. RA-TLS uses TEE as the hardware root of trust. The certificate and private key are generated in the enclave and are not stored on the disk. Therefore, it is impossible for the participants to obtain the certificate and private key in plain text, so man-in-the-middle attacks cannot be carried out. In this Private Set Intersection solution, RA-TLS is used to ensure the encrypted transmission of participant's data.
### Application integrity
To solve the problem of how to verify the untrusted application integrity, we use RA-TLS to verify the Intel SGX enclave. It ensures that the runtime application is a trusted version.


## Workflow
Our solution is implemented in a trusted execution environment, and its architecture is as follows:

<div align=center>
<img src=../../documents/readthedoc/docs/source/Solutions/psi/images/psi.svg>
</div>

The computing phase can be divided into the following steps:

&emsp;&ensp;**1.** All participants run in the TEE environment. Each client completes two-way authentication with the server through RA-TLS.

&emsp;&ensp;**2.** Clients transmit data securely and upload it to the server.

&emsp;&ensp;**3.** The server side waits for the data upload of all clients to complete, and then calculates the intersection of the data.

&emsp;&ensp;**4.** The server side sends the calculation results back to each participant through secure transmission.

In the above process, the client can only obtain the intersection data, but not the non-intersection data belonging to other clients. The server side is only responsible for computing and will not save or steal the data sent by clients.

## Build and installation

Currently, we only support building and installation from the source code. It will generate a docker 
images for developing the gRPC RA-TLS application.

### Prerequisites

- Ubuntu 20.04. This solution should work on other Linux distributions as well,
  but for simplicity we provide the steps for Ubuntu 20.04 only.

- Docker Engine. Docker Engine is an open-source containerization technology for
  building and containerizing your applications.
  Please follow [this guide](https://docs.docker.com/engine/install/ubuntu/#install-using-the-convenience-script)
  to install Docker engine.

- CCZoo Private Set Intersection source package:

    ```shell
    git clone https://github.com/intel/confidential-computing-zoo.git
    ```

- Intel SGX Driver and SDK/PSW. You need a machine that supports Intel SGX and FLC/DCAP. Please follow this guide to install the Intel SGX driver and SDK/PSW on the machine/VM. Make sure to install the driver with ECDSA/DCAP attestation.

  For deployments on Microsoft Azure, a script is provided to install general dependencies, Intel SGX DCAP dependencies, and the Azure DCAP Client. To run this script:

    ```shell
   cd cczoo/psi
   ./setup_azure_vm.sh
    ```
  After Intel SGX DCAP is setup, verify the Intel Architectural Enclave Service Manager is active (running):

    ```shell
    systemctl status aesmd
    ```

### Solution Ingredients
This solution uses the following ingredients, which are installed as part of the container build process.
- [Gramine](https://gramine.readthedocs.io)

### Setup docker images
For Ubuntu:

- For deployments on Microsoft Azure:
    ```bash
    cd cczoo/psi/gramine
    AZURE=1 ./build_docker_image.sh ubuntu:20.04
    ```
- For other cloud deployments:
    ```bash
    cd cczoo/psi/gramine
    ./build_docker_image.sh ubuntu:20.04
    ```

For Anolis OS:

- For deployments on Microsoft Azure: Currently not supported.

- For other cloud deployments:
    ```bash
    cd cczoo/common/docker/gramine
    ./build_docker_image.sh anolisos
    cd -
    cd cczoo/psi/gramine
    ./build_docker_image.sh anolisos
    ```

## Run PSI examples

This solution uses a two-way attestation scheme. The client and server on both sides of the communication authenticate each other.

This example only shows an example of deploying PSI locally. If you want to deploy the participants on different machines, please make sure that the correct measurements are filled in the `dynamic_config.json` file to ensure that the remote verification passes.

### Prepare the docker container
Start four containers (one server, three clients).
```bash
cd cczoo/psi
```

- For deployments on Microsoft Azure:

  In terminal 1, start the server container:
  ```bash
  ./start_container.sh server
  ```

  In terminal 2, start the client1 container:
  ```bash
  ./start_container.sh client1
  ```

  In terminal 3, start the client2 container:
  ```bash
  ./start_container.sh client2
  ```

  In terminal 4, start the client3 container:
  ```bash
  ./start_container.sh client3
  ```

- For other cloud deployments:

  In terminal 1, start the server container:
  ```bash
  ./start_container.sh server <pccs_service_ip>
  ```

  In terminal 2, start the client1 container:
  ```bash
  ./start_container.sh client1 <pccs_service_ip>
  ```

  In terminal 3, start the client2 container:
  ```bash
  ./start_container.sh client2 <pccs_service_ip>
  ```

  In terminal 4, start the client3 container:
  ```bash
  ./start_container.sh client3 <pccs_service_ip>
  ```

### Run the Python example

For each container (server, client1, client2, client3), build the Python example and note the mr_enclave value from the build output.

```bash
cd /gramine/CI-Examples/psi/python
./build.sh
```
Example mr_enclave value from each container.

server:
```bash
mr_enclave:  7d61ddedb4b8d3743f61ad255bae0ab56d3e3ad2547ef921476b25ac3ccad5ad
```

client1:
```bash
mr_enclave:  d65c397169a981d6a6a49c658235e5ac2b3f86944f957d942d406c79049e135a
```

client2:
```bash
mr_enclave:  39d2753b9c9a3da298edb685e5a436f921227956454a54b3f73881db350486e6
```

client3:
```bash
mr_enclave:  7762afd0bb1adf5374bf9737f6d7b102ae585f04b675bca64125761bb050787b
```
Modify /gramine/CI-Examples/psi/python/dynamic_config.json in each container as described below. Do not copy and paste the following example values. Use the actual mr_enclave values from your containers.

From the server container, modify /gramine/CI-Examples/psi/python/dynamic_config.json to include sgx_mrs entries containing the mr_enclave value for each client. For example:
```bash
{
  "verify_mr_enclave": "on",
  "verify_mr_signer": "on",
  "verify_isv_prod_id": "on",
  "verify_isv_svn": "on",
  "sgx_mrs": [
    {
      "mr_enclave": "d65c397169a981d6a6a49c658235e5ac2b3f86944f957d942d406c79049e135a",
      "mr_signer": "037ac2be3243ac7cd66dc39b0403056a54160f61f2d998d90327455e745e31f3",
      "isv_prod_id": "0",
      "isv_svn": "0"
    },
    {
      "mr_enclave": "39d2753b9c9a3da298edb685e5a436f921227956454a54b3f73881db350486e6",
      "mr_signer": "037ac2be3243ac7cd66dc39b0403056a54160f61f2d998d90327455e745e31f3",
      "isv_prod_id": "0",
      "isv_svn": "0"
    },
    {
      "mr_enclave": "7762afd0bb1adf5374bf9737f6d7b102ae585f04b675bca64125761bb050787b",
      "mr_signer": "037ac2be3243ac7cd66dc39b0403056a54160f61f2d998d90327455e745e31f3",
      "isv_prod_id": "0",
      "isv_svn": "0"
    }
  ]
}
```

From the client1, client2, client3 containers, modify /gramine/CI-Examples/psi/python/dynamic_config.json to include a sgx_mrs entry containing the mr_enclave value for the server. For example:
```bash
{
  "verify_mr_enclave": "on",
  "verify_mr_signer": "on",
  "verify_isv_prod_id": "on",
  "verify_isv_svn": "on",
  "sgx_mrs": [
    {
      "mr_enclave": "7d61ddedb4b8d3743f61ad255bae0ab56d3e3ad2547ef921476b25ac3ccad5ad",
      "mr_signer": "037ac2be3243ac7cd66dc39b0403056a54160f61f2d998d90327455e745e31f3",
      "isv_prod_id": "0",
      "isv_svn": "0"
    }
  ]
}
```

For each container (server, client1, client2, client3), run the specified script as described below.

- Two-party:

server:
```bash
gramine-sgx python -u server.py -host localhost:50051 -config dynamic_config.json
```

client1:
```bash
gramine-sgx python -u data_provider1.py -host localhost:50051 -config dynamic_config.json -is_chief True -data_dir "data1.txt" -client_num 2
```

client2:
```bash
gramine-sgx python -u data_provider2.py -host localhost:50051 -config dynamic_config.json -is_chief False -data_dir "data2.txt" -client_num 2
```

Each client will return the following intersection result:
```shell
['car', 'cat', 'train']
```

In the server container, use Ctrl-C to stop the server process.

- Three-party:

server:
```bash
gramine-sgx python -u server.py -host localhost:50051 -config dynamic_config.json
```

client1:
```bash
gramine-sgx python -u data_provider1.py -host localhost:50051 -config dynamic_config.json -is_chief True -data_dir "data1.txt" -client_num 3
```

client2:
```bash
gramine-sgx python -u data_provider2.py -host localhost:50051 -config dynamic_config.json -is_chief False -data_dir "data2.txt" -client_num 3
```

client3:
```bash
gramine-sgx python -u data_provider3.py -host localhost:50051 -config dynamic_config.json -is_chief False -data_dir "data3.txt" -client_num 3
```

Each client will return the following intersection result:
```shell
['train', 'car', 'cat']
```

In the server container, use Ctrl-C to stop the server process.

### Run the C++ example

Before performing the steps below, the Python example must be built first (as described in the previous section).

For each container (server, client1, client2, client3), build the C++ example.

```bash
cd /gramine/CI-Examples/psi/cpp
./build.sh
```

For each container (server, client1, client2, client3), run the specified script as described below.

- Two-party:

server:
```bash
cd /gramine/CI-Examples/psi/cpp/runtime/server
gramine-sgx grpc -host=localhost:50051 -config=dynamic_config.json
```

client1:
```bash
cd /gramine/CI-Examples/psi/cpp/runtime/data_provider1
gramine-sgx grpc -host=localhost:50051 -config=dynamic_config.json -is_chief=true -client_num=2 data_dir="data1.txt" client_name="data_provider1"
```

client2:
```bash
cd /gramine/CI-Examples/psi/cpp/runtime/data_provider2
gramine-sgx grpc -host=localhost:50051 -config=dynamic_config.json -is_chief=false -client_num=2 data_dir="data2.txt" client_name="data_provider2"
```

Each client will return the following intersection result:
```shell
car
cat
train
```

In the server container, use Ctrl-C to stop the server process.

- Three-party:

server:
```bash
cd /gramine/CI-Examples/psi/cpp/runtime/server
gramine-sgx grpc -host=localhost:50051 -config=dynamic_config.json
```

client1:
```bash
cd /gramine/CI-Examples/psi/cpp/runtime/data_provider1
gramine-sgx grpc -host=localhost:50051 -config=dynamic_config.json -is_chief=true -client_num=3 data_dir="data1.txt" client_name="data_provider1"
```

client2:
```bash
cd /gramine/CI-Examples/psi/cpp/runtime/data_provider2
gramine-sgx grpc -host=localhost:50051 -config=dynamic_config.json -is_chief=false -client_num=3 data_dir="data2.txt" client_name="data_provider2"
```

client3:
```bash
cd /gramine/CI-Examples/psi/cpp/runtime/data_provider3
gramine-sgx grpc -host=localhost:50051 -config=dynamic_config.json -is_chief=false -client_num=3 data_dir="data3.txt" client_name="data_provider3"
```

Each client will return the following intersection result:
```shell
car
cat
train
```

In the server container, use Ctrl-C to stop the server process.
