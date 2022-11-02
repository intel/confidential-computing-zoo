#!/bin/bash

#
# Copyright (c) 2021 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

function version_lt() { test "$(echo "$@" | tr " " "\n" | sort -rV | head -n 1)" != "$1"; }
function month()
{
local j=0
for i in Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec
    do
        let j+=1;
        if [[ $1 = $i ]];then

            return $j
            break
        else
            continue
        fi
    done
}
echo "begin to judge whether the GCC,kernel,OS satisfy requirements"
kernel_version_base="5.11.0"
gcc_version_base="7.5.0"
os_version_base="18.04"
kernel_v=$(uname -r)
kernel_version=${kernel_v%%-*}
echo $kernel_version
system_OS=$(awk -F= '/^NAME/{print $2}' /etc/os-release | sed 's/\"//g')
echo $system_OS
OS="Ubuntu"
if [ "$system_OS" != $OS ]; then
        echo "Cross_language_framework can only be used in Ubuntu"
        exit 1
fi
os_version=$(cat /etc/issue| sed '1!d' | sed -e 's/"//g' | awk '{print $2}')
if version_lt $os_version $os_version_base; then
        echo "Cross_language_framework can only be used in Ubuntu with version>=18.04"
        exit 1
fi
gcc_version=$(gcc --version |sed '1!d' | sed -e 's/"//g' | awk '{print $4}')
echo $gcc_version
if version_lt $gcc_version $gcc_version_base; then
        echo "gcc version dose not satisfy requirement, please use gcc version>=7.5.0"
        exit 1
fi
if version_lt $kernel_version $kernel_version_base; then
        echo "kernel version dose not satisfy requirement, please use kernel version>=5.11.0"
        exit 1
fi
#install SGX SDK
echo " begin to install SGX SDK Prerequisites"
apt-get update
apt-get install -y libssl-dev libcurl4-openssl-dev libprotobuf-dev
apt-get install -y build-essential python
apt-get install -y autoconf gawk bison
apt-get install -y libprotobuf-c-dev protobuf-c-compiler
apt-get install -y python3-protobuf
apt-get install -y unzip
if [[ -d "/opt/intel/sgxsdk/" ]]; then
  echo "SGX SDK has been installed"
elif [[   $os_version == *"20.04"* ]]; then
  echo "begin to download SGX SDK"
  sgx_sdk_url=https://download.01.org/intel-sgx/latest/dcap-latest/linux/distro/ubuntu20.04-server/
  res=`wget https://download.01.orwget -qO - ${sgx_sdk_url} | grep sdk|cut -d\" -f2|while read x; do wget ${sgx_sdk_url}${x}; break; done 2>&1`
  if [[ res == *"error"* ]]; then
  echo "there may be some error,you can download SGX SDK by yourself"
  exit 1
  fi
  echo 'deb [arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu focal main' | sudo tee /etc/apt/sources.list.d/intel-sgx.list
  wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | sudo apt-key add -
  echo "SGX SDK has been downloaded"
elif [[  $os_version == *"18.04"* ]]; then
  echo "begin to download SGX SDK"
  sgx_sdk_url=https://download.01.org/intel-sgx/latest/dcap-latest/linux/distro/ubuntu18.04-server/
  res=`wget https://download.01.orwget -qO - ${sgx_sdk_url} | grep sdk|cut -d\" -f2|while read x; do wget ${sgx_sdk_url}${x}; break; done 2>&1`
  if [[ res == *"error"* ]]; then
  echo "there may be some error,you can download SGX SDK by yourself"
  exit 1
  fi
  echo 'deb [arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu bionic main' | sudo tee /etc/apt/sources.list.d/intel-sgx.list
  wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | sudo apt-key add -
  echo "SGX SDK has been downloaded"
else
  echo " No suitable SGX SDK version for this Ubuntu version"
  exit 1
fi
echo "begin to install SGX SDK"
chmod +x *sdk*.bin
./*sdk*.bin << EOF
no
/opt/intel/
EOF
source /opt/intel/sgxsdk/environment
echo " SGX SDK has been installed "
# install SGX PSW
echo "begin to download SGX PSW"
sudo apt-get update
sudo apt-get install -y libsgx-urts libsgx-dcap-ql libsgx-dcap-default-qpl
sudo apt-get install -y libsgx-dcap-ql-dev libsgx-quote-ex-dev libsgx-dcap-quote-verify-dev
#verify whether SGX SDK and PSW has been installed successfully
cd /opt/intel/sgxsdk/SampleCode/SampleEnclave
sudo make
res=`echo '\n'|sudo ./app 2>&1`
if [[ $res == *"successfully"* ]]; then
echo "SGX SDK and PSW has been successfully installed"
else
echo "there may be some error with SGX SDK or PSW"
exit 1
fi
cd
# install SGX PCCS
curl -sL https://deb.nodesource.com/setup_14.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo apt-get install -y libcrack2    
echo "begin to download SGX PCCS,you may need to give some input"            
sudo apt-get install sgx-dcap-pccs 
echo "you may need to configure PCCS by yourself,  go to /etc/sgx_default_qcnl.conf and revise the pccs_url. If you build PCCS by yourself and use self-signed certs, you also need to set USE_SECURE_CERT=FALSE"
# test SGX DCAP function
git clone https://github.com/intel/SGXDataCenterAttestationPrimitives
cd  SGXDataCenterAttestationPrimitives/SampleCode/QuoteGenerationSample/
sudo make 
quote_generate_result=`sudo ./app 2>&1`
if [[ $quote_generate_result == *"Step1: Call sgx_qe_get_target_info:[get_platform_quote_cert_data ../qe_logic.cpp:378] Error returned from the p_sgx_get_quote_config API. 0xe019"* ]]; then
  echo "there may be something wrong with PCCS"
  aesm_date=`sudo systemctl status  aesmd.service|grep qeid|tail -1|grep -Eo "[a-zA-Z]+ [0-9]+ [0-9]+\:[0-9]+\:[0-9]+\:* "`   
  last_sgxconf_modified_timestamp=`stat -c %Y /etc/sgx_default_qcnl.conf`
  aesm_month=`echo $aesm_date|sed -e 's/"//g' | awk '{print $1}'`
  aesm_day=`echo $aesm_date|sed -e 's/"//g' | awk '{print $2}'`
  aesm_hour=`echo $aesm_date|sed -e 's/"//g' | awk '{print $3}'`
  month $aesm_month
  aesm_month_num=`month $aesm_month| echo $?`
  aesm_year=`date +"%Y"`
  aesm_time="$aesm_year-$aesm_month_num-$aesm_day $aesm_hour"
  aesm_timestamp=`date -d "$aesm_time" +%s`
  echo $aesm_timestamp
  echo $last_sgxconf_modified_timestamp
  if [[ $aesm_timestamp < $last_sgxconf_modified_timestamp ]]; then
     echo "PCCS configuration hae been updated, please restart aesm service"
     exit 1
  fi
elif [[  $quote_generate_result == *"rror"* ]]; then
  echo "there may be something wrong with SGX DCAP"
  exit 1
else
  continue
fi
rm -rf SGXDataCenterAttestationPrimitives/
#install gramine
echo "begin to install Gramine "
sudo apt-get install -y build-essential \
    autoconf bison gawk nasm ninja-build python3 python3-click \
    python3-jinja2 wget
sudo python3 -m pip install 'meson>=0.55' 'toml>=0.10'
sudo apt-get install -y libunwind8 musl-tools python3-pyelftools \
    python3-pytest
sudo apt-get install -y libcurl4-openssl-dev libprotobuf-c-dev \
    protobuf-c-compiler python3-cryptography python3-pip python3-protobuf    
git clone https://github.com/gramineproject/gramine.git
cd gramine
git checkout 74e74a87a1127124cf89bd487a021dc1ceb8fa75
meson setup build/ --buildtype=release -Ddirect=enabled -Dsgx=enabled  -Ddcap=enabled
ninja -C build/ 
sudo ninja -C build/ install
value1=`gramine-sgx-gen-private-key 2>&1`
if [[ $value1 == *"command not found"* ]]; then
  echo "there is some error with gramine installation"
  exit 1
fi
# install  Cross_language_framework
echo "begin to install cross_lang_framework"
sudo apt-get install -y openjdk-11-jdk-headless libatk-wrapper-java libmbedtls-dev
cd 
git clone https://github.com/intel/confidential-computing-zoo.git
cd confidential-computing-zoo/cczoo/cross_lang_framework/clf_server 
res1=`GRAMINEDIR=/home/ubuntu/gramine make 2>&1`
if [[ res1 == *"error"* ]]; then
	echo "there may be some error, you can make clean and then make for detailed information"
	exit 1
fi 
cd ../clf_client/java
res2=`GRAMINEDIR=/home/ubuntu/gramine make 2>&1`
if [[ res2 == *"error"* ]]; then
	echo "there may be some error, you can make clean and then make for detailed information"
	exit 1
fi 
cd ../app 
res3=`GRAMINEDIR=/home/ubuntu/gramine SGX_SIGNER_KEY=/home/ubuntu/.config/gramine/enclave-key.pem make SGX=1 2>&1`
if [[ res2 == *"error"* ]]; then
	echo "there may be some error, you can make clean and then make for detailed information"
	exit 1
fi
