"""
Storage and artifact management endpoints.

Provides endpoints for managing OSCAL artifacts, versions, and storage operations
including upload, download, and artifact lifecycle management.
"""

from pathlib import Path
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.core.database import get_db_session
from app.models import Artifact, ArtifactVersion, Operation
from app.services.storage_service import StorageService

logger = structlog.get_logger()
router = APIRouter()

# Service instance
storage_service = StorageService()


@router.post("/upload", response_model=dict)
async def upload_artifact(
    file: UploadFile = File(..., description="File to upload"),
    artifact_type: str = Form(..., description="Type of artifact (oscal, validation, printable, etc.)"),
    name: Optional[str] = Form(None, description="Human-readable artifact name"),
    description: Optional[str] = Form(None, description="Artifact description"),
    system_id: Optional[str] = Form(None, description="System identifier for SSPs"),
    system_name: Optional[str] = Form(None, description="System name for SSPs"),
    fedramp_baseline: Optional[str] = Form(None, description="FedRAMP baseline (low, moderate, high)"),
    tags: Optional[str] = Form(None, description="JSON string of tags/metadata"),
    version_label: Optional[str] = Form(None, description="Version label (e.g., 'v1.0.0')"),
    change_summary: Optional[str] = Form(None, description="Summary of changes in this version"),
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Upload an artifact file to storage with metadata tracking.
    
    Creates or updates an artifact with a new version, stores the file
    in S3-compatible storage, and tracks all metadata.
    """
    operation = Operation(
        operation_type="upload",
        operation_name=f"Upload {file.filename}",
        operation_description=f"Upload {artifact_type} artifact",
        input_data={
            "filename": file.filename,
            "content_type": file.content_type,
            "artifact_type": artifact_type,
            "file_size": file.size if hasattr(file, 'size') else None,
        }
    )
    
    try:
        operation.mark_started()
        db.add(operation)
        await db.commit()
        
        # Read file content
        content = await file.read()
        
        # Save to temporary file for storage service
        temp_file = Path(f"/tmp/upload_{operation.id}_{file.filename}")
        temp_file.write_bytes(content)
        
        # Store in S3
        storage_info = await storage_service.store_artifact(
            file_path=temp_file,
            artifact_type=artifact_type,
            original_filename=file.filename,
            metadata={
                "upload_operation_id": str(operation.id),
                "system_id": system_id,
                "system_name": system_name,
                "fedramp_baseline": fedramp_baseline,
            }
        )
        
        # Parse tags if provided
        artifact_tags = None
        if tags:
            import json
            try:
                artifact_tags = json.loads(tags)
            except json.JSONDecodeError:
                # Treat as simple comma-separated tags
                artifact_tags = {"tags": [tag.strip() for tag in tags.split(",")]}
        
        # Find or create artifact
        artifact_name = name or Path(file.filename).stem
        
        # Check if artifact already exists by name and type
        existing_query = select(Artifact).where(
            Artifact.name == artifact_name,
            Artifact.artifact_type == artifact_type
        )
        result = await db.execute(existing_query)
        artifact = result.scalar_one_or_none()
        
        if not artifact:
            # Create new artifact
            artifact = Artifact(
                name=artifact_name,
                description=description,
                artifact_type=artifact_type,
                system_id=system_id,
                system_name=system_name,
                fedramp_baseline=fedramp_baseline,
                tags=artifact_tags,
            )
            db.add(artifact)
            await db.flush()  # Get the ID
            
            version_number = 1
        else:
            # Update existing artifact metadata
            if description:
                artifact.description = description
            if system_id:
                artifact.system_id = system_id
            if system_name:
                artifact.system_name = system_name
            if fedramp_baseline:
                artifact.fedramp_baseline = fedramp_baseline
            if artifact_tags:
                artifact.tags = artifact_tags
            
            # Get next version number
            max_version_query = select(func.max(ArtifactVersion.version_number)).where(
                ArtifactVersion.artifact_id == artifact.id
            )
            result = await db.execute(max_version_query)
            max_version = result.scalar() or 0
            version_number = max_version + 1
        
        # Create artifact version
        artifact_version = ArtifactVersion(
            artifact_id=artifact.id,
            version_number=version_number,
            version_label=version_label or f"v{version_number}.0.0",
            original_filename=file.filename,
            file_size_bytes=len(content),
            content_type=file.content_type,
            file_format=Path(file.filename).suffix.lstrip(".") if Path(file.filename).suffix else None,
            sha256_checksum=storage_info.checksum,
            storage_bucket=storage_info.bucket,
            storage_key=storage_info.object_key,
            storage_url=storage_info.url,
            change_summary=change_summary,
            metadata={
                "storage_info": storage_info.dict(),
                "upload_metadata": {
                    "original_content_type": file.content_type,
                    "upload_time_ms": None,  # Could be calculated
                }
            }
        )
        db.add(artifact_version)
        
        # Complete operation
        output_data = {
            "artifact_id": str(artifact.id),
            "artifact_version_id": str(artifact_version.id),
            "version_number": version_number,
            "storage_info": storage_info.dict(),
        }
        operation.mark_completed(output_data)
        
        await db.commit()
        
        # Clean up temp file
        temp_file.unlink(missing_ok=True)
        
        return JSONResponse(
            status_code=201,
            content={
                "operation_id": str(operation.id),
                "artifact": {
                    "id": str(artifact.id),
                    "name": artifact.name,
                    "type": artifact.artifact_type,
                    "description": artifact.description,
                    "system_id": artifact.system_id,
                    "system_name": artifact.system_name,
                    "fedramp_baseline": artifact.fedramp_baseline,
                    "status": artifact.status,
                    "tags": artifact.tags,
                },
                "version": {
                    "id": str(artifact_version.id),
                    "version_number": version_number,
                    "version_label": artifact_version.version_label,
                    "filename": file.filename,
                    "file_size_bytes": len(content),
                    "content_type": file.content_type,
                    "checksum": storage_info.checksum,
                    "change_summary": change_summary,
                },
                "storage": storage_info.dict(),
                "download_url": f"/api/v1/storage/artifacts/{artifact.id}/versions/{artifact_version.id}/download",
            }
        )
        
    except Exception as e:
        operation.mark_failed(str(e), {"exception_type": type(e).__name__})
        await db.commit()
        
        # Clean up temp file
        if 'temp_file' in locals() and temp_file.exists():
            temp_file.unlink(missing_ok=True)
        
        logger.error("Upload failed", operation_id=str(operation.id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/artifacts", response_model=dict)
async def list_artifacts(
    limit: int = Query(50, description="Maximum number of artifacts to return"),
    offset: int = Query(0, description="Number of artifacts to skip"),
    artifact_type: Optional[str] = Query(None, description="Filter by artifact type"),
    status: Optional[str] = Query(None, description="Filter by artifact status"),
    system_id: Optional[str] = Query(None, description="Filter by system ID"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """List artifacts with optional filtering and pagination."""
    
    query = select(Artifact).order_by(desc(Artifact.updated_at))
    count_query = select(func.count(Artifact.id))
    
    # Apply filters
    if artifact_type:
        query = query.where(Artifact.artifact_type == artifact_type)
        count_query = count_query.where(Artifact.artifact_type == artifact_type)
    
    if status:
        query = query.where(Artifact.status == status)
        count_query = count_query.where(Artifact.status == status)
    
    if system_id:
        query = query.where(Artifact.system_id == system_id)
        count_query = count_query.where(Artifact.system_id == system_id)
    
    # Get total count
    total_count = (await db.execute(count_query)).scalar()
    
    # Apply pagination
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    artifacts = result.scalars().all()
    
    return {
        "artifacts": [
            {
                "id": str(artifact.id),
                "name": artifact.name,
                "description": artifact.description,
                "artifact_type": artifact.artifact_type,
                "oscal_document_type": artifact.oscal_document_type,
                "system_id": artifact.system_id,
                "system_name": artifact.system_name,
                "status": artifact.status,
                "fedramp_baseline": artifact.fedramp_baseline,
                "last_validated_at": artifact.last_validated_at.isoformat() if artifact.last_validated_at else None,
                "validation_status": artifact.validation_status,
                "tags": artifact.tags,
                "created_at": artifact.created_at.isoformat(),
                "updated_at": artifact.updated_at.isoformat(),
                "version_count": len(artifact.versions),
                "latest_version": {
                    "id": str(artifact.latest_version.id),
                    "version_number": artifact.latest_version.version_number,
                    "version_label": artifact.latest_version.version_label,
                    "file_size_bytes": artifact.latest_version.file_size_bytes,
                    "created_at": artifact.latest_version.created_at.isoformat(),
                } if artifact.latest_version else None,
            }
            for artifact in artifacts
        ],
        "pagination": {
            "total": total_count,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + limit) < total_count,
        }
    }


@router.get("/artifacts/{artifact_id}", response_model=dict)
async def get_artifact(
    artifact_id: UUID,
    include_versions: bool = Query(True, description="Include version details"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get detailed artifact information."""
    from sqlalchemy.orm import selectinload
    
    query = select(Artifact).where(Artifact.id == artifact_id)
    if include_versions:
        query = query.options(selectinload(Artifact.versions))
    
    result = await db.execute(query)
    artifact = result.scalar_one_or_none()
    
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    
    response_data = {
        "id": str(artifact.id),
        "name": artifact.name,
        "description": artifact.description,
        "artifact_type": artifact.artifact_type,
        "oscal_document_type": artifact.oscal_document_type,
        "oscal_version": artifact.oscal_version,
        "system_id": artifact.system_id,
        "system_name": artifact.system_name,
        "status": artifact.status,
        "is_active": artifact.is_active,
        "last_validated_at": artifact.last_validated_at.isoformat() if artifact.last_validated_at else None,
        "validation_status": artifact.validation_status,
        "fedramp_baseline": artifact.fedramp_baseline,
        "tags": artifact.tags,
        "created_at": artifact.created_at.isoformat(),
        "updated_at": artifact.updated_at.isoformat(),
    }
    
    if include_versions and artifact.versions:
        response_data["versions"] = [
            {
                "id": str(version.id),
                "version_number": version.version_number,
                "version_label": version.version_label,
                "original_filename": version.original_filename,
                "file_size_bytes": version.file_size_bytes,
                "content_type": version.content_type,
                "file_format": version.file_format,
                "sha256_checksum": version.sha256_checksum,
                "processed": version.processed,
                "validated": version.validated,
                "published": version.published,
                "change_summary": version.change_summary,
                "created_at": version.created_at.isoformat(),
                "download_url": f"/api/v1/storage/artifacts/{artifact_id}/versions/{version.id}/download",
            }
            for version in artifact.versions
        ]
    
    return response_data


@router.get("/artifacts/{artifact_id}/versions/{version_id}/download")
async def download_artifact_version(
    artifact_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    """Download a specific version of an artifact."""
    
    # Get the artifact version
    query = select(ArtifactVersion).where(
        ArtifactVersion.id == version_id,
        ArtifactVersion.artifact_id == artifact_id
    )
    result = await db.execute(query)
    version = result.scalar_one_or_none()
    
    if not version:
        raise HTTPException(status_code=404, detail="Artifact version not found")
    
    try:
        # Generate presigned download URL
        download_url = await storage_service.get_download_url(
            bucket=version.storage_bucket,
            object_key=version.storage_key,
            expires_in=3600  # 1 hour
        )
        
        return RedirectResponse(url=download_url, status_code=302)
        
    except Exception as e:
        logger.error(
            "Failed to generate download URL",
            artifact_id=str(artifact_id),
            version_id=str(version_id),
            error=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to generate download URL")


@router.delete("/artifacts/{artifact_id}")
async def delete_artifact(
    artifact_id: UUID,
    force: bool = Query(False, description="Force delete even if artifact has versions"),
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Delete an artifact and optionally its versions.
    
    By default, only deletes artifacts with no versions. Use force=True
    to delete artifacts with all their versions and storage objects.
    """
    from sqlalchemy.orm import selectinload
    
    # Get artifact with versions
    query = select(Artifact).options(selectinload(Artifact.versions)).where(Artifact.id == artifact_id)
    result = await db.execute(query)
    artifact = result.scalar_one_or_none()
    
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    
    if artifact.versions and not force:
        raise HTTPException(
            status_code=400,
            detail=f"Artifact has {len(artifact.versions)} versions. Use force=True to delete."
        )
    
    operation = Operation(
        operation_type="delete",
        operation_name=f"Delete artifact {artifact.name}",
        operation_description=f"Delete {artifact.artifact_type} artifact and {len(artifact.versions)} versions",
        input_data={
            "artifact_id": str(artifact_id),
            "artifact_name": artifact.name,
            "version_count": len(artifact.versions),
            "force": force,
        }
    )
    
    try:
        operation.mark_started()
        db.add(operation)
        await db.commit()
        
        # Delete storage objects for all versions
        deleted_objects = []
        for version in artifact.versions:
            try:
                await storage_service.delete_artifact(
                    bucket=version.storage_bucket,
                    object_key=version.storage_key
                )
                deleted_objects.append({
                    "version_id": str(version.id),
                    "object_key": version.storage_key,
                })
            except Exception as e:
                logger.warning(
                    "Failed to delete storage object",
                    version_id=str(version.id),
                    object_key=version.storage_key,
                    error=str(e)
                )
        
        # Delete from database (cascade should handle versions)
        await db.delete(artifact)
        
        operation.mark_completed({
            "deleted_versions": len(artifact.versions),
            "deleted_storage_objects": len(deleted_objects),
            "storage_objects": deleted_objects,
        })
        
        await db.commit()
        
        return JSONResponse(
            status_code=200,
            content={
                "operation_id": str(operation.id),
                "message": f"Artifact '{artifact.name}' deleted successfully",
                "deleted_versions": len(artifact.versions),
                "deleted_storage_objects": len(deleted_objects),
            }
        )
        
    except Exception as e:
        operation.mark_failed(str(e), {"exception_type": type(e).__name__})
        await db.commit()
        
        logger.error("Delete artifact failed", operation_id=str(operation.id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.get("/buckets", response_model=dict)
async def list_storage_buckets() -> dict:
    """List available storage buckets."""
    try:
        buckets = await storage_service.list_buckets()
        return {
            "buckets": [
                {
                    "name": bucket.name,
                    "created_at": bucket.creation_date.isoformat() if bucket.creation_date else None,
                }
                for bucket in buckets
            ]
        }
    except Exception as e:
        logger.error("Failed to list buckets", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list buckets: {str(e)}")


@router.get("/buckets/{bucket_name}/objects", response_model=dict)
async def list_bucket_objects(
    bucket_name: str,
    prefix: Optional[str] = Query(None, description="Object key prefix filter"),
    max_keys: int = Query(100, description="Maximum number of objects to return"),
) -> dict:
    """List objects in a storage bucket."""
    try:
        objects = await storage_service.list_objects(
            bucket=bucket_name,
            prefix=prefix,
            max_keys=max_keys
        )
        return {
            "bucket": bucket_name,
            "prefix": prefix,
            "objects": [
                {
                    "key": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                    "etag": obj.etag,
                    "content_type": obj.content_type,
                }
                for obj in objects
            ]
        }
    except Exception as e:
        logger.error("Failed to list bucket objects", bucket=bucket_name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list objects: {str(e)}")