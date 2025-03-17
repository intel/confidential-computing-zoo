# Dependencies
1. SGX DCAP packages
2. local or remote workable PCCS

# How to build
cd restful_tdx_att_service
./build.sh

# Run TDX attestation service
./attest_service
 
It will start the service and wait for connection: "Starting TDX Attestation Service on port 8443..."
 
