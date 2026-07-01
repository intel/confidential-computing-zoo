#!/bin/bash
# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Argus Evidence Provider and Guard startup script
# Provides TDX quote generation and evidence service for agent-to-service attestation

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

resolve_workload_identity() {
    local identity_vars=(ARGUS_WORKLOAD_IDENTITY ARGUS_SERVICE_NAME SERVICE_NAME K_SERVICE)
    local var_name
    local value

    for var_name in "${identity_vars[@]}"; do
        value="${!var_name:-}"
        value="${value#${value%%[![:space:]]*}}"
        value="${value%${value##*[![:space:]]}}"
        if [[ -n "$value" ]]; then
            printf '%s' "$value"
            return 0
        fi
    done

    return 1
}

require_workload_identity() {
    local identity
    if ! identity=$(resolve_workload_identity); then
        log_error "Missing stable workload identity. Set ARGUS_WORKLOAD_IDENTITY, ARGUS_SERVICE_NAME, SERVICE_NAME, or K_SERVICE before starting the Evidence Provider."
        exit 1
    fi

    log_info "Using workload identity: $identity"
}

# Check if running as root (required for TDX device access)
check_permissions() {
    if [[ $EUID -ne 0 ]]; then
        log_warn "Not running as root. TDX device access may require permissions."
    fi
}

# Check TDX device
check_tdx_device() {
    if [[ -c /dev/tdx_guest ]]; then
        log_info "TDX device found at /dev/tdx_guest"
    else
        log_warn "TDX device not found at /dev/tdx_guest. Quote generation will fail."
    fi
}

# Check TSM configfs
check_tsm_configfs() {
    if [[ -d /sys/kernel/config/tsm ]]; then
        log_info "TSM configfs found"
        if [[ -d /sys/kernel/config/tsm/report ]]; then
            log_info "TSM report interface available"
        fi
    else
        log_warn "TSM configfs not found. TSM-based quote generation will not work."
    fi
}

# Validate environment
validate_env() {
    log_info "Validating environment..."
    
    # Check Rust installation
    if command -v cargo &> /dev/null; then
        RUST_VERSION=$(rustc --version 2>/dev/null | awk '{print $2}')
        log_info "Rust version: $RUST_VERSION"
    else
        log_error "Rust not installed. Please install Rust 1.75 or later."
        exit 1
    fi
    
    # Check TDX device
    check_tdx_device
    
    # Check TSM configfs
    check_tsm_configfs

    if resolve_workload_identity > /dev/null; then
        log_info "Stable workload identity detected"
    else
        log_warn "No stable workload identity configured yet. Set ARGUS_WORKLOAD_IDENTITY, ARGUS_SERVICE_NAME, SERVICE_NAME, or K_SERVICE before starting the Evidence Provider."
    fi
}

# Start Evidence Provider
start_evidence_provider() {
    log_info "Starting Argus Evidence Provider on port 8008..."
    require_workload_identity
    
    # Set environment
    export RUST_LOG=${RUST_LOG:-info}
    export HOST=${HOST:-0.0.0.0}
    export PORT=${PORT:-8008}
    
    # Check if binary exists
    if [[ ! -f ./target/release/argus-evidence-provider ]]; then
        log_error "Evidence Provider binary not found. Building..."
        cargo build --release
    fi
    
    # Start in background if not already running
    if ! pgrep -f argus-evidence-provider &> /dev/null; then
        ./target/release/argus-evidence-provider &
        sleep 2
        
        # Check if started successfully
        if curl -s http://localhost:8008/health &> /dev/null; then
            log_info "Evidence Provider started successfully"
        else
            log_error "Failed to start Evidence Provider"
            exit 1
        fi
    else
        log_info "Evidence Provider already running"
    fi
}

# Start Guard Service
start_guard_service() {
    log_info "Starting Argus Guard on port 8007..."
    
    # Set environment
    export RUST_LOG=${RUST_LOG:-info}
    export HOST=${HOST:-0.0.0.0}
    export PORT=8007
    export EVIDENCE_ENDPOINT=${EVIDENCE_ENDPOINT:-http://localhost:8008}
    
    # Check if binary exists
    if [[ ! -f ./target/release/argus-guard ]]; then
        log_error "Guard binary not found. Building..."
        cargo build --release
    fi
    
    # Start in background if not already running
    if ! pgrep -f argus-guard &> /dev/null; then
        ./target/release/argus-guard &
        sleep 2
        
        # Check if started successfully
        if curl -s http://localhost:8007/health &> /dev/null; then
            log_info "Guard Service started successfully"
        else
            log_error "Failed to start Guard Service"
            exit 1
        fi
    else
        log_info "Guard Service already running"
    fi
}

stop_evidence_provider() {
    if pgrep -f argus-evidence-provider &> /dev/null; then
        log_info "Stopping Argus Evidence Provider..."
        pkill -f argus-evidence-provider 2>/dev/null || true
    else
        log_info "Argus Evidence Provider is not running"
    fi
}

stop_guard_service() {
    if pgrep -f argus-guard &> /dev/null; then
        log_info "Stopping Argus Guard..."
        pkill -f argus-guard 2>/dev/null || true
    else
        log_info "Argus Guard is not running"
    fi
}

# Stop all services
stop_services() {
    log_info "Stopping Argus services..."

    stop_evidence_provider
    stop_guard_service
    
    log_info "Services stopped"
}

# Health check all services
health_check() {
    log_info "Checking service health..."
    
    # Check Evidence Provider
    if curl -s http://localhost:8008/health &> /dev/null; then
        log_info "Evidence Provider: OK"
    else
        log_error "Evidence Provider: FAILED"
    fi
    
    # Check Guard Service
    if curl -s http://localhost:8007/health &> /dev/null; then
        log_info "Guard Service: OK"
    else
        log_error "Guard Service: FAILED"
    fi
}

# Test attestation flow
test_attestation() {
    log_info "Testing attestation flow..."

    local target_service_name
    target_service_name=${TARGET_SERVICE_NAME:-$(resolve_workload_identity || true)}

    if [[ -z "$target_service_name" ]]; then
        log_error "TARGET_SERVICE_NAME is not set and no workload identity could be resolved."
        exit 1
    fi
    
    local response=$(curl -s -X POST http://localhost:8007/ra/v1/verify \
        -H "Content-Type: application/json" \
        -d '{
            "target": {
                "service_name": "'"$target_service_name"'",
                "target_uri": "https://test.local"
            },
            "caller_id": "test",
            "requested_claims": []
        }')
    
    if echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print('Decision:', d['decision'])" 2>/dev/null; then
        log_info "Attestation test: PASSED"
        echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print('TEE type:', d['claims']['tee_type']); print('Quote valid:', d['claims']['quote_valid'])"
    else
        log_error "Attestation test: FAILED"
        echo "$response"
    fi
}

# Main command
case "${1:-start}" in
    start)
        check_permissions
        validate_env
        start_evidence_provider
        start_guard_service
        log_info "All services started"
        ;;
    start-provider)
        check_permissions
        validate_env
        start_evidence_provider
        ;;
    start-guard)
        validate_env
        start_guard_service
        ;;
    stop)
        stop_services
        ;;
    restart)
        stop_services
        sleep 2
        check_permissions
        validate_env
        start_evidence_provider
        start_guard_service
        log_info "All services restarted"
        ;;
    status)
        health_check
        ;;
    test)
        test_attestation
        ;;
    validate)
        check_permissions
        validate_env
        ;;
    *)
        echo "Usage: $0 {start|start-provider|start-guard|stop|restart|status|test|validate}"
        echo ""
        echo "Commands:"
        echo "  start           - Start all Argus services (Evidence Provider + Guard)"
        echo "  start-provider  - Start only the Argus Evidence Provider"
        echo "  start-guard     - Start only the Argus Guard"
        echo "  stop            - Stop all Argus services"
        echo "  restart         - Restart all Argus services"
        echo "  status          - Check health of all services"
        echo "  test            - Run attestation test"
        echo "  validate        - Validate environment (TDX device, TSM, etc.)"
        exit 1
        ;;
esac