"""
OSCAL validation endpoints.

Provides endpoints for validating OSCAL documents using the OSCAL CLI
with comprehensive error reporting and operation tracking.
"""

import asyncio
from pathlib import Path
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import Operation, ValidationRun, ValidationError
from app.services.oscal_service import OSCALService, ValidationResult
from app.services.storage_service import StorageService
from app.core.config import get_settings

logger = structlog.get_logger()
router = APIRouter()

# Service instances
oscal_service = OSCALService()
storage_service = StorageService()


@router.post("/file", response_model=dict)
async def validate_file(
    file: UploadFile = File(..., description="OSCAL file to validate"),
    validation_type: str = Form("schema", description="Type of validation (schema, constraints, full)"),
    store_result: bool = Form(True, description="Whether to store validation results"),
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Validate an uploaded OSCAL file.
    
    Supports JSON and XML OSCAL documents with comprehensive validation
    including schema validation and constraint checking.
    """
    if file.content_type not in ["application/json", "application/xml", "text/xml"]:
        raise HTTPException(
            status_code=400,
            detail="Only JSON and XML OSCAL files are supported"
        )
    
    operation = Operation(
        operation_type="validation",
        operation_name=f"Validate {file.filename}",
        operation_description=f"OSCAL {validation_type} validation of {file.filename}",
        input_data={
            "filename": file.filename,
            "content_type": file.content_type,
            "validation_type": validation_type,
            "file_size": file.size if hasattr(file, 'size') else None,
        }
    )
    
    try:
        operation.mark_started()
        db.add(operation)
        await db.commit()
        
        # Save uploaded file temporarily
        temp_file = Path(f"/tmp/{file.filename}")
        content = await file.read()
        temp_file.write_bytes(content)
        
        # Validate with OSCAL CLI
        validation_result: ValidationResult = await oscal_service.validate_document(
            file_path=temp_file,
            timeout=300
        )
        
        # Store validation run in database if requested
        validation_run = None
        if store_result:
            validation_run = ValidationRun(
                file_path=str(temp_file),
                file_name=file.filename,
                file_size_bytes=len(content),
                file_checksum=await storage_service._calculate_checksum(content),
                oscal_version="1.1.3",
                document_type=validation_result.document_type,
                validation_type=validation_type,
                is_valid=validation_result.is_valid,
                error_count=len([e for e in validation_result.errors if e.severity == "error"]),
                warning_count=len([e for e in validation_result.errors if e.severity == "warning"]),
                validation_time_ms=validation_result.duration_ms,
                cli_stdout=validation_result.cli_stdout,
                cli_stderr=validation_result.cli_stderr,
                cli_return_code=validation_result.return_code,
            )
            db.add(validation_run)
            await db.flush()
            
            # Store individual errors
            for error in validation_result.errors:
                validation_error = ValidationError(
                    validation_run_id=validation_run.id,
                    severity=error.severity,
                    message=error.message,
                    location=error.location,
                    line_number=error.line_number,
                    column_number=error.column_number,
                    error_code=error.error_code,
                    suggested_fix=error.suggested_fix,
                    context=error.context,
                )
                db.add(validation_error)
        
        # Mark operation as completed
        output_data = {
            "is_valid": validation_result.is_valid,
            "document_type": validation_result.document_type,
            "error_count": len([e for e in validation_result.errors if e.severity == "error"]),
            "warning_count": len([e for e in validation_result.errors if e.severity == "warning"]),
            "validation_run_id": str(validation_run.id) if validation_run else None,
        }
        operation.mark_completed(output_data)
        
        await db.commit()
        
        # Clean up temp file
        temp_file.unlink(missing_ok=True)
        
        return JSONResponse(
            status_code=200 if validation_result.is_valid else 400,
            content={
                "operation_id": str(operation.id),
                "validation_run_id": str(validation_run.id) if validation_run else None,
                "is_valid": validation_result.is_valid,
                "document_type": validation_result.document_type,
                "validation_type": validation_type,
                "summary": {
                    "errors": len([e for e in validation_result.errors if e.severity == "error"]),
                    "warnings": len([e for e in validation_result.errors if e.severity == "warning"]),
                    "duration_ms": validation_result.duration_ms,
                },
                "errors": [
                    {
                        "severity": error.severity,
                        "message": error.message,
                        "location": error.location,
                        "line_number": error.line_number,
                        "column_number": error.column_number,
                        "error_code": error.error_code,
                        "suggested_fix": error.suggested_fix,
                    }
                    for error in validation_result.errors
                ],
                "cli_output": {
                    "stdout": validation_result.cli_stdout,
                    "stderr": validation_result.cli_stderr,
                    "return_code": validation_result.return_code,
                } if validation_result.cli_stderr or validation_result.cli_stdout else None,
            }
        )
        
    except Exception as e:
        operation.mark_failed(str(e), {"exception_type": type(e).__name__})
        await db.commit()
        
        # Clean up temp file
        if 'temp_file' in locals():
            temp_file.unlink(missing_ok=True)
        
        logger.error("Validation failed", operation_id=str(operation.id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.post("/url", response_model=dict)
async def validate_url(
    url: str = Form(..., description="URL of OSCAL file to validate"),
    validation_type: str = Form("schema", description="Type of validation"),
    store_result: bool = Form(True, description="Whether to store validation results"),
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Validate an OSCAL file from a URL.
    
    Downloads and validates OSCAL documents from remote URLs.
    """
    import httpx
    
    operation = Operation(
        operation_type="validation",
        operation_name=f"Validate URL {url}",
        operation_description=f"OSCAL {validation_type} validation from URL",
        input_data={
            "url": url,
            "validation_type": validation_type,
        }
    )
    
    try:
        operation.mark_started()
        db.add(operation)
        await db.commit()
        
        # Download file from URL
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            content = response.content
        
        # Determine content type and filename
        content_type = response.headers.get("content-type", "application/json")
        filename = Path(url).name or "document.json"
        
        # Save to temp file
        temp_file = Path(f"/tmp/{filename}")
        temp_file.write_bytes(content)
        
        # Validate with OSCAL CLI
        validation_result: ValidationResult = await oscal_service.validate_document(
            file_path=temp_file,
            timeout=300
        )
        
        # Store results similar to file validation
        validation_run = None
        if store_result:
            validation_run = ValidationRun(
                file_path=url,  # Store original URL
                file_name=filename,
                file_size_bytes=len(content),
                file_checksum=await storage_service._calculate_checksum(content),
                oscal_version="1.1.3",
                document_type=validation_result.document_type,
                validation_type=validation_type,
                is_valid=validation_result.is_valid,
                error_count=len([e for e in validation_result.errors if e.severity == "error"]),
                warning_count=len([e for e in validation_result.errors if e.severity == "warning"]),
                validation_time_ms=validation_result.duration_ms,
                cli_stdout=validation_result.cli_stdout,
                cli_stderr=validation_result.cli_stderr,
                cli_return_code=validation_result.return_code,
                metadata={"source_url": url, "content_type": content_type}
            )
            db.add(validation_run)
            await db.flush()
            
            # Store errors
            for error in validation_result.errors:
                validation_error = ValidationError(
                    validation_run_id=validation_run.id,
                    severity=error.severity,
                    message=error.message,
                    location=error.location,
                    line_number=error.line_number,
                    column_number=error.column_number,
                    error_code=error.error_code,
                    suggested_fix=error.suggested_fix,
                    context=error.context,
                )
                db.add(validation_error)
        
        # Complete operation
        output_data = {
            "is_valid": validation_result.is_valid,
            "document_type": validation_result.document_type,
            "error_count": len([e for e in validation_result.errors if e.severity == "error"]),
            "warning_count": len([e for e in validation_result.errors if e.severity == "warning"]),
            "validation_run_id": str(validation_run.id) if validation_run else None,
        }
        operation.mark_completed(output_data)
        await db.commit()
        
        # Clean up
        temp_file.unlink(missing_ok=True)
        
        return JSONResponse(
            status_code=200 if validation_result.is_valid else 400,
            content={
                "operation_id": str(operation.id),
                "validation_run_id": str(validation_run.id) if validation_run else None,
                "is_valid": validation_result.is_valid,
                "document_type": validation_result.document_type,
                "validation_type": validation_type,
                "source_url": url,
                "summary": {
                    "errors": len([e for e in validation_result.errors if e.severity == "error"]),
                    "warnings": len([e for e in validation_result.errors if e.severity == "warning"]),
                    "duration_ms": validation_result.duration_ms,
                },
                "errors": [
                    {
                        "severity": error.severity,
                        "message": error.message,
                        "location": error.location,
                        "line_number": error.line_number,
                        "column_number": error.column_number,
                        "error_code": error.error_code,
                        "suggested_fix": error.suggested_fix,
                    }
                    for error in validation_result.errors
                ],
            }
        )
        
    except httpx.HTTPStatusError as e:
        operation.mark_failed(f"Failed to download from URL: {e.response.status_code}")
        await db.commit()
        raise HTTPException(status_code=400, detail=f"Failed to download from URL: {e.response.status_code}")
    
    except Exception as e:
        operation.mark_failed(str(e), {"exception_type": type(e).__name__})
        await db.commit()
        
        # Clean up
        if 'temp_file' in locals():
            temp_file.unlink(missing_ok=True)
        
        logger.error("URL validation failed", operation_id=str(operation.id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.get("/runs", response_model=dict)
async def list_validation_runs(
    limit: int = 50,
    offset: int = 0,
    is_valid: Optional[bool] = None,
    document_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """List validation runs with optional filtering."""
    from sqlalchemy import select, func, desc
    
    query = select(ValidationRun).order_by(desc(ValidationRun.created_at))
    count_query = select(func.count(ValidationRun.id))
    
    # Apply filters
    if is_valid is not None:
        query = query.where(ValidationRun.is_valid == is_valid)
        count_query = count_query.where(ValidationRun.is_valid == is_valid)
    
    if document_type:
        query = query.where(ValidationRun.document_type == document_type)
        count_query = count_query.where(ValidationRun.document_type == document_type)
    
    # Get total count
    total_count = (await db.execute(count_query)).scalar()
    
    # Apply pagination
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    validation_runs = result.scalars().all()
    
    return {
        "validation_runs": [
            {
                "id": str(run.id),
                "file_name": run.file_name,
                "document_type": run.document_type,
                "validation_type": run.validation_type,
                "is_valid": run.is_valid,
                "error_count": run.error_count,
                "warning_count": run.warning_count,
                "validation_time_ms": run.validation_time_ms,
                "created_at": run.created_at.isoformat(),
            }
            for run in validation_runs
        ],
        "pagination": {
            "total": total_count,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + limit) < total_count,
        }
    }


@router.get("/runs/{run_id}", response_model=dict)
async def get_validation_run(
    run_id: UUID,
    include_errors: bool = True,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get detailed validation run information."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    query = select(ValidationRun).where(ValidationRun.id == run_id)
    if include_errors:
        query = query.options(selectinload(ValidationRun.errors))
    
    result = await db.execute(query)
    validation_run = result.scalar_one_or_none()
    
    if not validation_run:
        raise HTTPException(status_code=404, detail="Validation run not found")
    
    response_data = {
        "id": str(validation_run.id),
        "file_path": validation_run.file_path,
        "file_name": validation_run.file_name,
        "file_size_bytes": validation_run.file_size_bytes,
        "file_checksum": validation_run.file_checksum,
        "oscal_version": validation_run.oscal_version,
        "document_type": validation_run.document_type,
        "validation_type": validation_run.validation_type,
        "is_valid": validation_run.is_valid,
        "error_count": validation_run.error_count,
        "warning_count": validation_run.warning_count,
        "validation_time_ms": validation_run.validation_time_ms,
        "cli_stdout": validation_run.cli_stdout,
        "cli_stderr": validation_run.cli_stderr,
        "cli_return_code": validation_run.cli_return_code,
        "metadata": validation_run.metadata,
        "created_at": validation_run.created_at.isoformat(),
        "updated_at": validation_run.updated_at.isoformat(),
    }
    
    if include_errors and validation_run.errors:
        response_data["errors"] = [
            {
                "id": str(error.id),
                "severity": error.severity,
                "message": error.message,
                "location": error.location,
                "line_number": error.line_number,
                "column_number": error.column_number,
                "error_code": error.error_code,
                "suggested_fix": error.suggested_fix,
                "context": error.context,
                "created_at": error.created_at.isoformat(),
            }
            for error in validation_run.errors
        ]
    
    return response_data