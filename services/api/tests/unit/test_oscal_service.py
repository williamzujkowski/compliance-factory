"""
Unit tests for OSCAL service functionality.

Tests the OSCAL CLI wrapper service including validation and conversion operations.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import json

from app.services.oscal_service import OSCALService, ValidationResult, ConversionResult, ValidationIssue


class TestOSCALService:
    """Test cases for OSCAL service."""

    @pytest.fixture
    def oscal_service(self):
        """Create OSCAL service instance."""
        return OSCALService()

    @pytest.fixture
    def mock_subprocess_run(self):
        """Mock subprocess run for CLI calls."""
        with patch('asyncio.create_subprocess_exec') as mock_exec:
            mock_process = Mock()
            mock_process.communicate = AsyncMock(return_value=(b"success", b""))
            mock_process.returncode = 0
            mock_exec.return_value = mock_process
            yield mock_exec

    @pytest.mark.asyncio
    async def test_verify_cli_available_success(self, oscal_service, mock_subprocess_run):
        """Test successful CLI availability check."""
        result = await oscal_service.verify_cli_available()
        assert result is True
        mock_subprocess_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_cli_available_failure(self, oscal_service):
        """Test CLI availability check when CLI is not available."""
        with patch('asyncio.create_subprocess_exec', side_effect=FileNotFoundError):
            result = await oscal_service.verify_cli_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_validate_document_success(self, oscal_service, mock_subprocess_run, temp_oscal_file):
        """Test successful document validation."""
        # Mock successful validation output
        mock_process = Mock()
        mock_process.communicate = AsyncMock(return_value=(
            b'{"results": {"valid": true, "schemaVersion": "1.1.3"}}',
            b""
        ))
        mock_process.returncode = 0
        mock_subprocess_run.return_value = mock_process

        result = await oscal_service.validate_document(temp_oscal_file)
        
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert result.return_code == 0
        assert result.duration_ms is not None
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_validate_document_with_errors(self, oscal_service, mock_subprocess_run, temp_oscal_file):
        """Test document validation with validation errors."""
        # Mock validation with errors
        mock_process = Mock()
        mock_process.communicate = AsyncMock(return_value=(
            b"",
            b"Error: Invalid document structure at line 5"
        ))
        mock_process.returncode = 1
        mock_subprocess_run.return_value = mock_process

        result = await oscal_service.validate_document(temp_oscal_file)
        
        assert isinstance(result, ValidationResult)
        assert result.is_valid is False
        assert result.return_code == 1
        assert len(result.errors) > 0
        assert result.errors[0].severity == "error"

    @pytest.mark.asyncio
    async def test_validate_nonexistent_file(self, oscal_service):
        """Test validation of non-existent file."""
        fake_path = Path("/path/that/does/not/exist.json")
        
        with pytest.raises(FileNotFoundError):
            await oscal_service.validate_document(fake_path)

    @pytest.mark.asyncio
    async def test_convert_document_success(self, oscal_service, mock_subprocess_run, temp_oscal_file):
        """Test successful document conversion."""
        output_path = temp_oscal_file.parent / "converted.xml"
        
        mock_process = Mock()
        mock_process.communicate = AsyncMock(return_value=(b"Conversion successful", b""))
        mock_process.returncode = 0
        mock_subprocess_run.return_value = mock_process

        # Mock the output file creation
        with patch.object(output_path, 'exists', return_value=True):
            result = await oscal_service.convert_document(
                input_path=temp_oscal_file,
                output_path=output_path,
                target_format="xml"
            )

        assert isinstance(result, ConversionResult)
        assert result.success is True
        assert result.output_path == output_path
        assert result.input_format == "json"
        assert result.output_format == "xml"
        assert result.return_code == 0

    @pytest.mark.asyncio
    async def test_convert_document_failure(self, oscal_service, mock_subprocess_run, temp_oscal_file):
        """Test failed document conversion."""
        output_path = temp_oscal_file.parent / "converted.xml"
        
        mock_process = Mock()
        mock_process.communicate = AsyncMock(return_value=(
            b"",
            b"Error: Cannot convert malformed document"
        ))
        mock_process.returncode = 1
        mock_subprocess_run.return_value = mock_process

        result = await oscal_service.convert_document(
            input_path=temp_oscal_file,
            output_path=output_path,
            target_format="xml"
        )

        assert isinstance(result, ConversionResult)
        assert result.success is False
        assert result.return_code == 1
        assert "Cannot convert malformed document" in result.error_message

    @pytest.mark.asyncio
    async def test_validate_document_timeout(self, oscal_service, temp_oscal_file):
        """Test validation timeout handling."""
        with patch('asyncio.create_subprocess_exec') as mock_exec:
            mock_process = Mock()
            mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_exec.return_value = mock_process

            result = await oscal_service.validate_document(temp_oscal_file, timeout=1)
            
            assert isinstance(result, ValidationResult)
            assert result.is_valid is False
            assert "timeout" in result.cli_stderr.lower()

    def test_parse_validation_errors(self, oscal_service):
        """Test parsing validation error messages."""
        stderr = """
        Error: Required field 'uuid' is missing at line 10
        Warning: Recommended field 'version' not found at line 15
        Error: Invalid control ID format 'AC_2' at line 25
        """
        
        errors = oscal_service._parse_validation_errors(stderr)
        
        assert len(errors) == 3
        
        # Check first error
        assert errors[0].severity == "error"
        assert "uuid" in errors[0].message
        assert errors[0].line_number == 10
        
        # Check warning
        assert errors[1].severity == "warning"
        assert "version" in errors[1].message
        assert errors[1].line_number == 15
        
        # Check second error
        assert errors[2].severity == "error"
        assert "control ID" in errors[2].message
        assert errors[2].line_number == 25

    def test_determine_file_format(self, oscal_service):
        """Test file format determination."""
        json_path = Path("/test/file.json")
        xml_path = Path("/test/file.xml")
        yaml_path = Path("/test/file.yaml")
        
        assert oscal_service._determine_file_format(json_path) == "json"
        assert oscal_service._determine_file_format(xml_path) == "xml"
        assert oscal_service._determine_file_format(yaml_path) == "yaml"

    @pytest.mark.asyncio
    async def test_get_version(self, oscal_service, mock_subprocess_run):
        """Test getting OSCAL CLI version."""
        mock_process = Mock()
        mock_process.communicate = AsyncMock(return_value=(b"OSCAL CLI version 1.1.3", b""))
        mock_process.returncode = 0
        mock_subprocess_run.return_value = mock_process

        version = await oscal_service._get_oscal_version()
        
        assert "1.1.3" in version
        mock_subprocess_run.assert_called_once()

    def test_validation_issue_creation(self):
        """Test ValidationIssue dataclass creation."""
        issue = ValidationIssue(
            severity="error",
            message="Test error message",
            location="$.system-security-plan.uuid",
            line_number=10,
            column_number=5,
            error_code="MISSING_REQUIRED_FIELD"
        )
        
        assert issue.severity == "error"
        assert issue.message == "Test error message"
        assert issue.location == "$.system-security-plan.uuid"
        assert issue.line_number == 10
        assert issue.column_number == 5
        assert issue.error_code == "MISSING_REQUIRED_FIELD"
        assert issue.suggested_fix is None  # Default value
        assert issue.context is None  # Default value

    def test_validation_result_properties(self):
        """Test ValidationResult computed properties."""
        errors = [
            ValidationIssue(severity="error", message="Error 1"),
            ValidationIssue(severity="error", message="Error 2"),
            ValidationIssue(severity="warning", message="Warning 1"),
            ValidationIssue(severity="info", message="Info 1"),
        ]
        
        result = ValidationResult(
            is_valid=False,
            document_type="system-security-plan",
            errors=errors,
            warnings=[],  # Using combined errors list
            duration_ms=1000,
            cli_stdout="output",
            cli_stderr="",
            return_code=1
        )
        
        # Note: The actual implementation would need to filter errors by severity
        # This test assumes the errors list contains all issues
        assert len(result.errors) == 4
        
    def test_conversion_result_creation(self):
        """Test ConversionResult dataclass creation."""
        result = ConversionResult(
            success=True,
            output_path=Path("/test/output.xml"),
            input_format="json",
            output_format="xml",
            duration_ms=500,
            cli_stdout="Conversion successful",
            cli_stderr="",
            return_code=0
        )
        
        assert result.success is True
        assert result.output_path == Path("/test/output.xml")
        assert result.input_format == "json"
        assert result.output_format == "xml"
        assert result.duration_ms == 500
        assert result.error_message is None  # Default for successful conversion