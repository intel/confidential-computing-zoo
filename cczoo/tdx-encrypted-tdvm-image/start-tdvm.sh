#!/bin/bash
#
set -ex
CURR_DIR=$(readlink -f "$(dirname "$0")")

# Set distro related parameters according to distro


DISTRO=$(grep -w 'NAME' /etc/os-release)
if [[ "$DISTRO" =~ .*"Ubuntu".* ]]; then
    QEMU_EXEC="/usr/bin/qemu-system-x86_64"
    LEGACY_BIOS="/usr/share/seabios/bios.bin"
else
    QEMU_EXEC="/usr/libexec/qemu-kvm"
    LEGACY_BIOS="/usr/share/qemu-kvm/bios.bin"
fi

# VM configurations
CPUS=1
MEM=4G

# Installed from the package of intel-mvp-tdx-tdvf
OVMF_CODE="/usr/share/qemu/OVMF_CODE.fd"
OVMF_VARS="/usr/share/qemu/OVMF_VARS.fd"
GUEST_IMG=""
DEFAULT_GUEST_IMG="${CURR_DIR}/td-guest.qcow2"
KERNEL=""
DEFAULT_KERNEL="${CURR_DIR}/vmlinuz"
VM_TYPE="td"
BOOT_TYPE="direct"
DEBUG=false
USE_VSOCK=false
USE_SERIAL_CONSOLE=false
FORWARD_PORT=10026
MONITOR_PORT=9002
ROOT_PARTITION="/dev/vda3"
KERNEL_CMD_NON_TD="root=${ROOT_PARTITION} rw console=hvc0"
KERNEL_CMD_TD="${KERNEL_CMD_NON_TD}"
MAC_ADDR=""
QUOTE_TYPE=""

# Just log message of serial into file without input
HVC_CONSOLE="-chardev stdio,id=mux,mux=on,logfile=$CURR_DIR/vm_log_$(date +"%FT%H%M").log \
             -device virtio-serial,romfile= \
             -device virtconsole,chardev=mux -monitor chardev:mux \
             -serial chardev:mux -nographic"
#
# In grub boot, serial consle need input to select grub menu instead of HVC
# Please make sure console=ttyS0 is added in grub.cfg since no virtconsole
#
SERIAL_CONSOLE="-serial stdio"

# Default template for QEMU command line
QEMU_CMD="${QEMU_EXEC} -accel kvm \
          -name process=tdxvm,debug-threads=on \
          -m $MEM -vga none \
          -monitor pty \
          -no-hpet -nodefaults"
PARAM_CPU=" -cpu host,-kvm-steal-time,pmu=off"
PARAM_MACHINE=" -machine q35"

usage() {
    cat << EOM
Usage: $(basename "$0") [OPTION]...
  -i <guest image file>     Default is td-guest.qcow2 under current directory
  -k <kernel file>          Default is vmlinuz under current directory
  -t [legacy|efi|td]        VM Type, default is "td"
  -b [direct|grub]          Boot type, default is "direct" which requires kernel binary specified via "-k"
  -p <Monitor port>         Monitor via telnet
  -f <SSH Forward port>     Host port for forwarding guest SSH
  -o <OVMF_CODE file>       BIOS CODE firmware device file, for "td" and "efi" VM only
  -a <OVMF_VARS file>       BIOS VARS template, for "td" and "efi" VM only
  -m <11:22:33:44:55:66>    MAC address, impact TDX measurement RTMR
  -q [tdvmcall|vsock]       Support for TD quote using tdvmcall or vsock
  -c <number>               Number of CPUs, default is 1
  -r <root partition>       root partition for direct boot, default is /dev/vda3
  -v                        Flag to enable vsock
  -d                        Flag to enable "debug=on" for GDB guest
  -s                        Flag to use serial console instead of HVC console
  -h                        Show this help
EOM
}

error() {
    echo -e "\e[1;31mERROR: $*\e[0;0m"
    exit 1
}

warn() {
    echo -e "\e[1;33mWARN: $*\e[0;0m"
}

process_args() {
    while getopts ":i:k:t:b:p:f:o:a:m:vdshq:c:r:" option; do
        case "$option" in
            i) GUEST_IMG=$OPTARG;;
            k) KERNEL=$OPTARG;;
            t) VM_TYPE=$OPTARG;;
            b) BOOT_TYPE=$OPTARG;;
            p) MONITOR_PORT=$OPTARG;;
            f) FORWARD_PORT=$OPTARG;;
            o) OVMF_CODE=$OPTARG;;
            a) OVMF_VARS=$OPTARG;;
            m) MAC_ADDR=$OPTARG;;
            v) USE_VSOCK=true;;
            d) DEBUG=true;;
            s) USE_SERIAL_CONSOLE=true;;
            q) QUOTE_TYPE=$OPTARG;;
            c) CPUS=$OPTARG;;
            r) ROOT_PARTITION=$OPTARG;;
            h) usage
               exit 0
               ;;
            *)
               echo "Invalid option '-$OPTARG'"
               usage
               exit 1
               ;;
        esac
    done

    if [[ ! -f ${QEMU_EXEC} ]]; then
        error "Please install QEMU which supports TDX."
    fi

    # Validate the number of CPUs
    if ! [[ ${CPUS} =~ ^[0-9]+$ && ${CPUS} -gt 0 ]]; then
        error "Invalid number of CPUs: ${CPUS}"
    fi

    GUEST_IMG="${GUEST_IMG:-${DEFAULT_GUEST_IMG}}"
    if [[ ! -f ${GUEST_IMG} ]]; then
        usage
        error "Guest image file ${GUEST_IMG} not exist. Please specify via option \"-i\""
    fi

    # Create Variable firmware device file from template
    if [[ ${OVMF_VARS} == "/usr/share/qemu/OVMF_VARS.fd" ]]; then
        OVMF_VARS="${CURR_DIR}/OVMF_VARS.fd"
        if [[ ! -f ${OVMF_VARS} ]]; then
            if [[ ! -f /usr/share/qemu/OVMF_CODE.fd ]]; then
                error "Could not find /usr/share/qemu/OVMF_CODE.fd. Please install TDVF(Trusted Domain Virtual Firmware)."
            fi
            echo "Create ${OVMF_VARS} from template /usr/share/qemu/OVMF_VARS.fd"
            cp /usr/share/qemu/OVMF_VARS.fd "${OVMF_VARS}"
        fi
    fi

    # Check parameter MAC address
    if [[ -n ${MAC_ADDR} ]]; then
        if [[ ! ${MAC_ADDR} =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]]; then
            error "Invalid MAC address: ${MAC_ADDR}"
        fi
    fi

    case ${GUEST_IMG##*.} in
        qcow2) FORMAT="qcow2";;
          img) FORMAT="raw";;
            *) echo "Unknown disk image's format"; exit 1 ;;
    esac

    # Guest rootfs changes
    if [[ ${ROOT_PARTITION} != "/dev/vda3" ]]; then
        KERNEL_CMD_NON_TD=${KERNEL_CMD_NON_TD//"/dev/vda3"/${ROOT_PARTITION}}
        KERNEL_CMD_TD="${KERNEL_CMD_NON_TD}"
    fi

    QEMU_CMD+=" -drive file=$(readlink -f "${GUEST_IMG}"),if=virtio,format=$FORMAT "
    QEMU_CMD+=" -monitor telnet:127.0.0.1:${MONITOR_PORT},server,nowait "

    if [[ ${DEBUG} == true ]]; then
        OVMF_CODE="/usr/share/qemu/OVMF_CODE.debug.fd"
    fi

    if [[ -n ${QUOTE_TYPE} ]]; then
        case ${QUOTE_TYPE} in
            "tdvmcall") ;;
            "vsock")
                USE_VSOCK=true
                ;;
            *)
                error "Invalid quote type \"$QUOTE_TYPE\", must be [vsock|tdvmcall]"
                ;;
        esac
    fi

    case ${VM_TYPE} in
        "td")
            cpu_tsc=$(grep 'cpu MHz' /proc/cpuinfo | head -1 | awk -F: '{print $2/1024}')
            if (( $(echo "$cpu_tsc < 1" |bc -l) )); then
                PARAM_CPU+=",tsc-freq=1000000000"
            fi
            # Note: "pic=no" could only be used in TD mode but not for non-TD mode
            PARAM_MACHINE+=",pic=no,kernel_irqchip=split,kvm-type=tdx,confidential-guest-support=tdx"
            QEMU_CMD+=" -device loader,file=${OVMF_CODE},id=fd0"
            QEMU_CMD+=",config-firmware-volume=${OVMF_VARS}"
            QEMU_CMD+=" -object tdx-guest,id=tdx,quote-generation-service=vsock:2:4050"
            if [[ ${QUOTE_TYPE} == "tdvmcall" ]]; then
                QEMU_CMD+=",quote-generation-service=vsock:2:4050"
            fi
            if [[ ${DEBUG} == true ]]; then
                QEMU_CMD+=",debug=on"
            fi
            ;;
        "efi")
            PARAM_MACHINE+=",kernel_irqchip=split"
            QEMU_CMD+=" -drive if=pflash,format=raw,readonly=on,file=${OVMF_CODE}"
            QEMU_CMD+=" -drive if=pflash,format=raw,file=${OVMF_VARS}"
            ;;
        "legacy")
            if [[ ! -f ${LEGACY_BIOS} ]]; then
                error "${LEGACY_BIOS} does not exist!"
            fi
            QEMU_CMD+=" -bios ${LEGACY_BIOS} "
            ;;
        *)
            error "Invalid ${VM_TYPE}, must be [legacy|efi|td]"
            ;;
    esac

    QEMU_CMD+=$PARAM_CPU
    QEMU_CMD+=$PARAM_MACHINE
    QEMU_CMD+=" -device virtio-net-pci,netdev=mynet0"

    # Specify the number of CPUs
    QEMU_CMD+=" -smp ${CPUS} "

    # Customize MAC address. NOTE: it will impact TDX measurement RTMR.
    if [[ -n ${MAC_ADDR} ]]; then
        QEMU_CMD+=",mac=${MAC_ADDR}"
    fi

    # Forward SSH port to the host
    QEMU_CMD+=" -netdev user,id=mynet0,hostfwd=tcp::$FORWARD_PORT-:22 "

    # Enable vsock
    if [[ ${USE_VSOCK} == true ]]; then
        QEMU_CMD+=" -device vhost-vsock-pci,guest-cid=3 "
    fi

    case ${BOOT_TYPE} in
        "direct")
            KERNEL="${KERNEL:-${DEFAULT_KERNEL}}"
            if [[ ! -f ${KERNEL} ]]; then
                usage
                error "Kernel image file ${KERNEL} not exist. Please specify via option \"-k\""
            fi

            QEMU_CMD+=" -kernel $(readlink -f "${KERNEL}") "
            if [[ ${VM_TYPE} == "td" ]]; then
                # shellcheck disable=SC2089
                QEMU_CMD+=" -append \"${KERNEL_CMD_TD}\" "
            else
                # shellcheck disable=SC2089
                QEMU_CMD+=" -append \"${KERNEL_CMD_NON_TD}\" "
            fi
            ;;
        "grub")
            if [[ ${USE_SERIAL_CONSOLE} == false ]]; then
                warn "Using HVC console for grub, could not accept key input in grub menu"
            fi
            ;;
        *)
            echo "Invalid ${BOOT_TYPE}, must be [direct|grub]"
            exit 1
            ;;
    esac

    echo "========================================="
    echo "Guest Image       : ${GUEST_IMG}"
    echo "Kernel binary     : ${KERNEL}"
    echo "OVMF_CODE         : ${OVMF_CODE}"
    echo "OVMF_VARS         : ${OVMF_VARS}"
    echo "VM Type           : ${VM_TYPE}"
    echo "CPUS              : ${CPUS}"
    echo "Boot type         : ${BOOT_TYPE}"
    echo "Monitor port      : ${MONITOR_PORT}"
    echo "Enable vsock      : ${USE_VSOCK}"
    echo "Enable debug      : ${DEBUG}"
    if [[ -n ${MAC_ADDR} ]]; then
        echo "MAC Address       : ${MAC_ADDR}"
    fi
    if [[ ${USE_SERIAL_CONSOLE} == true ]]; then
        QEMU_CMD+=" ${SERIAL_CONSOLE} "
        echo "Console           : Serial"
    else
        QEMU_CMD+=" ${HVC_CONSOLE} "
        echo "Console           : HVC"
    fi
    if [[ -n ${QUOTE_TYPE} ]]; then
        echo "Quote type        : ${QUOTE_TYPE}"
    fi
    echo "========================================="
}

launch_vm() {
    # remap CTRL-C to CTRL ]
    echo "Remapping CTRL-C to CTRL-]"
    stty intr ^]
    echo "Launch VM:"
    # shellcheck disable=SC2086,SC2090
    echo ${QEMU_CMD}
    # shellcheck disable=SC2086
    eval ${QEMU_CMD}
    # restore CTRL-C mapping
    stty intr ^c
}

process_args "$@"
launch_vm
