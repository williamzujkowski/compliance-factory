"""
OSCAL CLI wrapper service for validation and conversion operations.

Provides safe, async wrappers around the oscal-cli tool with proper error handling,
logging, and result parsing. Supports OSCAL 1.1.3 schema validation and format conversion.
"""

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import structlog
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.exceptions import (
    ConversionError,
    OSCALNotFoundError,
    ValidationError,
)


class ValidationResult(BaseModel):
    """Result of OSCAL document validation."""
    
    is_valid: bool = Field(description="Whether the document passed validation")
    errors: List[str] = Field(default_factory=list, description="Validation error messages")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    file_path: str = Field(description="Path to the validated file")
    oscal_version: str = Field(description="OSCAL version used for validation")
    document_type: Optional[str] = Field(None, description="Detected OSCAL document type")
    validation_time_ms: int = Field(description="Time taken for validation in milliseconds")


class ConversionResult(BaseModel):
    """Result of OSCAL format conversion."""
    
    success: bool = Field(description="Whether conversion was successful")
    source_path: str = Field(description="Path to source file")
    target_path: str = Field(description="Path to converted file")
    source_format: str = Field(description="Source format (json|xml)")
    target_format: str = Field(description="Target format (json|xml)")
    conversion_time_ms: int = Field(description="Time taken for conversion in milliseconds")
    file_size_bytes: int = Field(description="Size of converted file in bytes")
    errors: List[str] = Field(default_factory=list, description="Conversion errors if any")


class OSCALService:
    """Service for OSCAL CLI operations with proper error handling and logging."""
    
    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = structlog.get_logger(__name__)
        self.oscal_cli_path = self.settings.oscal_cli_path
        self._verify_oscal_cli()
    
    def _verify_oscal_cli(self) -> None:
        """Verify OSCAL CLI is available and executable."""
        if not shutil.which(self.oscal_cli_path) and not Path(self.oscal_cli_path).is_file():
            raise OSCALNotFoundError(
                f"OSCAL CLI not found at {self.oscal_cli_path}",
                details={
                    "configured_path": self.oscal_cli_path,
                    "suggestion": "Ensure oscal-cli is installed and path is correct"
                }
            )
    
    async def _run_oscal_command(
        self, 
        args: List[str], 
        timeout: int = 300
    ) -> tuple[int, str, str]:
        """
        Execute an OSCAL CLI command with proper error handling.
        
        Args:
            args: Command arguments (not including the binary path)
            timeout: Command timeout in seconds
            
        Returns:
            Tuple of (return_code, stdout, stderr)
            
        Raises:
            OSCALNotFoundError: If OSCAL CLI cannot be executed
        """
        cmd = [self.oscal_cli_path] + args
        
        self.logger.info("Executing OSCAL command", command=cmd, timeout=timeout)
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=timeout
            )
            
            return_code = process.returncode or 0
            stdout_str = stdout.decode('utf-8') if stdout else ""
            stderr_str = stderr.decode('utf-8') if stderr else ""
            
            self.logger.debug(
                "OSCAL command completed",
                return_code=return_code,
                stdout_length=len(stdout_str),
                stderr_length=len(stderr_str)
            )
            
            return return_code, stdout_str, stderr_str
            
        except asyncio.TimeoutError:
            self.logger.error("OSCAL command timed out", command=cmd, timeout=timeout)
            raise OSCALNotFoundError(
                f"OSCAL CLI command timed out after {timeout}s",
                details={"command": cmd, "timeout": timeout}
            )
        except FileNotFoundError as e:
            self.logger.error("OSCAL CLI not found", path=self.oscal_cli_path, error=str(e))
            raise OSCALNotFoundError(
                f"OSCAL CLI executable not found: {self.oscal_cli_path}",
                details={"path": self.oscal_cli_path, "error": str(e)}
            )
        except Exception as e:
            self.logger.error("OSCAL command failed", command=cmd, error=str(e))
            raise OSCALNotFoundError(
                f"Failed to execute OSCAL CLI: {str(e)}",
                details={"command": cmd, "error": str(e)}
            )
    
    def _parse_validation_errors(self, stderr: str) -> tuple[List[str], List[str]]:
        """
        Parse validation errors and warnings from OSCAL CLI output.
        
        Args:
            stderr: Standard error output from OSCAL CLI
            
        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []
        
        for line in stderr.splitlines():
            line = line.strip()
            if not line:
                continue
                
            # Parse different types of validation messages
            if "ERROR" in line.upper() or "FAIL" in line.upper():
                errors.append(line)
            elif "WARNING" in line.upper() or "WARN" in line.upper():
                warnings.append(line)
            elif "invalid" in line.lower() or "violation" in line.lower():
                errors.append(line)
            elif line.startswith("Validation"):
                # Catch validation summary messages
                if "failed" in line.lower():
                    errors.append(line)
                elif "warning" in line.lower():
                    warnings.append(line)
        
        return errors, warnings
    
    def _detect_document_type(self, file_path: Path) -> Optional[str]:
        """
        Detect OSCAL document type from file content.
        
        Args:
            file_path: Path to the OSCAL document
            
        Returns:
            Document type string or None if unable to detect
        """
        try:
            content = file_path.read_text()
            
            # Check for common OSCAL document types
            doc_types = [
                ("system-security-plan", ["system-security-plan", "ssp"]),
                ("catalog", ["catalog"]),
                ("profile", ["profile"]),
                ("component-definition", ["component-definition"]),
                ("assessment-plan", ["assessment-plan", "sap"]), 
                ("assessment-results", ["assessment-results", "sar"]),
                ("plan-of-action-and-milestones", ["plan-of-action-and-milestones", "poam"])
            ]
            
            content_lower = content.lower()
            for doc_type, patterns in doc_types:
                if any(pattern in content_lower for pattern in patterns):
                    return doc_type
                    
            return None
            
        except Exception as e:
            self.logger.warning("Failed to detect document type", file_path=str(file_path), error=str(e))
            return None
    
    async def validate_document(
        self,
        file_path: Union[str, Path],
        timeout: int = 300
    ) -> ValidationResult:
        """
        Validate an OSCAL document against schema.
        
        Args:
            file_path: Path to the OSCAL document to validate
            timeout: Validation timeout in seconds
            
        Returns:
            ValidationResult with validation status and details
            
        Raises:
            ValidationError: If validation fails due to system issues
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise ValidationError(
                f"File not found: {file_path}",
                details={"file_path": str(file_path)}
            )
        
        self.logger.info("Starting OSCAL validation", file_path=str(file_path))
        
        import time
        start_time = time.time()
        
        try:
            # Run validation command
            return_code, stdout, stderr = await self._run_oscal_command([
                "validate",
                str(file_path)
            ], timeout)
            
            validation_time_ms = int((time.time() - start_time) * 1000)
            
            # Parse results
            errors, warnings = self._parse_validation_errors(stderr)
            is_valid = return_code == 0 and not errors
            document_type = self._detect_document_type(file_path)
            
            result = ValidationResult(
                is_valid=is_valid,
                errors=errors,
                warnings=warnings,
                file_path=str(file_path),
                oscal_version=self.settings.oscal_version,
                document_type=document_type,
                validation_time_ms=validation_time_ms
            )
            
            self.logger.info(
                "OSCAL validation completed",
                file_path=str(file_path),
                is_valid=is_valid,
                errors_count=len(errors),
                warnings_count=len(warnings),
                validation_time_ms=validation_time_ms
            )
            
            return result
            
        except OSCALNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "OSCAL validation failed", 
                file_path=str(file_path), 
                error=str(e)
            )
            raise ValidationError(
                f"Validation failed: {str(e)}",
                details={
                    "file_path": str(file_path),
                    "error": str(e),
                    "validation_time_ms": int((time.time() - start_time) * 1000)
                }
            )
    
    async def convert_format(
        self,
        source_path: Union[str, Path],
        target_path: Union[str, Path],
        target_format: str,
        timeout: int = 300
    ) -> ConversionResult:
        """
        Convert OSCAL document between JSON and XML formats.
        
        Args:
            source_path: Path to source document
            target_path: Path where converted document should be saved
            target_format: Target format ("json" or "xml")
            timeout: Conversion timeout in seconds
            
        Returns:
            ConversionResult with conversion details
            
        Raises:
            ConversionError: If conversion fails
        """
        source_path = Path(source_path)
        target_path = Path(target_path)
        
        if not source_path.exists():
            raise ConversionError(
                f"Source file not found: {source_path}",
                details={"source_path": str(source_path)}
            )
        
        if target_format.lower() not in ["json", "xml"]:
            raise ConversionError(
                f"Unsupported target format: {target_format}",
                details={"target_format": target_format, "supported": ["json", "xml"]}
            )
        
        # Detect source format
        source_format = "xml" if source_path.suffix.lower() == ".xml" else "json"
        
        self.logger.info(
            "Starting OSCAL format conversion",
            source_path=str(source_path),
            target_path=str(target_path),
            source_format=source_format,
            target_format=target_format
        )
        
        import time
        start_time = time.time()
        
        try:
            # Create target directory if needed
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Run conversion command
            return_code, stdout, stderr = await self._run_oscal_command([
                "convert",
                f"--to={target_format.lower()}",
                str(source_path),
                str(target_path)
            ], timeout)
            
            conversion_time_ms = int((time.time() - start_time) * 1000)
            
            # Check if conversion was successful
            success = return_code == 0 and target_path.exists()
            errors = []
            
            if not success:
                errors = self._parse_validation_errors(stderr)[0]  # Get only errors
                if not errors and stderr:
                    errors = [stderr.strip()]
            
            # Get converted file size
            file_size_bytes = target_path.stat().st_size if target_path.exists() else 0
            
            result = ConversionResult(
                success=success,
                source_path=str(source_path),
                target_path=str(target_path),
                source_format=source_format,
                target_format=target_format,
                conversion_time_ms=conversion_time_ms,
                file_size_bytes=file_size_bytes,
                errors=errors
            )
            
            self.logger.info(
                "OSCAL format conversion completed",
                source_path=str(source_path),
                target_path=str(target_path),
                success=success,
                conversion_time_ms=conversion_time_ms,
                file_size_bytes=file_size_bytes
            )
            
            return result
            
        except OSCALNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "OSCAL format conversion failed",
                source_path=str(source_path),
                target_path=str(target_path),
                error=str(e)
            )
            raise ConversionError(
                f"Format conversion failed: {str(e)}",
                details={
                    "source_path": str(source_path),
                    "target_path": str(target_path),
                    "source_format": source_format,
                    "target_format": target_format,
                    "error": str(e),
                    "conversion_time_ms": int((time.time() - start_time) * 1000)
                }
            )
    
    async def get_oscal_version(self) -> Dict[str, Any]:
        """
        Get OSCAL CLI version information.
        
        Returns:
            Dictionary with version information
        """
        try:
            return_code, stdout, stderr = await self._run_oscal_command(["--version"])
            
            return {
                "oscal_cli_version": stdout.strip() if stdout else "unknown",
                "oscal_models_version": self.settings.oscal_version,
                "cli_path": self.oscal_cli_path,
                "available": return_code == 0
            }
            
        except Exception as e:
            self.logger.error("Failed to get OSCAL version", error=str(e))
            return {
                "oscal_cli_version": "unknown",
                "oscal_models_version": self.settings.oscal_version,
                "cli_path": self.oscal_cli_path,
                "available": False,
                "error": str(e)
            }


# Global service instance
_oscal_service: Optional[OSCALService] = None


def get_oscal_service() -> OSCALService:
    """Get the global OSCAL service instance."""
    global _oscal_service
    if _oscal_service is None:
        _oscal_service = OSCALService()
    return _oscal_service