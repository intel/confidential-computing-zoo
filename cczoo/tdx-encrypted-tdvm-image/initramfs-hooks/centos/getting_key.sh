#!/bin/sh

# get key via RA
APP_ID=luksKey
RA_SERVICE_ADDRESS=ra.service.com:50051

/sbin/dhclient
ip route add default via 10.0.2.2
try_count=0
while [ "$try_count" -lt "6" ]
do
    PASSWORD=`LD_LIBRARY_PATH=/usr/lib GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=/usr/bin/roots.pem /usr/bin/ra-client -host=$RA_SERVICE_ADDRESS -key=$APP_ID | grep 'Secret' | awk -F ': ' '{print $2}'` 
    try_count=$((try_count + 1))
    if [ "$PASSWORD" == "RPC failed" ]; then
        try_count=$((try_count + 1))
    else
        echo $PASSWORD
        break
    fi
done
