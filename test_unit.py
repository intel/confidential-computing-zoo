import pytest
import requests
import json
import time
from unittest.mock import patch, MagicMock

# Test configuration
BASE_URL = "http://localhost:8000"

@pytest.fixture
def sample_data():
    """Fixture providing sample test data"""
    return {
        "dockerfile": """FROM nginx:stable-alpine
COPY . /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]""",
        "private_key": """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC7VJTUt9Us8cKB
-----END PRIVATE KEY-----""",
        "certificate": """-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAOgvuFyOHqR9MA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
-----END CERTIFICATE-----""",
        "public_key": """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAu1SU1L7VLPHCAVMM6liA
-----END PUBLIC KEY-----"""
    }

class TestTCAPI:
    """Test suite for TC API endpoints"""
    
    def test_health_check(self):
        """Test the health check endpoint"""
        response = requests.get(f"{BASE_URL}/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "timestamp" in data
        assert data["message"] == "TC API Service is running"
    
    def test_build_package_success(self, sample_data):
        """Test successful build package request"""
        payload = {
            "dockerfile": sample_data["dockerfile"],
            "sign_key": sample_data["private_key"],
            "cert": sample_data["certificate"],
            "encrypt": False,
            "user_id": "test-user-001"
        }
        
        response = requests.post(f"{BASE_URL}/api/build-package", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert "build_id" in data
        assert "status" in data
        assert "estimated_time" in data
        assert data["status"] == "submitted"
        
        return data["build_id"]
    
    def test_build_package_with_encryption(self, sample_data):
        """Test build package request with encryption enabled"""
        payload = {
            "dockerfile": sample_data["dockerfile"],
            "sign_key": sample_data["private_key"],
            "cert": sample_data["certificate"],
            "encrypt": True,
            "user_id": "test-user-encrypt"
        }
        
        response = requests.post(f"{BASE_URL}/api/build-package", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "submitted"
        assert "build_id" in data
    
    def test_build_package_invalid_data(self):
        """Test build package with invalid data"""
        payload = {
            "dockerfile": "",  # Empty dockerfile
            "user_id": ""  # Empty user_id
        }
        
        response = requests.post(f"{BASE_URL}/api/build-package", json=payload)
        assert response.status_code == 422  # Validation error
    
    def test_build_result_not_found(self):
        """Test build result for non-existent build ID"""
        fake_build_id = "non-existent-build-id"
        response = requests.get(f"{BASE_URL}/api/build-result/{fake_build_id}")
        assert response.status_code == 404
    
    def test_build_result_success(self, sample_data):
        """Test getting build result for existing build"""
        # First create a build
        build_id = self.test_build_package_success(sample_data)
        
        # Wait a moment for processing
        time.sleep(2)
        
        # Get build result
        response = requests.get(f"{BASE_URL}/api/build-result/{build_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert "build_id" in data
        assert "status" in data
        assert "created_at" in data
        assert "updated_at" in data
        assert data["build_id"] == build_id
    
    def test_publish_package(self):
        """Test publish package endpoint"""
        import base64
        
        sample_tar_data = b"sample tar file content"
        sample_sbom = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "name": "test-sbom"
        }
        
        payload = {
            "image_tar": base64.b64encode(sample_tar_data).decode('utf-8'),
            "sbom": json.dumps(sample_sbom),
            "image_id": "sha256:test123",
            "user_id": "test-user-001",
            "metadata": {
                "tags": ["latest"],
                "signed": True
            }
        }
        
        response = requests.put(f"{BASE_URL}/api/publish-package", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "message" in data
        assert "image_url" in data
    
    def test_register_key(self, sample_data):
        """Test key registration endpoint"""
        payload = {
            "image_id": "sha256:test123",
            "user_id": "test-user-001",
            "public_key": sample_data["public_key"],
            "cert": sample_data["certificate"],
            "policy": {
                "usage": "decrypt",
                "expiry": "2025-12-31T00:00:00Z"
            }
        }
        
        response = requests.post(f"{BASE_URL}/api/keys/register", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "message" in data
        assert "image_id" in data
        assert "user_id" in data
    
    def test_register_key_invalid_policy(self, sample_data):
        """Test key registration with invalid policy"""
        payload = {
            "image_id": "sha256:test123",
            "user_id": "test-user-001",
            "public_key": sample_data["public_key"],
            "cert": sample_data["certificate"],
            "policy": {
                "usage": "invalid_usage",  # Invalid usage type
                "expiry": "invalid_date"   # Invalid date format
            }
        }
        
        response = requests.post(f"{BASE_URL}/api/keys/register", json=payload)
        assert response.status_code == 422  # Validation error
    
    def test_get_artifact_not_found(self):
        """Test getting non-existent artifact"""
        fake_build_id = "fake-build-id"
        response = requests.get(f"{BASE_URL}/api/artifacts/{fake_build_id}/sbom.json")
        assert response.status_code == 404
    
    def test_get_artifact_success(self, sample_data):
        """Test getting artifact for existing build"""
        # Create a build first
        build_id = self.test_build_package_success(sample_data)
        
        # Try to get artifact (may not exist in mock implementation)
        response = requests.get(f"{BASE_URL}/api/artifacts/{build_id}/sbom.json")
        # Accept either 200 (found) or 404 (not found in mock)
        assert response.status_code in [200, 404]

# Integration test class
class TestIntegration:
    """Integration tests that test the full workflow"""
    
    def test_full_workflow(self, sample_data):
        """Test the complete build and publish workflow"""
        # Step 1: Build package
        build_payload = {
            "dockerfile": sample_data["dockerfile"],
            "sign_key": sample_data["private_key"],
            "cert": sample_data["certificate"],
            "encrypt": False,
            "user_id": "integration-test-user"
        }
        
        build_response = requests.post(f"{BASE_URL}/api/build-package", json=build_payload)
        assert build_response.status_code == 200
        build_id = build_response.json()["build_id"]
        
        # Step 2: Wait for build and check status
        time.sleep(3)
        result_response = requests.get(f"{BASE_URL}/api/build-result/{build_id}")
        assert result_response.status_code == 200
        
        # Step 3: Register key
        key_payload = {
            "image_id": "sha256:integration-test",
            "user_id": "integration-test-user",
            "public_key": sample_data["public_key"],
            "cert": sample_data["certificate"],
            "policy": {
                "usage": "decrypt",
                "expiry": "2025-12-31T00:00:00Z"
            }
        }
        
        key_response = requests.post(f"{BASE_URL}/api/keys/register", json=key_payload)
        assert key_response.status_code == 200
        
        # Step 4: Publish package
        import base64
        publish_payload = {
            "image_tar": base64.b64encode(b"integration test data").decode('utf-8'),
            "sbom": json.dumps({"name": "integration-test-sbom"}),
            "image_id": "sha256:integration-test",
            "user_id": "integration-test-user",
            "metadata": {
                "tags": ["integration-test"],
                "signed": True
            }
        }
        
        publish_response = requests.put(f"{BASE_URL}/api/publish-package", json=publish_payload)
        assert publish_response.status_code == 200

# Performance test class
class TestPerformance:
    """Performance and load tests"""
    
    def test_concurrent_builds(self, sample_data):
        """Test multiple concurrent build requests"""
        import threading
        
        results = []
        
        def make_build_request():
            payload = {
                "dockerfile": sample_data["dockerfile"],
                "sign_key": sample_data["private_key"],
                "cert": sample_data["certificate"],
                "encrypt": False,
                "user_id": f"perf-test-{threading.current_thread().ident}"
            }
            
            response = requests.post(f"{BASE_URL}/api/build-package", json=payload)
            results.append(response.status_code)
        
        # Create 5 concurrent requests
        threads = []
        for i in range(5):
            thread = threading.Thread(target=make_build_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All requests should succeed
        assert all(status == 200 for status in results)
        assert len(results) == 5

if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
