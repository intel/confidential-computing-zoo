#!/bin/bash
#
# Copyright (c) 2023 Intel Corporation
#
# SPDX-License-Identifier: Apache-2.0

set -e

COLOR_RED='\033[0;31m'
COLOR_NONE='\033[0m'

function usage()
{
	echo 'sudo ./mount_guest_rootfs.sh [-i IMAGE] [-u]'
	echo '    IMAGE      image file'
	echo '    -u         umount'
}

function log_error()
{
	echo -e "${COLOR_RED}ERROR: ${@}${COLOR_NONE}"
}

function log_warning()
{
	echo -e "WARNING: ${@}"
}

function prompt_user()
{
	read -r -p "$1 (Y/n)? " response
	case "$response" in
		[Nn])
			return 1
			;;
		*)
			return 0
			;;
	esac
}

function get_image_abspath()
{
	image_dir=/opt/confidential-containers/share/kata-containers

	if [ -e "$IMAGE_NAME" ]; then
		IMAGE=$(readlink -f $IMAGE_NAME)
		return 0
	fi

	if [ ! -z "$IMAGE_NAME" ]; then
		try_images="
			$IMAGE_NAME
			$image_dir/$IMAGE_NAME
			$image_dir/${IMAGE_NAME}.image
			$image_dir/kata-ubuntu-latest-${IMAGE_NAME}.image
		"
	else
		try_images="
			$image_dir/kata-ubuntu-latest-tdx.image
			$image_dir/kata-ubuntu-latest.image
		"
	fi

	for image in $try_images; do
		if [ -e $image ]; then
			if prompt_user "[MOUNT] $image"; then
				IMAGE=$image
				break
			fi
		fi
	done
}

function partitions_filter()
{
	dev=$1
	# coco guest image only need mount partition 1.
	if echo $dev | grep -qE "^loop.+p1$"; then
		return 0
	fi
	return 1
}

while getopts "i:uh" opt; do
	case "${opt}" in
		i)
			IMAGE_NAME=${OPTARG}
			;;
		u)
			UNMOUNT_IMAGE=1
			;;
		h)
			usage
			exit 0
			;;
	esac
done

if [ $(id -u) != "0" ]; then
	log_error "please run as root."
	exit 1
fi

if [ -z "$UNMOUNT_IMAGE" ]; then
	get_image_abspath
	if [ -z "$IMAGE" ]; then
		log_warning "no image file to mount"
		exit 1
	fi

	mount_dir=$(mktemp -d --suffix=_COCO_GUEST_ROOTFS)
	blkdevs=$(kpartx -avs $IMAGE | grep -E "loop.+p.+" | awk '{print $3}')
	for dev in $blkdevs; do
		if ! partitions_filter $dev; then
			continue;
		fi
		part_dir=$mount_dir/$dev
		mkdir $part_dir
		if mount /dev/mapper/$dev $part_dir; then
			echo -e "[MOUNT] $dev mounted to ${COLOR_RED}${part_dir}${COLOR_NONE}"
		else
			rm -d $part_dir
			log_warning "mount $dev failed."
		fi
	done
else
	loopdevs=$(losetup -l | grep -E "\.image" | awk '{print $1}')
	if [ -z "$loopdevs" ]; then
		log_warning "not find guest image mapped to loop device."
		exit 0
	fi
	for loopdev in $loopdevs; do
		image=$(losetup -l $loopdev | tail -1 | awk '{print $6}')
		if ! prompt_user "[UMOUNT] $image"; then
			continue
		fi
		mount_points=$(mount | \
			grep -E "^/dev/mapper/$(basename $loopdev)" | \
			awk '{print $3}')
		for mp in $mount_points; do
			if umount $mp; then
				echo "[UMOUNT] $mp umounted."
				if [[ "$mp" =~ ^/tmp/tmp.*_COCO_GUEST_ROOTFS/loop*p* ]]; then
					if rm -d $mp; then
						echo "[RM] tmp mount point: $mp"
					else
						log_error "cannot remove mount point"
						exit 1
					fi
					# try remove parent dir created by mktemp
					tmpdir=$(dirname $mp)
					rm -d $tmpdir && \
						echo "[RM] tmp dir: $tmpdir" || true
				fi
			else
				log_error "umount $image failed."
				exit 1
			fi
		done
		kpartx -ds $image && \
			echo "[KPARTX] delete partition devmappings" || \
			log_warning "kpartx delete partition devmappings error."
	done
fi
