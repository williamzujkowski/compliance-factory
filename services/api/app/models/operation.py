"""
Database models for operation tracking and audit logs.
"""

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text, JSON, Enum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from .base import Base


class OperationStatus(str, enum.Enum):
    """Status of operations."""
    PENDING = "pending"
    RUNNING = "running" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OperationType(str, enum.Enum):
    """Types of operations."""
    VALIDATION = "validation"
    CONVERSION = "conversion"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    INGESTION = "ingestion"
    PRINTABLE_GENERATION = "printable_generation"
    FEDRAMP_CHECK = "fedramp_check"


class Operation(Base):
    """Track long-running operations and their status."""
    
    __tablename__ = "operations"
    
    # Operation identification
    operation_type = Column(
        Enum(OperationType),
        nullable=False,
        doc="Type of operation being performed"
    )
    
    operation_name = Column(
        String(255),
        nullable=False,
        doc="Human-readable name of the operation"
    )
    
    operation_description = Column(
        Text,
        nullable=True,
        doc="Detailed description of the operation"
    )
    
    # Status tracking
    status = Column(
        Enum(OperationStatus),
        nullable=False,
        default=OperationStatus.PENDING,
        doc="Current status of the operation"
    )
    
    progress_percent = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Progress percentage (0-100)"
    )
    
    # Timing
    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="When the operation started"
    )
    
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="When the operation completed"
    )
    
    duration_ms = Column(
        Integer,
        nullable=True,
        doc="Operation duration in milliseconds"
    )
    
    # Input and output
    input_data = Column(
        JSON,
        nullable=True,
        doc="Input parameters for the operation"
    )
    
    output_data = Column(
        JSON,
        nullable=True,
        doc="Output results from the operation"
    )
    
    # Error handling
    error_message = Column(
        Text,
        nullable=True,
        doc="Error message if operation failed"
    )
    
    error_details = Column(
        JSON,
        nullable=True,
        doc="Detailed error information"
    )
    
    retry_count = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of retry attempts"
    )
    
    max_retries = Column(
        Integer,
        nullable=False,
        default=3,
        doc="Maximum number of retry attempts"
    )
    
    # Context
    correlation_id = Column(
        String(64),
        nullable=True,
        doc="Correlation ID for tracking related operations"
    )
    
    parent_operation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("operations.id"),
        nullable=True,
        doc="ID of parent operation if this is a sub-operation"
    )
    
    # User context
    user_id = Column(
        String(255),
        nullable=True,
        doc="User who initiated the operation"
    )
    
    session_id = Column(
        String(255),
        nullable=True,
        doc="Session ID for the operation"
    )
    
    # Resource usage
    cpu_time_ms = Column(
        Integer,
        nullable=True,
        doc="CPU time consumed in milliseconds"
    )
    
    memory_peak_bytes = Column(
        Integer,
        nullable=True,
        doc="Peak memory usage in bytes"
    )
    
    # Relationships
    child_operations = relationship(
        "Operation",
        remote_side=[id],
        doc="Child operations"
    )
    
    logs = relationship(
        "OperationLog",
        back_populates="operation",
        cascade="all, delete-orphan",
        order_by="OperationLog.created_at"
    )
    
    def add_log(self, level: str, message: str, details: dict = None) -> "OperationLog":
        """Add a log entry for this operation."""
        log_entry = OperationLog(
            operation_id=self.id,
            level=level,
            message=message,
            details=details
        )
        self.logs.append(log_entry)
        return log_entry
    
    def mark_started(self) -> None:
        """Mark the operation as started."""
        from datetime import datetime, timezone
        self.status = OperationStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)
    
    def mark_completed(self, output_data: dict = None) -> None:
        """Mark the operation as completed."""
        from datetime import datetime, timezone
        self.status = OperationStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.progress_percent = 100
        if output_data:
            self.output_data = output_data
        
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)
    
    def mark_failed(self, error_message: str, error_details: dict = None) -> None:
        """Mark the operation as failed."""
        from datetime import datetime, timezone
        self.status = OperationStatus.FAILED
        self.completed_at = datetime.now(timezone.utc)
        self.error_message = error_message
        self.error_details = error_details
        
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)
    
    def __repr__(self) -> str:
        return (
            f"<Operation(id={self.id}, type='{self.operation_type}', "
            f"status='{self.status}', progress={self.progress_percent}%)>"
        )


class OperationLog(Base):
    """Log entries for operations."""
    
    __tablename__ = "operation_logs"
    
    # Link to operation
    operation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("operations.id", ondelete="CASCADE"),
        nullable=False,
        doc="ID of the parent operation"
    )
    
    # Log details
    level = Column(
        String(16),
        nullable=False,
        default="info",
        doc="Log level (debug, info, warning, error)"
    )
    
    message = Column(
        Text,
        nullable=False,
        doc="Log message"
    )
    
    details = Column(
        JSON,
        nullable=True,
        doc="Additional log details"
    )
    
    # Context
    component = Column(
        String(64),
        nullable=True,
        doc="Component that generated the log"
    )
    
    # Relationships
    operation = relationship(
        "Operation",
        back_populates="logs"
    )
    
    def __repr__(self) -> str:
        return (
            f"<OperationLog(id={self.id}, level='{self.level}', "
            f"message='{self.message[:50]}...')>"
        )