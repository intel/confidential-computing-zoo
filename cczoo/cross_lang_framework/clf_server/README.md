# Quick Start

## Build
```bash
GRAMINEDIR=%gramine_repo_local_path% make
```

## Run
```bash
RA_TLS_ALLOW_DEBUG_ENCLAVE_INSECURE=1 \
RA_TLS_ALLOW_OUTDATED_TCB_INSECURE=1 \
./clf_server -S -E -d -v  -s -p -c -k
& 

kill %%
```
-S means the value of MRSigner,
-E means the value of MREnclave,
-d means the value of isv_prod_id,
-v means the value of isv_svn,
-s means the key used to encrypt data,
-p means the port used in data/key transmission,
-c means the path of secret cert,
-k means the path of private key.

- If no parameter is given, the application will read the file "clf_server.conf" below this directory to get all these value.

- If users want to define these parameters values by themselves, they can use command like this
```bash
RA_TLS_ALLOW_DEBUG_ENCLAVE_INSECURE=1 RA_TLS_ALLOW_OUTDATED_TCB_INSECURE=1 ./clf_server 
-S0a85b393078ee06dafc58d6692a7a59bee27fdce2b70ae45730b501af6ae290a -d0 -v0 
-s58a7129dc07ba462ca8317d578a3d7cb -p4433 -ccerts/server_signed_cert.crt -kcerts/server_private_key.pem

# <server_signed_cert.crt> and <server_private_key.pem> can be created by ~/confidential-computing-zoo/cczoo/cross_lang_framework/tools/gen_cert.sh
```