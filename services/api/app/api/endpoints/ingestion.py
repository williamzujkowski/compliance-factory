"""
Document ingestion endpoints for DOCX to OSCAL mapping.

Provides endpoints for ingesting legacy document formats and converting
them to OSCAL structures, particularly for SSP generation.
"""

import json
from pathlib import Path
from typing import Literal, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import Operation
from app.services.ingestion_service import DocumentIngestionService, IngestionResult
from app.services.storage_service import StorageService

logger = structlog.get_logger()
router = APIRouter()

# Service instances
ingestion_service = DocumentIngestionService()
storage_service = StorageService()


@router.post("/docx", response_model=dict)
async def ingest_docx_file(
    file: UploadFile = File(..., description="DOCX file to ingest and convert to OSCAL"),
    target_document_type: Literal["ssp"] = Form("ssp", description="Target OSCAL document type"),
    system_id: Optional[str] = Form(None, description="System identifier for SSPs"),
    document_title: Optional[str] = Form(None, description="Document title (auto-generated if not provided)"),
    store_result: bool = Form(True, description="Whether to store the generated OSCAL document"),
    validate_output: bool = Form(True, description="Whether to validate the generated OSCAL document"),
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Ingest a DOCX file and convert it to OSCAL format.
    
    Supports conversion of legacy SSP documents in DOCX format to
    OSCAL System Security Plans with control mapping and structure extraction.
    """
    if not file.filename.lower().endswith('.docx'):
        raise HTTPException(
            status_code=400,
            detail="Only DOCX files are supported for ingestion"
        )
    
    operation = Operation(
        operation_type="ingestion",
        operation_name=f"Ingest {file.filename} to OSCAL {target_document_type.upper()}",
        operation_description=f"Document ingestion: DOCX to OSCAL {target_document_type}",
        input_data={
            "filename": file.filename,
            "target_document_type": target_document_type,
            "system_id": system_id,
            "document_title": document_title,
            "file_size": file.size if hasattr(file, 'size') else None,
        }
    )
    
    temp_file = None
    
    try:
        operation.mark_started()
        db.add(operation)
        await db.commit()
        
        # Save uploaded file temporarily
        temp_file = Path(f"/tmp/ingestion_{operation.id}_{file.filename}")
        content = await file.read()
        temp_file.write_bytes(content)
        
        # Ingest document
        ingestion_result: IngestionResult = await ingestion_service.ingest_docx(
            file_path=temp_file,
            target_document_type=target_document_type,
            system_id=system_id,
            document_title=document_title
        )
        
        if not ingestion_result.success:
            operation.mark_failed(
                f"Ingestion failed: {'; '.join(ingestion_result.issues)}",
                {
                    "ingestion_issues": ingestion_result.issues,
                    "processing_time_ms": ingestion_result.processing_time_ms
                }
            )
            await db.commit()
            
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Document ingestion failed",
                    "issues": ingestion_result.issues,
                    "operation_id": str(operation.id)
                }
            )
        
        # Validate generated OSCAL document if requested
        validation_result = None
        if validate_output and ingestion_result.oscal_document:
            validation_result = await ingestion_service.validate_ingested_document(
                ingestion_result.oscal_document
            )
        
        # Store generated OSCAL document if requested
        storage_info = None
        if store_result and ingestion_result.oscal_document:
            # Convert OSCAL document to JSON and store
            oscal_json = json.dumps(ingestion_result.oscal_document, indent=2)
            temp_oscal_file = Path(f"/tmp/generated_oscal_{operation.id}.json")
            temp_oscal_file.write_text(oscal_json, encoding='utf-8')
            
            storage_info = await storage_service.store_artifact(
                file_path=temp_oscal_file,
                artifact_type="ingested_oscal",
                original_filename=f"{Path(file.filename).stem}.json",
                metadata={
                    "source_document": file.filename,
                    "target_document_type": target_document_type,
                    "system_id": system_id,
                    "ingestion_operation_id": str(operation.id),
                    "generated_from": "docx_ingestion",
                    **ingestion_result.metadata
                }
            )
            
            # Clean up temp OSCAL file
            temp_oscal_file.unlink(missing_ok=True)
        
        # Complete operation
        output_data = {
            "success": True,
            "target_document_type": target_document_type,
            "processing_time_ms": ingestion_result.processing_time_ms,
            "extracted_metadata": ingestion_result.metadata,
            "storage_info": storage_info.dict() if storage_info else None,
            "validation_result": validation_result,
            "document_statistics": {
                "controls_identified": len(ingestion_result.extracted_content.get("controls_identified", [])),
                "sections_identified": len(ingestion_result.extracted_content.get("potential_ssp_sections", [])),
                "paragraphs_processed": ingestion_result.extracted_content.get("total_paragraphs", 0),
                "tables_processed": ingestion_result.extracted_content.get("total_tables", 0),
            }
        }
        operation.mark_completed(output_data)
        await db.commit()
        
        # Prepare response
        response_data = {
            "operation_id": str(operation.id),
            "success": True,
            "message": f"Successfully ingested {file.filename} to OSCAL {target_document_type.upper()}",
            "target_document_type": target_document_type,
            "processing_summary": {
                "processing_time_ms": ingestion_result.processing_time_ms,
                "controls_identified": len(ingestion_result.extracted_content.get("controls_identified", [])),
                "sections_mapped": len(ingestion_result.extracted_content.get("potential_ssp_sections", [])),
                "paragraphs_processed": ingestion_result.extracted_content.get("total_paragraphs", 0),
                "tables_processed": ingestion_result.extracted_content.get("total_tables", 0),
                "detected_document_type": ingestion_result.metadata.get("detected_document_type"),
            },
            "oscal_document": ingestion_result.oscal_document if not store_result else None,
            "storage": storage_info.dict() if storage_info else None,
            "validation": validation_result,
            "download_url": f"/api/v1/ingestion/operations/{operation.id}/download" if store_result else None,
        }
        
        return JSONResponse(status_code=200, content=response_data)
        
    except Exception as e:
        operation.mark_failed(str(e), {"exception_type": type(e).__name__})
        await db.commit()
        
        logger.error("Document ingestion failed", operation_id=str(operation.id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
        
    finally:
        # Clean up temp file
        if temp_file and temp_file.exists():
            temp_file.unlink(missing_ok=True)


@router.post("/analyze", response_model=dict)
async def analyze_document_structure(
    file: UploadFile = File(..., description="Document to analyze"),
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Analyze the structure of a document without full ingestion.
    
    Provides insights into document structure, identified sections,
    controls, and suitability for OSCAL conversion.
    """
    if not file.filename.lower().endswith('.docx'):
        raise HTTPException(
            status_code=400,
            detail="Only DOCX files are supported for analysis"
        )
    
    operation = Operation(
        operation_type="ingestion",
        operation_name=f"Analyze structure of {file.filename}",
        operation_description="Document structure analysis for ingestion planning",
        input_data={
            "filename": file.filename,
            "operation_type": "analysis_only",
            "file_size": file.size if hasattr(file, 'size') else None,
        }
    )
    
    temp_file = None
    
    try:
        operation.mark_started()
        db.add(operation)
        await db.commit()
        
        # Save uploaded file temporarily
        temp_file = Path(f"/tmp/analysis_{operation.id}_{file.filename}")
        content = await file.read()
        temp_file.write_bytes(content)
        
        # Load document and analyze structure
        from docx import Document
        doc = Document(temp_file)
        
        structure = ingestion_service.mapper.analyzer.analyze_document_structure(doc)
        
        # Complete operation
        output_data = {
            "analysis_complete": True,
            "document_statistics": structure,
            "suitability_assessment": {
                "recommended_target_type": structure.get("document_type", "ssp"),
                "confidence_score": len(structure.get("controls_identified", [])) / 50.0,  # Simple scoring
                "ingestion_feasibility": "high" if len(structure.get("controls_identified", [])) > 5 else "medium",
                "potential_issues": [
                    "Low control density" if len(structure.get("controls_identified", [])) < 5 else None,
                    "No clear sections identified" if not structure.get("potential_ssp_sections") else None,
                    "Complex table structure" if structure.get("total_tables", 0) > 20 else None
                ]
            }
        }
        output_data["suitability_assessment"]["potential_issues"] = [
            issue for issue in output_data["suitability_assessment"]["potential_issues"] if issue
        ]
        
        operation.mark_completed(output_data)
        await db.commit()
        
        return JSONResponse(
            status_code=200,
            content={
                "operation_id": str(operation.id),
                "filename": file.filename,
                "analysis_results": {
                    "document_type_detected": structure.get("document_type", "unknown"),
                    "total_paragraphs": structure.get("total_paragraphs", 0),
                    "total_tables": structure.get("total_tables", 0),
                    "headings_found": len(structure.get("headings", [])),
                    "controls_identified": len(structure.get("controls_identified", [])),
                    "ssp_sections_identified": len(structure.get("potential_ssp_sections", [])),
                },
                "identified_controls": [
                    {
                        "control_id": ctrl["control_id"],
                        "control_title": ctrl["control_title"]
                    }
                    for ctrl in structure.get("controls_identified", [])[:20]  # Limit to first 20
                ],
                "identified_sections": [
                    {
                        "section_type": section["section_type"],
                        "oscal_path": section["oscal_path"],
                        "confidence": section["confidence"]
                    }
                    for section in structure.get("potential_ssp_sections", [])
                ],
                "suitability_assessment": output_data["suitability_assessment"],
                "recommendations": {
                    "proceed_with_ingestion": len(structure.get("controls_identified", [])) > 3,
                    "recommended_target_type": structure.get("document_type", "ssp"),
                    "manual_review_recommended": len(structure.get("controls_identified", [])) < 5,
                    "preprocessing_suggestions": [
                        "Consider manual cleanup of table formatting" if structure.get("total_tables", 0) > 10 else None,
                        "Review control identification accuracy" if len(structure.get("controls_identified", [])) < 10 else None,
                        "Verify section mapping" if not structure.get("potential_ssp_sections") else None,
                    ]
                }
            }
        )
        
    except Exception as e:
        operation.mark_failed(str(e), {"exception_type": type(e).__name__})
        await db.commit()
        
        logger.error("Document analysis failed", operation_id=str(operation.id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
        
    finally:
        # Clean up temp file
        if temp_file and temp_file.exists():
            temp_file.unlink(missing_ok=True)


@router.get("/operations/{operation_id}/download")
async def download_ingested_document(
    operation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Download the OSCAL document generated from an ingestion operation."""
    from sqlalchemy import select
    
    # Get the operation
    query = select(Operation).where(
        Operation.id == operation_id,
        Operation.operation_type == "ingestion",
        Operation.status == "completed"
    )
    result = await db.execute(query)
    operation = result.scalar_one_or_none()
    
    if not operation:
        raise HTTPException(
            status_code=404,
            detail="Ingestion operation not found or not completed"
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
async def get_ingestion_operation(
    operation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get details of an ingestion operation."""
    from sqlalchemy import select
    
    query = select(Operation).where(
        Operation.id == operation_id,
        Operation.operation_type == "ingestion"
    )
    result = await db.execute(query)
    operation = result.scalar_one_or_none()
    
    if not operation:
        raise HTTPException(status_code=404, detail="Ingestion operation not found")
    
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


@router.get("/supported-formats", response_model=dict)
async def get_supported_formats() -> dict:
    """Get information about supported document formats for ingestion."""
    return {
        "supported_input_formats": [
            {
                "format": "docx",
                "description": "Microsoft Word Document (Office Open XML)",
                "supported_content_types": [
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ],
                "typical_use_cases": [
                    "Legacy SSP documents",
                    "Control implementation matrices",
                    "System documentation"
                ],
                "extraction_capabilities": [
                    "Text content and structure",
                    "Tables and structured data", 
                    "Section identification",
                    "Control pattern recognition"
                ]
            }
        ],
        "supported_output_formats": [
            {
                "format": "ssp",
                "description": "OSCAL System Security Plan",
                "version": "1.1.3",
                "file_extension": ".json",
                "content_type": "application/json"
            }
        ],
        "future_formats": [
            {
                "format": "pdf",
                "status": "planned",
                "description": "PDF document extraction (OCR-based)"
            },
            {
                "format": "xlsx", 
                "status": "planned",
                "description": "Excel spreadsheet control matrices"
            }
        ]
    }