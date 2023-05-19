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

LIBNAME := libra_ukey_exchange.a

OUT = $(TOPDIR)/$(OUTLIB_DIR)
CURDIR= $(PWD)
Include_Paths := \
	-I$(TOPDIR)/include \
	-I$(TOPDIR)/include/key_exchange \
	-I$(SGX_SDK)/include \

KE_DEFINITIONS = 
CXXFLAGS += $(SGX_COMMON_CXXFLAGS) -Wno-attributes -fPIC -fno-exceptions -fno-rtti $(KE_DEFINITIONS) $(Include_Paths)
CFLAGS += $(SGX_COMMON_CFLAGS) -fPIC $(KE_DEFINITIONS) $(Include_Paths)

SRC := $(wildcard *.cpp)

OBJ := $(sort $(SRC:.cpp=.o))

OBJ_C := se_thread.o

.PHONY: all
all: $(LIBNAME)
	@mkdir -p $(OUT)
	@mv $< $(OUT)

$(OBJ_C): se_thread.c
	@$(CC) $(CFLAGS) -c $< -o $@
	@echo "CC   <=  $<"

$(OBJ): %.o :%.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(LIBNAME): $(OBJ) $(OBJ_C)
	$(AR) rcsD $@ $^

.PHONY: clean
clean:
	@$(RM) $(OBJ) $(OBJ_C)
	@$(RM) $(LIBNAME)