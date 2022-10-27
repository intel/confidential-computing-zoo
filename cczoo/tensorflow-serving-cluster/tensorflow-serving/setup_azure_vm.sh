#!/usr/bin/bash

# exit when any command fails
set -e

# Install general dependencies
sudo apt-get install -y python3-pip libcurl4-openssl-dev libssl-dev pkg-config
sudo add-apt-repository ppa:team-xbmc/ppa -y
sudo apt-get update
sudo apt-get install nlohmann-json3-dev

# Install Intel SGX DCAP dependencies
echo "deb [trusted=yes arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu focal main" | sudo tee /etc/apt/sources.list.d/intel-sgx.list
wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | sudo apt-key add -
sudo apt-get update
sudo apt-get install -y sgx-aesm-service libsgx-dcap-ql-dev libsgx-dcap-quote-verify-dev

# Build and install Azure DCAP Client 1.10.0 release
cd ~
git clone https://github.com/microsoft/Azure-DCAP-Client; cd Azure-DCAP-Client/
git checkout 1.10.0; git submodule update --recursive --init
cd src/Linux/; ./configure; make DEBUG=1
sudo make install
sudo cp libdcap_quoteprov.so /usr/lib/x86_64-linux-gnu/
