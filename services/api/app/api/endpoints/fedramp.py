"""
FedRAMP constraint validation endpoints.

Provides endpoints for validating OSCAL documents against FedRAMP 20x
requirements including baseline-specific constraints and compliance validation.
"""

from pathlib import Path
from typing import Literal, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import Operation
from app.services.fedramp_service import FedRAMPService, FedRAMPValidationResult

logger = structlog.get_logger()
router = APIRouter()

# Service instance
fedramp_service = FedRAMPService()


@router.post("/validate/file", response_model=dict)
async def validate_fedramp_file(
    file: UploadFile = File(..., description="OSCAL file to validate against FedRAMP constraints"),
    baseline: Literal["low", "moderate", "high"] = Form("moderate", description="FedRAMP baseline"),
    document_type: Optional[str] = Form(None, description="OSCAL document type (auto-detected if not provided)"),
    store_result: bool = Form(True, description="Whether to store validation results"),
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Validate an uploaded OSCAL file against FedRAMP constraints.
    
    Performs FedRAMP-specific validation beyond basic OSCAL schema validation,
    including baseline requirements, control implementation validation, and
    compliance checking.
    """
    if file.content_type not in ["application/json", "application/xml", "text/xml"]:
        raise HTTPException(
            status_code=400,
            detail="Only JSON and XML OSCAL files are supported"
        )
    
    operation = Operation(
        operation_type="fedramp_check",
        operation_name=f"FedRAMP {baseline.title()} validation of {file.filename}",
        operation_description=f"FedRAMP constraint validation for {baseline} baseline",
        input_data={
            "filename": file.filename,
            "content_type": file.content_type,
            "baseline": baseline,
            "document_type": document_type,
            "file_size": file.size if hasattr(file, 'size') else None,
        }
    )
    
    temp_file = None
    
    try:
        operation.mark_started()
        db.add(operation)
        await db.commit()
        
        # Save uploaded file temporarily
        temp_file = Path(f"/tmp/fedramp_{operation.id}_{file.filename}")
        content = await file.read()
        temp_file.write_bytes(content)
        
        # Validate with FedRAMP service
        fedramp_result: FedRAMPValidationResult = await fedramp_service.validate_document(
            file_path=temp_file,
            baseline=baseline,
            document_type=document_type
        )
        
        # TODO: Store detailed results in database if store_result=True
        # This would involve extending the database models to handle FedRAMP results
        
        # Complete operation
        output_data = {
            "is_compliant": fedramp_result.is_compliant,
            "baseline": fedramp_result.baseline,
            "document_type": fedramp_result.document_type,
            "error_count": fedramp_result.error_count,
            "warning_count": fedramp_result.warning_count,
            "total_issues": len(fedramp_result.issues),
            "validation_time_ms": fedramp_result.validation_time_ms,
        }
        operation.mark_completed(output_data)
        await db.commit()
        
        # Prepare response
        response_data = {
            "operation_id": str(operation.id),
            "is_compliant": fedramp_result.is_compliant,
            "baseline": fedramp_result.baseline,
            "document_type": fedramp_result.document_type,
            "validation_summary": {
                "total_issues": len(fedramp_result.issues),
                "errors": fedramp_result.error_count,
                "warnings": fedramp_result.warning_count,
                "validation_time_ms": fedramp_result.validation_time_ms,
            },
            "issues": [
                {
                    "severity": issue.severity,
                    "code": issue.code,
                    "message": issue.message,
                    "location": issue.location,
                    "requirement": issue.requirement,
                    "baseline": issue.baseline,
                    "suggested_fix": issue.suggested_fix,
                    "context": issue.context,
                }
                for issue in fedramp_result.issues
            ],
            "metadata": fedramp_result.metadata,
        }
        
        status_code = 200 if fedramp_result.is_compliant else 400
        return JSONResponse(status_code=status_code, content=response_data)
        
    except Exception as e:
        operation.mark_failed(str(e), {"exception_type": type(e).__name__})
        await db.commit()
        
        logger.error("FedRAMP validation failed", operation_id=str(operation.id), error=str(e))
        raise HTTPException(status_code=500, detail=f"FedRAMP validation failed: {str(e)}")
        
    finally:
        # Clean up temp file
        if temp_file and temp_file.exists():
            temp_file.unlink(missing_ok=True)


@router.get("/baselines/{baseline}/requirements", response_model=dict)
async def get_baseline_requirements(
    baseline: Literal["low", "moderate", "high"],
) -> dict:
    """
    Get the requirements for a specific FedRAMP baseline.
    
    Returns the control requirements, metadata requirements, and other
    constraints for the specified baseline.
    """
    try:
        requirements = await fedramp_service.get_baseline_requirements(baseline)
        
        if not requirements:
            raise HTTPException(
                status_code=404,
                detail=f"Requirements not found for baseline: {baseline}"
            )
        
        return {
            "baseline": baseline,
            "requirements": requirements,
            "description": f"FedRAMP {baseline.title()} baseline requirements",
            "last_updated": "2024-01-01",  # Would be actual date from requirements
        }
        
    except Exception as e:
        logger.error("Failed to get baseline requirements", baseline=baseline, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get baseline requirements: {str(e)}"
        )


@router.get("/baselines", response_model=dict)
async def list_baselines() -> dict:
    """List available FedRAMP baselines and their basic information."""
    return {
        "baselines": [
            {
                "id": "low",
                "name": "FedRAMP Low",
                "description": "Low impact systems with basic security controls",
                "min_controls": 108,
                "use_cases": ["Public information", "Low-risk applications"],
            },
            {
                "id": "moderate",
                "name": "FedRAMP Moderate",
                "description": "Moderate impact systems with comprehensive security controls",
                "min_controls": 325,
                "use_cases": ["Sensitive but unclassified information", "Business applications"],
            },
            {
                "id": "high",
                "name": "FedRAMP High",
                "description": "High impact systems with extensive security controls",
                "min_controls": 421,
                "use_cases": ["Sensitive/classified information", "Critical infrastructure"],
            },
        ],
        "default_baseline": "moderate",
        "oscal_version": "1.1.3",
    }


@router.post("/validate/batch", response_model=dict)
async def validate_fedramp_batch(
    files: list[UploadFile] = File(..., description="OSCAL files to validate"),
    baseline: Literal["low", "moderate", "high"] = Form("moderate", description="FedRAMP baseline"),
    store_results: bool = Form(True, description="Whether to store validation results"),
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Validate multiple OSCAL files against FedRAMP constraints in batch.
    
    Processes multiple files and returns individual validation results
    for each file along with a summary.
    """
    if len(files) > 20:  # Reasonable batch size for FedRAMP validation
        raise HTTPException(
            status_code=400,
            detail="Batch size limited to 20 files maximum for FedRAMP validation"
        )
    
    # Create parent operation for batch tracking
    parent_operation = Operation(
        operation_type="fedramp_check",
        operation_name=f"FedRAMP batch validation of {len(files)} files ({baseline} baseline)",
        operation_description=f"Batch FedRAMP constraint validation for {baseline} baseline",
        input_data={
            "file_count": len(files),
            "baseline": baseline,
            "filenames": [f.filename for f in files],
        }
    )
    parent_operation.mark_started()
    db.add(parent_operation)
    await db.commit()
    
    results = []
    compliant_count = 0
    
    try:
        import asyncio
        
        async def validate_single_file(file: UploadFile) -> dict:
            """Validate a single file and return result info."""
            nonlocal compliant_count
            
            temp_file = None
            child_operation = None
            
            try:
                # Create child operation
                child_operation = Operation(
                    operation_type="fedramp_check",
                    operation_name=f"FedRAMP validation: {file.filename}",
                    operation_description=f"Batch item: FedRAMP {baseline} validation",
                    parent_operation_id=parent_operation.id,
                    input_data={
                        "filename": file.filename,
                        "baseline": baseline,
                        "batch_item": True,
                    }
                )
                child_operation.mark_started()
                db.add(child_operation)
                await db.flush()
                
                # Save file temporarily
                temp_file = Path(f"/tmp/fedramp_batch_{child_operation.id}_{file.filename}")
                content = await file.read()
                temp_file.write_bytes(content)
                
                # Validate with FedRAMP service
                fedramp_result = await fedramp_service.validate_document(
                    file_path=temp_file,
                    baseline=baseline
                )
                
                if fedramp_result.is_compliant:
                    compliant_count += 1
                
                child_operation.mark_completed({
                    "is_compliant": fedramp_result.is_compliant,
                    "error_count": fedramp_result.error_count,
                    "warning_count": fedramp_result.warning_count,
                })
                
                return {
                    "operation_id": str(child_operation.id),
                    "filename": file.filename,
                    "is_compliant": fedramp_result.is_compliant,
                    "document_type": fedramp_result.document_type,
                    "summary": {
                        "errors": fedramp_result.error_count,
                        "warnings": fedramp_result.warning_count,
                        "total_issues": len(fedramp_result.issues),
                    },
                    "issues": [
                        {
                            "severity": issue.severity,
                            "code": issue.code,
                            "message": issue.message,
                            "location": issue.location,
                            "requirement": issue.requirement,
                        }
                        for issue in fedramp_result.issues[:10]  # Limit to first 10 issues
                    ],
                    "truncated_issues": len(fedramp_result.issues) > 10,
                }
                
            except Exception as e:
                if child_operation:
                    child_operation.mark_failed(str(e))
                
                return {
                    "operation_id": str(child_operation.id) if child_operation else None,
                    "filename": file.filename,
                    "is_compliant": False,
                    "error": str(e),
                }
                
            finally:
                # Clean up temp file
                if temp_file and temp_file.exists():
                    temp_file.unlink(missing_ok=True)
        
        # Process files with limited concurrency (FedRAMP validation is more intensive)
        semaphore = asyncio.Semaphore(3)  # Process 3 files at a time
        
        async def validate_with_semaphore(file):
            async with semaphore:
                return await validate_single_file(file)
        
        results = await asyncio.gather(
            *[validate_with_semaphore(file) for file in files],
            return_exceptions=True
        )
        
        # Handle any exceptions from gather
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                results[i] = {
                    "filename": files[i].filename,
                    "is_compliant": False,
                    "error": str(result),
                }
        
        # Complete parent operation
        parent_operation.mark_completed({
            "total_files": len(files),
            "compliant_files": compliant_count,
            "non_compliant_files": len(files) - compliant_count,
            "baseline": baseline,
        })
        
        await db.commit()
        
        return JSONResponse(
            status_code=200,
            content={
                "batch_operation_id": str(parent_operation.id),
                "baseline": baseline,
                "summary": {
                    "total_files": len(files),
                    "compliant": compliant_count,
                    "non_compliant": len(files) - compliant_count,
                    "compliance_rate": (compliant_count / len(files) * 100) if files else 0,
                },
                "results": results,
            }
        )
        
    except Exception as e:
        parent_operation.mark_failed(str(e))
        await db.commit()
        logger.error("FedRAMP batch validation failed", operation_id=str(parent_operation.id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Batch validation failed: {str(e)}")


@router.get("/validate/operations/{operation_id}", response_model=dict)
async def get_fedramp_operation(
    operation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get details of a FedRAMP validation operation."""
    from sqlalchemy import select
    
    query = select(Operation).where(
        Operation.id == operation_id,
        Operation.operation_type == "fedramp_check"
    )
    result = await db.execute(query)
    operation = result.scalar_one_or_none()
    
    if not operation:
        raise HTTPException(status_code=404, detail="FedRAMP validation operation not found")
    
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


@router.get("/controls", response_model=dict)
async def get_control_information(
    control_id: Optional[str] = Query(None, description="Specific control ID (e.g., 'ac-2')"),
    baseline: Optional[Literal["low", "moderate", "high"]] = Query(None, description="Filter by baseline"),
) -> dict:
    """
    Get information about NIST 800-53 controls and their FedRAMP requirements.
    
    Returns control definitions, implementation requirements, and baseline mappings.
    """
    # This would typically load from external control catalogs/registries
    # For now, return basic information
    
    if control_id:
        # Return specific control information
        control_info = {
            "id": control_id.lower(),
            "title": f"Control {control_id.upper()}",
            "description": f"This would contain the full description for control {control_id.upper()}",
            "baseline_requirements": {
                "low": control_id.lower() in ["ac-1", "ac-2", "ac-3", "ac-7"],
                "moderate": control_id.lower() in ["ac-1", "ac-2", "ac-3", "ac-4", "ac-5", "ac-6", "ac-7"],
                "high": True,  # Assume all controls are required for high
            },
            "implementation_guidance": f"Implementation guidance for {control_id.upper()} would be provided here",
            "fedramp_requirements": [
                "Standard NIST 800-53 implementation",
                "FedRAMP-specific parameters and guidance",
            ]
        }
        
        return {
            "control": control_info,
            "last_updated": "2024-01-01",
        }
    
    else:
        # Return summary information
        return {
            "message": "Control catalog information",
            "total_controls": 421,  # Approximate number in NIST 800-53
            "baselines": {
                "low": {"control_count": 108},
                "moderate": {"control_count": 325},
                "high": {"control_count": 421},
            },
            "note": "Use control_id parameter to get specific control information",
        }