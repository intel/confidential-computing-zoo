ARCH_LIBDIR ?= /lib/$(shell $(CC) -dumpmachine)

SGX_SIGNER_KEY ?= ../../Pal/src/host/Linux-SGX/signer/enclave-key.pem

ifeq ($(DEBUG),1)
GRAMINE_LOG_LEVEL = debug
else
GRAMINE_LOG_LEVEL = error
endif

SOURCE_FILES = \
	MultiThreadMain.java GramineJni/gramine_xx.java GramineJni/gramine_jni.java

CLASS_FILES = $(SOURCE_FILES:.java=.class)

%.class: %.java
	javac -d . $<

.PHONY: all
all: $(CLASS_FILES) java.manifest jni
ifeq ($(SGX),1)
all: java.manifest.sgx java.sig java.token
endif

.PHONY: jni
jni:
	cd GramineJni && make DEBUG=$(DEBUG)

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

.PHONY: clean
clean:
	$(RM) *.token *.sig *.manifest.sgx *.manifest *.class
	cd GramineJni && make clean

.PHONY: distclean
distclean: clean
