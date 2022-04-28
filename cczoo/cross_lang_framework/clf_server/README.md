# Quick Start

## Build
```bash
GRAMINEDIR=%gramine_repo_local_path% make
```

## Run
```bash
RA_TLS_ALLOW_DEBUG_ENCLAVE_INSECURE=1 \
RA_TLS_ALLOW_OUTDATED_TCB_INSECURE=1 \
./clf_server &

kill %%
```
