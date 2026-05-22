# Deploy Confidential Container in TDVM

This document shows how to deploy AA/ASR/CDH in a container.

## Quick Start
### make configuration
1. Generate key pair
```bash
mkdir -p certs
openssl genrsa -out certs/key.pem
openssl rsa -in certs/key.pem -pubout -out certs/pub.pem
```

### Build image & start service in container
2. Build image

```bash
# Build image(if proxy needed, add --build-arg http_proxy=xxx in follow command line)
docker build -t {image_name:image_tag} .

# Run container(if proxy needed, add -e http_proxy=xxx in follow command line)
docker run -it --network host --privileged \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /dev/tdx_guest:/dev/tdx_guest \
  -v /etc/tdx-attest.conf:/etc/tdx-attest.conf \
  -v /etc/sgx_default_qcnl.conf:/etc/sgx_default_qcnl.conf \
  -v /etc/hosts:/etc/hosts \
  -v /sys/kernel/config:/sys/kernel/config \
  -p 8006:8006 \
  {image_name:image_tag}
```

##### Notice: Check the port in Dockerfile to ensure the ports are not in use. 
##### Please refer to: [https://github.com/RodgerZhu/deploy-encrypted-image-in-tdvm?tab=readme-ov-file](https://github.com/RodgerZhu/deploy-encrypted-image-in-tdvm?tab=readme-ov-file).
