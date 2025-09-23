# Use ubuntu 24.04 as base
FROM ubuntu:24.04

# set env to aviod interactive
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Install system dependencies for Docker tools
RUN apt-get update && apt-get install -y \
    python3 \
    python3-venv \
    curl \
    wget \
    gnupg \
    lsb-release \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    build-essential \
    libssl-dev \
    libsox-fmt-all \
    python3-pip \
    net-tools \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce docker-ce-cli containerd.io \
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

#COPY file
COPY . /app/
RUN mv libtdx_attest.so* /usr/lib/x86_64-linux-gnu/ \
    && ln -s /usr/lib/x86_64-linux-gnu/libtdx_attest.so.1.21.100.3 /usr/lib/x86_64-linux-gnu/libtdx_attest.so.1 \
    && ln -s /usr/lib/x86_64-linux-gnu/libtdx_attest.so.1 /usr/lib/x86_64-linux-gnu/libtdx_attest.so

#RUN pip3 install --no-cache-dir -r requirements.txt
RUN python3 -m venv /app/venv
RUN if [ -f "requirements.txt" ]; then \
        /app/venv/bin/pip install --no-cache-dir -r requirements.txt; \
    fi

# Create necessary directories
RUN mkdir -p /app/uploads /app/builds /app/logs /app/certs

# Copy aa/asr/cdh binary
COPY ./certs /app/certs/

# Expose port
EXPOSE 8000 8001 8006

# Set environment variables
ENV HOST=0.0.0.0
ENV PORT=8000
ENV UPLOAD_DIR=/app/uploads
ENV BUILD_DIR=/app/builds
ENV LOGS_DIR=/app/logs

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/ || exit 1

#Run the application
RUN chmod +x *service.sh
ENTRYPOINT ["./bld_service.sh"]
#ENTRYPOINT ["./luh_service.sh"]
