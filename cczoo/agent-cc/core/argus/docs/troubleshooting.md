# Argus Troubleshooting Guide

This guide covers common issues and solutions for Argus Evidence Provider and Guard Service.

## Table of Contents

- [Build Issues](#build-issues)
- [Runtime Issues](#runtime-issues)
- [Attestation Issues](#attestation-issues)
- [Configuration Issues](#configuration-issues)

## Build Issues

### Rust Version Too Old

**Symptom**: Build fails with error about missing Rust features

```
error: this crate requires the `rustc` version 1.75 or later
```

**Solution**:
```bash
# Install Rust via rustup
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Upgrade to latest stable
rustup default stable
rustc --version  # Verify 1.75+
```

### Missing Dependencies

**Symptom**: Build fails with missing header files

```
fatal error: tss2/tcti-device.h: No such file or directory
```

**Solution**:
```bash
# Install TCTI device development files
sudo apt-get install libtss2-dev

# For Ubuntu/Debian
sudo apt-get install -y \
    build-essential \
    pkg-config \
    libtss2-dev \
    clang \
    musl-dev \
    musl-tools
```

### Compilation Errors

**Symptom**: Build fails with Rust compilation errors

```
error[E0596]: cannot borrow `x` as mutable
```

**Solution**:
```bash
# Clean and rebuild
cargo clean
cargo build --release 2>&1 | head -50
```

## Runtime Issues

### Service Fails to Start

**Symptom**: Service exits immediately after starting

**Diagnosis**:
```bash
# Run in foreground to see errors
RUST_LOG=debug ./target/release/argus-evidence-provider

# Check system logs
journalctl -u argus-evidence-provider -n 50
```

**Common Causes**:

1. **Port already in use**:
   ```bash
   lsof -i :8008
   # Kill conflicting process
   sudo kill <PID>
   ```

2. **Permission denied**:
   ```bash
   # Check device permissions
   ls -la /dev/tdx_guest
   # Fix if needed
   sudo chmod 666 /dev/tdx_guest
   ```

3. **Missing TDX device**:
   ```bash
   # Verify TDX device exists
   ls -la /dev/tdx_guest
   # If missing, load kernel module
   sudo modprobe tdx_guest
   ```

### Service Hangs on Start

**Symptom**: Service starts but never responds to requests

**Diagnosis**:
```bash
# Check if process is running
ps aux | grep argus

# Check network binding
ss -tlnp | grep 8008

# Test locally
curl -v http://localhost:8008/health
```

### Health Check Fails

**Symptom**: Health endpoint returns non-200 status

**Diagnosis**:
```bash
# Check service logs
curl http://localhost:8008/health
# Should return: {"status":"OK","version":"v1"}

# Check if service is actually running
ps aux | grep argus-evidence-provider

# Check port binding
ss -tlnp | grep 8008
```

## Attestation Issues

### TDX Quote Generation Fails

**Symptom**: Evidence Provider cannot generate TDX quote

**Diagnosis**:
```bash
# Enable debug logging
RUST_LOG=debug ./target/release/argus-evidence-provider 2>&1 | grep -i tdx

# Check TDX device
ls -la /dev/tdx_guest
cat /sys/firmware/acpi/tables/TDX1 2>/dev/null || echo "TDX1 table not found"
```

**Common Causes**:

1. **TDX Device Not Available**:
   ```bash
   # Check kernel messages
   dmesg | grep -i tdx
   # Verify device exists
   ls -la /dev/tdx_guest
   ```

2. **TSM Not Configured**:
   ```bash
   # Check TSM configfs
   ls -la /sys/kernel/config/tsm/
   # Mount if needed
   sudo mount -t configfs configfs /sys/kernel/config
   ```

3. **Quote Generation Timeout**:
   ```
   ERROR argus::service::engine: Quote generation timed out
   ```
   
   **Solution**: Increase timeout or check TDX subsystem load

### TSM Instance Creation Fails

**Symptom**: Error creating TSM instance directory

```
ERROR argus::service::engine: Failed to create TSM instance: Permission denied
```

**Diagnosis**:
```bash
# Check TSM report directory
ls -la /sys/kernel/config/tsm/report/

# Check write permissions
touch /sys/kernel/config/tsm/report/test_write
```

**Solution**:
```bash
# Ensure TSM report directory exists and is writable
sudo mkdir -p /sys/kernel/config/tsm/report
sudo chmod 755 /sys/kernel/config/tsm/report

# Verify TSM kernel support
grep CONFIG_TSM /boot/config-$(uname -r)
```

### Quote Verification Fails

**Symptom**: Guard Service fails to verify quote

```
ERROR argus::verifier: Quote verification failed: Invalid signature
```

**Diagnosis**:
```bash
# Enable debug logging on Guard
RUST_LOG=debug ./target/release/argus-guard 2>&1

# Check quote data format
curl -s http://localhost:8008/ra/v1/evidence | python3 -m json.tool
```

**Common Causes**:

1. **Nonce Mismatch**: Quote was generated with different nonce than expected
2. **Expired Quote**: Quote timestamp is too old
3. **Platform State Changed**: TDX platform configuration changed since quote generation

### Evidence Request Returns 404

**Symptom**: Guard cannot fetch evidence from Evidence Provider

```
ERROR argus::engine: Evidence request failed with status 404
```

**Diagnosis**:
```bash
# Verify Evidence Provider is running
curl http://localhost:8008/health

# Check Guard configuration
grep EVIDENCE_ENDPOINT /proc/$(pgrep argus-guard)/environ

# Test direct evidence endpoint
curl -X POST http://localhost:8008/ra/v1/evidence \
  -H "Content-Type: application/json" \
  -d '{"version":"v1","nonce":"test","caller_id":"test"}'
```

**Solution**:
```bash
# Update Guard endpoint configuration
export EVIDENCE_ENDPOINT=http://localhost:8008

# Or set at compile time in guard.rs
# Change default: .unwrap_or_else(|_| "http://localhost:8008".to_string())
```

## Configuration Issues

### Environment Variables Not Applied

**Symptom**: Service uses default values instead of configured ones

**Diagnosis**:
```bash
# Check environment variables for running process
cat /proc/$(pgrep argus-evidence-provider)/environ | tr '\0' '\n'

# List all ARGUS_* variables
env | grep ARGUS
```

**Solution**:
```bash
# Set environment before starting
export PORT=8008
export HOST=0.0.0.0
export RUST_LOG=debug

# Start service
./target/release/argus-evidence-provider
```

### TC-API Connection Fails

**Symptom**: Evidence Provider cannot connect to TC-API

```
ERROR argus::tc_api_client: TC-API request failed: Connection refused
```

**Diagnosis**:
```bash
# Check if TC-API is running
curl http://localhost:8080/health

# Check TC-API logs
docker logs tc-api 2>&1 | tail -20

# Verify network connectivity
nc -zv localhost 8080
```

**Solution**:
```bash
# If TC-API is not needed, disable it
# Evidence Provider will fall back to TSM
export TC_API_URL=

# Or configure correct TC-API endpoint
export TC_API_URL=http://localhost:8080
```

### Guard Evidence Endpoint Misconfigured

**Symptom**: Guard points to wrong Evidence Provider port

```
INFO argus_guard: Evidence endpoint: http://localhost:8006
```

**Solution**:
```bash
# Set correct endpoint
export EVIDENCE_ENDPOINT=http://localhost:8008

# Or update in source code (guard.rs line ~268)
# Change default from 8006 to 8008
```

## Performance Issues

### High Latency in Quote Generation

**Symptom**: Evidence requests take too long to complete

**Diagnosis**:
```bash
# Measure request latency
time curl -X POST http://localhost:8008/ra/v1/evidence \
  -H "Content-Type: application/json" \
  -d '{"version":"v1","nonce":"test","caller_id":"test"}'

# Check TSM performance
cat /sys/kernel/config/tsm/report/performance 2>/dev/null
```

**Solution**:
```bash
# Reduce logging verbosity in production
export RUST_LOG=warn

# Increase worker threads
export TOKIO_WORKER_THREADS=8
```

### Memory Usage High

**Symptom**: Service memory usage grows over time

**Diagnosis**:
```bash
# Monitor memory usage
ps aux | grep argus-evidence-provider
watch -n 1 'cat /proc/$(pgrep argus-evidence-provider)/status | grep VmRSS'

# Check for memory leaks
valgrind --leak-check=full ./target/release/argus-evidence-provider
```

## Debugging Tips

### Enable Debug Logging

```bash
# Run with debug logging
RUST_LOG=debug ./target/release/argus-evidence-provider 2>&1 | tee debug.log

# Run Guard with debug logging
RUST_LOG=debug ./target/release/argus-guard 2>&1 | tee guard-debug.log
```

### Capture Full Request/Response

```bash
# Test evidence request with verbose output
curl -v -X POST http://localhost:8008/ra/v1/evidence \
  -H "Content-Type: application/json" \
  -d '{"version":"v1","nonce":"test","caller_id":"test"}' 2>&1
```

### Check System Resources

```bash
# CPU and memory
top -p $(pgrep argus-evidence-provider)

# Disk I/O
iostat -x 1 5

# Network connections
ss -tlnp | grep argus
```

### Core Dump Analysis

```bash
# Enable core dumps
ulimit -c unlimited

# Generate core dump
gdb ./target/release/argus-evidence-provider core.<PID>
bt full
info threads
```

## Getting Help

### Log Collection

When reporting issues, collect the following:

```bash
# Service logs
RUST_LOG=debug ./target/release/argus-evidence-provider 2>&1 > evidence-provider.log

# System information
uname -a > system-info.txt
ls -la /dev/tdx_guest >> system-info.txt
cat /sys/kernel/config/tsm/report/ >> system-info.txt

# Process environment
cat /proc/$(pgrep argus-evidence-provider)/environ > evidence-env.txt
```

### Reporting Bugs

Include the following information:
1. Argus version (`argus-evidence-provider --version` or check Cargo.toml)
2. Rust version (`rustc --version`)
3. Kernel version (`uname -r`)
4. TDX module version
5. Full error logs with debug logging enabled
6. Steps to reproduce the issue