# gRPC

This directory contains the Makefile and the template manifest for the most
recent version of gRPC (as of this writing, version 3.18.1). This was tested
on a machine with SGX v2 and Ubuntu 18.04.

The Makefile and the template manifest contain extensive comments and are made
self-explanatory. Please review them to gain understanding of Gramine-SGX
and requirements for applications running under Gramine-SGX.

# Quick Start

1. Build example

    ```
    ./build.sh
    ```

    It will generate "dynamic_config.json" include enclave infos (sgx_mrs) of remote party.

    Whether to check "sgx_mrs" by setting to "on" or "off" on parameters ("verify_mr_enclave" "verify_mr_signer" "verify_isv_prod_id" "verify_isv_svn").

    ```
    {
        "verify_mr_enclave": "on",
        "verify_mr_signer": "on",
        "verify_isv_prod_id": "on",
        "verify_isv_svn": "on",
        "sgx_mrs": [
            {
            "mr_enclave": "f416c988c27c3b3dcdd0d99a61d8797a08c6026fab08bda47f992e0d9c0de641",
            "mr_signer": "126fa00be457bf85a8d864c44bc8f025d35eb7e870868e79ee147145fcacb92a",
            "isv_prod_id": "0",
            "isv_svn": "0"
            }
        ],
    }
    ```

2. Run gRPC RA-TLS server

    ```
    ./run.sh server &
    ```

3. Run gRPC RA-TLS client

    ```
    ./run.sh client
    ```
