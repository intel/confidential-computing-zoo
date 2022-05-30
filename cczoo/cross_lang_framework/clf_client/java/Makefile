$(info "target:$(MAKECMDGOALS)")

ifneq ($(MAKECMDGOALS),clean)
ifeq ($(GRAMINEDIR),)
$(error "GRAMINEDIR is not specified. You may specify and make like: GRAMINEDIR=/home/ubuntu/gramine make")
endif
endif

ARCH_LIBDIR ?= /lib/$(shell $(CC) -dumpmachine)

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
all: libgramine_jni.so clf_client_java_lib

#---------- libgramine_jni.so --------
CFLAGS += -Wall -std=c11 \
          -I ../../inc \
          -I$(GRAMINEDIR)/Pal/src/host/Linux-SGX/tools/ra-tls \
          -I /usr/lib/jvm/java-11-openjdk-amd64/include/ \
          -I /usr/lib/jvm/java-11-openjdk-amd64/include/linux/ \
          $(shell pkg-config --cflags mbedtls_gramine)
LDFLAGS += $(shell pkg-config --libs mbedtls_gramine)

clf_client_comm_src := \
	clf_client.c \
	debug.c

clf_client_comm_objs := $(clf_client_comm_src:%.c=../%.o)

clf_comm_src := \
	util.c

clf_comm_objs := $(clf_comm_src:%.c=../../comm/%.o)

.PHONY: libgramine_jni.so
libgramine_jni.so: $(clf_client_comm_objs) $(clf_comm_objs)  gramine_jni.c
	$(CC) $^ $(CFLAGS) $(LDFLAGS) -lsecret_prov_attest -o $@
	sudo cp $@ /usr/lib/$@
	md5sum $@ /usr/lib/$@

#------------ Java ---------------
SOURCE_FILES = \
    gramine_jni.java gramine_xx.java 

CLASS_FILES = $(SOURCE_FILES:.java=.class)

%.class: %.java
	javac -Xlint:deprecation -d ../app $<

.PHONY: clf_client_java_lib
clf_client_java_lib: $(CLASS_FILES)
	
#---------- clean ----------------
.PHONY: clean
clean:
	$(RM) *.token *.sig *.manifest.sgx *.manifest *.class *.so *.o $(clf_client_comm_objs) $(clf_comm_objs)

