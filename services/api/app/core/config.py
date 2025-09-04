"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Optional

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )
    
    # Application settings
    debug: bool = Field(default=False, description="Enable debug mode")
    version: str = Field(default="0.1.0", description="Application version")
    api_v1_str: str = Field(default="/api/v1", description="API v1 prefix")
    project_name: str = Field(
        default="OSCAL Compliance Factory",
        description="Project name"
    )
    
    # Security settings
    secret_key: str = Field(
        default="change-me-in-production",
        description="Secret key for cryptographic operations"
    )
    allowed_hosts: Optional[list[str]] = Field(
        default=None,
        description="Allowed host/domain names"
    )
    
    # Database settings
    database_url: PostgresDsn = Field(
        default="postgresql://postgres:password@localhost:5432/compliance_factory",
        description="PostgreSQL database URL"
    )
    
    # MinIO/S3 settings
    minio_endpoint: str = Field(
        default="localhost:9000",
        description="MinIO endpoint"
    )
    minio_access_key: str = Field(
        default="minio",
        description="MinIO access key"
    )
    minio_secret_key: str = Field(
        default="password123",
        description="MinIO secret key"
    )
    minio_bucket: str = Field(
        default="compliance-artifacts",
        description="Default S3 bucket for artifacts"
    )
    minio_secure: bool = Field(
        default=False,
        description="Use HTTPS for MinIO connections"
    )
    
    # OSCAL settings
    oscal_cli_path: str = Field(
        default="/opt/oscal-cli/oscal-cli",
        description="Path to OSCAL CLI executable"
    )
    oscal_version: str = Field(
        default="1.1.3",
        description="OSCAL version for validation"
    )
    nist_sp800_53_version: str = Field(
        default="5.2.0",
        description="NIST SP 800-53 catalog version"
    )
    
    # FedRAMP settings
    fedramp_registry_url: str = Field(
        default="https://github.com/GSA/fedramp-automation/raw/master/",
        description="FedRAMP automation registry base URL"
    )
    fedramp_baseline: str = Field(
        default="low",
        description="Default FedRAMP baseline (low/moderate/high)"
    )
    
    # File processing settings
    max_upload_size: int = Field(
        default=50 * 1024 * 1024,  # 50MB
        description="Maximum upload file size in bytes"
    )
    workspace_dir: str = Field(
        default="/app/workspace",
        description="Working directory for file processing"
    )
    content_dir: str = Field(
        default="/app/content",
        description="Directory for OSCAL catalogs and profiles"
    )
    
    # Logging settings
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    log_format: str = Field(
        default="json",
        description="Log format (json|text)"
    )
    
    # Cloud.gov specific settings
    vcap_services: Optional[str] = Field(
        default=None,
        description="VCAP_SERVICES for cloud.gov deployment"
    )
    vcap_application: Optional[str] = Field(
        default=None,
        description="VCAP_APPLICATION for cloud.gov deployment"
    )
    
    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v: Optional[str]) -> Optional[list[str]]:
        """Parse comma-separated allowed hosts."""
        if v is None:
            return None
        if isinstance(v, str):
            return [host.strip() for host in v.split(",") if host.strip()]
        return v
    
    @property
    def database_url_str(self) -> str:
        """Get database URL as string."""
        return str(self.database_url)
    
    @property
    def minio_endpoint_url(self) -> str:
        """Get complete MinIO endpoint URL."""
        protocol = "https" if self.minio_secure else "http"
        return f"{protocol}://{self.minio_endpoint}"


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()