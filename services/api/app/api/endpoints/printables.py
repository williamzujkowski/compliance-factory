"""
Printable document generation endpoints.

Provides endpoints for generating human-readable printable documents
from OSCAL content including PDFs, HTML, and other formats.
"""

import json
from pathlib import Path
from typing import Dict, Literal, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import Operation
from app.services.printable_service import PrintableGenerationService, PrintableGenerationResult
from app.services.storage_service import StorageService

logger = structlog.get_logger()
router = APIRouter()

# Service instances
printable_service = PrintableGenerationService()
storage_service = StorageService()


@router.post("/generate", response_model=dict)
async def generate_printable_document(
    file: UploadFile = File(..., description="OSCAL document file to generate printable from"),
    output_format: Literal["pdf", "html"] = Form("pdf", description="Output format for printable document"),
    store_result: bool = Form(True, description="Whether to store the generated document"),
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Generate a printable document from an uploaded OSCAL file.
    
    Supports conversion of OSCAL documents to human-readable formats
    suitable for printing, sharing, and distribution.
    """
    if file.content_type not in ["application/json", "application/xml", "text/xml"]:
        raise HTTPException(
            status_code=400,
            detail="Only JSON and XML OSCAL files are supported"
        )
    
    operation = Operation(
        operation_type="printable_generation",
        operation_name=f"Generate {output_format.upper()} printable from {file.filename}",
        operation_description=f"Printable document generation: {output_format.upper()}",
        input_data={
            "filename": file.filename,
            "content_type": file.content_type,
            "output_format": output_format,
            "file_size": file.size if hasattr(file, 'size') else None,
        }
    )
    
    temp_input_file = None
    
    try:
        operation.mark_started()
        db.add(operation)
        await db.commit()
        
        # Read and parse OSCAL document
        content = await file.read()
        
        if file.content_type == "application/json":
            try:
                oscal_document = json.loads(content.decode('utf-8'))
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
        else:
            # XML parsing would be implemented here
            raise HTTPException(status_code=400, detail="XML parsing not yet implemented")
        
        # Generate printable document
        generation_result: PrintableGenerationResult = await printable_service.generate_printable(
            oscal_document=oscal_document,
            output_format=output_format
        )
        
        if not generation_result.success:
            operation.mark_failed(
                f"Printable generation failed: {'; '.join(generation_result.issues)}",
                {
                    "generation_issues": generation_result.issues,
                    "processing_time_ms": generation_result.generation_time_ms
                }
            )
            await db.commit()
            
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Printable generation failed",
                    "issues": generation_result.issues,
                    "operation_id": str(operation.id)
                }
            )
        
        # Store generated document if requested
        storage_info = None
        if store_result and generation_result.output_file_path:
            storage_info = await storage_service.store_artifact(
                file_path=generation_result.output_file_path,
                artifact_type="printable",
                original_filename=generation_result.output_file_path.name,
                metadata={
                    "source_document": file.filename,
                    "document_type": generation_result.document_type,
                    "output_format": generation_result.output_format,
                    "generation_operation_id": str(operation.id),
                    "generated_from": "oscal_document",
                    **generation_result.metadata
                }
            )
        
        # Complete operation
        output_data = {
            "success": True,
            "document_type": generation_result.document_type,
            "output_format": generation_result.output_format,
            "file_size_bytes": generation_result.file_size_bytes,
            "generation_time_ms": generation_result.generation_time_ms,
            "storage_info": storage_info.dict() if storage_info else None,
            "generation_metadata": generation_result.metadata,
        }
        operation.mark_completed(output_data)
        await db.commit()
        
        # Prepare response
        response_data = {
            "operation_id": str(operation.id),
            "success": True,
            "message": f"Successfully generated {output_format.upper()} printable document",
            "document_type": generation_result.document_type,
            "output_format": generation_result.output_format,
            "generation_summary": {
                "processing_time_ms": generation_result.generation_time_ms,
                "file_size_bytes": generation_result.file_size_bytes,
                "controls_included": generation_result.metadata.get("controls_count", 0),
                "components_included": generation_result.metadata.get("components_count", 0),
                "document_title": generation_result.metadata.get("document_title"),
                "system_name": generation_result.metadata.get("system_name"),
            },
            "storage": storage_info.dict() if storage_info else None,
            "download_url": f"/api/v1/printables/operations/{operation.id}/download" if generation_result.success else None,
        }
        
        return JSONResponse(status_code=200, content=response_data)
        
    except Exception as e:
        operation.mark_failed(str(e), {"exception_type": type(e).__name__})
        await db.commit()
        
        logger.error("Printable generation failed", operation_id=str(operation.id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")
        
    finally:
        # Clean up temp file
        if temp_input_file and temp_input_file.exists():
            temp_input_file.unlink(missing_ok=True)


@router.post("/generate-from-json", response_model=dict)
async def generate_from_json_data(
    oscal_data: Dict = Form(..., description="OSCAL document data as JSON"),
    output_format: Literal["pdf", "html"] = Form("pdf", description="Output format"),
    document_title: Optional[str] = Form(None, description="Document title override"),
    store_result: bool = Form(True, description="Whether to store the generated document"),
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Generate a printable document from JSON OSCAL data.
    
    Alternative endpoint that accepts OSCAL data directly as JSON
    instead of requiring file upload.
    """
    operation = Operation(
        operation_type="printable_generation", 
        operation_name=f"Generate {output_format.upper()} from JSON data",
        operation_description=f"Printable generation from direct JSON: {output_format.upper()}",
        input_data={
            "source": "json_data",
            "output_format": output_format,
            "document_title": document_title,
        }
    )
    
    try:
        operation.mark_started()
        db.add(operation)
        await db.commit()
        
        # Override document title if provided
        if document_title and "system-security-plan" in oscal_data:
            ssp = oscal_data["system-security-plan"]
            if "metadata" not in ssp:
                ssp["metadata"] = {}
            ssp["metadata"]["title"] = document_title
        
        # Generate printable document
        generation_result: PrintableGenerationResult = await printable_service.generate_printable(
            oscal_document=oscal_data,
            output_format=output_format
        )
        
        if not generation_result.success:
            operation.mark_failed(
                f"Generation failed: {'; '.join(generation_result.issues)}"
            )
            await db.commit()
            
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Printable generation failed",
                    "issues": generation_result.issues
                }
            )
        
        # Store if requested
        storage_info = None
        if store_result and generation_result.output_file_path:
            storage_info = await storage_service.store_artifact(
                file_path=generation_result.output_file_path,
                artifact_type="printable",
                original_filename=generation_result.output_file_path.name,
                metadata={
                    "source": "json_data",
                    "document_type": generation_result.document_type,
                    "output_format": generation_result.output_format,
                    "generation_operation_id": str(operation.id),
                    **generation_result.metadata
                }
            )
        
        # Complete operation
        output_data = {
            "success": True,
            "document_type": generation_result.document_type,
            "output_format": generation_result.output_format,
            "generation_metadata": generation_result.metadata,
            "storage_info": storage_info.dict() if storage_info else None,
        }
        operation.mark_completed(output_data)
        await db.commit()
        
        return JSONResponse(
            status_code=200,
            content={
                "operation_id": str(operation.id),
                "success": True,
                "document_type": generation_result.document_type,
                "output_format": generation_result.output_format,
                "generation_summary": {
                    "processing_time_ms": generation_result.generation_time_ms,
                    "file_size_bytes": generation_result.file_size_bytes,
                },
                "storage": storage_info.dict() if storage_info else None,
                "download_url": f"/api/v1/printables/operations/{operation.id}/download"
            }
        )
        
    except Exception as e:
        operation.mark_failed(str(e))
        await db.commit()
        
        logger.error("JSON printable generation failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@router.get("/operations/{operation_id}/download")
async def download_printable_document(
    operation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Download the printable document generated from an operation."""
    from sqlalchemy import select
    
    # Get the operation
    query = select(Operation).where(
        Operation.id == operation_id,
        Operation.operation_type == "printable_generation",
        Operation.status == "completed"
    )
    result = await db.execute(query)
    operation = result.scalar_one_or_none()
    
    if not operation:
        raise HTTPException(
            status_code=404,
            detail="Printable generation operation not found or not completed"
        )
    
    output_data = operation.output_data
    storage_info = output_data.get("storage_info") if output_data else None
    
    if not storage_info:
        raise HTTPException(
            status_code=404,
            detail="Generated document not available for download"
        )
    
    try:
        # Generate download URL
        download_url = await storage_service.get_download_url(
            bucket=storage_info["bucket"],
            object_key=storage_info["object_key"],
            expires_in=3600  # 1 hour
        )
        
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=download_url, status_code=302)
        
    except Exception as e:
        logger.error("Failed to generate download URL", operation_id=str(operation_id), error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate download URL")


@router.get("/operations/{operation_id}", response_model=dict)
async def get_printable_operation(
    operation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get details of a printable generation operation."""
    from sqlalchemy import select
    
    query = select(Operation).where(
        Operation.id == operation_id,
        Operation.operation_type == "printable_generation"
    )
    result = await db.execute(query)
    operation = result.scalar_one_or_none()
    
    if not operation:
        raise HTTPException(status_code=404, detail="Printable generation operation not found")
    
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
        "created_at": operation.created_at.isoformat(),
        "updated_at": operation.updated_at.isoformat(),
    }


@router.get("/templates", response_model=dict)
async def list_available_templates() -> dict:
    """List available printable document templates."""
    return {
        "document_types": [
            {
                "type": "ssp",
                "name": "System Security Plan",
                "description": "Comprehensive system security documentation",
                "supported_formats": ["pdf", "html"],
                "template_version": "1.0",
                "status": "available"
            },
            {
                "type": "sap", 
                "name": "Security Assessment Plan",
                "description": "Assessment planning documentation",
                "supported_formats": ["pdf", "html"],
                "template_version": "1.0",
                "status": "coming_soon"
            },
            {
                "type": "sar",
                "name": "Security Assessment Report", 
                "description": "Assessment results documentation",
                "supported_formats": ["pdf", "html"],
                "template_version": "1.0",
                "status": "coming_soon"
            },
            {
                "type": "poam",
                "name": "Plan of Action and Milestones",
                "description": "Remediation planning documentation",
                "supported_formats": ["pdf", "html"],
                "template_version": "1.0", 
                "status": "coming_soon"
            }
        ],
        "output_formats": [
            {
                "format": "pdf",
                "description": "Portable Document Format",
                "mime_type": "application/pdf",
                "suitable_for": ["printing", "distribution", "archival"]
            },
            {
                "format": "html",
                "description": "HyperText Markup Language",
                "mime_type": "text/html",
                "suitable_for": ["web_viewing", "integration", "customization"]
            }
        ],
        "template_features": [
            "Professional formatting",
            "Automatic table of contents",
            "Control-by-control implementation details",
            "System component documentation",
            "Responsible roles and parties",
            "Custom CSS styling for PDF",
            "Markdown content support"
        ]
    }


@router.get("/preview/{document_type}", response_model=dict)
async def preview_template(
    document_type: Literal["ssp", "sap", "sar", "poam"],
    format: Literal["pdf", "html"] = Query("html", description="Preview format")
) -> JSONResponse:
    """
    Get a preview of a document template with sample data.
    
    Useful for understanding template structure and layout
    before generating actual documents.
    """
    if document_type != "ssp":
        raise HTTPException(
            status_code=501,
            detail=f"Template preview for {document_type} not yet implemented"
        )
    
    # Sample OSCAL SSP data for preview
    sample_ssp = {
        "system-security-plan": {
            "uuid": "12345678-1234-5678-9abc-123456789012",
            "metadata": {
                "title": "Sample System Security Plan",
                "version": "1.0",
                "last-modified": "2024-01-15T10:30:00Z",
                "oscal-version": "1.1.3",
                "roles": [
                    {"id": "system-owner", "title": "System Owner"},
                    {"id": "isso", "title": "Information System Security Officer"}
                ],
                "parties": [
                    {
                        "uuid": "party-1",
                        "type": "organization",
                        "name": "Sample Organization",
                        "email-addresses": [{"addr": "contact@example.com"}]
                    }
                ]
            },
            "system-characteristics": {
                "system-id": "sample-system-001",
                "system-name": "Sample Information System",
                "description": "This is a sample system security plan for demonstration purposes.",
                "authorization-boundary": {
                    "description": "The authorization boundary includes all components within the sample system."
                }
            },
            "system-implementation": {
                "components": [
                    {
                        "uuid": "comp-1",
                        "type": "software",
                        "title": "Sample Application Server",
                        "description": "Primary application server hosting the sample system",
                        "status": {"state": "operational"},
                        "responsible-roles": [{"role-id": "system-owner"}]
                    }
                ]
            },
            "control-implementation": {
                "implemented-requirements": [
                    {
                        "uuid": "req-ac-2",
                        "control-id": "ac-2",
                        "statements": [
                            {
                                "statement-id": "ac-2_stmt",
                                "uuid": "stmt-ac-2",
                                "description": "The organization manages information system accounts including establishment, activation, modification, review, and removal of accounts."
                            }
                        ],
                        "responsible-roles": [{"role-id": "isso"}]
                    },
                    {
                        "uuid": "req-ac-3",
                        "control-id": "ac-3",
                        "statements": [
                            {
                                "statement-id": "ac-3_stmt",
                                "uuid": "stmt-ac-3", 
                                "description": "The information system enforces approved authorizations for logical access to information and system resources."
                            }
                        ],
                        "responsible-roles": [{"role-id": "system-owner"}]
                    }
                ]
            }
        }
    }
    
    try:
        # Generate preview
        generation_result = await printable_service.generate_printable(
            oscal_document=sample_ssp,
            output_format=format
        )
        
        if not generation_result.success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate preview: {'; '.join(generation_result.issues)}"
            )
        
        # For HTML, return content directly; for PDF, return metadata
        if format == "html" and generation_result.output_file_path:
            html_content = generation_result.output_file_path.read_text(encoding='utf-8')
            return JSONResponse(
                status_code=200,
                content={
                    "document_type": document_type,
                    "format": format,
                    "preview_content": html_content,
                    "generation_metadata": generation_result.metadata,
                    "note": "This is a preview with sample data"
                }
            )
        else:
            return JSONResponse(
                status_code=200,
                content={
                    "document_type": document_type,
                    "format": format,
                    "file_size_bytes": generation_result.file_size_bytes,
                    "generation_metadata": generation_result.metadata,
                    "note": f"Preview {format.upper()} generated successfully",
                    "download_note": "Use the generate endpoint with actual OSCAL data to create downloadable documents"
                }
            )
            
    except Exception as e:
        logger.error("Template preview failed", document_type=document_type, error=str(e))
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {str(e)}")
    
    finally:
        # Clean up preview file
        if 'generation_result' in locals() and generation_result.output_file_path and generation_result.output_file_path.exists():
            generation_result.output_file_path.unlink(missing_ok=True)