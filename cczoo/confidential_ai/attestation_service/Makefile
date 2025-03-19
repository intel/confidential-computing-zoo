#
# Copyright (C) 2011-2021 Intel Corporation. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#   * Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright
#     notice, this list of conditions and the following disclaimer in
#     the documentation and/or other materials provided with the
#     distribution.
#   * Neither the name of Intel Corporation nor the names of its
#     contributors may be used to endorse or promote products derived
#     from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
#

######## SGX SDK Settings ########

SGX_SDK ?= /opt/intel/sgxsdk
SGX_ARCH ?= x64
SGX_DEBUG ?= 0
SGX_QPL_LOGGING ?= 1
QVL_ONLY ?= 0


# Don't support 32bit in this sample 

SGX_COMMON_FLAGS := -m64
SGX_LIBRARY_PATH := $(SGX_SDK)/lib64
SGX_ENCLAVE_SIGNER := $(SGX_SDK)/bin/x64/sgx_sign
SGX_EDGER8R := $(SGX_SDK)/bin/x64/sgx_edger8r

ifeq ($(SGX_DEBUG), 1)
ifeq ($(SGX_PRERELEASE), 1)
$(error Cannot set SGX_DEBUG and SGX_PRERELEASE at the same time!!)
endif
endif

ifeq ($(SGX_DEBUG), 1)
        SGX_COMMON_FLAGS += -O0 -g3  -ggdb
else
        SGX_COMMON_FLAGS += -O2
endif

SGX_COMMON_FLAGS += -DSGX_TRUSTED -Wall -Wextra -Winit-self -Wpointer-arith -Wreturn-type \
                    -Waddress -Wsequence-point -Wformat-security \
                    -Wmissing-include-dirs -Wfloat-equal -Wundef \
                    -Wcast-align -Wcast-qual -Wredundant-decls
SGX_COMMON_CFLAGS := $(SGX_COMMON_FLAGS) -Wjump-misses-init -Wstrict-prototypes -Wunsuffixed-float-constants
SGX_COMMON_CXXFLAGS := $(SGX_COMMON_FLAGS) -Wnon-virtual-dtor -std=c++11

######## App Settings ########

Urts_Library_Name := sgx_urts


App_Cpp_Files := App/App.cpp
ifeq ($(QVL_ONLY), 1)
App_Include_Paths := -IApp -Iinclude -Ijson/include
else
App_Include_Paths := -IApp -I$(SGX_SDK)/include
endif

App_C_Flags := -fPIC -Wno-attributes $(App_Include_Paths)

# Three configuration modes - Debug, prerelease, release
#   Debug - Macro DEBUG enabled.
#   Prerelease - Macro NDEBUG and EDEBUG enabled.
#   Release - Macro NDEBUG enabled.
ifeq ($(SGX_DEBUG), 1)
        App_C_Flags += -DDEBUG -UNDEBUG -UEDEBUG
else ifeq ($(SGX_PRERELEASE), 1)
        App_C_Flags += -DNDEBUG -DEDEBUG -UDEBUG
else
        App_C_Flags += -DNDEBUG -UEDEBUG -UDEBUG
endif

ifeq ($(QVL_ONLY), 1)
        App_C_Flags += -DQVL_ONLY
endif

App_Cpp_Flags := $(App_C_Flags)
ifeq ($(QVL_ONLY), 1)
App_Link_Flags := -L$(SGX_LIBRARY_PATH) -lsgx_dcap_quoteverify -lpthread -ldl -lssl -lcrypto
else
App_Link_Flags := -L$(SGX_LIBRARY_PATH) -lsgx_dcap_quoteverify -l$(Urts_Library_Name) -lpthread -ldl
endif

# Check if SGX_QPL_LOGGING is either 0 or 1 or 2
ifeq ($(filter $(SGX_QPL_LOGGING),0 1 2),)
    $(error SGX_QPL_LOGGING must be set to either 0 , 1 or 2.\
			0 means disable QPL logging.\
			1 means QPL logging error level.\
			2 means QPL logging info level.)
endif

ifneq ($(SGX_QPL_LOGGING), 0)
App_Link_Flags += -ldcap_quoteprov
endif
App_Cpp_Flags += -DSGX_QPL_LOGGING=$(SGX_QPL_LOGGING)

App_Cpp_Objects := $(App_Cpp_Files:.cpp=.o)

App_Name := attest_service

######## Enclave Settings ########


Trts_Library_Name := sgx_trts
Service_Library_Name := sgx_tservice

Crypto_Library_Name := sgx_tcrypto
DCAP_DIR  ?= ../../

Enclave_Cpp_Files := Enclave/Enclave.cpp
Enclave_Include_Paths := -IEnclave -I$(SGX_SDK)/include -I$(SGX_SDK)/include/tlibc -I$(SGX_SDK)/include/libcxx

Enclave_C_Flags := $(Enclave_Include_Paths) -nostdinc -fvisibility=hidden -fpie -ffunction-sections -fdata-sections
CC_BELOW_4_9 := $(shell expr "`$(CC) -dumpversion`" \< "4.9")
ifeq ($(CC_BELOW_4_9), 1)
	Enclave_C_Flags += -fstack-protector
else
	Enclave_C_Flags += -fstack-protector-strong
endif

Enclave_Cpp_Flags := $(Enclave_C_Flags) -nostdinc++

# Enable the security flags
Enclave_Security_Link_Flags := -Wl,-z,relro,-z,now,-z,noexecstack

# To generate a proper enclave, it is recommended to follow below guideline to link the trusted libraries:
#    1. Link sgx_trts with the `--whole-archive' and `--no-whole-archive' options,
#       so that the whole content of trts is included in the enclave.
#    2. For other libraries, you just need to pull the required symbols.
#       Use `--start-group' and `--end-group' to link these libraries.
# Do NOT move the libraries linked with `--start-group' and `--end-group' within `--whole-archive' and `--no-whole-archive' options.
# Otherwise, you may get some undesirable errors.
Enclave_Link_Flags := $(Enclave_Security_Link_Flags) -fPIC \
    -Wl,--no-undefined -nostdlib -nodefaultlibs -nostartfiles -L$(SGX_LIBRARY_PATH) \
	-Wl,--whole-archive -lsgx_dcap_tvl -l$(Trts_Library_Name) -Wl,--no-whole-archive \
	-Wl,--start-group -lsgx_tstdc -lsgx_tcxx -l$(Crypto_Library_Name) -l$(Service_Library_Name) -Wl,--end-group \
	-Wl,-Bstatic -Wl,-Bsymbolic -Wl,--no-undefined \
	-Wl,-pie,-eenclave_entry -Wl,--export-dynamic  \
	-Wl,--defsym,__ImageBase=0 -Wl,--gc-sections   \
	-Wl,--version-script=Enclave/Enclave.lds

Enclave_Cpp_Objects := $(sort $(Enclave_Cpp_Files:.cpp=.o))

Enclave_Name := enclave.so
Signed_Enclave_Name := enclave.signed.so
Enclave_Config_File := Enclave/Enclave.config.xml
Enclave_Test_Key := Enclave/Enclave_private_sample.pem

ifeq ($(SGX_DEBUG), 1)
	Build_Mode = HW_DEBUG
else ifeq ($(SGX_PRERELEASE), 1)
	Build_Mode = HW_PRERELEASE
else
	Build_Mode = HW_RELEASE
endif


.PHONY: all target run
all: .config_$(Build_Mode)_$(SGX_ARCH)
	@$(MAKE) target
ifeq ($(QVL_ONLY), 1)
target: $(App_Name)
else
ifeq ($(Build_Mode), HW_RELEASE)
target:  $(App_Name) $(Enclave_Name)
	@echo "The project has been built in release hardware mode."
	@echo "Please sign the $(Enclave_Name) first with your signing key before you run the $(App_Name) to launch and access the enclave."
	@echo "To sign the enclave use the command:"
	@echo "   $(SGX_ENCLAVE_SIGNER) sign -key <your key> -enclave $(Enclave_Name) -out <$(Signed_Enclave_Name)> -config $(Enclave_Config_File)"
	@echo "You can also sign the enclave using an external signing tool."


else
target: $(App_Name) $(Signed_Enclave_Name)
ifeq ($(Build_Mode), HW_DEBUG)
	@echo "The project has been built in debug hardware mode."
else ifeq ($(Build_Mode), HW_PRERELEASE)
	@echo "The project has been built in pre-release hardware mode."
else
	@echo "The project has been built in release mode."
endif
endif

endif

run: all
ifneq ($(Build_Mode), HW_RELEASE)
	@$(CURDIR)/$(App_Name)
	@echo "RUN  =>  $(App_Name) [$(SGX_ARCH), OK]"
endif

.config_$(Build_Mode)_$(SGX_ARCH):
	@rm -f .config_* $(App_Name) $(Enclave_Name) $(Signed_Enclave_Name) $(App_Cpp_Objects) App/Enclave_u.* $(Enclave_Cpp_Objects) Enclave/Enclave_t.*
	@touch .config_$(Build_Mode)_$(SGX_ARCH)

######## App Objects ########

App/Enclave_u.h: $(SGX_EDGER8R) Enclave/Enclave.edl
	@cd App && $(SGX_EDGER8R) --untrusted ../Enclave/Enclave.edl --search-path ../Enclave --search-path $(SGX_SDK)/include
	@echo "GEN  =>  $@"

App/Enclave_u.c: App/Enclave_u.h

App/Enclave_u.o: App/Enclave_u.c
	@$(CC) $(SGX_COMMON_CFLAGS) $(App_C_Flags) -c $< -o $@
	@echo "CC   <=  $<"

ifeq ($(QVL_ONLY), 1)
App/%.o: App/%.cpp
else
App/%.o: App/%.cpp  App/Enclave_u.h
endif
	@$(CXX) $(SGX_COMMON_CXXFLAGS) $(App_Cpp_Flags) -c $< -o $@
	@echo "CXX  <=  $<"

ifeq ($(QVL_ONLY), 1)
$(App_Name): $(App_Cpp_Objects)
else
$(App_Name): App/Enclave_u.o $(App_Cpp_Objects)
endif
	@$(CXX) $^ -o $@ $(App_Link_Flags)
	@echo "LINK =>  $@"

######## Enclave Objects ########

Enclave/Enclave_t.h: $(SGX_EDGER8R) Enclave/Enclave.edl
	@cd Enclave && $(SGX_EDGER8R) --trusted ../Enclave/Enclave.edl --search-path ../Enclave --search-path $(SGX_SDK)/include
	@echo "GEN  =>  $@"

Enclave/Enclave_t.c: Enclave/Enclave_t.h

Enclave/Enclave_t.o: Enclave/Enclave_t.c
	@$(CC) $(SGX_COMMON_CFLAGS) $(Enclave_C_Flags) -c $< -o $@
	@echo "CC   <=  $<"

Enclave/%.o: Enclave/%.cpp Enclave/Enclave_t.h
	@$(CXX) $(SGX_COMMON_CXXFLAGS) $(Enclave_Cpp_Flags) -c $< -o $@
	@echo "CXX  <=  $<"

$(Enclave_Name): Enclave/Enclave_t.o $(Enclave_Cpp_Objects)
	$(CXX) $^ -o $@ $(Enclave_Link_Flags)
	echo "LINK =>  $@"

$(Signed_Enclave_Name): $(Enclave_Name)
ifeq ($(wildcard $(Enclave_Test_Key)),)
	@echo "There is no enclave test key<Enclave_private_sample.pem>."
	@echo "The project will generate a key<Enclave_private_sample.pem> for test."
	@openssl genrsa -out $(Enclave_Test_Key) -3 3072
endif
	@$(SGX_ENCLAVE_SIGNER) sign -key $(Enclave_Test_Key) -enclave $(Enclave_Name) -out $@ -config $(Enclave_Config_File)
	@echo "SIGN =>  $@"

.PHONY: clean

clean:
	@rm -f .config_* $(App_Name) $(Enclave_Name) $(Signed_Enclave_Name) $(App_Cpp_Objects) App/*_u.* $(Enclave_Cpp_Objects) Enclave/Enclave_t.*
