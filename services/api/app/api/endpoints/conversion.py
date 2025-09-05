"""
OSCAL conversion endpoints.

Provides endpoints for converting OSCAL documents between JSON and XML formats
using the OSCAL CLI with operation tracking and storage integration.
"""

from pathlib import Path
from typing import Literal, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import Operation
from app.services.oscal_service import OSCALService, ConversionResult
from app.services.storage_service import StorageService

logger = structlog.get_logger()
router = APIRouter()

# Service instances
oscal_service = OSCALService()
storage_service = StorageService()


@router.post("/file", response_model=dict)
async def convert_file(
    file: UploadFile = File(..., description="OSCAL file to convert"),
    target_format: Literal["json", "xml"] = Form(..., description="Target format"),
    store_result: bool = Form(True, description="Whether to store converted file"),
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Convert an OSCAL file between JSON and XML formats.
    
    Supports bidirectional conversion using the OSCAL CLI with
    comprehensive validation of both input and output.
    """
    # Validate input file type
    if file.content_type not in ["application/json", "application/xml", "text/xml"]:
        raise HTTPException(
            status_code=400,
            detail="Only JSON and XML OSCAL files are supported"
        )
    
    # Determine source format from content type
    source_format = "json" if "json" in file.content_type else "xml"
    
    if source_format == target_format:
        raise HTTPException(
            status_code=400,
            detail="Source and target formats are the same"
        )
    
    operation = Operation(
        operation_type="conversion",
        operation_name=f"Convert {file.filename} to {target_format.upper()}",
        operation_description=f"OSCAL {source_format.upper()} to {target_format.upper()} conversion",
        input_data={
            "filename": file.filename,
            "content_type": file.content_type,
            "source_format": source_format,
            "target_format": target_format,
            "file_size": file.size if hasattr(file, 'size') else None,
        }
    )
    
    temp_input_file = None
    temp_output_file = None
    
    try:
        operation.mark_started()
        db.add(operation)
        await db.commit()
        
        # Save uploaded file temporarily
        temp_input_file = Path(f"/tmp/input_{operation.id}.{source_format}")
        content = await file.read()
        temp_input_file.write_bytes(content)
        
        # Generate output filename
        input_stem = Path(file.filename).stem
        output_filename = f"{input_stem}.{target_format}"
        temp_output_file = Path(f"/tmp/output_{operation.id}_{output_filename}")
        
        # Convert with OSCAL CLI
        conversion_result: ConversionResult = await oscal_service.convert_document(
            input_path=temp_input_file,
            output_path=temp_output_file,
            target_format=target_format,
            timeout=300
        )
        
        if not conversion_result.success:
            operation.mark_failed(
                f"Conversion failed: {conversion_result.error_message}",
                {
                    "cli_stdout": conversion_result.cli_stdout,
                    "cli_stderr": conversion_result.cli_stderr,
                    "return_code": conversion_result.return_code,
                }
            )
            await db.commit()
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Conversion failed",
                    "error": conversion_result.error_message,
                    "cli_output": {
                        "stdout": conversion_result.cli_stdout,
                        "stderr": conversion_result.cli_stderr,
                        "return_code": conversion_result.return_code,
                    }
                }
            )
        
        # Read converted content
        converted_content = temp_output_file.read_bytes()
        
        # Store converted file if requested
        storage_info = None
        if store_result:
            storage_info = await storage_service.store_artifact(
                file_path=temp_output_file,
                artifact_type="converted",
                original_filename=output_filename,
                metadata={
                    "source_format": source_format,
                    "target_format": target_format,
                    "source_filename": file.filename,
                    "conversion_operation_id": str(operation.id),
                }
            )
        
        # Mark operation as completed
        output_data = {
            "source_format": source_format,
            "target_format": target_format,
            "input_size_bytes": len(content),
            "output_size_bytes": len(converted_content),
            "output_filename": output_filename,
            "conversion_time_ms": conversion_result.duration_ms,
            "storage_info": storage_info.dict() if storage_info else None,
        }
        operation.mark_completed(output_data)
        await db.commit()
        
        return JSONResponse(
            status_code=200,
            content={
                "operation_id": str(operation.id),
                "success": True,
                "source_format": source_format,
                "target_format": target_format,
                "input_filename": file.filename,
                "output_filename": output_filename,
                "conversion_time_ms": conversion_result.duration_ms,
                "file_sizes": {
                    "input_bytes": len(content),
                    "output_bytes": len(converted_content),
                },
                "storage": storage_info.dict() if storage_info else None,
                "download_url": f"/api/v1/convert/download/{operation.id}" if conversion_result.success else None,
            }
        )
        
    except Exception as e:
        operation.mark_failed(str(e), {"exception_type": type(e).__name__})
        await db.commit()
        
        logger.error("Conversion failed", operation_id=str(operation.id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")
        
    finally:
        # Clean up temp files
        if temp_input_file and temp_input_file.exists():
            temp_input_file.unlink(missing_ok=True)
        if temp_output_file and temp_output_file.exists():
            temp_output_file.unlink(missing_ok=True)


@router.get("/download/{operation_id}")
async def download_converted_file(
    operation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    """
    Download the converted file from a conversion operation.
    """
    from sqlalchemy import select
    
    # Get the operation
    query = select(Operation).where(
        Operation.id == operation_id,
        Operation.operation_type == "conversion",
        Operation.status == "completed"
    )
    result = await db.execute(query)
    operation = result.scalar_one_or_none()
    
    if not operation:
        raise HTTPException(
            status_code=404,
            detail="Conversion operation not found or not completed"
        )
    
    output_data = operation.output_data
    if not output_data or not output_data.get("storage_info"):
        raise HTTPException(
            status_code=404,
            detail="Converted file not available for download"
        )
    
    storage_info = output_data["storage_info"]
    
    try:
        # Get download URL from storage
        download_url = await storage_service.get_download_url(
            bucket=storage_info["bucket"],
            object_key=storage_info["object_key"],
            expires_in=3600  # 1 hour
        )
        
        # For direct file response, we'd need to stream from storage
        # For now, redirect to the presigned URL
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=download_url, status_code=302)
        
    except Exception as e:
        logger.error("Failed to generate download URL", operation_id=str(operation_id), error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate download URL")


@router.post("/batch", response_model=dict)
async def convert_batch(
    files: list[UploadFile] = File(..., description="OSCAL files to convert"),
    target_format: Literal["json", "xml"] = Form(..., description="Target format"),
    store_results: bool = Form(True, description="Whether to store converted files"),
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Convert multiple OSCAL files in batch.
    
    Processes multiple files in parallel with individual operation tracking
    for each file conversion.
    """
    if len(files) > 50:  # Reasonable batch size limit
        raise HTTPException(
            status_code=400,
            detail="Batch size limited to 50 files maximum"
        )
    
    # Create parent operation for batch tracking
    parent_operation = Operation(
        operation_type="conversion",
        operation_name=f"Batch convert {len(files)} files to {target_format.upper()}",
        operation_description=f"Batch OSCAL conversion of {len(files)} files to {target_format}",
        input_data={
            "file_count": len(files),
            "target_format": target_format,
            "filenames": [f.filename for f in files],
        }
    )
    parent_operation.mark_started()
    db.add(parent_operation)
    await db.commit()
    
    results = []
    successful_conversions = 0
    
    try:
        import asyncio
        
        async def convert_single_file(file: UploadFile) -> dict:
            """Convert a single file and return result info."""
            nonlocal successful_conversions
            
            try:
                # Create child operation
                source_format = "json" if "json" in file.content_type else "xml"
                
                child_operation = Operation(
                    operation_type="conversion",
                    operation_name=f"Convert {file.filename}",
                    operation_description=f"Batch item: {source_format.upper()} to {target_format.upper()}",
                    parent_operation_id=parent_operation.id,
                    input_data={
                        "filename": file.filename,
                        "source_format": source_format,
                        "target_format": target_format,
                    }
                )
                child_operation.mark_started()
                db.add(child_operation)
                await db.flush()
                
                # Save file temporarily
                temp_input = Path(f"/tmp/batch_input_{child_operation.id}_{file.filename}")
                content = await file.read()
                temp_input.write_bytes(content)
                
                # Convert
                output_filename = f"{Path(file.filename).stem}.{target_format}"
                temp_output = Path(f"/tmp/batch_output_{child_operation.id}_{output_filename}")
                
                conversion_result = await oscal_service.convert_document(
                    input_path=temp_input,
                    output_path=temp_output,
                    target_format=target_format,
                    timeout=120  # Shorter timeout for batch
                )
                
                if conversion_result.success:
                    converted_content = temp_output.read_bytes()
                    
                    # Store if requested
                    storage_info = None
                    if store_results:
                        storage_info = await storage_service.store_artifact(
                            file_path=temp_output,
                            artifact_type="batch_converted",
                            original_filename=output_filename,
                            metadata={
                                "batch_operation_id": str(parent_operation.id),
                                "source_filename": file.filename,
                                "source_format": source_format,
                                "target_format": target_format,
                            }
                        )
                    
                    child_operation.mark_completed({
                        "output_filename": output_filename,
                        "output_size_bytes": len(converted_content),
                        "storage_info": storage_info.dict() if storage_info else None,
                    })
                    successful_conversions += 1
                    
                    return {
                        "operation_id": str(child_operation.id),
                        "filename": file.filename,
                        "success": True,
                        "output_filename": output_filename,
                        "storage": storage_info.dict() if storage_info else None,
                    }
                else:
                    child_operation.mark_failed(conversion_result.error_message)
                    return {
                        "operation_id": str(child_operation.id),
                        "filename": file.filename,
                        "success": False,
                        "error": conversion_result.error_message,
                    }
                    
            except Exception as e:
                if 'child_operation' in locals():
                    child_operation.mark_failed(str(e))
                return {
                    "operation_id": str(child_operation.id) if 'child_operation' in locals() else None,
                    "filename": file.filename,
                    "success": False,
                    "error": str(e),
                }
            finally:
                # Clean up temp files
                if 'temp_input' in locals() and temp_input.exists():
                    temp_input.unlink(missing_ok=True)
                if 'temp_output' in locals() and temp_output.exists():
                    temp_output.unlink(missing_ok=True)
        
        # Process files with limited concurrency
        semaphore = asyncio.Semaphore(5)  # Process 5 files at a time
        
        async def convert_with_semaphore(file):
            async with semaphore:
                return await convert_single_file(file)
        
        results = await asyncio.gather(
            *[convert_with_semaphore(file) for file in files],
            return_exceptions=True
        )
        
        # Handle any exceptions from gather
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                results[i] = {
                    "filename": files[i].filename,
                    "success": False,
                    "error": str(result),
                }
        
        # Complete parent operation
        parent_operation.mark_completed({
            "total_files": len(files),
            "successful_conversions": successful_conversions,
            "failed_conversions": len(files) - successful_conversions,
            "target_format": target_format,
        })
        
        await db.commit()
        
        return JSONResponse(
            status_code=200,
            content={
                "batch_operation_id": str(parent_operation.id),
                "summary": {
                    "total_files": len(files),
                    "successful": successful_conversions,
                    "failed": len(files) - successful_conversions,
                    "target_format": target_format,
                },
                "results": results,
            }
        )
        
    except Exception as e:
        parent_operation.mark_failed(str(e))
        await db.commit()
        logger.error("Batch conversion failed", operation_id=str(parent_operation.id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Batch conversion failed: {str(e)}")


@router.get("/operations/{operation_id}", response_model=dict)
async def get_conversion_operation(
    operation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get details of a conversion operation."""
    from sqlalchemy import select
    
    query = select(Operation).where(
        Operation.id == operation_id,
        Operation.operation_type == "conversion"
    )
    result = await db.execute(query)
    operation = result.scalar_one_or_none()
    
    if not operation:
        raise HTTPException(status_code=404, detail="Conversion operation not found")
    
    return {
        "operation_id": str(operation.id),
        "operation_name": operation.operation_name,
        "operation_description": operation.operation_description,
        "status": operation.status,
        "progress_percent": operation.progress_percent,
        "started_at": operation.started_at.isoformat() if operation.started_at else None,
        "completed_at": operation.completed_at.isoformat() if operation.completed_at else None,
        "duration_ms": operation.duration_ms,
        "input_data": operation.input_data,
        "output_data": operation.output_data,
        "error_message": operation.error_message,
        "retry_count": operation.retry_count,
        "created_at": operation.created_at.isoformat(),
        "updated_at": operation.updated_at.isoformat(),
    }