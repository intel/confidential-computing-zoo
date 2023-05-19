ARCH_LIBDIR ?= /lib/$(shell $(CC) -dumpmachine)
GRAMINE_PKGLIBDIR ?= /usr/lib/x86_64-linux-gnu/gramine

ifeq ($(DEBUG),1)
GRAMINE_LOG_LEVEL = debug
else
GRAMINE_LOG_LEVEL = error
endif

.PHONY: all
all: homo_lr.manifest
ifeq ($(SGX),1)
all: homo_lr.manifest.sgx homo_lr.sig homo_lr.token
endif

homo_lr.manifest: homo_lr.manifest.template
	gramine-manifest \
		-Dlog_level=$(GRAMINE_LOG_LEVEL) \
		-Darch_libdir=$(ARCH_LIBDIR) \
		-Dentrypoint=$(realpath $(shell sh -c "command -v python3")) \
		$< >$@

homo_lr.manifest.sgx: homo_lr.manifest
	gramine-sgx-sign \
		--manifest $< \
		--output $@

homo_lr.sig: homo_lr.manifest.sgx

homo_lr.token: homo_lr.sig
	gramine-sgx-get-token --output $@ --sig $<

.PHONY: clean
clean:
	$(RM) *.manifest *.manifest.sgx *.token *.sig OUTPUT* *.PID TEST_STDOUT TEST_STDERR
	$(RM) -r scripts/__pycache__

.PHONY: distclean
distclean: clean
