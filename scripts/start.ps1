# TC API Startup Script for Windows

param(
    [string]$Mode = "prod"
)

Write-Host "Starting TC API Service..." -ForegroundColor Green

# Check if Python is available
try {
    $pythonVersion = python --version 2>$null
    Write-Host "✓ Python is available: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Error: Python is not installed or not in PATH" -ForegroundColor Red
    exit 1
}

# Check if Docker is available
try {
    $dockerVersion = docker --version 2>$null
    Write-Host "✓ Docker is available: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Error: Docker is not installed or not in PATH" -ForegroundColor Red
    exit 1
}

# Check external tools (optional)
function Check-Tool($toolName) {
    try {
        $version = & $toolName --version 2>$null
        Write-Host "✓ $toolName is available" -ForegroundColor Green
    } catch {
        Write-Host "⚠ Warning: $toolName is not installed. Some features may not work." -ForegroundColor Yellow
    }
}

Write-Host "Checking external tools..." -ForegroundColor Blue
Check-Tool "cosign"
Check-Tool "syft"
Check-Tool "skopeo"

# Create necessary directories
$directories = @("uploads", "builds", "logs")
foreach ($dir in $directories) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "✓ Created directory: $dir" -ForegroundColor Green
    }
}

# Set default environment variables if not set
if (!$env:HOST) { $env:HOST = "0.0.0.0" }
if (!$env:PORT) { $env:PORT = "8000" }
if (!$env:DEBUG) { $env:DEBUG = "false" }
$srcPath = Join-Path $PSScriptRoot "..\src"
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$srcPath$([IO.Path]::PathSeparator)$($env:PYTHONPATH)"
} else {
    $env:PYTHONPATH = $srcPath
}

Write-Host "Starting TC API on $($env:HOST):$($env:PORT)" -ForegroundColor Blue
Write-Host "Debug mode: $($env:DEBUG)" -ForegroundColor Blue

# Start the FastAPI application
if ($Mode -eq "dev") {
    Write-Host "Starting in development mode with auto-reload..." -ForegroundColor Yellow
    uvicorn tc_api.main:app --host $env:HOST --port $env:PORT --reload
} else {
    Write-Host "Starting in production mode..." -ForegroundColor Green
    uvicorn tc_api.main:app --host $env:HOST --port $env:PORT --workers 4
}
