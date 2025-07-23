# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for Docker tools
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    lsb-release \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
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

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/uploads /app/builds /app/logs

# Expose port
EXPOSE 8000

# Set environment variables
ENV HOST=0.0.0.0
ENV PORT=8000
ENV UPLOAD_DIR=/app/uploads
ENV BUILD_DIR=/app/builds
ENV LOGS_DIR=/app/logs

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run the application
CMD ["python", "main.py"]
