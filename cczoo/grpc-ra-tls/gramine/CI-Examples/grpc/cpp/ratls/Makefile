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

################################# CONSTANTS ###################################

ARCH_LIBDIR ?= /lib/$(shell $(CC) -dumpmachine)

ifeq ($(DEBUG),1)
GRAMINE_LOG_LEVEL = debug
else
GRAMINE_LOG_LEVEL = error
endif

all: grpc.manifest
ifeq ($(SGX),1)
all: grpc.manifest.sgx grpc.sig
endif

################################ gRPC MANIFEST ###############################

grpc.manifest: grpc.manifest.template
	gramine-manifest \
		-Dlog_level=$(GRAMINE_LOG_LEVEL) \
		-Dentrypoint=$(ENTRYPOINT) \
		-Darch_libdir=$(ARCH_LIBDIR) \
		$< >$@

grpc.manifest.sgx grpc.sig: sgx_sign
	@:

.INTERMEDIATE: sgx_sign
sgx_sign: grpc.manifest
	gramine-sgx-sign \
		--manifest $< \
		--output $<.sgx

################################## CLEANUP ####################################

clean:
	$(RM) *.token *.sig *.manifest.sgx *.manifest

distclean: clean
