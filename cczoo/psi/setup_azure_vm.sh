#!/usr/bin/bash
#
# Copyright (c) 2022 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# exit when any command fails
set -e

# Install general dependencies
sudo apt-get install -y libcurl4-openssl-dev libssl-dev pkg-config
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
