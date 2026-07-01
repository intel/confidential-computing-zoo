# Argus Quick Start Guide

This guide provides a quick introduction to running Argus Evidence Provider and Guard Service for TDX attestation.

## Prerequisites

- Intel TDX-enabled platform
- Linux kernel 5.15+ with TDX support
- Rust 1.75+
- `/dev/tdx_guest` device
- TSM configfs interface at `/sys/kernel/config/tsm/report/`

## Step 1: Build Argus

```bash
cd /home/siyuan/confidential-computing-zoo/cczoo/agent-cc/core/argus
cargo build --release
```

## Step 2: Validate Environment

```bash
./start_argus.sh validate
```

Expected output:
```
[INFO] Validating environment...
[INFO] Rust version: 1.96.0
[INFO] TDX device found at /dev/tdx_guest
[INFO] TSM configfs found
[INFO] TSM report interface available
```

## Step 3: Start Services

```bash
# Start Evidence Provider and Guard
./start_argus.sh start

# Check service status
./start_argus.sh status
```

## Step 4: Test Attestation Flow

```bash
# Run attestation test
./start_argus.sh test
```

Expected output:
```
[INFO] Testing attestation flow...
[INFO] Attestation test: PASSED
TEE type: tdx
Quote valid: True
```

## Manual Testing

### Health Checks

```bash
# Check Evidence Provider health
curl http://localhost:8008/health

# Check Guard health
curl http://localhost:8007/health
```

### Request Evidence

```bash
curl -X POST http://localhost:8008/ra/v1/evidence \
  -H "Content-Type: application/json" \
  -d '{
    "version": "v1",
    "nonce": "test-nonce-12345",
    "caller_id": "test-caller",
    "target": {
      "service_name": "test-service",
      "target_uri": "https://test.local"
    },
    "requested_claims": []
  }'
```

### Verify Evidence

```bash
curl -X POST http://localhost:8007/ra/v1/verify \
  -H "Content-Type: application/json" \
  -d '{
    "target": {
      "service_name": "test-service",
      "target_uri": "https://test.local"
    },
    "caller_id": "test-caller",
    "requested_claims": []
  }'
```

Expected response:
```json
{
  "decision": "ALLOW",
  "claims": {
    "tee_type": "tdx",
    "quote_valid": true
  }
}
```

## Using the Startup Script

The `start_argus.sh` script provides convenient commands:

```bash
./start_argus.sh start      # Start all services
./start_argus.sh stop       # Stop all services
./start_argus.sh restart    # Restart all services
./start_argus.sh status     # Check service health
./start_argus.sh test       # Run attestation test
./start_argus.sh validate   # Validate environment
```

## Docker Deployment

### Build Image

```bash
docker build -t argus:latest .
```

### Run with Docker Compose

```bash
docker-compose up -d
docker-compose ps
docker-compose logs -f argus-provider argus-guard
```

## Systemd Deployment

### Install

```bash
sudo cp target/release/argus-evidence-provider /usr/local/bin/
sudo cp target/release/argus-guard /usr/local/bin/

sudo tee /etc/systemd/system/argus-evidence-provider.service > /dev/null <<'EOF'
[Unit]
Description=Argus Evidence Provider
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/argus-evidence-provider
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/argus-guard.service > /dev/null <<'EOF'
[Unit]
Description=Argus Guard Service
After=network.target argus-evidence-provider.service

[Service]
Type=simple
User=root
Environment="EVIDENCE_ENDPOINT=http://localhost:8008"
ExecStart=/usr/local/bin/argus-guard
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable argus-evidence-provider argus-guard
sudo systemctl start argus-evidence-provider argus-guard
```

### Check Status

```bash
sudo systemctl status argus-evidence-provider
sudo systemctl status argus-guard
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RUST_LOG` | `info` | Logging level (trace, debug, info, warn, error) |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8008/8007` | Service port |
| `EVIDENCE_ENDPOINT` | `http://localhost:8008` | Evidence Provider endpoint |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Caller Service                          │
│                   (Service Mesh, SDK)                        │
└─────────────────────────┬───────────────────────────────────┘
                          │ POST /ra/v1/verify
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Argus Guard (8007)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Policy    │  │    RA       │  │  Evidence Fetcher   │  │
│  │  Evaluator  │  │  Verifier   │  │  (HTTP Client)      │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │ GET /ra/v1/evidence
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Argus Evidence Provider (8008)                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Evidence   │  │   Quote     │  │    TSM Generator     │  │
│  │   Engine    │  │  Generator  │  │  (configfs TSM)      │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │ /dev/tdx_guest
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    TDX Hardware                             │
│                   /dev/tdx_guest                            │
└─────────────────────────────────────────────────────────────┘
```

## Next Steps

- Read the [Architecture Documentation](architecture.md) for system design details
- Review the [API Documentation](api.md) for endpoint specifications
- See the [Deployment Guide](deployment.md) for production deployment options
- Check the [Troubleshooting Guide](troubleshooting.md) for common issues