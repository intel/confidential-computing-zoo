# Use a smaller Python base image.
FROM python:3.11-slim-bookworm

# Optional build-time proxy arguments.
ARG http_proxy
ARG https_proxy
ARG no_proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

# set env to aviod interactive
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Install system dependencies for external tools.
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    apt-transport-https \
    ca-certificates \
    cryptsetup \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian bookworm stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Install Cosign
RUN wget https://github.com/sigstore/cosign/releases/download/v2.2.1/cosign-linux-amd64 \
    && chmod +x cosign-linux-amd64 \
    && mv cosign-linux-amd64 /usr/local/bin/cosign

# Install Syft
RUN wget https://github.com/anchore/syft/releases/download/v0.96.0/syft_0.96.0_linux_amd64.tar.gz \
    && tar -xzf syft_0.96.0_linux_amd64.tar.gz \
    && chmod +x syft \
    && mv syft /usr/local/bin/syft \
    && rm syft_0.96.0_linux_amd64.tar.gz

# Install Skopeo
RUN apt-get update && apt-get install -y skopeo \
    && rm -rf /var/lib/apt/lists/*

# Install Intel TDX attestation runtime used by TruCon quote/RTMR fallbacks.
RUN wget -q https://download.01.org/intel-sgx/sgx-dcap/1.22/linux/distro/Debian12_temp/sgx_debian_local_repo.tgz \
    && tar xf sgx_debian_local_repo.tgz \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ./sgx_debian_local_repo/pool/main/libt/libtdx-attest/libtdx-attest_* \
        ./sgx_debian_local_repo/pool/main/libt/libtdx-attest/libtdx-attest-dev_* \
    && ldconfig \
    && rm -rf /var/lib/apt/lists/* sgx_debian_local_repo sgx_debian_local_repo.tgz

# Copy packages into the image (targeted, not the entire workspace).
COPY ../tlog /app/tlog
COPY ../config /app/config
COPY ./* /app/tc-api/

WORKDIR /app/tlog
RUN python -m pip install -e .
RUN python -m pip install -e '.[rekor]'

WORKDIR /app/tc-api
RUN mkdir -p uploads builds logs
RUN pip install -r requirements.txt

# Expose port
EXPOSE 8000 8001 8002 8006

# Set environment variables
ENV HOST=0.0.0.0
ENV PORT=8000
ENV UPLOAD_DIR=/app/tc-api/uploads
ENV BUILD_DIR=/app/tc-api/builds
ENV LOGS_DIR=/app/tc-api/logs

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

#Run the application
RUN chmod +x /app/tc-api/start.sh
ENTRYPOINT ["bash","/app/tc-api/start.sh"]
