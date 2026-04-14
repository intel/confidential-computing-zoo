# Use Python 3.11 slim image as base
FROM  ubuntu:24.04

# set env to aviod interactive
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Install system dependencies for Docker tools
RUN apt-get update && apt-get install -y \
    rustup \
    git \
    libcryptsetup-dev \
    clang \
    musl-dev \
    musl-tools \
    pkg-config \
    libtss2-dev \
    curl \
    wget \
    gnupg \
    lsb-release \
    apt-transport-https \
    ca-certificates \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce docker-ce-cli containerd.io \
    && rm -rf /var/lib/apt/lists/*

# Install CDH/AA/ASR
RUN git clone https://github.com/confidential-containers/guest-components.git

## Install CDH
RUN cd guest-components/confidential-data-hub \
    && make RESOURCE_PROVIDER=kbs KMS_PROVIDER=none STORAGE=none && make install

## Install AA
RUN cd guest-components/attestation-agent \
    && make ATTESTER=tdx-attester && make install

##Install ASR
RUN cd guest-components/api-server-rest \
    && make && make install

#Clean
RUN rm -rf /app/guest-components
COPY ./*.toml /app/

EXPOSE 8006 4050

RUN mkdir -p /app/kbs /app/certs
COPY ./certs /app/certs
COPY ./trust_service.sh /app/
#Run the application
RUN chmod +x *service.sh
CMD ["bash", "/app/trust_service.sh"]
