import requests
import json
import time
import base64
from datetime import datetime

BASE_URL = "http://localhost:8000"

def test_health_check():
    """Test health check endpoint"""
    print("\nTesting health check...")
    response = requests.get(f"{BASE_URL}/")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

def test_build_package():
    """Test build package endpoint"""
    print("\nTesting build package...")
    
    payload = {
        "dockerfile": "FROM python:3.9-slim\nWORKDIR /app\nCOPY . .",
        "app_binary": base64.b64encode(b"test binary").decode(),
        "configs": [base64.b64encode(b"config1").decode()],
        "data": [base64.b64encode(b"data1").decode()],
        "encrypt": True,
        "user_id": "test-user"
    }
    
    response = requests.post(f"{BASE_URL}/api/build-package", json=payload)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Build ID: {data['build_id']}")
        print(f"Status: {data['status']}")
        return data['build_id']
    return None

def test_publish_package(image_id="sha256:test123"):
    """Test publish package endpoint"""
    print("\nTesting publish package...")
    
    payload = {
        "image_id": image_id,
        "user_id": "test-user",
        "log_evidence": True,
        "metadata": {
            "tags": ["latest", "v1.0"],
            "description": "Test image"
        }
    }
    
    response = requests.put(f"{BASE_URL}/api/publish-package", json=payload)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

def test_deploy_launch(image_id="sha256:test123"):
    """Test deploy launch endpoint"""
    print("\nTesting deploy launch...")
    
    payload = {
        "image_id": image_id,
        "user_id": "test-user",
        "image_url": "docker.io/myrepo/test:latest",
        "sbom_url": "https://registry.example.com/sbom.json",
        "attestation_required": True
    }
    
    response = requests.post(f"{BASE_URL}/api/deploy-launch", json=payload)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Launch ID: {data['launch_id']}")
        print(f"Status: {data['status']}")
        return data['launch_id']
    return None

def test_launch_result(launch_id):
    """Test launch result endpoint"""
    print(f"\nTesting launch result for {launch_id}...")
    
    response = requests.get(f"{BASE_URL}/api/launch-result/{launch_id}")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Response: {response.json()}")

def run_comprehensive_tests():
    """Run all API tests in sequence"""
    print("\nTC API Comprehensive Test Suite")
    print("=" * 60)
    
    try:
        # Test health check
        test_health_check()
        
        # Test build package
        build_id = test_build_package()
        if build_id:
            time.sleep(2)  # Wait for processing
            
        # Test publish package
        test_publish_package()
        
        # Test deploy launch
        launch_id = test_deploy_launch()
        if launch_id:
            time.sleep(2)  # Wait for processing
            test_launch_result(launch_id)
        
        print("\nAll tests completed!")
        
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to TC API service")
    except Exception as e:
        print(f"Error running tests: {str(e)}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        if test_name == "health":
            test_health_check()
        elif test_name == "build":
            test_build_package()
        elif test_name == "publish":
            test_publish_package()
        elif test_name == "launch":
            test_deploy_launch()
    else:
        run_comprehensive_tests()
