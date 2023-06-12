#!/usr/bin/env bash
#
# Copyright (c) 2023 Intel Corporation
#
# SPDX-License-Identifier: Apache-2.0

set -o nounset
set -o pipefail

readonly script_name="$(basename "${BASH_SOURCE[0]}")"

no_proxy="${no_proxy:-}"

die() {
	echo >&2 "ERROR: $*"
	exit 1
}

generate_certificate() {
	local registry_name="${1:-}"
	[ -n "${registry_name}" ] || die "registry_name not provided"

	command -v openssl &>/dev/null || die "openssl command is not in your $PATH"

	sudo -E mkdir -p /opt/registry/certs/
	sudo -E openssl req \
		-newkey rsa:4096 -nodes -sha256 -keyout /opt/registry/certs/domain.key \
		-subj "/CN=${registry_name}" \
		-addext "subjectAltName = DNS:${registry_name}" \
		-x509 -days 365 -out /opt/registry/certs/domain.crt
}

install_docker_registry() {
	docker run -d \
		--restart=always \
		--name registry \
		-v /opt/registry/certs:/certs \
		-e REGISTRY_HTTP_ADDR=0.0.0.0:443 \
		-e REGISTRY_HTTP_TLS_CERTIFICATE=/certs/domain.crt \
		-e REGISTRY_HTTP_TLS_KEY=/certs/domain.key \
		-p 443:443 \
		registry:2
}

install_k8s_registry() {
	kubectl apply -f self-hosted-registry.yaml
	while [[ $(kubectl get pods -l app=self-hosted-registry -o 'jsonpath={..status.conditions[?(@.type=="Ready")].status}') != "True" ]]; do
		echo "waiting for registry pod" && sleep 1;
	done
}

install_registry() {
	local registry_service="$1"
	local registry_name="$2"

	# Generate self-signed certificates for registry
	generate_certificate "$registry_name"

	# Deploy registry service
	if [ "$registry_service" = "docker" ]; then
		echo "Install docker registry"
		install_docker_registry
	elif [ "$registry_service" = "k8s" ]; then
		echo "Install k8s registry"
		install_k8s_registry
	elif [ "$registry_service" = "harbor" ]; then
		echo "Not implemeted yet!"
	else
		echo "Invalid param, Please specify 'docker', 'k8s', or 'harbor' as the registry service." && print_usage 1
	fi

	# Add self-signed certificates to trust chain
	source /etc/os-release
	case "$ID" in
	"ubuntu"|"debian")
		sudo cp /opt/registry/certs/domain.crt /usr/local/share/ca-certificates/$registry_name.crt
		sudo update-ca-certificates
		;;
	"centos"|"fedora"|"alinux")
		sudo cat /opt/registry/certs/domain.crt >> /etc/pki/ca-trust/extracted/openssl/ca-bundle.trust.crt
		;;
	"rhel")
		# https://access.redhat.com/solutions/3220561
		sudo cp /opt/registry/certs/domain.crt /etc/pki/ca-trust/source/anchors/
		sudo update-ca-trust extract
		cd /etc/pki/tls/certs/ && sudo openssl x509 -in ca-bundle.crt -text -noout
		;;
	*)
		echo "Unsupported OS. Please manual add registry certificates to host trust chain."
		exit 1
		;;
	esac

	# Append the entry to allow ip-address resolved to the registry name
	registry_ip=`hostname -I | awk '{print $1}'`
	echo "$registry_ip   $registry_name" | sudo tee -a /etc/hosts

	# Verifiy registry service works
	export no_proxy=$no_proxy,$registry_name
	if ! curl https://$registry_name/v2/_catalog ; then
		if ! nc -zv $registry_name 443 ; then
			echo "ERROR: failed to connect to 443 port "
		fi

		echo "ERROR: registry service is not ready"
		exit 1
	fi

	echo "Self hosted registry is deployed successfully!"
	echo "registry ip: $registry_ip registry name: $registry_name"
}

uninstall_registry() {
	local registry_service="$1"

	if [ "$registry_service" = "docker" ]; then
		echo "Uninstall docker registry"
		docker stop registry
		docker rm registry
		docker ps -a
	elif [ "$registry_service" = "k8s" ]; then
		echo "Uninstall k8s registry"
		kubectl delete -f self-hosted-registry.yaml
	elif [ "$registry_service" = "harbor" ]; then
		echo "Not implemeted yet!"
	else
		echo "Invalid param, Please specify 'docker', 'k8s', or 'harbor' as the registry service." && print_usage 1
	fi
}

print_usage() {
        exit_code="$1"
        cat <<EOF
Usage:
        ${script_name} [options] <args>
Options:
        -h : Display this help.
	-i : Install local registry
        -u : Uninstall local registry
Args:
        registry_service     : Supported registry service: docker, k8s
        registry_name        : The registry name, default: registry.domain.local
Example:
        ${script_name} -i k8s
        ${script_name} -i docker
        ${script_name} -i k8s registry.domain.local
        ${script_name} -u k8s
EOF
        exit "$exit_code"
}

main() {
	action=""

        while getopts "hiu" opt; do
                case "$opt" in
                h)
                        print_usage
                        exit 0
                        ;;

                i)
                        action="install"
                        ;;
                u)
                        action="uninstall"
                        ;;
                esac
        done

	shift $((OPTIND - 1))

	registry_service="${1:-}"
	[ -n "${registry_service}" ] || { echo "ERROR: no registry_service" && print_usage 1; }

	case "$action" in
	"install")
		local registry_name="${2:-registry.domain.local}"
		echo "Deploy $registry_name with $registry_service ..."
		install_registry $registry_service $registry_name
		;;
	"uninstall")
		uninstall_registry $registry_service
		;;
	*)
		echo "Unsupported action" && print_usage 1
		;;
	esac
}

main "$@"
