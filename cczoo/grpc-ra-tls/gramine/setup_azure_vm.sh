#!/usr/bin/bash

# exit when any command fails
set -e

# Install Intel SGX DCAP dependencies
echo "deb [trusted=yes arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu jammy main" | sudo tee /etc/apt/sources.list.d/intel-sgx.list
wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | sudo apt-key add -
sudo apt-get update
sudo apt-get install -y sgx-aesm-service libsgx-dcap-ql-dev libsgx-dcap-quote-verify-dev

# Install Azure DCAP Client 1.12.1 release
wget -q http://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2_amd64.deb
sudo dpkg -i libssl1.1_1.1.1f-1ubuntu2_amd64.deb
sudo rm libssl1.1_1.1.1f-1ubuntu2_amd64.deb
wget -q https://github.com/microsoft/Azure-DCAP-Client/releases/download/1.12.1/az-dcap-client_1.12.1_amd64.deb
sudo dpkg -i az-dcap-client_1.12.1_amd64.deb
sudo rm az-dcap-client_1.12.1_amd64.deb
sudo cp /usr/lib/libdcap_quoteprov.so /usr/lib/x86_64-linux-gnu/
