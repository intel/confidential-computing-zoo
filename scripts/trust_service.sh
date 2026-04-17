#!/bin/bash
#Login DockerHub
docker login -u {docker_hub account}

export no_proxy="localhost,127.0.0.1,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,.local"
echo "Start attestation-agent"
RUST_LOG=debug  ./attestation-agent -c aa.toml &
sleep 5
echo "Start confidential-data-hub"
RUST_LOG=debug  ./confidential-data-hub -c cdh.toml &
sleep 5
echo "Start api-server-rest"
./api-server-rest &
sleep 5
# Generate TruCon service token if not set
if [ -z "$TRUCON_SERVICE_TOKEN" ]; then
    export TRUCON_SERVICE_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    echo "✓ Generated TRUCON_SERVICE_TOKEN for this session"
fi
echo "Start tc_api"
/app/venv/bin/python -m tc_api.main
