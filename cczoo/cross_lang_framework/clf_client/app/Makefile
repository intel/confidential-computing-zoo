ifneq ($(MAKECMDGOALS),clean)
ifneq ($(MAKECMDGOALS),test)
ifeq ($(SGX_SIGNER_KEY),)
$(error "SGX_SIGNER_KEY is not specified. Specify and make like GRAMINEDIR=/home/ubuntu/gramine SGX_SIGNER_KEY=/home/ubuntu/gramine/Pal/src/host/Linux-SGX/signer/enclave-key.pem make SGX=1")
endif
endif
endif

ifeq ($(MAKECMDGOALS),test)
ifeq ($(GRAMINEDIR),)
$(error "GRAMINEDIR is not specified. You may specify and make like: GRAMINEDIR=/home/ubuntu/gramine make test")
endif
endif

ARCH_LIBDIR ?= /lib/$(shell $(CC) -dumpmachine)

ifeq ($(DEBUG),1)
GRAMINE_LOG_LEVEL = debug
else
GRAMINE_LOG_LEVEL = error
endif

SOURCE_FILES = \
	clf_test.java

CLASS_FILES = $(SOURCE_FILES:.java=.class)

%.class: %.java
	javac -d . $<

.PHONY: all
all: test $(CLASS_FILES) java.manifest test.manifest
ifeq ($(SGX),1)
all: java.manifest.sgx java.sig java.token test.manifest.sgx test.token
endif

java.manifest: java.manifest.template
	gramine-manifest \
		-Dlog_level=$(GRAMINE_LOG_LEVEL) \
		-Darch_libdir=$(ARCH_LIBDIR) \
		-Dentrypoint=$(realpath $(shell sh -c "command -v java")) \
		$< >$@

java.manifest.sgx: java.manifest
	@test -s $(SGX_SIGNER_KEY) || \
		{ echo "SGX signer private key was not found, please specify SGX_SIGNER_KEY!"; exit 1; }
	gramine-sgx-sign \
		--key $(SGX_SIGNER_KEY) \
		--manifest $< \
		--output $@

java.sig: java.manifest.sgx

java.token: java.sig
	gramine-sgx-get-token --output $@ --sig $<

test.manifest: test.manifest.template
	gramine-manifest \
		-Dlog_level=$(GRAMINE_LOG_LEVEL) \
		-Darch_libdir=$(ARCH_LIBDIR) \
		-Dentrypoint=test \
		$< >$@

test.manifest.sgx: test.manifest
	@test -s $(SGX_SIGNER_KEY) || \
		{ echo "SGX signer private key was not found, please specify SGX_SIGNER_KEY!"; exit 1; }
	gramine-sgx-sign \
		--key $(SGX_SIGNER_KEY) \
		--manifest $< \
		--output $@

test.sig: test.manifest.sgx

test.token: test.sig
	gramine-sgx-get-token --output $@ --sig $<

lib_src = clf_client.c debug.c
lib_obj = $(lib_src:%.c=../%.o)

CFLAGS += -O0 -ggdb3
CFLAGS += -fPIE
CFLAGS += -Wall -std=c11 \
          -I ../../inc \
          -I ../ \
          -I$(GRAMINEDIR)/Pal/src/host/Linux-SGX/tools/ra-tls \
          -I /usr/lib/jvm/java-11-openjdk-amd64/include/ \
          -I /usr/lib/jvm/java-11-openjdk-amd64/include/linux/ \
          $(shell pkg-config --cflags mbedtls_gramine)
LDFLAGS += $(shell pkg-config --libs mbedtls_gramine)

.PHONY: test
test: test.c $(lib_obj)
	$(CC) $^ $(CFLAGS) $(LDFLAGS) -lsecret_prov_attest -o $@

.PHONY: clean
clean:
	$(RM) *.token *.sig *.manifest.sgx *.manifest *.class ../*.o test

.PHONY: distclean
distclean: clean
