# TC API Test Runner Script
# PowerShell script to run the TC API test suite

param(
    [string]$TestType = "all",  # all, manual, unit, integration, performance
    [string]$TestName = "",     # specific test name for manual tests
    [switch]$Verbose = $false,   # verbose output
    [switch]$StopOnFail = $false # stop on first failure
)

Write-Host "TC API Test Runner" -ForegroundColor Green
Write-Host "==================" -ForegroundColor Green

# Check if virtual environment exists
if (Test-Path "venv") {
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    & .\venv\Scripts\Activate.ps1
} else {
    Write-Host "No virtual environment found. Using global Python." -ForegroundColor Yellow
}

# Function to check if service is running
function Test-ServiceRunning {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8000/" -TimeoutSec 5
        return $true
    } catch {
        return $false
    }
}

# Function to start service in background
function Start-Service {
    Write-Host "Starting TC API service..." -ForegroundColor Yellow
    
    # Start the service in a new PowerShell session
    $job = Start-Job -ScriptBlock {
        Set-Location $using:PWD
        python main.py
    }
    
    # Wait for service to start (max 30 seconds)
    $timeout = 30
    $elapsed = 0
    
    while ($elapsed -lt $timeout) {
        Start-Sleep -Seconds 2
        $elapsed += 2
        
        if (Test-ServiceRunning) {
            Write-Host "Service started successfully!" -ForegroundColor Green
            return $job
        }
        
        Write-Host "Waiting for service to start... ($elapsed/$timeout seconds)" -ForegroundColor Yellow
    }
    
    Write-Host "Failed to start service within timeout" -ForegroundColor Red
    Stop-Job $job
    Remove-Job $job
    return $null
}

# Function to stop service
function Stop-Service($job) {
    if ($job) {
        Write-Host "Stopping TC API service..." -ForegroundColor Yellow
        Stop-Job $job
        Remove-Job $job
        Write-Host "Service stopped." -ForegroundColor Green
    }
}

# Check if service is already running
$serviceRunning = Test-ServiceRunning
$serviceJob = $null

if (-not $serviceRunning) {
    Write-Host "TC API service not running. Starting it..." -ForegroundColor Yellow
    $serviceJob = Start-Service
    
    if (-not $serviceJob) {
        Write-Host "Failed to start service. Exiting." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "TC API service is already running." -ForegroundColor Green
}

try {
    # Run tests based on type
    switch ($TestType.ToLower()) {
        "manual" {
            Write-Host "Running manual integration tests..." -ForegroundColor Cyan
            if ($TestName) {
                python test_api.py $TestName
            } else {
                python test_api.py
            }
        }
        
        "unit" {
            Write-Host "Running unit tests..." -ForegroundColor Cyan
            if ($Verbose) {
                pytest test_unit.py::TestTCAPI -v --tb=short
            } else {
                pytest test_unit.py::TestTCAPI
            }
        }
        
        "integration" {
            Write-Host "Running integration tests..." -ForegroundColor Cyan
            if ($Verbose) {
                pytest test_unit.py::TestIntegration -v --tb=short
            } else {
                pytest test_unit.py::TestIntegration
            }
        }
        
        "performance" {
            Write-Host "Running performance tests..." -ForegroundColor Cyan
            if ($Verbose) {
                pytest test_unit.py::TestPerformance -v --tb=short
            } else {
                pytest test_unit.py::TestPerformance
            }
        }
        
        "all" {
            Write-Host "Running all tests..." -ForegroundColor Cyan
            Write-Host ""
            
            # Manual tests
            Write-Host "1. Manual Integration Tests" -ForegroundColor Magenta
            Write-Host "============================" -ForegroundColor Magenta
            python test_api.py
            
            if ($LASTEXITCODE -ne 0 -and $StopOnFail) {
                throw "Manual tests failed"
            }
            
            Write-Host ""
            
            # Unit tests
            Write-Host "2. Automated Unit Tests" -ForegroundColor Magenta
            Write-Host "=======================" -ForegroundColor Magenta
            if ($Verbose) {
                pytest test_unit.py -v --tb=short
            } else {
                pytest test_unit.py
            }
            
            if ($LASTEXITCODE -ne 0 -and $StopOnFail) {
                throw "Unit tests failed"
            }
        }
        
        default {
            Write-Host "Invalid test type: $TestType" -ForegroundColor Red
            Write-Host "Valid options: all, manual, unit, integration, performance" -ForegroundColor Yellow
            exit 1
        }
    }
    
    Write-Host ""
    Write-Host "Test execution completed!" -ForegroundColor Green
    
} catch {
    Write-Host "Test execution failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
    
} finally {
    # Stop service if we started it
    if ($serviceJob) {
        Stop-Service $serviceJob
    }
}

Write-Host ""
Write-Host "Test runner finished." -ForegroundColor Green
