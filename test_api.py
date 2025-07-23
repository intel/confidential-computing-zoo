import requests
import json
import time

# API base URL
BASE_URL = "http://localhost:8000"

def test_health_check():
    """Test health check endpoint"""
    print("Testing health check...")
    response = requests.get(f"{BASE_URL}/")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    print("-" * 50)

def test_build_package():
    """Test build package endpoint"""
    print("Testing build package...")
    
    dockerfile_content = """
FROM nginx:stable-alpine
EXPOSE 80
"""
    
    payload = {
        "dockerfile": dockerfile_content,
        "sign_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----",
        "cert": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
        "encrypt": False,
        "user_id": "user-001"
    }
    
    response = requests.post(f"{BASE_URL}/api/build-package", json=payload)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Build ID: {result['build_id']}")
        print(f"Status: {result['status']}")
        print(f"Estimated Time: {result['estimated_time']}")
        return result['build_id']
    else:
        print(f"Error: {response.text}")
        return None
    
    print("-" * 50)

def test_build_result(build_id):
    """Test build result endpoint"""
    if not build_id:
        return
    
    print(f"Testing build result for {build_id}...")
    
    # Wait a bit for the build to process
    time.sleep(2)
    
    response = requests.get(f"{BASE_URL}/api/build-result/{build_id}")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Build Status: {result['status']}")
        print(f"Created At: {result['created_at']}")
        print(f"Updated At: {result['updated_at']}")
        if result.get('image_id'):
            print(f"Image ID: {result['image_id']}")
    else:
        print(f"Error: {response.text}")
    
    print("-" * 50)

def test_register_key():
    """Test key registration endpoint"""
    print("Testing key registration...")
    
    payload = {
        "image_id": "sha256:abcd1234",
        "user_id": "user-001",
        "public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----",
        "cert": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
        "policy": {
            "usage": "decrypt",
            "expiry": "2025-12-31T00:00:00Z"
        }
    }
    
    response = requests.post(f"{BASE_URL}/api/keys/register", json=payload)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Registration Status: {result['status']}")
        print(f"Message: {result['message']}")
    else:
        print(f"Error: {response.text}")
    
    print("-" * 50)

if __name__ == "__main__":
    print("TC API Test Script")
    print("=" * 50)
    
    try:
        # Test health check
        test_health_check()
        
        # Test build package
        build_id = test_build_package()
        
        # Test build result
        test_build_result(build_id)
        
        # Test key registration
        test_register_key()
        
        print("All tests completed!")
        
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to TC API service.")
        print("Please make sure the service is running on http://localhost:8000")
    except Exception as e:
        print(f"Error running tests: {str(e)}")
