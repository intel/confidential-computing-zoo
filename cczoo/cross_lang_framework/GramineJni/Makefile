GRAMINEDIR ?= ../../..
SGX_SIGNER_KEY ?= $(GRAMINEDIR)/Pal/src/host/Linux-SGX/signer/enclave-key.pem
GRAMINE_PKGLIBDIR ?= /usr/lib/x86_64-linux-gnu/gramine # this is debian/ubuntu specific

ARCH_LIBDIR ?= /lib/$(shell $(CC) -dumpmachine)

# for EPID attestation, specify your SPID and linkable/unlinkable attestation policy;
# for DCAP/ECDSA attestation, specify SPID as empty string (linkable value is ignored)
RA_CLIENT_SPID ?=
RA_CLIENT_LINKABLE ?= 0

ifeq ($(DEBUG),1)
GRAMINE_LOG_LEVEL = debug
CFLAGS += -O0 -ggdb3
else
GRAMINE_LOG_LEVEL = error
CFLAGS += -O2
endif

CFLAGS += -fPIC
LDFLAGS += -shared

.PHONY: all
all: libgramine_jni.so

######################### CLIENT/SERVER EXECUTABLES ###########################

CFLAGS += -Wall -std=c11 -I$(GRAMINEDIR)/Pal/src/host/Linux-SGX/tools/ra-tls \
          -I /usr/lib/jvm/java-11-openjdk-amd64/include/ -I /usr/lib/jvm/java-11-openjdk-amd64/include/linux/ \
          $(shell pkg-config --cflags mbedtls_gramine)
LDFLAGS += $(shell pkg-config --libs mbedtls_gramine)

# linker option --no-as-needed is required because SGX DCAP library (libsgx_dcap_quoteverify.so)
# does dlopen() instead of directly linking against libsgx_urts.so, and without this option
# compilers remove the "seemingly unused" libsgx_urts.so
#secret_prov_server_dcap: src/secret_prov_server.c
#    $(CC) $< $(CFLAGS) $(LDFLAGS) -Wl,--no-as-needed -lsgx_urts -lsecret_prov_verify_dcap -pthread -o $@

.PHONY: libgramine_jni.so
libgramine_jni.so: secret_prov_client.c gramine_jni.c
	$(CC) $^ $(CFLAGS) $(LDFLAGS) -lsecret_prov_attest -o $@
	sudo cp $@ /usr/lib/$@
	md5sum $@ /usr/lib/$@

.PHONY: clean
clean:
	$(RM) *.token *.sig *.manifest.sgx *.manifest *.class

