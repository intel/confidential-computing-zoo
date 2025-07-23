import requests
import json
import time
import base64
import os

# API base URL
BASE_URL = "http://localhost:8000"

# Sample data for testing
SAMPLE_DOCKERFILE = """FROM nginx:stable-alpine
COPY . /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
"""

SAMPLE_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC7VJTUt9Us8cKB
UwzqWIDqF9I+ZiU1QgQp4HYbXL3CG7n8YVhHE0YO7p8vK2YW1W8ZL7v3XG+l
-----END PRIVATE KEY-----"""

SAMPLE_CERTIFICATE = """-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAOgvuFyOHqR9MA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX
-----END CERTIFICATE-----"""

SAMPLE_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAu1SU1L7VLPHCAVMM6liA
6hfSPmYlNUIEKeB2G1y9whu5/GFYRxNGDu6fLytmFtVvGS+791xvpQ==
-----END PUBLIC KEY-----"""

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
    
    payload = {
        "dockerfile": SAMPLE_DOCKERFILE,
        "sign_key": SAMPLE_PRIVATE_KEY,
        "cert": SAMPLE_CERTIFICATE,
        "encrypt": True,
        "user_id": "test-user-001"
    }
    
    response = requests.post(f"{BASE_URL}/api/build-package", json=payload)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Build ID: {result['build_id']}")
        print(f"Status: {result['status']}")
        print(f"Estimated Time: {result['estimated_time']}")
        print("-" * 50)
        return result['build_id']
    else:
        print(f"Error: {response.text}")
        print("-" * 50)
        return None

def test_build_result(build_id):
    """Test build result endpoint"""
    if not build_id:
        print("Skipping build result test - no build ID")
        print("-" * 50)
        return None
    
    print(f"Testing build result for {build_id}...")
    
    # Wait a bit for the build to process
    print("Waiting for build to process...")
    time.sleep(3)
    
    response = requests.get(f"{BASE_URL}/api/build-result/{build_id}")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Build ID: {result['build_id']}")
        print(f"Build Status: {result['status']}")
        print(f"Created At: {result['created_at']}")
        print(f"Updated At: {result['updated_at']}")
        if result.get('image_id'):
            print(f"Image ID: {result['image_id']}")
        if result.get('sbom_url'):
            print(f"SBOM URL: {result['sbom_url']}")
        if result.get('image_url'):
            print(f"Image URL: {result['image_url']}")
        if result.get('error_message'):
            print(f"Error: {result['error_message']}")
        print("-" * 50)
        return result
    else:
        print(f"Error: {response.text}")
        print("-" * 50)
        return None

def test_publish_package():
    """Test publish package endpoint"""
    print("Testing publish package...")
    
    # Generate some sample binary data for image tar
    sample_tar_data = b"sample tar file content for testing"
    sample_sbom_data = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "test-image-sbom",
        "packages": []
    }
    
    payload = {
        "image_tar": base64.b64encode(sample_tar_data).decode('utf-8'),
        "sbom": json.dumps(sample_sbom_data),
        "image_id": "sha256:abcd1234567890",
        "user_id": "test-user-001",
        "metadata": {
            "tags": ["latest", "v1.0"],
            "signed": True,
            "registry": "docker.io/myrepo"
        }
    }
    
    response = requests.put(f"{BASE_URL}/api/publish-package", json=payload)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Status: {result['status']}")
        print(f"Message: {result['message']}")
        if result.get('image_url'):
            print(f"Image URL: {result['image_url']}")
        if result.get('published_at'):
            print(f"Published At: {result['published_at']}")
    else:
        print(f"Error: {response.text}")
    
    print("-" * 50)

def test_get_artifact(build_id, artifact_type="sbom.json"):
    """Test get artifact endpoint"""
    if not build_id:
        print("Skipping artifact test - no build ID")
        print("-" * 50)
        return
    
    print(f"Testing get artifact for build {build_id}, type: {artifact_type}...")
    
    response = requests.get(f"{BASE_URL}/api/artifacts/{build_id}/{artifact_type}")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Message: {result['message']}")
        print(f"Path: {result['path']}")
    elif response.status_code == 404:
        print("Artifact not found (expected for mock implementation)")
    else:
        print(f"Error: {response.text}")
    
    print("-" * 50)

def test_register_key():
    """Test key registration endpoint"""
    print("Testing key registration...")
    
    payload = {
        "image_id": "sha256:abcd1234567890",
        "user_id": "test-user-001",
        "public_key": SAMPLE_PUBLIC_KEY,
        "cert": SAMPLE_CERTIFICATE,
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
        if result.get('image_id'):
            print(f"Image ID: {result['image_id']}")
        if result.get('user_id'):
            print(f"User ID: {result['user_id']}")
        if result.get('registered_at'):
            print(f"Registered At: {result['registered_at']}")
    else:
        print(f"Error: {response.text}")
    
    print("-" * 50)

def run_comprehensive_tests():
    """Run all API tests in sequence"""
    print("TC API Comprehensive Test Suite")
    print("=" * 60)
    
    try:
        # Test 1: Health check
        test_health_check()
        
        # Test 2: Build package
        build_id = test_build_package()
        
        # Test 3: Get build result (poll for completion)
        build_result = None
        if build_id:
            print("Waiting for build to complete...")
            for attempt in range(5):  # Poll up to 5 times
                build_result = test_build_result(build_id)
                if build_result and build_result.get('status') in ['success', 'failed']:
                    break
                print(f"Build still in progress (attempt {attempt + 1}/5)...")
                time.sleep(5)
        
        # Test 4: Publish package
        test_publish_package()
        
        # Test 5: Register key
        test_register_key()
        
        # Test 6: Get artifacts
        if build_id:
            test_get_artifact(build_id, "sbom.json")
            test_get_artifact(build_id, "log.txt")
            test_get_artifact(build_id, "cert.pem")
        
        print("=" * 60)
        print("All tests completed successfully!")
        
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to TC API service.")
        print("Please make sure the service is running on http://localhost:8000")
    except Exception as e:
        print(f"Error running tests: {str(e)}")

def run_single_test(test_name):
    """Run a single test by name"""
    test_functions = {
        "health": test_health_check,
        "build": test_build_package,
        "publish": test_publish_package,
        "register": test_register_key,
    }
    
    if test_name in test_functions:
        print(f"Running single test: {test_name}")
        print("-" * 40)
        test_functions[test_name]()
    else:
        print(f"Unknown test: {test_name}")
        print(f"Available tests: {', '.join(test_functions.keys())}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        run_single_test(test_name)
    else:
        run_comprehensive_tests()
