$(info "target:$(MAKECMDGOALS)")

ifneq ($(MAKECMDGOALS),clean)
ifeq ($(GRAMINEDIR),)
$(error "GRAMINEDIR is not specified. You may specify and make like: GRAMINEDIR=/home/ubuntu/gramine make")
endif
endif

ifeq ($(DEBUG),1)
GRAMINE_LOG_LEVEL = debug
CFLAGS += -O0 -ggdb3
else
GRAMINE_LOG_LEVEL = error
CFLAGS += -O2
endif

CFLAGS += -fPIE
LDFLAGS += -pie

.PHONY: all
all: clf_server


CFLAGS += -Wall -std=c11 -I$(GRAMINEDIR)/Pal/src/host/Linux-SGX/tools/ra-tls \
			-I ../inc \
          $(shell pkg-config --cflags mbedtls_gramine)
LDFLAGS += $(shell pkg-config --libs mbedtls_gramine)

clf_cur_src := \
	clf_server.c interact.c

clf_cur_objs := $(clf_cur_src:%.c=%.o)

clf_comm_src := \
	util.c \
	fop.c

clf_comm_objs := $(clf_comm_src:%.c=../comm/%.o)


# linker option --no-as-needed is required because SGX DCAP library (libsgx_dcap_quoteverify.so)
# does dlopen() instead of directly linking against libsgx_urts.so, and without this option
# compilers remove the "seemingly unused" libsgx_urts.so
clf_server: $(clf_cur_objs) $(clf_comm_objs)
	$(CC) $^ $(CFLAGS) $(LDFLAGS) -Wl,--no-as-needed -lsgx_urts -lsecret_prov_verify_dcap -pthread -o $@


.PHONY: clean
clean:
	$(RM) -r \
		clf_server $(clf_cur_objs) $(clf_comm_objs)

