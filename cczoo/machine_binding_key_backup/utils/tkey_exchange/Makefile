#
# Copyright (c) 2022 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
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

include ../../buildenv.mk

LIBNAME := libra_tkey_exchange.a

OUT = $(TOPDIR)/$(OUTLIB_DIR)

Include_Paths := \
	-I$(TOPDIR)/include \
	-I$(TOPDIR)/include/key_exchange \
	-I$(SGX_SDK)/include \
	-I$(SGX_SDK)/include/tlibc \
	-I$(SGX_SDK)/include/libcxx

CXXFLAGS += $(ENCLAVE_CXXFLAGS) $(Include_Paths)

SRC := $(wildcard *.cpp)

OBJ := $(sort $(SRC:.cpp=.o))

.PHONY: all
all: $(LIBNAME)
	@mkdir -p $(OUT)
	@mv $< $(OUT)

sgx_tkey_exchange_t.c: $(SGX_EDGER8R) sgx_tkey_exchange.edl
	@$(SGX_EDGER8R) sgx_tkey_exchange.edl --search-path .
	@echo "GEN  =>  $@"

tkey_exchange.o: sgx_tkey_exchange_t.c
	@$(CC) $(CXXFLAGS) -c $< -o $@
	@echo "CC   <=  $<"

$(OBJ): %.o :%.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(LIBNAME): $(OBJ)
	$(AR) rcsD $@ $^

.PHONY: clean
clean:
	@$(RM) $(OBJ)
	@$(RM) sgx_tkey_exchange_t.* sgx_tkey_exchange_u.*
	@$(RM) $(LIBNAME)

