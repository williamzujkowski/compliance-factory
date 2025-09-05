"""
Base model class with common fields and utilities.
"""

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from sqlalchemy import Column, DateTime, String, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import Session


class BaseModel:
    """Base model with common fields and utilities."""
    
    @declared_attr
    def __tablename__(cls) -> str:
        """Generate table name from class name."""
        return cls.__name__.lower()
    
    # Primary key
    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid4,
        doc="Unique identifier"
    )
    
    # Audit fields
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        doc="Creation timestamp"
    )
    
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        doc="Last update timestamp"
    )
    
    # Optional tracking fields
    created_by = Column(
        String(255),
        nullable=True,
        doc="User or system that created this record"
    )
    
    updated_by = Column(
        String(255), 
        nullable=True,
        doc="User or system that last updated this record"
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary."""
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                result[column.name] = value.isoformat()
            else:
                result[column.name] = value
        return result
    
    def __repr__(self) -> str:
        """String representation."""
        return f"<{self.__class__.__name__}(id={self.id})>"


# Create base class with the mixin
Base = declarative_base(cls=BaseModel)


@event.listens_for(BaseModel, 'before_update', propagate=True)
def update_modified_timestamp(mapper, connection, target):
    """Automatically update the updated_at timestamp before updates."""
    target.updated_at = datetime.now(timezone.utc)