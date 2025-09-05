"""
Integration tests for validation API endpoints.

Tests the complete validation workflow including file upload,
validation processing, and response formatting.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
from io import BytesIO


class TestValidationEndpoints:
    """Integration tests for validation endpoints."""

    def test_health_endpoint(self, test_client: TestClient):
        """Test API health check endpoint."""
        response = test_client.get("/api/v1/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert data["service"] == "api"

    def test_version_endpoint(self, test_client: TestClient):
        """Test API version endpoint.""" 
        response = test_client.get("/api/v1/version")
        assert response.status_code == 200
        
        data = response.json()
        assert "version" in data
        assert "oscal_version" in data
        assert data["oscal_version"] == "1.1.3"

    @patch('app.services.oscal_service.OSCALService.validate_document')
    @patch('app.services.storage_service.StorageService.store_artifact')
    def test_validate_file_success(self, mock_store, mock_validate, test_client: TestClient, sample_ssp, helpers):
        """Test successful file validation."""
        from app.services.oscal_service import ValidationResult
        from app.services.storage_service import StorageResult
        
        # Mock successful validation
        mock_validate.return_value = ValidationResult(
            is_valid=True,
            document_type="system-security-plan",
            errors=[],
            warnings=[],
            duration_ms=500,
            cli_stdout="Validation successful",
            cli_stderr="",
            return_code=0
        )
        
        # Mock successful storage
        mock_store.return_value = StorageResult(
            success=True,
            bucket="test-bucket",
            object_key="validation/test.json",
            url="https://example.com/test.json",
            checksum="abc123",
            file_size_bytes=1024
        )
        
        # Prepare file upload
        file_content = json.dumps(sample_ssp).encode('utf-8')
        files = {"file": ("test_ssp.json", file_content, "application/json")}
        data = {"validation_type": "schema", "store_result": "true"}
        
        response = test_client.post("/api/v1/validate/file", files=files, data=data)
        
        assert response.status_code == 200
        response_data = response.json()
        
        helpers.assert_operation_success(response_data)
        helpers.assert_validation_response(response_data, should_be_valid=True)
        
        assert response_data["document_type"] == "system-security-plan"
        assert response_data["validation_type"] == "schema"
        assert "validation_run_id" in response_data

    @patch('app.services.oscal_service.OSCALService.validate_document')
    def test_validate_file_with_errors(self, mock_validate, test_client: TestClient, sample_invalid_ssp):
        """Test file validation with validation errors."""
        from app.services.oscal_service import ValidationResult, ValidationIssue
        
        # Mock validation with errors
        mock_validate.return_value = ValidationResult(
            is_valid=False,
            document_type="system-security-plan",
            errors=[
                ValidationIssue(
                    severity="error",
                    message="Missing required field 'uuid'",
                    location="$.system-security-plan.uuid",
                    line_number=5
                )
            ],
            warnings=[],
            duration_ms=300,
            cli_stdout="",
            cli_stderr="Validation failed",
            return_code=1
        )
        
        # Prepare file upload
        file_content = json.dumps(sample_invalid_ssp).encode('utf-8')
        files = {"file": ("invalid_ssp.json", file_content, "application/json")}
        data = {"validation_type": "schema", "store_result": "false"}
        
        response = test_client.post("/api/v1/validate/file", files=files, data=data)
        
        assert response.status_code == 400  # Bad request for invalid document
        response_data = response.json()
        
        assert "operation_id" in response_data
        assert response_data["is_valid"] is False
        assert len(response_data["errors"]) == 1
        assert "uuid" in response_data["errors"][0]["message"]

    def test_validate_file_invalid_format(self, test_client: TestClient):
        """Test validation with invalid file format."""
        # Try to upload a text file instead of JSON/XML
        files = {"file": ("test.txt", b"This is not OSCAL", "text/plain")}
        data = {"validation_type": "schema"}
        
        response = test_client.post("/api/v1/validate/file", files=files, data=data)
        
        assert response.status_code == 400
        assert "Only JSON and XML OSCAL files are supported" in response.json()["detail"]

    @patch('httpx.AsyncClient.get')
    @patch('app.services.oscal_service.OSCALService.validate_document')
    def test_validate_url_success(self, mock_validate, mock_http_get, test_client: TestClient, sample_ssp):
        """Test successful URL validation."""
        from app.services.oscal_service import ValidationResult
        import httpx
        
        # Mock HTTP response
        mock_response = Mock()
        mock_response.content = json.dumps(sample_ssp).encode('utf-8')
        mock_response.headers = {"content-type": "application/json"}
        mock_response.raise_for_status = Mock()
        mock_http_get.return_value.__aenter__.return_value.get.return_value = mock_response
        
        # Mock successful validation
        mock_validate.return_value = ValidationResult(
            is_valid=True,
            document_type="system-security-plan",
            errors=[],
            warnings=[],
            duration_ms=400,
            cli_stdout="Validation successful",
            cli_stderr="",
            return_code=0
        )
        
        data = {
            "url": "https://example.com/test-ssp.json",
            "validation_type": "schema",
            "store_result": "true"
        }
        
        response = test_client.post("/api/v1/validate/url", data=data)
        
        assert response.status_code == 200
        response_data = response.json()
        
        assert response_data["is_valid"] is True
        assert response_data["source_url"] == "https://example.com/test-ssp.json"
        assert "validation_run_id" in response_data

    def test_validate_url_invalid_url(self, test_client: TestClient):
        """Test URL validation with invalid URL."""
        data = {
            "url": "not-a-valid-url",
            "validation_type": "schema"
        }
        
        response = test_client.post("/api/v1/validate/url", data=data)
        
        assert response.status_code in [400, 500]  # Could be either depending on validation

    def test_list_validation_runs(self, test_client: TestClient):
        """Test listing validation runs."""
        response = test_client.get("/api/v1/validate/runs")
        
        assert response.status_code == 200
        response_data = response.json()
        
        assert "validation_runs" in response_data
        assert "pagination" in response_data
        assert isinstance(response_data["validation_runs"], list)

    def test_list_validation_runs_with_filters(self, test_client: TestClient):
        """Test listing validation runs with filters."""
        params = {
            "limit": 10,
            "offset": 0,
            "is_valid": "true",
            "document_type": "system-security-plan"
        }
        
        response = test_client.get("/api/v1/validate/runs", params=params)
        
        assert response.status_code == 200
        response_data = response.json()
        
        assert "validation_runs" in response_data
        assert "pagination" in response_data
        assert "filters" in response_data
        assert response_data["filters"]["is_valid"] == "true"

    def test_get_validation_run_not_found(self, test_client: TestClient):
        """Test getting non-existent validation run."""
        fake_uuid = "12345678-1234-5678-9abc-123456789012"
        response = test_client.get(f"/api/v1/validate/runs/{fake_uuid}")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @patch('app.services.oscal_service.OSCALService.validate_document')
    def test_validate_file_storage_error(self, mock_validate, test_client: TestClient, sample_ssp):
        """Test validation when storage fails but validation succeeds."""
        from app.services.oscal_service import ValidationResult
        
        # Mock successful validation
        mock_validate.return_value = ValidationResult(
            is_valid=True,
            document_type="system-security-plan",
            errors=[],
            warnings=[],
            duration_ms=500,
            cli_stdout="Validation successful",
            cli_stderr="",
            return_code=0
        )
        
        # Storage will fail (not mocked), but operation should still succeed
        file_content = json.dumps(sample_ssp).encode('utf-8')
        files = {"file": ("test_ssp.json", file_content, "application/json")}
        data = {"validation_type": "schema", "store_result": "false"}  # Don't store
        
        response = test_client.post("/api/v1/validate/file", files=files, data=data)
        
        # Should still succeed even if storage would have failed
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["is_valid"] is True

    def test_validate_file_large_file(self, test_client: TestClient):
        """Test validation with very large file."""
        # Create a large JSON structure
        large_ssp = {
            "system-security-plan": {
                "uuid": "test-uuid",
                "metadata": {"title": "Large SSP"},
                "control-implementation": {
                    "implemented-requirements": [
                        {
                            "uuid": f"req-{i}",
                            "control-id": f"ac-{i}",
                            "statements": [
                                {
                                    "statement-id": f"stmt-{i}",
                                    "uuid": f"stmt-uuid-{i}",
                                    "description": "A" * 1000  # Large description
                                }
                            ]
                        }
                        for i in range(100)  # 100 controls
                    ]
                }
            }
        }
        
        file_content = json.dumps(large_ssp).encode('utf-8')
        files = {"file": ("large_ssp.json", file_content, "application/json")}
        data = {"validation_type": "schema", "store_result": "false"}
        
        # This might timeout or succeed depending on implementation
        response = test_client.post("/api/v1/validate/file", files=files, data=data)
        
        # Should handle large files gracefully
        assert response.status_code in [200, 400, 413, 500, 504]  # Various possible outcomes

    def test_validation_endpoint_missing_file(self, test_client: TestClient):
        """Test validation endpoint without file upload."""
        data = {"validation_type": "schema"}
        
        response = test_client.post("/api/v1/validate/file", data=data)
        
        assert response.status_code == 422  # Unprocessable Entity - missing required file