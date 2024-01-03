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
		-Dentrypoint=$(GRAMINE_ENTRYPOINT) \
		-Darch_libdir=$(ARCH_LIBDIR) \
		-Dlog_level=$(GRAMINE_LOG_LEVEL) \
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
