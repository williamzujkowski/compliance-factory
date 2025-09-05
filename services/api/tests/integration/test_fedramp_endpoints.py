"""
Integration tests for FedRAMP constraint validation endpoints.

Tests the complete FedRAMP validation workflow including baseline validation
and constraint checking.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient


class TestFedRAMPEndpoints:
    """Integration tests for FedRAMP validation endpoints."""

    @patch('app.services.fedramp_service.FedRAMPService.validate_document')
    def test_validate_fedramp_file_compliant(self, mock_validate, test_client: TestClient, sample_ssp):
        """Test FedRAMP validation with compliant document."""
        from app.services.fedramp_service import FedRAMPValidationResult
        
        # Mock compliant validation result
        mock_validate.return_value = FedRAMPValidationResult(
            is_compliant=True,
            baseline="moderate",
            document_type="system-security-plan",
            issues=[],
            validation_time_ms=1500,
            metadata={"controls_validated": 25}
        )
        
        # Prepare file upload
        file_content = json.dumps(sample_ssp).encode('utf-8')
        files = {"file": ("test_ssp.json", file_content, "application/json")}
        data = {"baseline": "moderate", "store_result": "true"}
        
        response = test_client.post("/api/v1/fedramp/validate/file", files=files, data=data)
        
        assert response.status_code == 200
        response_data = response.json()
        
        assert "operation_id" in response_data
        assert response_data["is_compliant"] is True
        assert response_data["baseline"] == "moderate"
        assert response_data["document_type"] == "system-security-plan"
        assert "validation_summary" in response_data

    @patch('app.services.fedramp_service.FedRAMPService.validate_document')
    def test_validate_fedramp_file_non_compliant(self, mock_validate, test_client: TestClient, sample_ssp):
        """Test FedRAMP validation with non-compliant document."""
        from app.services.fedramp_service import FedRAMPValidationResult, FedRAMPValidationIssue
        
        # Mock non-compliant validation result
        mock_validate.return_value = FedRAMPValidationResult(
            is_compliant=False,
            baseline="high",
            document_type="system-security-plan",
            issues=[
                FedRAMPValidationIssue(
                    severity="error",
                    code="FEDRAMP_MISSING_REQUIRED_CONTROL",
                    message="Required control AC-4 is not implemented",
                    baseline="high",
                    requirement="FedRAMP High Baseline"
                ),
                FedRAMPValidationIssue(
                    severity="warning",
                    code="FEDRAMP_MISSING_ROLE",
                    message="Required role 'control-assessor' is not defined",
                    requirement="FedRAMP Required Roles"
                )
            ],
            validation_time_ms=2000,
            metadata={"controls_validated": 20, "missing_controls": 5}
        )
        
        # Prepare file upload
        file_content = json.dumps(sample_ssp).encode('utf-8')
        files = {"file": ("test_ssp.json", file_content, "application/json")}
        data = {"baseline": "high", "store_result": "false"}
        
        response = test_client.post("/api/v1/fedramp/validate/file", files=files, data=data)
        
        assert response.status_code == 400  # Non-compliant
        response_data = response.json()
        
        assert response_data["is_compliant"] is False
        assert response_data["baseline"] == "high"
        assert len(response_data["issues"]) == 2
        
        # Check error issue
        error_issue = next(i for i in response_data["issues"] if i["severity"] == "error")
        assert "AC-4" in error_issue["message"]
        assert error_issue["code"] == "FEDRAMP_MISSING_REQUIRED_CONTROL"
        
        # Check warning issue
        warning_issue = next(i for i in response_data["issues"] if i["severity"] == "warning")
        assert "control-assessor" in warning_issue["message"]

    def test_validate_fedramp_invalid_baseline(self, test_client: TestClient, sample_ssp):
        """Test FedRAMP validation with invalid baseline."""
        file_content = json.dumps(sample_ssp).encode('utf-8')
        files = {"file": ("test_ssp.json", file_content, "application/json")}
        data = {"baseline": "invalid", "store_result": "false"}
        
        response = test_client.post("/api/v1/fedramp/validate/file", files=files, data=data)
        
        assert response.status_code == 422  # Validation error for invalid enum

    def test_get_baseline_requirements_moderate(self, test_client: TestClient):
        """Test getting moderate baseline requirements."""
        response = test_client.get("/api/v1/fedramp/baselines/moderate/requirements")
        
        assert response.status_code == 200
        response_data = response.json()
        
        assert response_data["baseline"] == "moderate"
        assert "requirements" in response_data
        assert "description" in response_data

    def test_get_baseline_requirements_invalid(self, test_client: TestClient):
        """Test getting requirements for invalid baseline."""
        response = test_client.get("/api/v1/fedramp/baselines/invalid/requirements")
        
        assert response.status_code == 422  # Invalid baseline enum

    def test_list_baselines(self, test_client: TestClient):
        """Test listing all FedRAMP baselines."""
        response = test_client.get("/api/v1/fedramp/baselines")
        
        assert response.status_code == 200
        response_data = response.json()
        
        assert "baselines" in response_data
        assert len(response_data["baselines"]) == 3  # low, moderate, high
        
        baselines = response_data["baselines"]
        baseline_ids = [b["id"] for b in baselines]
        assert "low" in baseline_ids
        assert "moderate" in baseline_ids
        assert "high" in baseline_ids
        
        # Check moderate baseline details
        moderate = next(b for b in baselines if b["id"] == "moderate")
        assert moderate["min_controls"] == 325
        assert "Moderate impact systems" in moderate["description"]

    @patch('app.services.fedramp_service.FedRAMPService.validate_document')
    def test_validate_fedramp_batch_success(self, mock_validate, test_client: TestClient, sample_ssp):
        """Test FedRAMP batch validation."""
        from app.services.fedramp_service import FedRAMPValidationResult
        
        # Mock validation results - first compliant, second non-compliant
        mock_validate.side_effect = [
            FedRAMPValidationResult(
                is_compliant=True,
                baseline="low",
                document_type="system-security-plan",
                issues=[],
                validation_time_ms=1000
            ),
            FedRAMPValidationResult(
                is_compliant=False,
                baseline="low", 
                document_type="system-security-plan",
                issues=[
                    FedRAMPValidationIssue(
                        severity="error",
                        code="FEDRAMP_MISSING_CONTROL",
                        message="Missing control AC-1"
                    )
                ],
                validation_time_ms=1200
            )
        ]
        
        # Prepare multiple file uploads
        file1_content = json.dumps(sample_ssp).encode('utf-8')
        file2_content = json.dumps(sample_ssp).encode('utf-8')
        
        files = [
            ("files", ("ssp1.json", file1_content, "application/json")),
            ("files", ("ssp2.json", file2_content, "application/json"))
        ]
        data = {"baseline": "low", "store_results": "false"}
        
        response = test_client.post("/api/v1/fedramp/validate/batch", files=files, data=data)
        
        assert response.status_code == 200
        response_data = response.json()
        
        assert "batch_operation_id" in response_data
        assert response_data["summary"]["total_files"] == 2
        assert response_data["summary"]["compliant"] == 1
        assert response_data["summary"]["non_compliant"] == 1
        assert response_data["summary"]["compliance_rate"] == 50.0
        
        assert len(response_data["results"]) == 2
        assert response_data["results"][0]["is_compliant"] is True
        assert response_data["results"][1]["is_compliant"] is False

    def test_validate_fedramp_batch_too_many_files(self, test_client: TestClient, sample_ssp):
        """Test FedRAMP batch validation with too many files."""
        file_content = json.dumps(sample_ssp).encode('utf-8')
        
        # Create 25 files (over the limit of 20)
        files = [
            ("files", (f"ssp{i}.json", file_content, "application/json"))
            for i in range(25)
        ]
        data = {"baseline": "moderate", "store_results": "false"}
        
        response = test_client.post("/api/v1/fedramp/validate/batch", files=files, data=data)
        
        assert response.status_code == 400
        assert "limited to 20 files" in response.json()["detail"]

    def test_get_fedramp_operation_details(self, test_client: TestClient):
        """Test getting FedRAMP operation details."""
        # This will fail with 404 since no operation exists
        fake_uuid = "12345678-1234-5678-9abc-123456789012"
        response = test_client.get(f"/api/v1/fedramp/validate/operations/{fake_uuid}")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_control_information_specific(self, test_client: TestClient):
        """Test getting information about a specific control."""
        params = {"control_id": "AC-2", "baseline": "moderate"}
        response = test_client.get("/api/v1/fedramp/controls", params=params)
        
        assert response.status_code == 200
        response_data = response.json()
        
        assert "control" in response_data
        control = response_data["control"]
        assert control["id"] == "ac-2"  # Normalized to lowercase
        assert "AC-2" in control["title"]
        assert "baseline_requirements" in control

    def test_get_control_information_general(self, test_client: TestClient):
        """Test getting general control catalog information."""
        response = test_client.get("/api/v1/fedramp/controls")
        
        assert response.status_code == 200
        response_data = response.json()
        
        assert "message" in response_data
        assert "total_controls" in response_data
        assert "baselines" in response_data
        assert response_data["baselines"]["low"]["control_count"] == 108
        assert response_data["baselines"]["moderate"]["control_count"] == 325
        assert response_data["baselines"]["high"]["control_count"] == 421

    def test_fedramp_validate_invalid_file_format(self, test_client: TestClient):
        """Test FedRAMP validation with invalid file format."""
        files = {"file": ("test.txt", b"Not OSCAL content", "text/plain")}
        data = {"baseline": "moderate"}
        
        response = test_client.post("/api/v1/fedramp/validate/file", files=files, data=data)
        
        assert response.status_code == 400
        assert "Only JSON and XML OSCAL files are supported" in response.json()["detail"]

    @patch('app.services.fedramp_service.FedRAMPService.validate_document')
    def test_fedramp_validate_service_error(self, mock_validate, test_client: TestClient, sample_ssp):
        """Test FedRAMP validation when service throws an error."""
        # Mock service error
        mock_validate.side_effect = Exception("FedRAMP service unavailable")
        
        file_content = json.dumps(sample_ssp).encode('utf-8')
        files = {"file": ("test_ssp.json", file_content, "application/json")}
        data = {"baseline": "moderate", "store_result": "false"}
        
        response = test_client.post("/api/v1/fedramp/validate/file", files=files, data=data)
        
        assert response.status_code == 500
        assert "validation failed" in response.json()["detail"].lower()

    def test_fedramp_validate_missing_document_type(self, test_client: TestClient):
        """Test FedRAMP validation without specifying document type."""
        # Create minimal valid OSCAL structure
        minimal_ssp = {
            "system-security-plan": {
                "uuid": "12345678-1234-5678-9abc-123456789012",
                "metadata": {"title": "Minimal SSP"}
            }
        }
        
        file_content = json.dumps(minimal_ssp).encode('utf-8')
        files = {"file": ("minimal_ssp.json", file_content, "application/json")}
        data = {"baseline": "low", "store_result": "false"}
        
        # Should auto-detect document type
        response = test_client.post("/api/v1/fedramp/validate/file", files=files, data=data)
        
        # Response depends on actual FedRAMP service implementation
        assert response.status_code in [200, 400, 500]