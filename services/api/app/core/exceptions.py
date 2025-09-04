"""Custom exceptions for the OSCAL Compliance Factory."""

from typing import Any, Optional


class ComplianceFactoryException(Exception):
    """Base exception for all Compliance Factory errors."""
    
    def __init__(
        self,
        message: str,
        error_code: str,
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(ComplianceFactoryException):
    """Raised when OSCAL validation fails."""
    
    def __init__(
        self,
        message: str = "OSCAL validation failed",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=422,
            details=details,
        )


class ConversionError(ComplianceFactoryException):
    """Raised when OSCAL format conversion fails."""
    
    def __init__(
        self,
        message: str = "OSCAL format conversion failed",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="CONVERSION_ERROR", 
            status_code=422,
            details=details,
        )


class FedRAMPError(ComplianceFactoryException):
    """Raised when FedRAMP constraint validation fails."""
    
    def __init__(
        self,
        message: str = "FedRAMP compliance check failed",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="FEDRAMP_ERROR",
            status_code=422,
            details=details,
        )


class StorageError(ComplianceFactoryException):
    """Raised when S3/MinIO storage operations fail."""
    
    def __init__(
        self,
        message: str = "Storage operation failed",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="STORAGE_ERROR",
            status_code=503,
            details=details,
        )


class DocumentProcessingError(ComplianceFactoryException):
    """Raised when document import/processing fails."""
    
    def __init__(
        self,
        message: str = "Document processing failed",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="DOCUMENT_PROCESSING_ERROR",
            status_code=422,
            details=details,
        )


class OSCALNotFoundError(ComplianceFactoryException):
    """Raised when OSCAL CLI is not found or not working."""
    
    def __init__(
        self,
        message: str = "OSCAL CLI not found or not working",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="OSCAL_CLI_ERROR",
            status_code=503,
            details=details,
        )