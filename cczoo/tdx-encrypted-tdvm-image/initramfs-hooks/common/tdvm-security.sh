#!/bin/sh

log_console()
{
	echo "tdvm-security: $*" > /dev/console 2>/dev/null || true
}

require_safe_cmdline()
{
	saw_panic=0

	cmdline=$(cat /proc/cmdline 2>/dev/null)
	[ -n "${cmdline}" ] || {
		log_console "kernel command line is unavailable"
		return 1
	}

	for arg in ${cmdline}; do
		case "${arg}" in
			panic=*)
				value=${arg#panic=}
				if [ -z "${value}" ] || [ "${value}" = "0" ]; then
					log_console "panic must be non-zero"
					return 1
				fi
				saw_panic=1
				;;
			break|break=*|rd.break|rd.break=*|init=*|single|s|rescue|emergency|systemd.debug-shell|systemd.unit=rescue.target|systemd.unit=emergency.target|rd.shell|rd.shell=1|rd.emergency=shell)
				log_console "unsafe kernel argument detected: ${arg}"
				return 1
				;;
			debug)
				log_console "debug shell boot is not allowed for encrypted TDVM images"
				return 1
				;;
			esac
	done

	if [ "${saw_panic}" -ne 1 ]; then
		log_console "panic boot policy missing"
		return 1
	fi

	return 0
}

require_td_guest()
{
	if ! grep -q 'tdx_guest' /proc/cpuinfo 2>/dev/null; then
		log_console "refusing to release disk key outside a TDX guest"
		return 1
	fi

	return 0
}

require_ra_materials()
{
	for artifact in /usr/bin/ra-client /usr/bin/roots.pem; do
		if [ ! -x "${artifact}" ] && [ "${artifact}" = "/usr/bin/ra-client" ]; then
			log_console "missing required RA client: ${artifact}"
			return 1
		fi

		if [ ! -e "${artifact}" ] && [ "${artifact}" != "/usr/bin/ra-client" ]; then
			log_console "missing required RA artifact: ${artifact}"
			return 1
		fi
	done

	return 0
}

close_luks_mapping()
{
	cryptsetup close luks-rootfs >/dev/null 2>&1 || true
}

case "${1:-}" in
	validate-cmdline)
		require_safe_cmdline
		;;
	validate-td)
		require_td_guest
		;;
	validate-ra)
		require_ra_materials
		;;
	close-luks)
		close_luks_mapping
		;;
	*)
		echo "usage: $0 {validate-cmdline|validate-td|validate-ra|close-luks}" >&2
		exit 2
		;;
esac