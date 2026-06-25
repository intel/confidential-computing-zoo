# Argus Evidence Provider and Guard Sidecar
# Provides TDX quote generation and evidence service for agent-to-service attestation

FROM ubuntu:24.04

# set env to avoid interactive
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    rustup \
    git \
    curl \
    wget \
    gnupg \
    lsb-release \
    apt-transport-https \
    ca-certificates \
    build-essential \
    pkg-config \
    libtss2-dev \
    clang \
    musl-dev \
    musl-tools \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI (for container metadata)
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce docker-ce-cli containerd.io \
    && rm -rf /var/lib/apt/lists/*

# Install CDH/AA/ASR for TDX attestation
RUN git clone https://github.com/confidential-containers/guest-components.git

## Install CDH
RUN cd guest-components/confidential-data-hub \
    && make RESOURCE_PROVIDER=kbs KMS_PROVIDER=none STORAGE=none && make install

## Install AA (TDX attester)
RUN cd guest-components/attestation-agent \
    && make ATTESTER=tdx-attester && make install

## Install ASR
RUN cd guest-components/api-server-rest \
    && make && make install

# Clean guest-components
RUN rm -rf /app/guest-components

# Copy argus source
COPY Cargo.toml Cargo.lock* ./
COPY src/ ./src/

# Build argus binaries
RUN cargo build --release --manifest-path ./Cargo.toml

# Create argus user
RUN useradd -m -s /bin/bash argus && mkdir -p /app/argus/bin

# Copy binaries
RUN cp /app/target/release/argus-evidence-provider /app/argus/bin/argus-evidence-provider || \
    cp /app/target/debug/argus-evidence-provider /app/argus/bin/argus-evidence-provider
RUN cp /app/target/release/argus-guard /app/argus/bin/argus-guard || \
    cp /app/target/debug/argus-guard /app/argus/bin/argus-guard

# Create entrypoint scripts
RUN echo '#!/bin/bash\n\
set -e\n\
echo "Starting Argus Evidence Provider..."\n\
exec /app/argus/bin/argus-evidence-provider' > /app/argus/bin/argus-evidence-provider.sh && \
    chmod +x /app/argus/bin/argus-evidence-provider.sh

RUN echo '#!/bin/bash\n\
set -e\n\
echo "Starting Argus Guard..."\n\
exec /app/argus/bin/argus-guard' > /app/argus/bin/argus-guard.sh && \
    chmod +x /app/argus/bin/argus-guard.sh

# Set ownership
RUN chown -R argus:argus /app/argus

# Expose ports
EXPOSE 8006 8007

# Environment variables
ENV ARGUS_SERVICE_NAME=${ARGUS_SERVICE_NAME:-unknown}
ENV ARGUS_SERVICE_ID=${ARGUS_SERVICE_ID:-}
ENV ARGUS_IMAGE_DIGEST=${ARGUS_IMAGE_DIGEST:-}
ENV TC_API_URL=${TC_API_URL:-http://tc-api:8000}
ENV TRUCON_SERVICE_TOKEN=${TRUCON_SERVICE_TOKEN:-}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8006/health || exit 1

# Run argus evidence provider
USER argus
WORKDIR /app/argus

CMD ["/app/argus/bin/argus-evidence-provider"]