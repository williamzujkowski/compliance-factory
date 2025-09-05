"""
Database models for artifact and version tracking.
"""

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base


class Artifact(Base):
    """Track OSCAL artifacts and their metadata."""
    
    __tablename__ = "artifacts"
    
    # Basic information
    name = Column(
        String(255),
        nullable=False,
        doc="Human-readable name of the artifact"
    )
    
    description = Column(
        Text,
        nullable=True,
        doc="Description of the artifact"
    )
    
    artifact_type = Column(
        String(64),
        nullable=False,
        doc="Type of artifact (oscal, validation, printable, etc.)"
    )
    
    # OSCAL-specific fields
    oscal_document_type = Column(
        String(64),
        nullable=True,
        doc="OSCAL document type (ssp, catalog, profile, etc.)"
    )
    
    oscal_version = Column(
        String(32),
        nullable=True,
        doc="OSCAL model version"
    )
    
    system_id = Column(
        String(255),
        nullable=True,
        doc="System identifier for SSPs"
    )
    
    system_name = Column(
        String(255),
        nullable=True,
        doc="System name for SSPs"
    )
    
    # Status and lifecycle
    status = Column(
        String(32),
        nullable=False,
        default="draft",
        doc="Artifact status (draft, validated, published, archived)"
    )
    
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        doc="Whether this artifact is active"
    )
    
    # Compliance and validation
    last_validated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="Last successful validation timestamp"
    )
    
    validation_status = Column(
        String(32),
        nullable=True,
        doc="Latest validation status"
    )
    
    fedramp_baseline = Column(
        String(32),
        nullable=True,
        doc="FedRAMP baseline (low, moderate, high)"
    )
    
    # Metadata and tags
    tags = Column(
        JSON,
        nullable=True,
        doc="Custom tags and metadata"
    )
    
    # Relationships
    versions = relationship(
        "ArtifactVersion",
        back_populates="artifact",
        cascade="all, delete-orphan",
        order_by="ArtifactVersion.version_number.desc()"
    )
    
    @property
    def latest_version(self) -> "ArtifactVersion":
        """Get the latest version of this artifact."""
        return self.versions[0] if self.versions else None
    
    def __repr__(self) -> str:
        return (
            f"<Artifact(id={self.id}, name='{self.name}', "
            f"type='{self.artifact_type}', status='{self.status}')>"
        )


class ArtifactVersion(Base):
    """Track versions of artifacts with storage details."""
    
    __tablename__ = "artifact_versions"
    
    # Link to parent artifact
    artifact_id = Column(
        UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="CASCADE"),
        nullable=False,
        doc="ID of the parent artifact"
    )
    
    # Version information
    version_number = Column(
        Integer,
        nullable=False,
        doc="Sequential version number"
    )
    
    version_label = Column(
        String(64),
        nullable=True,
        doc="Human-readable version label (e.g., 'v1.2.3')"
    )
    
    # File details
    original_filename = Column(
        String(255),
        nullable=False,
        doc="Original filename when uploaded"
    )
    
    file_size_bytes = Column(
        Integer,
        nullable=False,
        doc="File size in bytes"
    )
    
    content_type = Column(
        String(128),
        nullable=False,
        doc="MIME content type"
    )
    
    file_format = Column(
        String(16),
        nullable=True,
        doc="File format (json, xml, pdf, etc.)"
    )
    
    # Checksums and integrity
    sha256_checksum = Column(
        String(64),
        nullable=False,
        unique=True,
        doc="SHA-256 checksum for integrity verification"
    )
    
    md5_checksum = Column(
        String(32),
        nullable=True,
        doc="MD5 checksum (legacy compatibility)"
    )
    
    # Storage information
    storage_bucket = Column(
        String(255),
        nullable=False,
        doc="S3 bucket where file is stored"
    )
    
    storage_key = Column(
        String(1024),
        nullable=False,
        doc="S3 object key"
    )
    
    storage_url = Column(
        String(2048),
        nullable=True,
        doc="Storage URL for access"
    )
    
    # Processing and validation
    upload_time_ms = Column(
        Integer,
        nullable=True,
        doc="Time taken to upload in milliseconds"
    )
    
    processed = Column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether this version has been processed"
    )
    
    validated = Column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether this version has been validated"
    )
    
    published = Column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether this version has been published"
    )
    
    # Change tracking
    change_summary = Column(
        Text,
        nullable=True,
        doc="Summary of changes in this version"
    )
    
    # Metadata
    metadata = Column(
        JSON,
        nullable=True,
        doc="Additional version metadata"
    )
    
    # Relationships
    artifact = relationship(
        "Artifact",
        back_populates="versions"
    )
    
    def __repr__(self) -> str:
        return (
            f"<ArtifactVersion(id={self.id}, artifact_id={self.artifact_id}, "
            f"version={self.version_number}, filename='{self.original_filename}')>"
        )