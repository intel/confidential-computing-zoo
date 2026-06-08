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

import requests
import time
import base64
import os

BASE_URL = os.getenv("TC_API_BASE_URL", "http://localhost:8000")

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
        #"identity_token": 'serialized_token'
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

def test_publish_package():
    """Test publish package endpoint"""
    print("\nTesting publish package...")
    import time
    print(time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(time.time())))
    payload = {
        "build_id": "bld-71b8057",
        "image_id": "oci:./builds/bld-71b8057/test-bld-71b8057",
        "user_id": "test-user",
        "sbom_url": "./builds/bld-71b8057/bld-71b8057-sbom.json",
        "log_evidence": True
    }
    
    response = requests.post(f"{BASE_URL}/api/publish-package", json=payload)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

    if response.status_code != 200:
        print(f"Build submission failed: {response.text}")
        return None

    data = response.json()
    print(f"Build ID: {data}")
    print(time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(time.time())))
    return None

def test_deploy_launch(image_id="test-bld-71b8057"):
    """Test deploy launch endpoint"""
    print("\nTesting deploy launch...")
    
    payload = {
        "image_id": image_id,
        #"build_id": "bld-71b8057",
        "user_id": "test_user",
        "image_url": "docker.io/testsig/test-bld-71b8057:latest-encrypted",
        "sbom_url": "./builds/bld-71b8057/bld-71b8057-sbom.json",
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
    else:
        run_comprehensive_tests()
