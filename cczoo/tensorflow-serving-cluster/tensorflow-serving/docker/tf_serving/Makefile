# Building the manifest for TF-Serving:
#
# - make                Build for Linux, TF-Serving with Release build
# - make DEBUG=1        Build for Linux, TF-Serving with Debug build, Gramine with debug output
# - make SGX=1          Build for SGX, TF-Serving with Release build
# - make SGX=1 DEBUG=1  Build for SGX, TF-Serving with Debug build, Gramine with debug output
#
# Use `make clean` to remove Graminne-generated files.
#
# Use `make distclean` to further remove the TF-Serving source and installation.

THIS_DIR := $(dir $(lastword $(MAKEFILE_LIST)))

ARCH_LIBDIR ?= /lib/$(shell $(CC) -dumpmachine)
# Relative path to Gramine root and key for enclave signing
GRAMINE_DIR ?= /gramine
SGX_SIGNER_KEY ?= $(GRAMINE_DIR)/Pal/src/host/Linux-SGX/signer/enclave-key.pem

TF-SERVING_DIR := /usr/bin
MODEL_DIR := $(GRAMINE_DIR)/CI-Examples/tensorflow-serving-cluster/tensorflow-serving/models



ifeq ($(DEBUG),1)
GRAMINE_LOG_LEVEL = debug
TF-SERVING_BUILD = Debug
else
GRAMINE_LOG_LEVEL = error
TF-SERVING_BUILD = Release
endif

.PHONY: all
all: tensorflow_model_server.manifest tensorflow_model_server libgcc libstdc libcurl libz libcom

ifeq ($(SGX),1)
all: tensorflow_model_server.manifest.sgx tensorflow_model_server.sig tensorflow_model_server.token
endif

libgcc:
	cp /lib/x86_64-linux-gnu/libgcc_s.so.1 .

libstdc:
	cp /usr/lib/x86_64-linux-gnu/libstdc++.so.6 .

libcurl:
	cp /usr/lib/x86_64-linux-gnu/libcurl.so.4 .

libz:
	cp /lib/x86_64-linux-gnu/libz.so.1 .

libcom:
	cp /lib/x86_64-linux-gnu/libcom_err.so.2 .

tensorflow_model_server.manifest: tensorflow_model_server.manifest.template
	gramine-manifest \
                -Darch_libdir=$(ARCH_LIBDIR) \
                -Dlog_level=$(GRAMINE_LOG_LEVEL) \
                $< >$@
# Generating the SGX-specific manifest (tensorflow_model_server.manifest.sgx), the enclave signature,
# and the token for enclave initialization.
tensorflow_model_server.manifest.sgx: tensorflow_model_server.manifest
	gramine-sgx-sign \
                --key $(SGX_SIGNER_KEY) \
                --manifest $< \
                --output $@

tensorflow_model_server.sig: tensorflow_model_server.manifest.sgx

tensorflow_model_server.token: tensorflow_model_server.sig
	gramine-sgx-get-token --output $@ --sig $<

tensorflow_model_server:
	ln -s $(TF-SERVING_DIR)/tensorflow_model_server $@


.PHONY: clean
clean:
	$(RM) *.manifest *.manifest.sgx *.token *.sig OUTPUT* *.PID tensorflow_model_server libgcc_s.so.1 libstdc++.so.6

