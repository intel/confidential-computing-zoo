# Argus Deployment Guide

This guide covers deployment options for Argus Evidence Provider and Guard Service in production environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Docker Deployment](#docker-deployment)
- [Systemd Service Deployment](#systemd-service-deployment)
- [Environment Configuration](#environment-configuration)
- [Health Checks](#health-checks)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Hardware Requirements

- Intel TDX-enabled processor (TDX capable platform)
- `/dev/tdx_guest` device available
- TSM (Trusted Security Module) kernel configfs interface

### Software Requirements

- Rust 1.75 or later
- Linux kernel 5.15+ with TDX support
- TSM report interface at `/sys/kernel/config/tsm/report/`

### Environment Validation

```bash
# Check TDX device
ls -la /dev/tdx_guest

# Check TSM configfs
ls -la /sys/kernel/config/tsm/

# Validate Rust version
rustc --version  # Should be 1.75+
```

## Quick Start

### 1. Build Argus

```bash
cd core/argus
cargo build --release
```

### 2. Validate Environment

```bash
./start_argus.sh validate
```

Expected output:
```
[INFO] Validating environment...
[INFO] Rust version: 1.x.x
[INFO] TDX device found at /dev/tdx_guest
[INFO] TSM configfs found
[INFO] TSM report interface available
```

### 3. Start Services

```bash
# Start all services
./start_argus.sh start

# Check status
./start_argus.sh status

# Test attestation
./start_argus.sh test
```

## Docker Deployment

### Build Docker Image

```bash
cd core/argus
docker build -t argus:latest .
```

### Run Container

```bash
# Run Evidence Provider
docker run -d \
  --name argus-provider \
  -p 8008:8008 \
  -e RUST_LOG=info \
  argus:latest \
  /app/argus/bin/argus-evidence-provider

# Run Guard Service
docker run -d \
  --name argus-guard \
  -p 8007:8007 \
  -e EVIDENCE_ENDPOINT=http://argus-provider:8008 \
  argus:latest \
  /app/argus/bin/argus-guard
```

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  argus-provider:
    image: argus:latest
    container_name: argus-evidence-provider
    ports:
      - "8008:8008"
    environment:
      - RUST_LOG=info
      - HOST=0.0.0.0
      - PORT=8008
    volumes:
      - /dev/tdx_guest:/dev/tdx_guest
    devices:
      - /dev/tdx_guest:/dev/tdx_guest
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8008/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  argus-guard:
    image: argus:latest
    container_name: argus-guard
    ports:
      - "8007:8007"
    environment:
      - RUST_LOG=info
      - HOST=0.0.0.0
      - PORT=8007
      - EVIDENCE_ENDPOINT=http://argus-provider:8008
    depends_on:
      argus-provider:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8007/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
```

Start services:

```bash
docker-compose up -d
docker-compose ps
```

## Systemd Service Deployment

### Install Binaries

```bash
# Build release binaries
cargo build --release

# Install binaries
sudo cp target/release/argus-evidence-provider /usr/local/bin/
sudo cp target/release/argus-guard /usr/local/bin/

# Set permissions
sudo chmod +x /usr/local/bin/argus-*
```

### Create Evidence Provider Service

Create `/etc/systemd/system/argus-evidence-provider.service`:

```ini
[Unit]
Description=Argus Evidence Provider
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
Group=root
Environment="RUST_LOG=info"
Environment="HOST=0.0.0.0"
Environment="PORT=8008"
ExecStart=/usr/local/bin/argus-evidence-provider
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=false
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log/argus

# TDX device access
DeviceAllow=/dev/tdx_guest rw

[Install]
WantedBy=multi-user.target
```

### Create Guard Service

Create `/etc/systemd/system/argus-guard.service`:

```ini
[Unit]
Description=Argus Guard Service
After=network.target argus-evidence-provider.service
Wants=argus-evidence-provider.service

[Service]
Type=simple
User=root
Group=root
Environment="RUST_LOG=info"
Environment="HOST=0.0.0.0"
Environment="PORT=8007"
Environment="EVIDENCE_ENDPOINT=http://localhost:8008"
ExecStart=/usr/local/bin/argus-guard
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=false
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log/argus

[Install]
WantedBy=multi-user.target
```

### Enable and Start Services

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable argus-evidence-provider
sudo systemctl enable argus-guard

# Start services
sudo systemctl start argus-evidence-provider
sudo systemctl start argus-guard

# Check status
sudo systemctl status argus-evidence-provider
sudo systemctl status argus-guard
```

## Environment Configuration

### Evidence Provider Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8008` | Service port |
| `RUST_LOG` | `info` | Logging level |
| `TC_API_URL` | `http://localhost:8080` | TC-API endpoint |

### Guard Service Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8007` | Service port |
| `EVIDENCE_ENDPOINT` | `http://localhost:8008` | Evidence Provider endpoint |
| `RUST_LOG` | `info` | Logging level |
| `AGENT_TC_API_URL` | - | Agent TC-API URL (optional) |
| `TRUCON_SERVICE_TOKEN` | - | Trucon service token (optional) |

## Health Checks

### Manual Health Check

```bash
# Check Evidence Provider
curl http://localhost:8008/health

# Check Guard Service
curl http://localhost:8007/health
```

Expected response:
```json
{"status":"OK","version":"v1"}
```

### Automated Health Check Script

```bash
#!/bin/bash
for service in "8008" "8007"; do
  if curl -s "http://localhost:$service/health" > /dev/null; then
    echo "Service on port $service: OK"
  else
    echo "Service on port $service: FAILED"
    exit 1
  fi
done
```

## Troubleshooting

### TDX Device Not Found

**Symptom**: Quote generation fails with "TDX device not found"

**Solution**:
1. Verify TDX kernel support:
   ```bash
   dmesg | grep -i tdx
   uname -r  # Should be 5.15+
   ```

2. Check device exists:
   ```bash
   ls -la /dev/tdx_guest
   ```

3. Load TDX module if needed:
   ```bash
   sudo modprobe tdx_guest
   ```

### TSM Configfs Not Available

**Symptom**: TSM quote generation fails with "TSM configfs not found"

**Solution**:
1. Check kernel config:
   ```bash
   grep CONFIG_TSM /boot/config-$(uname -r)
   ```

2. Mount configfs if needed:
   ```bash
   sudo mount -t configfs configfs /sys/kernel/config
   ```

3. Verify TSM interface:
   ```bash
   ls -la /sys/kernel/config/tsm/report/
   ```

### Port Binding Issues

**Symptom**: Service fails to start with "Address already in use"

**Solution**:
1. Check for conflicting services:
   ```bash
   sudo lsof -i :8008
   sudo lsof -i :8007
   ```

2. Kill existing processes:
   ```bash
   pkill -f argus-evidence-provider
   pkill -f argus-guard
   ```

3. Wait and restart:
   ```bash
   sleep 2
   ./start_argus.sh start
   ```

### Evidence Request Fails with 404

**Symptom**: Guard returns "Evidence request failed with status 404"

**Solution**:
1. Verify Evidence Provider is running:
   ```bash
   curl http://localhost:8008/health
   ```

2. Check Guard configuration:
   ```bash
   grep EVIDENCE_ENDPOINT /proc/$(pgrep argus-guard)/environ
   ```

3. Update Guard endpoint if needed:
   ```bash
   export EVIDENCE_ENDPOINT=http://localhost:8008
   ```

### Quote Generation Fails

**Symptom**: Evidence Provider fails to generate quote

**Solution**:
1. Check TDX device access:
   ```bash
   ls -la /dev/tdx_guest
   groups  # Ensure user is in appropriate group
   ```

2. Verify TSM instance creation:
   ```bash
   ls -la /sys/kernel/config/tsm/report/
   ```

3. Check logs for detailed error:
   ```bash
   RUST_LOG=debug ./target/release/argus-evidence-provider
   ```

## Security Considerations

### Network Security

- Bind services to internal interfaces in production
- Use TLS for inter-service communication
- Implement firewall rules to restrict access

### TDX Attestation

- Verify platform TDX capabilities before deployment
- Monitor quote generation success rates
- Implement quote freshness validation

### Access Control

- Run services with minimal required privileges
- Use device cgroups for TDX device access control
- Implement audit logging for attestation events

## Performance Tuning

### Resource Limits

```bash
# Set process limits
sudo systemctl edit argus-evidence-provider
```

```ini
[Service]
LimitNOFILE=65536
LimitNPROC=4096
```

### Concurrency Settings

Adjust worker threads based on workload:

```bash
# For high-throughput scenarios
export TOKIO_WORKER_THREADS=16
```