import requests
import json
import time
import base64
import glob
import os
from pathlib import Path


BASE_URL = "http://localhost:8000"

def test_health_check():
    """Test health check endpoint"""
    print("\nTesting health check...")
    response = requests.get(f"{BASE_URL}/")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

def test_build_package():
    """Test build package endpoint with status monitoring"""
    print("\nTesting build package...")
    
    payload = {
        "dockerfile": "FROM python:3.9-slim\nWORKDIR /app\nCOPY . .",
        "app_binary": base64.b64encode(b"test binary").decode(),
        "configs": [base64.b64encode(b"config1").decode()],
        "data": [base64.b64encode(b"data1").decode()],
        "encrypt": True,
        "user_id": "test-user"
    }
    
    # Submit build request
    response = requests.post(f"{BASE_URL}/api/build-package", json=payload)
    print(f"Initial Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"Build submission failed: {response.text}")
        return None
        
    data = response.json()
    build_id = data['build_id']
    print(f"Build ID: {build_id}")
    print(f"Initial Status: {data['status']}")
    
    # Monitor build status
    max_attempts = 30  # Maximum number of status checks
    check_interval = 5 # Time between checks in seconds
    current_attempt = 0
    
    while current_attempt < max_attempts:
        time.sleep(check_interval)
        status_response = requests.get(f"{BASE_URL}/api/build-result/{build_id}")
        
        if status_response.status_code != 200:
            print(f"Failed to get build status: {status_response.text}")
            return None
            
        status_data = status_response.json()
        current_status = status_data.get('status')
        print(f"Current Status: {current_status}")
        
        # Check for terminal states
        if current_status == "success":
            print("Build completed successfully!")
            print(f"Image URL: {status_data.get('image_url')}")
            print(f"SBOM URL: {status_data.get('sbom_url')}")
            print(status_data)
            return build_id
        elif current_status == "failed":
            print(f"Build failed: {status_data.get('error_message')}")
            return None
        elif current_status in ["submitted", "preparing", "building", "generating_sbom", "encrypting", "pushing", "signing"]:
            current_step = status_data.get('current_step', 'In progress')
            print(f"Build in progress... ({current_attempt + 1}/{max_attempts})")
            print(f"Current step: {current_step}")
        else:
            print(f"Unknown status: {current_status}")
            
        current_attempt += 1
    
    print("Build monitoring timed out")
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

def test_deploy_launch(image_id="test-bld-437a737"):
    """Test deploy launch endpoint"""
    print("\nTesting deploy launch...")
    
    payload = {
        "image_id": image_id,
        "user_id": "testsig",
        "image_url": "docker.io/testsig/test-bld-437a737:latest-encrypted",
        "sbom_url": "./builds/bld-437a737/bld-437a737-sbom.json",
        "attestation_required": True
    }
    
    response = requests.post(f"{BASE_URL}/api/deploy-launch", json=payload)
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"Launch failed: {response.text}")

    data = response.json()
    print(f"Launch ID: {data['launch_id']}")
    print(f"Status: {data['status']}")

    # Monitor build status
    max_attempts = 30  # Maximum number of status checks
    check_interval = 3 # Time between checks in seconds
    current_attempt = 0
    
    while current_attempt < max_attempts:
        time.sleep(check_interval)
        status_response = requests.get(f"{BASE_URL}/api/launch-result/{data['launch_id']}")
        
        if status_response.status_code != 200:
            print(f"Failed to get build status: {status_response.text}")
            return None
            
        status_data = status_response.json()
        current_status = status_data.get('status')
        print(f"Current Status: {current_status}")
        
        # Check for terminal states
        if current_status == "success":
            print("Launch completed successfully!")
            #print(f"Image URL: {status_data.get('image_url')}")
            #print(f"SBOM URL: {status_data.get('sbom_url')}")
            return None
        elif current_status == "failed":
            print(f"Launch failed: {status_data.get('error_message')}")
            return None
        elif current_status in ["initiated", "launching"]:
            print(f"Launch in progress... ({current_attempt + 1}/{max_attempts})")
            print(f"Current step: {current_status}")
        else:
            print(f"Unknown status: {current_status}")
            
        current_attempt += 1
    
    print("Launch monitoring timed out")
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
        if not build_id:
            print("Build package test failed, skipping remaining tests")
            
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


def test_build_launch():
    """Test build and launch"""

    print("\nStart building ...\n")
    build_payload = {
        "dockerfile": "FROM python:3.9-slim\nWORKDIR /app\nCOPY . .",
        "app_binary": base64.b64encode(b"test binary").decode(),
        "configs": [base64.b64encode(b"config1").decode()],
        "data": [base64.b64encode(b"data1").decode()],
        "encrypt": True,
        "user_id": "testsig"
    }

    response = requests.post(f"{BASE_URL}/api/build-package", json=build_payload)
    print(f"Initial Status: {response.status_code}")

    if response.status_code != 200:
        print(f"Build submission failed: {response.text}")
        return None

    data = response.json()
    build_id = data['build_id']
    print(f"Build ID: {build_id}")
    print(f"Initial Status: {data['status']}")

    # Monitor build status
    max_attempts = 30  # Maximum number of status checks
    check_interval = 5 # Time between checks in seconds
    current_attempt = 0

    while current_attempt < max_attempts:
        time.sleep(check_interval)
        status_response = requests.get(f"{BASE_URL}/api/build-result/{build_id}")

        if status_response.status_code != 200:
            print(f"Failed to get build status: {status_response.text}")
            return None

        status_data = status_response.json()
        current_status = status_data.get('status')
        print(f"Current Status: {current_status}")

        # Check for terminal states
        if current_status == "success":
            print("Build completed successfully!")
            print(f"Image URL: {status_data.get('image_url')}")
            print(f"SBOM URL: {status_data.get('sbom_url')}")

            # return build_id
            print("\nStart launching ...")
            payload = {
                "image_id": status_data.get('image_id'),
                "user_id": "testsig",
                "image_url": "docker.io/testsig/"+status_data.get('image_id').split("/")[-1]+":latest-encrypted",
                "sbom_url": status_data.get('sbom_url'),
                "attestation_required": True
            }

            response = requests.post(f"{BASE_URL}/api/deploy-launch", json=payload)
            print(f"Status: {response.status_code}")
            if response.status_code != 200:
                print(f"Launch failed: {response.text}")

            data = response.json()
            print(f"Launch ID: {data['launch_id']}")
            print(f"Status: {data['status']}")

            while current_attempt < max_attempts:
                time.sleep(check_interval)
                s_response = requests.get(f"{BASE_URL}/api/launch-result/{data['launch_id']}")

                if s_response.status_code != 200:
                    print(f"Failed to get build status: {s_response.text}")
                    return None

                s_data = s_response.json()
                current_s = s_data.get('status')
                print(f"Current Status: {current_s}")

                # Check for terminal states
                if current_s == "success":
                    print("Launch completed successfully!")
                    return None
                elif current_s == "failed":
                    print(f"Launch failed: {s_data.get('error_message')}")
                    return None
                elif current_s in ["initiated", "launching"]:
                    print(f"Launch in progress... ({current_attempt + 1}/{max_attempts})")
                    print(f"Current step: {current_s}")
                else:
                    print(f"Unknown status: {current_s}")

                current_attempt += 1

            print("Launch monitoring timed out")
            return None

        elif current_status == "failed":
            print(f"Build failed: {status_data.get('error_message')}")
            return None
        elif current_status in ["submitted", "preparing", "building", "generating_sbom", "encrypting", "pushing", "signing"]:
            current_step = status_data.get('current_step', 'In progress')
            print(f"Build in progress... ({current_attempt + 1}/{max_attempts})")
            print(f"Current step: {current_step}")
        else:
            print(f"Unknown status: {current_status}")

        current_attempt += 1

    print("Build monitoring timed out")
    return None


def test_verify_tlog():
    """Test verify transparency log endpoint"""

    print("\nTesting verify transparency log...")

    PATH_PREFIX = "tlog/"
    RAW_FILE_LIST = sorted([os.path.basename(f) for f in glob.glob("tlog/*.json") if not f.endswith('.sigstore.json')])
    BUNDLE_FILE_LIST = sorted([os.path.basename(f) for f in glob.glob("tlog/entry*.sigstore.json")])
    CHAIN_FILE = "chain.sigstore.json"
    email_addr = "siyuan.hui@intel.com"

    print(f"Raw files: {RAW_FILE_LIST}")
    print(f"Bundle files: {BUNDLE_FILE_LIST}")
    print(f"Chain file: {CHAIN_FILE}")

    raw_file = {}
    bundle_file = {}
    for RAW_FILE, BUNDLE_FILE in zip(RAW_FILE_LIST, BUNDLE_FILE_LIST):
        raw_file_content = Path(PATH_PREFIX + RAW_FILE).read_text(encoding='utf-8')
        raw_file.update({RAW_FILE: raw_file_content})

        bundle_file_content = Path(PATH_PREFIX + BUNDLE_FILE).read_text(encoding='utf-8')
        bundle_file.update({BUNDLE_FILE: bundle_file_content})

    chain_file_content = Path(PATH_PREFIX + CHAIN_FILE).read_text(encoding='utf-8')
    chain_file = {CHAIN_FILE: chain_file_content}

    payload = {
        "raw_file": raw_file,
        "bundle_file": bundle_file,
        "chain_file": chain_file,
        "email_addr": email_addr
    }

    response = requests.post(f"{BASE_URL}/api/verify-tlog", json=payload)
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"Verification Success: {result['success']}")

        if result['success'] and result['summary']:
            print("Verification Summary:")
            print(json.dumps(result['summary'], indent=2))
        elif not result['success'] and result['error']:
            print(f"Verification Error: {result['error']}")
    else:
        print(f"Request failed: {response.text}")

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
        elif test_name == "build_launch":
            test_build_launch()
        elif test_name == "verify_tlog":
            test_verify_tlog()
    else:
        run_comprehensive_tests()
