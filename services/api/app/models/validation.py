"""
Database models for OSCAL validation tracking.
"""

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base


class ValidationRun(Base):
    """Track OSCAL validation operations."""
    
    __tablename__ = "validation_runs"
    
    # File information
    file_path = Column(
        String(1024),
        nullable=False,
        doc="Path to the validated file"
    )
    
    file_name = Column(
        String(255),
        nullable=False,
        doc="Name of the validated file"
    )
    
    file_size_bytes = Column(
        Integer,
        nullable=True,
        doc="Size of validated file in bytes"
    )
    
    file_checksum = Column(
        String(64),
        nullable=True,
        doc="SHA-256 checksum of validated file"
    )
    
    # Validation details
    oscal_version = Column(
        String(32),
        nullable=False,
        default="1.1.3",
        doc="OSCAL version used for validation"
    )
    
    document_type = Column(
        String(64),
        nullable=True,
        doc="Detected OSCAL document type"
    )
    
    validation_type = Column(
        String(32),
        nullable=False,
        default="schema",
        doc="Type of validation (schema, constraints, etc.)"
    )
    
    # Results
    is_valid = Column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether validation passed"
    )
    
    error_count = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of validation errors"
    )
    
    warning_count = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of validation warnings"
    )
    
    validation_time_ms = Column(
        Integer,
        nullable=True,
        doc="Time taken for validation in milliseconds"
    )
    
    # CLI output
    cli_stdout = Column(
        Text,
        nullable=True,
        doc="Standard output from OSCAL CLI"
    )
    
    cli_stderr = Column(
        Text,
        nullable=True,
        doc="Standard error from OSCAL CLI"
    )
    
    cli_return_code = Column(
        Integer,
        nullable=True,
        doc="Return code from OSCAL CLI"
    )
    
    # Metadata
    metadata = Column(
        JSON,
        nullable=True,
        doc="Additional validation metadata"
    )
    
    # Relationships
    errors = relationship(
        "ValidationError",
        back_populates="validation_run",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return (
            f"<ValidationRun(id={self.id}, file_name='{self.file_name}', "
            f"is_valid={self.is_valid}, errors={self.error_count})>"
        )


class ValidationError(Base):
    """Individual validation errors and warnings."""
    
    __tablename__ = "validation_errors"
    
    # Link to validation run
    validation_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("validation_runs.id", ondelete="CASCADE"),
        nullable=False,
        doc="ID of the parent validation run"
    )
    
    # Error details
    severity = Column(
        String(16),
        nullable=False,
        default="error",
        doc="Severity level (error, warning, info)"
    )
    
    message = Column(
        Text,
        nullable=False,
        doc="Error or warning message"
    )
    
    location = Column(
        String(512),
        nullable=True,
        doc="JSONPath or XPath location of the error"
    )
    
    line_number = Column(
        Integer,
        nullable=True,
        doc="Line number in source file (if available)"
    )
    
    column_number = Column(
        Integer,
        nullable=True,
        doc="Column number in source file (if available)"
    )
    
    error_code = Column(
        String(64),
        nullable=True,
        doc="Error code or identifier"
    )
    
    suggested_fix = Column(
        Text,
        nullable=True,
        doc="Suggested fix for the error"
    )
    
    # Context
    context = Column(
        JSON,
        nullable=True,
        doc="Additional context about the error"
    )
    
    # Relationships
    validation_run = relationship(
        "ValidationRun",
        back_populates="errors"
    )
    
    def __repr__(self) -> str:
        return (
            f"<ValidationError(id={self.id}, severity='{self.severity}', "
            f"message='{self.message[:50]}...')>"
        )