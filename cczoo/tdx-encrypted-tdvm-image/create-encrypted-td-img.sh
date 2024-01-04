#!/bin/bash
#

set -e
set -x

trap unmount ERR EXIT

ENC_IMG_NAME="encrypted-td.qcow2"
DEFAULT_ENC_IMG_SIZE="30G"

# Reference image device
IMG_REF_MOUNT_NBD="/dev/nbd1"
IMG_REF_MOUNT="/tmp/ref-mnt-tmp"
IMG_REF_EFI_MOUNT="/tmp/ref-mnt-efi"

# Define the new image partition info:
# - boot
# - efi
# - luks-rootfs
IMG_BOOT_MOUNT_NR="1"
IMG_BOOT_MOUNT_NAME="boot"
IMG_BOOT_MOUNT_LABEL="${IMG_BOOT_MOUNT_NAME}"

IMG_EFI_MOUNT_NR="2"
IMG_EFI_MOUNT_NAME="UEFI"
IMG_EFI_MOUNT_LABEL="${IMG_EFI_MOUNT_NAME}"

IMG_LUKS_MOUNT_NR="3"
IMG_LUKS_MOUNT_NAME="luks-rootfs"
IMG_LUKS_MOUNT_LABEL="${IMG_LUKS_MOUNT_NAME}"
IMG_LUKS_MOUNT_DM="${IMG_LUKS_MOUNT_NAME}"

IMG_LUKS_MOUNT_NBD="/dev/nbd3"
IMG_LUKS_MOUNT="/tmp/luks-mnt-tmp"

printinfo()
{
	echo -e "\e[1;33m${@}\e[0m"
}

unmount()
{
	echo
	printinfo "Unmount partitions..."

	# Unmount filesystems
	if mount | grep ${IMG_REF_MOUNT} > /dev/null 2>&1; then
		umount -R ${IMG_REF_MOUNT}
		rmdir ${IMG_REF_MOUNT}
	fi

	if mount | grep ${IMG_LUKS_MOUNT} > /dev/nul 2>&1; then
		umount -R ${IMG_LUKS_MOUNT}
		rmdir ${IMG_LUKS_MOUNT}
	fi

	# Close the LUKS device
	[ -a /dev/mapper/${IMG_LUKS_MOUNT_DM} ] && cryptsetup close ${IMG_LUKS_MOUNT_DM}

	printinfo "Disconnect nbd devices."
	qemu-nbd -d ${IMG_LUKS_MOUNT_NBD}
	qemu-nbd -d ${IMG_REF_MOUNT_NBD}
}

stderr()
{
	echo "${@}" > /dev/stderr
}

stop()
{
	stderr "ERROR: ${FUNCNAME[1]}: ${@}"
	exit 1
}


make_new_disk_parts()
{
	local dev=${1}

	[ -z "${dev}" ] && stop "disk device unspecified"

	sgdisk --zap-all ${dev}

	# Partition: /boot
	sgdisk --new=${IMG_BOOT_MOUNT_NR}:0:+512M ${dev}
	sgdisk --typecode=${IMG_BOOT_MOUNT_NR}:8301 ${dev}
	sgdisk --change-name=${IMG_BOOT_MOUNT_NAME}:${IMG_BOOT_MOUNT_NAME} ${dev}

	# Partion: /boot/efi
	sgdisk --new=${IMG_EFI_MOUNT_NR}:0:+100M ${dev}	
	sgdisk --typecode=${IMG_EFI_MOUNT_NR}:ef00 ${dev}
	sgdisk --change-name=${IMG_EFI_MOUNT_NR}:${IMG_EFI_MOUNT_NAME} ${dev}

	# Partion: luks-rootfs
	sgdisk --new=${IMG_LUKS_MOUNT_NR}:0:0 ${dev}
	sgdisk --typecode=${IMG_LUKS_MOUNT_NR}:8309 ${dev}
	sgdisk --change-name=${IMG_LUKS_MOUNT_NR}:${IMG_LUKS_MOUNT_NAME} ${dev}

	sgdisk --print ${nbd}
}

update_fstab_entry()
{
	local fstab=${1}
	local entry=${2}

    # check parameters
	[ -z "${fstab}" ] && stop "fstab location is required!"
	[ ! -w "${fstab}" ] && stop "${fstab} is not writable!"
	[ -z "${entry}" ] && stop "fstab entry is required!"

	# Get existing fstab entries
	local -a fstab_entries=( "${entry}" )
	readarray -O 1 -t fstab_entries < ${fstab}

	# update new entry
	for i in ${!fstab_entries[@]}; do
		echo ${fstab_entries[${i}]}
	done | sort -k 2,3 -o ${fstab}
}

execute_chroot()
{
	local root_path=${1}
	shift

	[ -z "${root_path}" ] && stop "root path is required!"
	[ ${#} -eq 0 ] && stop "excutable command is needed!"

	mount --bind /dev ${root_path}/dev
	mount --bind /dev/pts ${root_path}/dev/pts
	mount -t proc proc ${root_path}/proc
	mount -t sysfs sysfs ${root_path}/sys
	mount -t tmpfs tmpfs ${root_path}/run

	local resolv=$(realpath -m ${root_path}/etc/resolv.conf)
	local parent=$(dirname ${resolv})
	[ ! -d "${parent}" ] && mkdir -p ${parent}
	touch ${resolv}
	mount --bind /etc/resolv.conf ${resolv}

	chroot "${root_path}" \
	/usr/bin/env -i HOME=/root TERM="${TERM}" PATH=/usr/bin:/usr/sbin \
	${@}

	# Unmount vfs
	umount ${resolv}
	umount ${root_path}/dev{/pts,}
	umount ${root_path}/{sys,proc,run}

	echo "\n\n exit execute_chroot \n\n"
}

main()
{
	local ref_qcow2=${1}
	local enc_qcow2=${2:-${ENC_IMG_NAME}}
	local enc_qcow2_size=${3:-${DEFAULT_ENC_IMG_SIZE}}
	local new_img_nbd=${IMG_LUKS_MOUNT_NBD}
	local ref_img_nbd=${IMG_REF_MOUNT_NBD}

	root_id=`virt-filesystems -a ${ref_qcow2} --filesystems -l | grep -i 'root' \
	| awk '{print $1}' | sed 's/[^0-9]*//g'`

	# Check the current UID
	if [ "${UID}" -ne 0 ]; then
		printinfo "Please run the script with root privilege"
		exec sudo ${0} $@
	fi

	[ -z "${ref_qcow2}" ] && stop "Reference image is required!"
	[ ! -r "${ref_qcow2}" ] && stop "${ref_qcow2} is not readable!"

	# 1. Create empty qcow2
	qemu-img create -f qcow2 ${enc_qcow2} ${enc_qcow2_size}

	# 2. Bind to nbd
	[ ! -r "${new_img_nbd}" -o ! -r ${ref_img_nbd} ] && modprobe nbd
	qemu-nbd -c ${new_img_nbd} -f qcow2 ${enc_qcow2}
	qemu-nbd -c ${ref_img_nbd} -f qcow2 ${ref_qcow2}

	# 3. Create new partitions
	printinfo "Partitioning the image..."
	make_new_disk_parts ${new_img_nbd}

	local boot_partition=${new_img_nbd}p${IMG_BOOT_MOUNT_NR}
	local efi_partition=${new_img_nbd}p${IMG_EFI_MOUNT_NR}
	local luks_partition=${new_img_nbd}p${IMG_LUKS_MOUNT_NR}

	# 4. Create LUKS partition
	# the input key for LUKS partition should be restored in secret.json of ra-server
	printinfo "Setting up LUKS encryption for the root partition..."
	cryptsetup luksFormat ${luks_partition}

	printinfo "Unlocking the LUKS partition for installation..."
	cryptsetup open ${luks_partition} ${IMG_LUKS_MOUNT_DM}

	# 5. Format partition
	printinfo "Formatting ${IMG_BOOT_MOUNT_NAME} partition..."
	mkfs.ext4 -L ${IMG_BOOT_MOUNT_LABEL} ${boot_partition}

	printinfo "Formatting ${IMG_EFI_MOUNT_NAME} partition..."
	mkfs.vfat -F 16 -n ${IMG_EFI_MOUNT_LABEL} ${efi_partition}

        local IMG_REF_MOUNT="/tmp/ref-mnt-tmp"
        mkdir -p ${IMG_REF_MOUNT}

        # 6. Copy files to luks partition
	printinfo "Transferring files from reference image to LUKS encrypted image..."
        dd if=/dev/nbd1p${root_id} of=/dev/mapper/luks-rootfs status=progress

	# 7. Mount the image files
	local IMG_REF_MOUNT=${IMG_REF_MOUNT}
	local IMG_LUKS_MOUNT="/tmp/luks-mnt-tmp"

	mkdir -p ${IMG_REF_MOUNT}
	mkdir -p ${IMG_LUKS_MOUNT}
	mount /dev/mapper/${IMG_LUKS_MOUNT_DM} ${IMG_LUKS_MOUNT}

	# 8. Move the contents from orginal /boot to the new boot partition
	mv ${IMG_LUKS_MOUNT}/boot ${IMG_LUKS_MOUNT}/boot.orig
	mkdir -p ${IMG_LUKS_MOUNT}/boot

	mount ${boot_partition} ${IMG_LUKS_MOUNT}/boot

	mv -f /tmp/luks-mnt-tmp/boot.orig/* /tmp/luks-mnt-tmp/boot/
	rm -rf ${IMG_LUKS_MOUNT}/boot.orig
	
	# 9. Update etc/fstab to include the new boot partition
	printinfo "Updating etc/fstab..."
	update_fstab_entry ${IMG_LUKS_MOUNT}/etc/fstab "LABEL=boot /boot ext4 defaults 0 1"

	. ${IMG_LUKS_MOUNT}/etc/os-release


	if [ "${ID}" == "ubuntu" ]; then
		# 10. Install GRUB
		printinfo "Installing ubuntu GRUB..."
		mount ${efi_partition} ${IMG_LUKS_MOUNT}/boot/efi
		execute_chroot ${IMG_LUKS_MOUNT} grub-install --target=x86_64-efi ${new_img_nbd}

		echo "Installing uncloking scripts to Initramfs..."
		SHELL_FOLDER=$(cd "$(dirname "$0")";pwd)
		hook_path="${SHELL_FOLDER}/initramfs-hooks/ubuntu/"

		pushd ${hook_path}
		echo "Copying initramfs hooks..."
		cp -f hook-add-executables ${IMG_LUKS_MOUNT}/etc/initramfs-tools/hooks/
		cp -f hook-unlock ${IMG_LUKS_MOUNT}/etc/initramfs-tools/scripts/init-premount/

		echo "Replacing fstab..."
		cp -f fstab ${IMG_LUKS_MOUNT}/etc/fstab

		echo "Instaling getting_key script..."
		cp -f getting_key.sh ${IMG_LUKS_MOUNT}/sbin/

		echo "Instaling opening_disk script..."
		cp -f opening_disk.sh ${IMG_LUKS_MOUNT}/sbin/

		echo "Instaling Remote Attestation client..."
		rm -rf ../ra/ra-client/usr/bin/ra-client
                unzip ../ra/ra-client/usr/bin/ra-client.zip -d ../ra/ra-client/usr/bin/
                cp -rf ../ra/ra-client ${IMG_LUKS_MOUNT}/
                rm -rf ${IMG_LUKS_MOUNT}/ra-client/usr/bin/ra-client.zip
                sync
		popd

		execute_chroot ${IMG_LUKS_MOUNT} update-initramfs -u -k all
		printinfo "Update grub ..."
		cp -rf ${hook_path}/ubuntu-grub-cfg/50-cloudimg-settings.cfg ${IMG_LUKS_MOUNT}/etc/default/grub.d/50-cloudimg-settings.cfg
		echo "GRUB_DISABLE_OS_PROBER=true" >> ${IMG_LUKS_MOUNT}/etc/default/grub
		echo "GRUB_ENABLE_BLSCFG=false" >> ${IMG_LUKS_MOUNT}/etc/default/grub
		execute_chroot ${IMG_LUKS_MOUNT} update-grub
	fi

	if [ "${ID}" == "centos" ]; then
		SHELL_FOLDER=$(cd "$(dirname "$0")";pwd)
		initramfs_hook_dir="${SHELL_FOLDER}/initramfs-hooks/"
		execute_chroot ${IMG_LUKS_MOUNT} dnf install cryptsetup dracut-network dhclient dhcp-client -y

		pushd ${initramfs_hook_dir}/centos
		echo "Copying initramfs hooks..."
		mkdir -p ${IMG_LUKS_MOUNT}/usr/lib/dracut/hooks/
		mkdir -p ${IMG_LUKS_MOUNT}/usr/lib/dracut/hooks/initqueue/
		mkdir -p ${IMG_LUKS_MOUNT}/usr/lib/dracut/hooks/initqueue/finished/

		mkdir -p ${IMG_LUKS_MOUNT}/usr/lib/dracut/modules.d/99custom/
		mkdir -p ${IMG_LUKS_MOUNT}/usr/lib/dracut/modules.d/99cryptsetup/

		cp -f decrypt-module-setup.sh ${IMG_LUKS_MOUNT}/usr/lib/dracut/modules.d/99custom/module-setup.sh
		cp -f opening_disk.sh ${IMG_LUKS_MOUNT}/usr/lib/dracut/modules.d/99custom/
		cp -f crypt-module-setup.sh ${IMG_LUKS_MOUNT}/usr/lib/dracut/modules.d/99cryptsetup/module-setup.sh

		echo "Replacing fstab..."
		cp -f fstab ${IMG_LUKS_MOUNT}/etc/fstab
		echo "Filling getting_key script..."
		cp -f getting_key.sh ${IMG_LUKS_MOUNT}/sbin/
		cp -f resolv.conf ${IMG_LUKS_MOUNT}/root/

		# For Remote Attestation
		rm -rf ../ra/ra-client/usr/bin/ra-client
		unzip ../ra/ra-client/usr/bin/ra-client.zip -d ../ra/ra-client/usr/bin/
		cp -rf ../ra/ra-client ${IMG_LUKS_MOUNT}/
		rm -rf ${IMG_LUKS_MOUNT}/ra-client/usr/bin/ra-client.zip
		sync
		#Installing crypsetup in initramfs
		cp -f crypt.conf ${IMG_LUKS_MOUNT}/etc/dracut.conf.d/crypt.conf
		cp -f network.conf ${IMG_LUKS_MOUNT}/etc/dracut.conf.d/network.conf
		popd

		execute_chroot ${IMG_LUKS_MOUNT} dracut -f -v --regenerate-all

		#generate EFI partition
		mkdir -p ${IMG_REF_EFI_MOUNT}
		mount ${IMG_REF_MOUNT_NBD}p${IMG_EFI_MOUNT_NR} ${IMG_REF_EFI_MOUNT}
		mount ${efi_partition} ${IMG_LUKS_MOUNT}/boot/efi
		cp -rf ${IMG_REF_EFI_MOUNT}/* ${IMG_LUKS_MOUNT}/boot/efi/
		sync

		#update grub
		echo "GRUB_DISABLE_OS_PROBER=true" >> ${IMG_LUKS_MOUNT}/etc/default/grub
		echo "GRUB_ENABLE_BLSCFG=false" >> ${IMG_LUKS_MOUNT}/etc/default/grub
		sed -i "s|"/dev/vda3"|"/dev/mapper/luks-rootfs"|g" ${IMG_LUKS_MOUNT}/etc/default/grub
		execute_chroot ${IMG_LUKS_MOUNT} grub2-mkconfig -o /boot/efi/EFI/centos/grub.cfg

		umount ${IMG_REF_EFI_MOUNT}
		umount ${IMG_LUKS_MOUNT}/boot/efi/
		rmdir ${IMG_REF_EFI_MOUNT}
	fi

	printinfo "Successfully created ${enc_qcow2}!"
	exit 0
}

main $@
