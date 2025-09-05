"""Main API router configuration."""

from fastapi import APIRouter

# Import route modules
from app.api.endpoints import (
    validation,
    conversion,
    storage,
    operations,
    fedramp,
    ingestion,
    printables,
)

api_router = APIRouter()

# Health check routes
@api_router.get("/health")
async def health() -> dict[str, str]:
    """API health check."""
    from app.core.database import check_database_health
    
    # Check database connectivity
    db_health = await check_database_health()
    
    overall_status = "healthy" if db_health["status"] == "healthy" else "degraded"
    
    return {
        "status": overall_status,
        "service": "api",
        "database": db_health["status"],
        "timestamp": "2024-01-01T00:00:00Z",  # Will be updated with real time
    }

# Version and info routes
@api_router.get("/version")
async def version() -> dict[str, str]:
    """Get API version information."""
    from app.core.config import get_settings
    settings = get_settings()
    return {
        "version": settings.version,
        "oscal_version": "1.1.3",
        "api_version": "v1",
        "service": "OSCAL Compliance Factory",
    }

# Include endpoint routers
api_router.include_router(
    validation.router, 
    prefix="/validate", 
    tags=["Validation"],
    responses={
        400: {"description": "Validation failed"},
        422: {"description": "Invalid request format"},
        500: {"description": "Server error"},
    }
)

api_router.include_router(
    conversion.router, 
    prefix="/convert", 
    tags=["Conversion"],
    responses={
        400: {"description": "Conversion failed"},
        422: {"description": "Invalid request format"}, 
        500: {"description": "Server error"},
    }
)

api_router.include_router(
    storage.router, 
    prefix="/storage", 
    tags=["Storage & Artifacts"],
    responses={
        404: {"description": "Artifact not found"},
        422: {"description": "Invalid request format"},
        500: {"description": "Server error"},
    }
)

api_router.include_router(
    operations.router, 
    prefix="/operations", 
    tags=["Operations & Monitoring"],
    responses={
        404: {"description": "Operation not found"},
        422: {"description": "Invalid request format"},
        500: {"description": "Server error"},
    }
)

api_router.include_router(
    fedramp.router, 
    prefix="/fedramp", 
    tags=["FedRAMP Compliance"],
    responses={
        400: {"description": "Compliance validation failed"},
        404: {"description": "Resource not found"},
        422: {"description": "Invalid request format"},
        500: {"description": "Server error"},
    }
)

api_router.include_router(
    ingestion.router, 
    prefix="/ingestion", 
    tags=["Document Ingestion"],
    responses={
        400: {"description": "Ingestion failed"},
        404: {"description": "Resource not found"},
        422: {"description": "Invalid request format"},
        500: {"description": "Server error"},
    }
)

api_router.include_router(
    printables.router, 
    prefix="/printables", 
    tags=["Printable Generation"],
    responses={
        400: {"description": "Generation failed"},
        404: {"description": "Resource not found"},
        422: {"description": "Invalid request format"},
        501: {"description": "Feature not implemented"},
        500: {"description": "Server error"},
    }
)