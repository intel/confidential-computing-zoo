# Cross languages framework based on Gramine

This framework aims to ease different programming languages to use Gramine
based sgx functionality. Currently it only supports Java.

## Build and installation

- Clone Gramine repo to local
```bash
git clone https://github.com/gramineproject/gramine.git
```
- Clone this repo to local
```bash
git clone https://github.com/intel/confidential-computing-zoo.git
```
- Build cross languages framework server part
  Switch to the path of clf_server and type make
```bash
GRAMINEDIR=%gramine_repo_local_path% make
```
e.g.
```bash
cd ~/confidential-computing-zoo/cczoo/cross_lang_framework/clf_server
GRAMINEDIR=/home/ubuntu/gramine make
```
- Build JNI C language library and Jave package
  Switch to Java JNI folder and type make
```bash
GRAMINEDIR=%gramine_repo_local_path% make
```
e.g.
```bash
cd ~/confidential-computing-zoo/cczoo/cross_lang_framework/clf_client/java
GRAMINEDIR=/home/ubuntu/gramine make
```
- Build sample app
  Switch to sample app folder and make
```bash
GRAMINEDIR=%gramine_repo_local_path% SGX_SIGNER_KEY=%sgx_signer_key_path% make SGX=1
```
e.g.
```bash
cd ~/confidential-computing-zoo/cczoo/cross_lang_framework/clf_client/app
GRAMINEDIR=/home/ubuntu/gramine SGX_SIGNER_KEY=/home/ubuntu/gramine/Pal/src/host/Linux-SGX/signer/enclave-key.pem make SGX=1
```

## Run the framework and sample code
- Launch the server
```bash
cd ~/confidential-computing-zoo/cczoo/cross_lang_framework/clf_server

RA_TLS_ALLOW_DEBUG_ENCLAVE_INSECURE=1 \
RA_TLS_ALLOW_OUTDATED_TCB_INSECURE=1 \
./clf_server &
```
- Launch the sample app (client)
```bash
cd ~/confidential-computing-zoo/cczoo/cross_lang_framework/clf_client/app
gramine-sgx java -Xmx8G clf_test
```

