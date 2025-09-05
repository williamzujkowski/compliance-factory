"""
MinIO/S3 storage service for artifact management.

Handles secure upload/download of OSCAL documents, validation results, 
and generated artifacts with versioning, checksums, and audit trails.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote

import structlog
from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.exceptions import StorageError


class StorageMetadata(BaseModel):
    """Metadata for stored artifacts."""
    
    object_key: str = Field(description="S3 object key")
    bucket: str = Field(description="S3 bucket name")
    content_type: str = Field(description="MIME content type")
    size_bytes: int = Field(description="File size in bytes")
    sha256_checksum: str = Field(description="SHA-256 checksum")
    uploaded_at: datetime = Field(description="Upload timestamp")
    artifact_type: str = Field(description="Type of artifact (oscal, validation, printable)")
    version: str = Field(description="Artifact version")
    tags: Dict[str, str] = Field(default_factory=dict, description="Custom tags")


class UploadResult(BaseModel):
    """Result of file upload operation."""
    
    success: bool = Field(description="Whether upload was successful")
    metadata: Optional[StorageMetadata] = Field(None, description="Upload metadata")
    public_url: Optional[str] = Field(None, description="Public URL if available")
    presigned_url: Optional[str] = Field(None, description="Presigned URL for access")
    upload_time_ms: int = Field(description="Time taken for upload in milliseconds")
    errors: List[str] = Field(default_factory=list, description="Upload errors if any")


class DownloadResult(BaseModel):
    """Result of file download operation."""
    
    success: bool = Field(description="Whether download was successful")
    local_path: Optional[str] = Field(None, description="Path to downloaded file")
    metadata: Optional[StorageMetadata] = Field(None, description="File metadata")
    download_time_ms: int = Field(description="Time taken for download in milliseconds")
    checksum_verified: bool = Field(default=False, description="Whether checksum was verified")
    errors: List[str] = Field(default_factory=list, description="Download errors if any")


class StorageService:
    """Service for S3-compatible storage operations with MinIO."""
    
    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = structlog.get_logger(__name__)
        self.client = self._create_client()
        self.bucket = self.settings.minio_bucket
        
    def _create_client(self) -> Minio:
        """Create MinIO client with configuration."""
        try:
            client = Minio(
                endpoint=self.settings.minio_endpoint,
                access_key=self.settings.minio_access_key,
                secret_key=self.settings.minio_secret_key,
                secure=self.settings.minio_secure,
            )
            
            self.logger.info(
                "MinIO client created",
                endpoint=self.settings.minio_endpoint,
                secure=self.settings.minio_secure
            )
            
            return client
            
        except Exception as e:
            self.logger.error("Failed to create MinIO client", error=str(e))
            raise StorageError(
                f"Failed to initialize storage client: {str(e)}",
                details={"endpoint": self.settings.minio_endpoint}
            )
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum for a file."""
        sha256_hash = hashlib.sha256()
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        
        return sha256_hash.hexdigest()
    
    def _generate_object_key(
        self, 
        file_path: Path, 
        artifact_type: str,
        version: Optional[str] = None,
        prefix: Optional[str] = None
    ) -> str:
        """
        Generate S3 object key with proper organization.
        
        Pattern: [prefix/]artifact_type/YYYY/MM/DD/filename-checksum[.ext]
        """
        now = datetime.now(timezone.utc)
        date_path = f"{now.year:04d}/{now.month:02d}/{now.day:02d}"
        
        # Calculate checksum for uniqueness
        checksum = self._calculate_checksum(file_path)
        checksum_short = checksum[:8]  # First 8 characters
        
        # Build filename
        stem = file_path.stem
        suffix = file_path.suffix
        filename = f"{stem}-{checksum_short}{suffix}"
        
        # Build object key
        parts = []
        if prefix:
            parts.append(prefix)
        parts.extend([artifact_type, date_path, filename])
        
        object_key = "/".join(parts)
        
        # URL encode for safety
        return quote(object_key, safe='/-.')
    
    def _create_metadata(
        self,
        object_key: str,
        file_path: Path,
        artifact_type: str,
        version: str = "1.0.0",
        tags: Optional[Dict[str, str]] = None
    ) -> StorageMetadata:
        """Create metadata object for stored artifact."""
        
        # Determine content type
        content_types = {
            ".json": "application/json",
            ".xml": "application/xml", 
            ".pdf": "application/pdf",
            ".md": "text/markdown",
            ".txt": "text/plain",
        }
        content_type = content_types.get(file_path.suffix.lower(), "application/octet-stream")
        
        return StorageMetadata(
            object_key=object_key,
            bucket=self.bucket,
            content_type=content_type,
            size_bytes=file_path.stat().st_size,
            sha256_checksum=self._calculate_checksum(file_path),
            uploaded_at=datetime.now(timezone.utc),
            artifact_type=artifact_type,
            version=version,
            tags=tags or {}
        )
    
    async def ensure_bucket_exists(self) -> bool:
        """
        Ensure the configured bucket exists, create if necessary.
        
        Returns:
            True if bucket exists or was created successfully
        """
        try:
            if not self.client.bucket_exists(self.bucket):
                self.logger.info("Creating storage bucket", bucket=self.bucket)
                self.client.make_bucket(self.bucket)
                
                # Set bucket policy for appropriate access
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"AWS": "*"},
                            "Action": ["s3:GetObject"],
                            "Resource": [f"arn:aws:s3:::{self.bucket}/public/*"]
                        }
                    ]
                }
                
                try:
                    self.client.set_bucket_policy(self.bucket, json.dumps(policy))
                except S3Error:
                    # Policy setting might not be supported, continue anyway
                    self.logger.warning("Could not set bucket policy", bucket=self.bucket)
            
            self.logger.info("Storage bucket ready", bucket=self.bucket)
            return True
            
        except Exception as e:
            self.logger.error("Failed to ensure bucket exists", bucket=self.bucket, error=str(e))
            raise StorageError(
                f"Failed to access or create bucket '{self.bucket}': {str(e)}",
                details={"bucket": self.bucket}
            )
    
    async def upload_file(
        self,
        file_path: Union[str, Path],
        artifact_type: str,
        version: str = "1.0.0",
        tags: Optional[Dict[str, str]] = None,
        prefix: Optional[str] = None
    ) -> UploadResult:
        """
        Upload file to storage with metadata and checksums.
        
        Args:
            file_path: Path to file to upload
            artifact_type: Type of artifact (oscal, validation, printable, etc.)
            version: Artifact version
            tags: Optional metadata tags
            prefix: Optional object key prefix
            
        Returns:
            UploadResult with upload details
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            return UploadResult(
                success=False,
                upload_time_ms=0,
                errors=[f"File not found: {file_path}"]
            )
        
        self.logger.info(
            "Starting file upload",
            file_path=str(file_path),
            artifact_type=artifact_type,
            version=version
        )
        
        import time
        start_time = time.time()
        
        try:
            # Ensure bucket exists
            await self.ensure_bucket_exists()
            
            # Generate object key and metadata
            object_key = self._generate_object_key(file_path, artifact_type, version, prefix)
            metadata = self._create_metadata(object_key, file_path, artifact_type, version, tags)
            
            # Prepare metadata for S3
            s3_metadata = {
                "artifact-type": artifact_type,
                "version": version,
                "sha256-checksum": metadata.sha256_checksum,
                "uploaded-at": metadata.uploaded_at.isoformat(),
            }
            
            # Add custom tags to metadata
            for key, value in (tags or {}).items():
                s3_metadata[f"tag-{key}"] = value
            
            # Upload file
            self.client.fput_object(
                bucket_name=self.bucket,
                object_name=object_key,
                file_path=str(file_path),
                content_type=metadata.content_type,
                metadata=s3_metadata
            )
            
            upload_time_ms = int((time.time() - start_time) * 1000)
            
            # Generate presigned URL for access (valid for 7 days)
            presigned_url = None
            try:
                from datetime import timedelta
                presigned_url = self.client.presigned_get_object(
                    bucket_name=self.bucket,
                    object_name=object_key,
                    expires=timedelta(days=7)
                )
            except Exception as e:
                self.logger.warning("Could not generate presigned URL", error=str(e))
            
            result = UploadResult(
                success=True,
                metadata=metadata,
                presigned_url=presigned_url,
                upload_time_ms=upload_time_ms
            )
            
            self.logger.info(
                "File upload completed",
                file_path=str(file_path),
                object_key=object_key,
                size_bytes=metadata.size_bytes,
                upload_time_ms=upload_time_ms
            )
            
            return result
            
        except Exception as e:
            upload_time_ms = int((time.time() - start_time) * 1000)
            self.logger.error(
                "File upload failed",
                file_path=str(file_path),
                error=str(e)
            )
            
            return UploadResult(
                success=False,
                upload_time_ms=upload_time_ms,
                errors=[f"Upload failed: {str(e)}"]
            )
    
    async def download_file(
        self,
        object_key: str,
        local_path: Union[str, Path],
        verify_checksum: bool = True
    ) -> DownloadResult:
        """
        Download file from storage with checksum verification.
        
        Args:
            object_key: S3 object key
            local_path: Local path where file should be saved
            verify_checksum: Whether to verify SHA-256 checksum
            
        Returns:
            DownloadResult with download details
        """
        local_path = Path(local_path)
        
        self.logger.info(
            "Starting file download",
            object_key=object_key,
            local_path=str(local_path)
        )
        
        import time
        start_time = time.time()
        
        try:
            # Create local directory if needed
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Get object metadata first
            stat = self.client.stat_object(self.bucket, object_key)
            expected_checksum = stat.metadata.get("x-amz-meta-sha256-checksum")
            
            # Download file
            self.client.fget_object(
                bucket_name=self.bucket,
                object_name=object_key,
                file_path=str(local_path)
            )
            
            download_time_ms = int((time.time() - start_time) * 1000)
            
            # Verify checksum if requested and available
            checksum_verified = False
            if verify_checksum and expected_checksum:
                actual_checksum = self._calculate_checksum(local_path)
                checksum_verified = actual_checksum == expected_checksum
                
                if not checksum_verified:
                    self.logger.error(
                        "Checksum verification failed",
                        object_key=object_key,
                        expected=expected_checksum,
                        actual=actual_checksum
                    )
            
            # Build metadata from S3 metadata
            metadata = None
            if stat.metadata:
                metadata = StorageMetadata(
                    object_key=object_key,
                    bucket=self.bucket,
                    content_type=stat.content_type or "application/octet-stream",
                    size_bytes=stat.size,
                    sha256_checksum=expected_checksum or "",
                    uploaded_at=stat.last_modified,
                    artifact_type=stat.metadata.get("x-amz-meta-artifact-type", "unknown"),
                    version=stat.metadata.get("x-amz-meta-version", "unknown"),
                    tags={
                        k.replace("x-amz-meta-tag-", ""): v
                        for k, v in stat.metadata.items()
                        if k.startswith("x-amz-meta-tag-")
                    }
                )
            
            result = DownloadResult(
                success=True,
                local_path=str(local_path),
                metadata=metadata,
                download_time_ms=download_time_ms,
                checksum_verified=checksum_verified
            )
            
            self.logger.info(
                "File download completed",
                object_key=object_key,
                local_path=str(local_path),
                download_time_ms=download_time_ms,
                checksum_verified=checksum_verified
            )
            
            return result
            
        except Exception as e:
            download_time_ms = int((time.time() - start_time) * 1000)
            self.logger.error(
                "File download failed",
                object_key=object_key,
                local_path=str(local_path),
                error=str(e)
            )
            
            return DownloadResult(
                success=False,
                download_time_ms=download_time_ms,
                errors=[f"Download failed: {str(e)}"]
            )
    
    async def list_artifacts(
        self,
        artifact_type: Optional[str] = None,
        prefix: Optional[str] = None,
        limit: int = 100
    ) -> List[StorageMetadata]:
        """
        List stored artifacts with optional filtering.
        
        Args:
            artifact_type: Filter by artifact type
            prefix: Filter by object key prefix
            limit: Maximum number of results
            
        Returns:
            List of StorageMetadata objects
        """
        try:
            # Build prefix filter
            search_prefix = ""
            if prefix:
                search_prefix = prefix
            elif artifact_type:
                search_prefix = f"{artifact_type}/"
            
            objects = self.client.list_objects(
                bucket_name=self.bucket,
                prefix=search_prefix,
                recursive=True
            )
            
            artifacts = []
            count = 0
            
            for obj in objects:
                if count >= limit:
                    break
                
                try:
                    # Get detailed metadata
                    stat = self.client.stat_object(self.bucket, obj.object_name)
                    
                    metadata = StorageMetadata(
                        object_key=obj.object_name,
                        bucket=self.bucket,
                        content_type=stat.content_type or "application/octet-stream",
                        size_bytes=stat.size,
                        sha256_checksum=stat.metadata.get("x-amz-meta-sha256-checksum", ""),
                        uploaded_at=stat.last_modified,
                        artifact_type=stat.metadata.get("x-amz-meta-artifact-type", "unknown"),
                        version=stat.metadata.get("x-amz-meta-version", "unknown"),
                        tags={
                            k.replace("x-amz-meta-tag-", ""): v
                            for k, v in stat.metadata.items()
                            if k.startswith("x-amz-meta-tag-")
                        }
                    )
                    
                    # Apply artifact type filter if specified
                    if artifact_type and metadata.artifact_type != artifact_type:
                        continue
                    
                    artifacts.append(metadata)
                    count += 1
                    
                except Exception as e:
                    self.logger.warning(
                        "Failed to get metadata for object",
                        object_key=obj.object_name,
                        error=str(e)
                    )
                    continue
            
            self.logger.info(
                "Listed artifacts",
                count=len(artifacts),
                artifact_type=artifact_type,
                prefix=prefix
            )
            
            return artifacts
            
        except Exception as e:
            self.logger.error(
                "Failed to list artifacts",
                error=str(e),
                artifact_type=artifact_type,
                prefix=prefix
            )
            raise StorageError(
                f"Failed to list artifacts: {str(e)}",
                details={"artifact_type": artifact_type, "prefix": prefix}
            )
    
    async def delete_artifact(self, object_key: str) -> bool:
        """
        Delete artifact from storage.
        
        Args:
            object_key: S3 object key to delete
            
        Returns:
            True if deletion was successful
        """
        try:
            self.client.remove_object(self.bucket, object_key)
            
            self.logger.info("Artifact deleted", object_key=object_key)
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to delete artifact",
                object_key=object_key,
                error=str(e)
            )
            return False
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage usage statistics.
        
        Returns:
            Dictionary with storage statistics
        """
        try:
            objects = list(self.client.list_objects(self.bucket, recursive=True))
            
            total_objects = len(objects)
            total_size = sum(obj.size for obj in objects if obj.size)
            
            # Group by artifact type
            by_type = {}
            for obj in objects:
                try:
                    stat = self.client.stat_object(self.bucket, obj.object_name)
                    artifact_type = stat.metadata.get("x-amz-meta-artifact-type", "unknown")
                    
                    if artifact_type not in by_type:
                        by_type[artifact_type] = {"count": 0, "size_bytes": 0}
                    
                    by_type[artifact_type]["count"] += 1
                    by_type[artifact_type]["size_bytes"] += obj.size or 0
                    
                except Exception:
                    continue
            
            return {
                "bucket": self.bucket,
                "total_objects": total_objects,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / 1024 / 1024, 2),
                "by_artifact_type": by_type,
                "collected_at": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            self.logger.error("Failed to get storage stats", error=str(e))
            return {
                "bucket": self.bucket,
                "error": str(e),
                "collected_at": datetime.now(timezone.utc).isoformat()
            }


# Global service instance
_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """Get the global storage service instance."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service