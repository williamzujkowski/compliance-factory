"""
Operations tracking and monitoring endpoints.

Provides endpoints for tracking long-running operations, monitoring their progress,
and retrieving operational logs and metrics.
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.orm import selectinload

from app.core.database import get_db_session
from app.models import Operation, OperationLog

logger = structlog.get_logger()
router = APIRouter()


@router.get("/", response_model=dict)
async def list_operations(
    limit: int = Query(50, description="Maximum number of operations to return"),
    offset: int = Query(0, description="Number of operations to skip"),
    operation_type: Optional[str] = Query(None, description="Filter by operation type"),
    status: Optional[str] = Query(None, description="Filter by operation status"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    since: Optional[datetime] = Query(None, description="Filter operations since this timestamp"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """List operations with optional filtering and pagination."""
    
    query = select(Operation).order_by(desc(Operation.created_at))
    count_query = select(func.count(Operation.id))
    
    # Apply filters
    filters = []
    
    if operation_type:
        filters.append(Operation.operation_type == operation_type)
    
    if status:
        filters.append(Operation.status == status)
    
    if user_id:
        filters.append(Operation.user_id == user_id)
    
    if since:
        filters.append(Operation.created_at >= since)
    
    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))
    
    # Get total count
    total_count = (await db.execute(count_query)).scalar()
    
    # Apply pagination
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    operations = result.scalars().all()
    
    return {
        "operations": [
            {
                "id": str(op.id),
                "operation_type": op.operation_type,
                "operation_name": op.operation_name,
                "operation_description": op.operation_description,
                "status": op.status,
                "progress_percent": op.progress_percent,
                "started_at": op.started_at.isoformat() if op.started_at else None,
                "completed_at": op.completed_at.isoformat() if op.completed_at else None,
                "duration_ms": op.duration_ms,
                "error_message": op.error_message,
                "retry_count": op.retry_count,
                "user_id": op.user_id,
                "session_id": op.session_id,
                "correlation_id": op.correlation_id,
                "parent_operation_id": str(op.parent_operation_id) if op.parent_operation_id else None,
                "created_at": op.created_at.isoformat(),
                "updated_at": op.updated_at.isoformat(),
            }
            for op in operations
        ],
        "pagination": {
            "total": total_count,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + limit) < total_count,
        },
        "filters": {
            "operation_type": operation_type,
            "status": status,
            "user_id": user_id,
            "since": since.isoformat() if since else None,
        }
    }


@router.get("/{operation_id}", response_model=dict)
async def get_operation(
    operation_id: UUID,
    include_logs: bool = Query(True, description="Include operation logs"),
    include_children: bool = Query(False, description="Include child operations"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get detailed operation information."""
    
    query = select(Operation).where(Operation.id == operation_id)
    
    if include_logs:
        query = query.options(selectinload(Operation.logs))
    
    if include_children:
        query = query.options(selectinload(Operation.child_operations))
    
    result = await db.execute(query)
    operation = result.scalar_one_or_none()
    
    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    response_data = {
        "id": str(operation.id),
        "operation_type": operation.operation_type,
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
        "error_details": operation.error_details,
        "retry_count": operation.retry_count,
        "max_retries": operation.max_retries,
        "correlation_id": operation.correlation_id,
        "parent_operation_id": str(operation.parent_operation_id) if operation.parent_operation_id else None,
        "user_id": operation.user_id,
        "session_id": operation.session_id,
        "cpu_time_ms": operation.cpu_time_ms,
        "memory_peak_bytes": operation.memory_peak_bytes,
        "created_at": operation.created_at.isoformat(),
        "updated_at": operation.updated_at.isoformat(),
    }
    
    if include_logs and operation.logs:
        response_data["logs"] = [
            {
                "id": str(log.id),
                "level": log.level,
                "message": log.message,
                "details": log.details,
                "component": log.component,
                "created_at": log.created_at.isoformat(),
            }
            for log in operation.logs
        ]
    
    if include_children and operation.child_operations:
        response_data["child_operations"] = [
            {
                "id": str(child.id),
                "operation_type": child.operation_type,
                "operation_name": child.operation_name,
                "status": child.status,
                "progress_percent": child.progress_percent,
                "duration_ms": child.duration_ms,
                "error_message": child.error_message,
                "created_at": child.created_at.isoformat(),
                "completed_at": child.completed_at.isoformat() if child.completed_at else None,
            }
            for child in operation.child_operations
        ]
    
    return response_data


@router.post("/{operation_id}/cancel", response_model=dict)
async def cancel_operation(
    operation_id: UUID,
    reason: Optional[str] = Query(None, description="Reason for cancellation"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Cancel a running operation."""
    
    query = select(Operation).where(Operation.id == operation_id)
    result = await db.execute(query)
    operation = result.scalar_one_or_none()
    
    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    if operation.status not in ["pending", "running"]:
        raise HTTPException(
            status_code=400,
            detail=f"Operation cannot be cancelled (status: {operation.status})"
        )
    
    try:
        # Update operation status
        operation.status = "cancelled"
        operation.completed_at = datetime.now(timezone.utc)
        operation.error_message = reason or "Operation cancelled by user"
        
        if operation.started_at:
            delta = operation.completed_at - operation.started_at
            operation.duration_ms = int(delta.total_seconds() * 1000)
        
        # Add cancellation log
        operation.add_log(
            level="info",
            message="Operation cancelled",
            details={
                "reason": reason,
                "cancelled_at": operation.completed_at.isoformat(),
                "cancelled_by": "api_request",  # Could be enhanced with user context
            }
        )
        
        await db.commit()
        
        logger.info(
            "Operation cancelled",
            operation_id=str(operation_id),
            reason=reason,
        )
        
        return {
            "operation_id": str(operation_id),
            "status": "cancelled",
            "message": "Operation cancelled successfully",
            "cancelled_at": operation.completed_at.isoformat(),
            "reason": reason,
        }
        
    except Exception as e:
        await db.rollback()
        logger.error("Failed to cancel operation", operation_id=str(operation_id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to cancel operation: {str(e)}")


@router.get("/{operation_id}/logs", response_model=dict)
async def get_operation_logs(
    operation_id: UUID,
    level: Optional[str] = Query(None, description="Filter by log level"),
    limit: int = Query(100, description="Maximum number of logs to return"),
    offset: int = Query(0, description="Number of logs to skip"),
    since: Optional[datetime] = Query(None, description="Filter logs since this timestamp"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get logs for a specific operation."""
    
    # Verify operation exists
    op_query = select(Operation.id).where(Operation.id == operation_id)
    op_result = await db.execute(op_query)
    if not op_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Operation not found")
    
    # Build logs query
    query = select(OperationLog).where(OperationLog.operation_id == operation_id)
    count_query = select(func.count(OperationLog.id)).where(OperationLog.operation_id == operation_id)
    
    filters = []
    
    if level:
        filters.append(OperationLog.level == level)
    
    if since:
        filters.append(OperationLog.created_at >= since)
    
    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))
    
    # Order by creation time
    query = query.order_by(desc(OperationLog.created_at))
    
    # Get total count
    total_count = (await db.execute(count_query)).scalar()
    
    # Apply pagination
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()
    
    return {
        "operation_id": str(operation_id),
        "logs": [
            {
                "id": str(log.id),
                "level": log.level,
                "message": log.message,
                "details": log.details,
                "component": log.component,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
        "pagination": {
            "total": total_count,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + limit) < total_count,
        },
        "filters": {
            "level": level,
            "since": since.isoformat() if since else None,
        }
    }


@router.get("/stats/summary", response_model=dict)
async def get_operations_summary(
    timeframe_hours: int = Query(24, description="Timeframe in hours for statistics"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get summary statistics for operations."""
    
    since_time = datetime.now(timezone.utc) - timedelta(hours=timeframe_hours)
    
    # Overall statistics
    total_query = select(func.count(Operation.id)).where(Operation.created_at >= since_time)
    total_operations = (await db.execute(total_query)).scalar()
    
    # Status breakdown
    status_query = select(
        Operation.status,
        func.count(Operation.id).label('count')
    ).where(
        Operation.created_at >= since_time
    ).group_by(Operation.status)
    
    status_result = await db.execute(status_query)
    status_breakdown = {row.status: row.count for row in status_result}
    
    # Type breakdown
    type_query = select(
        Operation.operation_type,
        func.count(Operation.id).label('count')
    ).where(
        Operation.created_at >= since_time
    ).group_by(Operation.operation_type)
    
    type_result = await db.execute(type_query)
    type_breakdown = {row.operation_type: row.count for row in type_result}
    
    # Average duration for completed operations
    duration_query = select(
        func.avg(Operation.duration_ms).label('avg_duration'),
        func.min(Operation.duration_ms).label('min_duration'),
        func.max(Operation.duration_ms).label('max_duration')
    ).where(
        and_(
            Operation.created_at >= since_time,
            Operation.status == "completed",
            Operation.duration_ms.isnot(None)
        )
    )
    
    duration_result = await db.execute(duration_query)
    duration_stats = duration_result.first()
    
    # Error rate
    error_query = select(func.count(Operation.id)).where(
        and_(
            Operation.created_at >= since_time,
            Operation.status == "failed"
        )
    )
    error_count = (await db.execute(error_query)).scalar()
    
    # Success rate
    success_query = select(func.count(Operation.id)).where(
        and_(
            Operation.created_at >= since_time,
            Operation.status == "completed"
        )
    )
    success_count = (await db.execute(success_query)).scalar()
    
    # Active operations
    active_query = select(func.count(Operation.id)).where(
        Operation.status.in_(["pending", "running"])
    )
    active_count = (await db.execute(active_query)).scalar()
    
    return {
        "timeframe_hours": timeframe_hours,
        "since": since_time.isoformat(),
        "summary": {
            "total_operations": total_operations,
            "active_operations": active_count,
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": (success_count / total_operations * 100) if total_operations > 0 else 0,
            "error_rate": (error_count / total_operations * 100) if total_operations > 0 else 0,
        },
        "status_breakdown": status_breakdown,
        "type_breakdown": type_breakdown,
        "duration_stats": {
            "avg_duration_ms": float(duration_stats.avg_duration) if duration_stats.avg_duration else None,
            "min_duration_ms": duration_stats.min_duration,
            "max_duration_ms": duration_stats.max_duration,
        } if duration_stats else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/stats/performance", response_model=dict)
async def get_performance_metrics(
    operation_type: Optional[str] = Query(None, description="Filter by operation type"),
    timeframe_hours: int = Query(24, description="Timeframe in hours"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get performance metrics for operations."""
    
    since_time = datetime.now(timezone.utc) - timedelta(hours=timeframe_hours)
    
    # Base query for completed operations
    base_query = select(Operation).where(
        and_(
            Operation.created_at >= since_time,
            Operation.status == "completed",
            Operation.duration_ms.isnot(None)
        )
    )
    
    if operation_type:
        base_query = base_query.where(Operation.operation_type == operation_type)
    
    result = await db.execute(base_query)
    operations = result.scalars().all()
    
    if not operations:
        return {
            "message": "No completed operations found for the specified criteria",
            "timeframe_hours": timeframe_hours,
            "operation_type": operation_type,
        }
    
    durations = [op.duration_ms for op in operations if op.duration_ms is not None]
    cpu_times = [op.cpu_time_ms for op in operations if op.cpu_time_ms is not None]
    memory_peaks = [op.memory_peak_bytes for op in operations if op.memory_peak_bytes is not None]
    
    # Calculate percentiles for duration
    import statistics
    
    def calculate_percentile(data, percentile):
        if not data:
            return None
        return statistics.quantiles(sorted(data), n=100)[percentile - 1] if len(data) > 1 else data[0]
    
    performance_metrics = {
        "timeframe_hours": timeframe_hours,
        "operation_type": operation_type,
        "operation_count": len(operations),
        "duration_metrics": {
            "avg_ms": statistics.mean(durations) if durations else None,
            "median_ms": statistics.median(durations) if durations else None,
            "min_ms": min(durations) if durations else None,
            "max_ms": max(durations) if durations else None,
            "p50_ms": calculate_percentile(durations, 50),
            "p95_ms": calculate_percentile(durations, 95),
            "p99_ms": calculate_percentile(durations, 99),
            "std_dev_ms": statistics.stdev(durations) if len(durations) > 1 else None,
        },
        "resource_usage": {
            "cpu_time": {
                "avg_ms": statistics.mean(cpu_times) if cpu_times else None,
                "max_ms": max(cpu_times) if cpu_times else None,
                "operations_with_data": len(cpu_times),
            },
            "memory": {
                "avg_bytes": statistics.mean(memory_peaks) if memory_peaks else None,
                "max_bytes": max(memory_peaks) if memory_peaks else None,
                "operations_with_data": len(memory_peaks),
            }
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    return performance_metrics