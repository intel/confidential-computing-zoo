#!/bin/sh

set -eu

# get key via RA
APP_ID=luksKey
RA_SERVICE_ADDRESS=ra.service.com:50051

/sbin/tdvm-security.sh validate-cmdline
/sbin/tdvm-security.sh validate-td
/sbin/tdvm-security.sh validate-ra

/sbin/dhclient
ip route add default via 10.0.2.2
try_count=1
while [ "${try_count}" -le 5 ]
do
    PASSWORD=$(LD_LIBRARY_PATH=/usr/lib GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=/usr/bin/roots.pem \
        /usr/bin/ra-client -host="${RA_SERVICE_ADDRESS}" -key="${APP_ID}" 2>/dev/null \
        | awk -F ': ' '/^Secret: / { print $2; found=1; exit } END { if (!found) exit 1 }') || PASSWORD=""

    if [ -n "${PASSWORD}" ]; then
        printf '%s' "${PASSWORD}"
        unset PASSWORD
        exit 0
    fi

    try_count=$((try_count + 1))
done

echo "tdvm-security: failed to retrieve disk key from RA service" > /dev/console
exit 1
