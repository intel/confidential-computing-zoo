#!/bin/bash

# TC API Test Runner Script
# Bash script to run the TC API test suite

# Default parameters
TEST_TYPE="all"
TEST_NAME=""
VERBOSE=false
STOP_ON_FAIL=false
SERVICE_PID=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--type)
            TEST_TYPE="$2"
            shift 2
            ;;
        -n|--name)
            TEST_NAME="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -s|--stop-on-fail)
            STOP_ON_FAIL=true
            shift
            ;;
        -h|--help)
            echo "TC API Test Runner"
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  -t, --type TYPE      Test type: all, manual, unit, integration, performance"
            echo "  -n, --name NAME      Specific test name (for manual tests)"
            echo "  -v, --verbose        Verbose output"
            echo "  -s, --stop-on-fail   Stop on first failure"
            echo "  -h, --help           Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "\033[32mTC API Test Runner\033[0m"
echo -e "\033[32m==================\033[0m"

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo -e "\033[33mActivating virtual environment...\033[0m"
    source venv/bin/activate
else
    echo -e "\033[33mNo virtual environment found. Using global Python.\033[0m"
fi

# Function to check if service is running
check_service() {
    if curl -s -f http://localhost:8000/ > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to start service
start_service() {
    echo -e "\033[33mStarting TC API service...\033[0m"
    
    # Start service in background
    python main.py &
    SERVICE_PID=$!
    
    # Wait for service to start (max 30 seconds)
    local timeout=30
    local elapsed=0
    
    while [ $elapsed -lt $timeout ]; do
        sleep 2
        elapsed=$((elapsed + 2))
        
        if check_service; then
            echo -e "\033[32mService started successfully! (PID: $SERVICE_PID)\033[0m"
            return 0
        fi
        
        echo -e "\033[33mWaiting for service to start... ($elapsed/$timeout seconds)\033[0m"
    done
    
    echo -e "\033[31mFailed to start service within timeout\033[0m"
    if [ ! -z "$SERVICE_PID" ]; then
        kill $SERVICE_PID 2>/dev/null
    fi
    return 1
}

# Function to stop service
stop_service() {
    if [ ! -z "$SERVICE_PID" ]; then
        echo -e "\033[33mStopping TC API service (PID: $SERVICE_PID)...\033[0m"
        kill $SERVICE_PID 2>/dev/null
        wait $SERVICE_PID 2>/dev/null
        echo -e "\033[32mService stopped.\033[0m"
        SERVICE_PID=""
    fi
}

# Cleanup function
cleanup() {
    stop_service
    exit $1
}

# Set trap for cleanup
trap 'cleanup $?' EXIT INT TERM

# Check if service is already running
if check_service; then
    echo -e "\033[32mTC API service is already running.\033[0m"
else
    echo -e "\033[33mTC API service not running. Starting it...\033[0m"
    if ! start_service; then
        echo -e "\033[31mFailed to start service. Exiting.\033[0m"
        exit 1
    fi
fi

# Function to run tests with error handling
run_test() {
    local test_command="$1"
    local test_description="$2"
    
    echo -e "\033[36m$test_description\033[0m"
    eval $test_command
    local exit_code=$?
    
    if [ $exit_code -ne 0 ] && [ "$STOP_ON_FAIL" = true ]; then
        echo -e "\033[31m$test_description failed with exit code $exit_code\033[0m"
        exit $exit_code
    fi
    
    return $exit_code
}

# Run tests based on type
case $TEST_TYPE in
    "manual")
        echo -e "\033[36mRunning manual integration tests...\033[0m"
        if [ ! -z "$TEST_NAME" ]; then
            run_test "python test_api.py $TEST_NAME" "Manual test: $TEST_NAME"
        else
            run_test "python test_api.py" "All manual tests"
        fi
        ;;
        
    "unit")
        echo -e "\033[36mRunning unit tests...\033[0m"
        if [ "$VERBOSE" = true ]; then
            run_test "pytest test_unit.py::TestTCAPI -v --tb=short" "Unit tests (verbose)"
        else
            run_test "pytest test_unit.py::TestTCAPI" "Unit tests"
        fi
        ;;
        
    "integration")
        echo -e "\033[36mRunning integration tests...\033[0m"
        if [ "$VERBOSE" = true ]; then
            run_test "pytest test_unit.py::TestIntegration -v --tb=short" "Integration tests (verbose)"
        else
            run_test "pytest test_unit.py::TestIntegration" "Integration tests"
        fi
        ;;
        
    "performance")
        echo -e "\033[36mRunning performance tests...\033[0m"
        if [ "$VERBOSE" = true ]; then
            run_test "pytest test_unit.py::TestPerformance -v --tb=short" "Performance tests (verbose)"
        else
            run_test "pytest test_unit.py::TestPerformance" "Performance tests"
        fi
        ;;
        
    "all")
        echo -e "\033[36mRunning all tests...\033[0m"
        echo ""
        
        # Manual tests
        echo -e "\033[35m1. Manual Integration Tests\033[0m"
        echo -e "\033[35m============================\033[0m"
        run_test "python test_api.py" "Manual integration tests"
        
        echo ""
        
        # Unit tests
        echo -e "\033[35m2. Automated Unit Tests\033[0m"
        echo -e "\033[35m=======================\033[0m"
        if [ "$VERBOSE" = true ]; then
            run_test "pytest test_unit.py -v --tb=short" "All automated tests (verbose)"
        else
            run_test "pytest test_unit.py" "All automated tests"
        fi
        ;;
        
    *)
        echo -e "\033[31mInvalid test type: $TEST_TYPE\033[0m"
        echo -e "\033[33mValid options: all, manual, unit, integration, performance\033[0m"
        exit 1
        ;;
esac

echo ""
echo -e "\033[32mTest execution completed!\033[0m"
echo ""
echo -e "\033[32mTest runner finished.\033[0m"
