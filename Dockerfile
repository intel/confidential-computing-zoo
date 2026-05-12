# Use a smaller Python base image.
FROM python:3.11-slim-bookworm

# Optional build-time proxy arguments.
ARG http_proxy
ARG https_proxy
ARG no_proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG ENABLE_TDX=false

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

# Copy packages into the image (targeted, not the entire repo).
COPY tlog/    /app/tlog/
COPY tlog-rekor/ /app/tlog-rekor/
COPY tc-api/  /app/tc-api/

# Todo libtdx_attest.so source
RUN if [ "$ENABLE_TDX" = "true" ]; then \ 
        if ls /app/tc-api/libtdx_attest.so* >/dev/null 2>&1; then \
            mv /app/tc-api/libtdx_attest.so* /usr/lib/x86_64-linux-gnu/ && \
            ln -sf /usr/lib/x86_64-linux-gnu/libtdx_attest.so.1.21.100.3 /usr/lib/x86_64-linux-gnu/libtdx_attest.so.1 && \
            ln -sf /usr/lib/x86_64-linux-gnu/libtdx_attest.so.1 /usr/lib/x86_64-linux-gnu/libtdx_attest.so; \
        else \
            echo "ENABLE_TDX=true but libtdx_attest.so* not found in build context" >&2; \
            exit 1; \
        fi; \
    else \
        echo "ENABLE_TDX=false, skipping TDX extension setup"; \
    fi

WORKDIR /app/tc-api

RUN python -m venv /app/venv
RUN /app/venv/bin/pip install --no-cache-dir \
    -e /app/tlog \
    -e /app/tlog-rekor \
    .

# Create necessary directories
RUN mkdir -p /app/tc-api/uploads /app/tc-api/builds /app/tc-api/logs /app/tc-api/certs

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
