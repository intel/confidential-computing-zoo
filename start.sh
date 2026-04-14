#!/bin/bash

# TC API Startup Script

set -e

echo "Starting TC API Service..."

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed or not in PATH"
    exit 1
fi

# Check if required tools are available (optional check)
check_tool() {
    if command -v $1 &> /dev/null; then
        echo "✓ $1 is available"
    else
        echo "⚠ Warning: $1 is not installed. Some features may not work."
    fi
}

echo "Checking external tools..."
check_tool cosign
check_tool syft  
check_tool skopeo

# Check for active swap to prevent memory-backed DB leaks
if swapon --show | grep -q "/"; then
    echo "⚠ Warning: Memory swapping is active! The ephemeral SQLite queue in /dev/shm may leak to disk."
    if [ "$STRICT_MODE" = "true" ]; then
        echo "Error: STRICT_MODE requires swap to be disabled. Aborting."
        exit 1
    fi
fi

# Create necessary directories
mkdir -p uploads builds logs /dev/shm

# Set default environment variables if not set
export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8000}
export DEBUG=${DEBUG:-false}

echo "Starting Standalone Trusted Log Daemon..."
python tlog_daemon.py &
DAEMON_PID=$!

# Function to gracefully shutdown the daemon when the script exits
cleanup() {
    echo "Stopping Trusted Log Daemon (PID: $DAEMON_PID)..."
    kill -TERM $DAEMON_PID 2>/dev/null || true
    wait $DAEMON_PID 2>/dev/null || true
    echo "Daemon stopped."
}
trap cleanup EXIT INT TERM

echo "Starting TC API on $HOST:$PORT"
echo "Debug mode: $DEBUG"

# Start the FastAPI application
if [ "$1" = "dev" ]; then
    echo "Starting in development mode with auto-reload..."
    uvicorn main:app --host $HOST --port $PORT --reload
else
    echo "Starting in production mode..."
    uvicorn main:app --host $HOST --port $PORT --workers 4
fi
