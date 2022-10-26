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

################################# CONSTANTS ###################################

THIS_DIR := $(dir $(lastword $(MAKEFILE_LIST)))
ARCH_LIBDIR ?= /lib/$(shell $(CC) -dumpmachine)
ENTRYPOINT ?= ""

ifeq ($(DEBUG),1)
GRAMINE_LOG_LEVEL = debug
else
GRAMINE_LOG_LEVEL = error
endif

.PHONY: all
all: infer_server.manifest
ifeq ($(SGX),1)
all: infer_server.manifest.sgx infer_server.sig infer_server.token
endif

################################ MANIFEST ###############################

infer_server.manifest: infer_server.manifest.template
	gramine-manifest \
		-Dlog_level=$(GRAMINE_LOG_LEVEL) \
		-Dentrypoint=$(ENTRYPOINT) \
		-Darch_libdir=$(ARCH_LIBDIR) \
		$< >$@

infer_server.manifest.sgx: infer_server.manifest
	gramine-sgx-sign \
		--manifest $< \
		--output $@

infer_server.sig: infer_server.manifest.sgx

infer_server.token: infer_server.sig
	gramine-sgx-get-token --output $@ --sig $<

################################## CLEANUP ####################################

.PHONY: clean
clean:
	$(RM) *.token *.sig *.manifest.sgx *.manifest
	$(RM) -r scripts/__pycache__

.PHONY: distclean
distclean: clean
