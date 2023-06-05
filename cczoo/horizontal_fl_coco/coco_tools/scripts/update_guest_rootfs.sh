#!/bin/bash
#
# Copyright (c) 2023 Intel Corporation
#
# SPDX-License-Identifier: Apache-2.0

COLOR_RED='\033[0;31m'
COLOR_NONE='\033[0m'

REMOTE_SCRIPTS=()
ROOTFS_SCRIPTS=()
FUNCTIONS=()

# common functions
# ==============================================================================
function usage()
{
	echo "Usage: ./update_guest_rootfs.sh [-h] [SUBCOMMAND] [NODES]"
	echo "          -h    help"
	echo "  SUBCOMMAND    "
	echo "                append_certificate"
	echo "                append_hostname --host_ip=[hostname],[ipaddr]"
	echo "                update_image_storage_size --percent=[X]% | --size=[Y]"
	echo "                update_roothash"
	echo "                set_default_vcpu_memory --vcpu=X --memory=Y"
	echo "                cp_to_image --image=[image file] --dest_dir=[dest dir] --src=[src file]"
	echo "                            --image is optional"
	echo "       NODES    node list"
}

function log_error()
{
	echo -e "${COLOR_RED}ERROR: ${@}${COLOR_NONE}"
}

function log_warning()
{
	echo -e "WARNING: ${@}"
}

function construct_remote_rootfs_script()
{
	for s in ${ROOTFS_SCRIPTS[@]}; do
		echo "echo [$NODE_ADDR] REMOTE_RUN $s"
		eval "echo \$$s"
	done
}

function construct_remote_script()
{
	for s in ${REMOTE_SCRIPTS[@]}; do
		echo "echo [$NODE_ADDR] REMOTE_RUN $s"
		eval "echo \$$s"
	done
}

function is_local_addr()
{
	if [ -z "$1" ] || [ $(id -u) != "0" ]; then
		return 1
	fi

	addr=$(getent ahostsv4 "$1" | grep STREAM | head -1 | awk '{print $1}')
	if ip route get $addr | head -1 | grep -Ewq "^local"; then
		return 0
	fi

	return 1
}

function add_function()
{
	func=$1
	echo "${FUNCTIONS[@]}" | grep -wq $func
	if [ $? != 0 ]; then
		FUNCTIONS=(${FUNCTIONS[@]} ${func})
	fi
}

# subcommand functions
# ==============================================================================
function f10_scp_crt()
{
	$SCP_CMD /opt/registry/certs/domain.crt ${SCP_TARGET_PREFIX}${WORK_DIR}
}

function f20_run_remote_script()
{
	$SSH_CMD "bash -s" << EOF
	node_addr=$NODE_ADDR
	work_dir=$WORK_DIR
	is_local=$IS_LOCAL

	$(construct_remote_script)

	if [ "${#ROOTFS_SCRIPTS[@]}" = "0" ]; then
		exit 0
	fi
	images="
/opt/confidential-containers/share/kata-containers/kata-ubuntu-latest.image
/opt/confidential-containers/share/kata-containers/kata-ubuntu-latest-tdx.image
"
	mkdir \$work_dir/rootfs

	for image in \$images; do
		echo [$NODE_ADDR] MOUNT image: \$image
		blkdevp1=\$(kpartx -avs \$image | grep -E "loop.+p1" \
			| awk '{print \$3}')
		blkdevp2=\$(kpartx -avs \$image | grep -E "loop.+p2" \
			| awk '{print \$3}')
		mount /dev/mapper/\$blkdevp1 \$work_dir/rootfs
		$(construct_remote_rootfs_script)
		umount \$work_dir/rootfs

		echo [$NODE_ADDR] update root hash

		configuration_dir=/opt/confidential-containers/share/defaults/kata-containers/
		if [ "\$(basename \$image)" = "kata-ubuntu-latest.image" ]; then
			toml_files="\$(find \$configuration_dir -type f \
					! -name "configuration-qemu-tdx.toml")"
		else
			toml_files=\$configuration_dir/configuration-qemu-tdx.toml
		fi
		hash_val=\$(veritysetup format \
			/dev/mapper/\$blkdevp1 /dev/mapper/\$blkdevp2 | \
			grep "Root hash" | awk '{print \$3}')
		for toml_file in \$toml_files; do
			sed -i "s/cc_rootfs_verity.hash=[^\"[:space:]]*/cc_rootfs_verity.hash=\$hash_val/" \
				\$toml_file
		done

		sync
		kpartx -ds \$image
	done
EOF
}

s10_append_certificate="
	cat \$work_dir/domain.crt >> \
		\$work_dir/rootfs/etc/ssl/certs/ca-certificates.crt
"

function append_certificate()
{
	add_function f10_scp_crt
	ROOTFS_SCRIPTS=(${ROOTFS_SCRIPTS[@]} "s10_append_certificate")
	return 0
}

function append_hostname()
{
	case "$1" in
		--host_ip=*)
			host_ip="${1#*=}"
			host_ip=(${host_ip/,/ })
			HOST_IP_HOST=${host_ip[0]}
			HOST_IP_IP=${host_ip[1]}
			if [ -z "$HOST_IP_HOST" ] || [ -z "$HOST_IP_IP" ]; then
				log_error "parse host_ip($1) hostname,ipaddr failed"
				return -1
			fi
			echo "[PREPARING] append_hostname $HOST_IP_HOST,$HOST_IP_IP"
			;;
		*)
			log_error "append_hostname require option '--host_ip=[hostname],[ipaddr]'"
			return -1
			;;
	esac

	s10_append_hostname="
		hosts_file=\$work_dir/rootfs/etc/hosts;
		[ -e \$hosts_file ] && sed -i '/${HOST_IP_HOST}/d' \$hosts_file;
		echo -e \"${HOST_IP_IP}\t\t${HOST_IP_HOST}\" >> \$hosts_file
	"

	ROOTFS_SCRIPTS=(${ROOTFS_SCRIPTS[@]} "s10_append_hostname")
	return 1
}

function update_image_storage_size()
{
	case "$1" in
		--percent=*)
			IMAGE_STORAGE_SIZE="${1#*=}"
			if ! [[ "$IMAGE_STORAGE_SIZE" =~ ^[0-9]+%$ ]]; then
				log_error "parameter format error."
				return -1
			fi
			;;
		--size=*)
			IMAGE_STORAGE_SIZE="${1#*=}"
			;;
		*)
			log_error "update_image_storage_size require a option '--percent=xx%' or '--size=yy'"
			return -1
			;;
	esac

	s10_update_image_storage_size="
		fstab_file=\$work_dir/rootfs/etc/fstab;
		[ -e \$fstab_file ] && sed -i '/\/run/d' \$fstab_file;
		echo \"tmpfs /run tmpfs nodev,nosuid,size=$IMAGE_STORAGE_SIZE 0 0\" >> \$fstab_file;
		kata_systemd_target=\$work_dir/rootfs/usr/lib/systemd/system/kata-containers.target;
		grep -qE \"^Requires=.*systemd-remount-fs\\.service.*\" \$kata_systemd_target || \
			echo \"Requires=systemd-remount-fs.service\" >> \$kata_systemd_target;
	"

	ROOTFS_SCRIPTS=(${ROOTFS_SCRIPTS[@]} "s10_update_image_storage_size")
	return 1
}

function update_roothash()
{
	s10_update_roothash="
		echo \"[\$node_addr] update_roothash by force\";
	"
	ROOTFS_SCRIPTS=(${ROOTFS_SCRIPTS[@]} "s10_update_roothash")
	return 0
}

function set_default_vcpu_memory()
{
	for (( i=0; i<2; i++ )); do
		case "$1" in
			--vcpu=*)
				CONFIG_VCPU="${1#*=}"
				if ! [[ "$CONFIG_VCPU" =~ ^[0-9]+$ ]]; then
					log_error "parameter should be a number."
					return -1
				fi
				shift
				;;
			--memory=*)
				CONFIG_MEMORY="${1#*=}"
				if ! [[ "$CONFIG_MEMORY" =~ ^[0-9]+$ ]]; then
					log_error "parameter should be a number."
					return -1
				fi
				shift
				;;
			*)
				break;
				;;
		esac
	done
	if [ "$i" = "0" ]; then
		log_error "set_default_vcpu_memory require at least one option '--vcpu=x' or '--memory=y'"
		return -1
	fi

	r10_set_vcpu_memory=$(cat <<- EOF
	configuration_dir=/opt/confidential-containers/share/defaults/kata-containers/;
	for toml_file in \$(find \$configuration_dir -type f); do
		if ! [ -z "${CONFIG_VCPU}" ]; then
			sed -i "s/default_vcpus.*=.*\\$/default_vcpus = ${CONFIG_VCPU}/" \
				\$toml_file;
		fi;
		if ! [ -z "${CONFIG_MEMORY}" ]; then
			sed -i "s/default_memory.*=.*\\$/default_memory = ${CONFIG_MEMORY}/" \
				\$toml_file;
		fi;
	done;
	EOF
	)

	REMOTE_SCRIPTS=(${REMOTE_SCRIPTS[@]} r10_set_vcpu_memory)
	return $i
}

function f10_cp_to_image()
{
	if [ "$IS_LOCAL" != "true" ]; then
		echo "[$NODE_ADDRS] scp $CP_TO_IMAGE_SRC to $NODE_ADDR"
		if [ -d "$CP_TO_IMAGE_SRC" ]; then
			scp -rq $CP_TO_IMAGE_SRC ${SCP_TARGET_PREFIX}${WORK_DIR}
		elif [ -f "$CP_TO_IMAGE_SRC" ]; then
			scp -q $CP_TO_IMAGE_SRC ${SCP_TARGET_PREFIX}${WORK_DIR}
		fi
	fi
}

function cp_to_image()
{
	for (( i=0; i<3; i++ )); do
		case "$1" in
			--image=*)
				CP_TO_IMAGE_IMAGE="${1#*=}"
				shift
				;;
			--dest_dir=*)
				CP_TO_IMAGE_DEST_DIR="${1#*=}"
				shift
				;;
			--src=*)
				CP_TO_IMAGE_SRC="${1#*=}"
				shift
				;;
			*)
				break;
				;;
		esac
	done

	if [ -z "$CP_TO_IMAGE_DEST_DIR" ] || [ -z "$CP_TO_IMAGE_SRC" ]; then
		log_error "cp_to_image require option --dest_dir= --src="
		return -1
	fi

	s10_cp_to_image=$(cat <<- EOF
	if [ -z "${CP_TO_IMAGE_IMAGE}" ] || \
		[[ "\$image" -ef "${CP_TO_IMAGE_IMAGE}" ]] || \
		[ "\$(basename \$image)" = "${CP_TO_IMAGE_IMAGE}" ]; then
		mkdir -p \$work_dir/rootfs/${CP_TO_IMAGE_DEST_DIR};
		echo "[\$node_addr] cp ${CP_TO_IMAGE_SRC} to ${CP_TO_IMAGE_DEST_DIR}";
		if [ "\$is_local" = "true" ]; then
			cp -a ${CP_TO_IMAGE_SRC} \
				\$work_dir/rootfs/${CP_TO_IMAGE_DEST_DIR};
		else
			cp -a \$work_dir/${CP_TO_IMAGE_SRC} \
				\$work_dir/rootfs/${CP_TO_IMAGE_DEST_DIR};
		fi
	else
		echo "[\$node_addr] not copy file to image: \$image";
	fi
	EOF
	)

	ROOTFS_SCRIPTS=(${ROOTFS_SCRIPTS[@]} s10_cp_to_image)
	add_function f10_cp_to_image
	return $i;
}

SUBCOMMANDS=(
	"append_certificate"
	"append_hostname"
	"update_image_storage_size"
	"update_roothash"
	"set_default_vcpu_memory"
	"cp_to_image"
	)

# main
# ==============================================================================

case "$1" in
	-h|--help)
		usage
		exit 0
		;;
esac

while [ $# -gt 0 ]; do
	subcommand=$1
	# if is subcommand
	echo "${SUBCOMMANDS[@]}" | grep -qw "$subcommand"
	if [ $? = 0 ]; then
		shift
		echo "[PREPARING] $subcommand"
		eval "$subcommand $@"
		num=$?
		if [ $num = 255 ];then
			log_error "subcommand: $subcommand failed."
			exit 1
		else
			shift $num
		fi
	else
		NODE_ADDRS=$@
		break
	fi
done

if [ ${#ROOTFS_SCRIPTS[@]} != 0 ] || [ ${#REMOTE_SCRIPTS[@]} != 0 ]; then
	add_function f20_run_remote_script
fi

if [ ${#FUNCTIONS[@]} == 0 ]; then
	usage
	exit 0
fi

IFS=$'\n' FUNCTIONS=($(sort <<< "${FUNCTIONS[*]}")); unset IFS
IFS=$'\n' ROOTFS_SCRIPTS=($(sort <<< "${ROOTFS_SCRIPTS[*]}")); unset IFS

if [ -z "$NODE_ADDRS" ];then
	NODE_ADDRS=$(kubectl get nodes -o \
		jsonpath='{ $.items[*].status.addresses[?(@.type=="InternalIP")].address }')
fi

for NODE_ADDR in $NODE_ADDRS; do
	echo "[$NODE_ADDR] EXECUTING ..."

	SCP_CMD="scp -q"
	SCP_TARGET_PREFIX="root@${NODE_ADDR}:"
	SSH_CMD="ssh -T root@$NODE_ADDR"

	if is_local_addr $NODE_ADDR; then
		IS_LOCAL=true
		SCP_CMD="cp -a"
		SCP_TARGET_PREFIX=""
		SSH_CMD="bash -c"
	fi

	WORK_DIR=$(${SSH_CMD} "mktemp -d --suffix=_COCO_TOOLS")
	for func in "${FUNCTIONS[@]}"; do
		echo "[$NODE_ADDR] RUN $func"
		$func
		ret=$?
		if [ $ret != 0 ]; then
			echo "[$NODE_ADDR] WARNING: $func: return $ret"
		fi
	done
	$SSH_CMD "rm -rf $WORK_DIR"
done
