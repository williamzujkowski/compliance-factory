"""Main API router configuration."""

from fastapi import APIRouter

# Import route modules (will be created later)
# from app.api.endpoints import (
#     oscal,
#     validation, 
#     conversion,
#     documents,
#     storage,
#     health,
# )

api_router = APIRouter()

# Health check routes
@api_router.get("/health")
async def health() -> dict[str, str]:
    """API health check."""
    return {"status": "healthy", "service": "api"}

# Placeholder routes - will be implemented in separate modules
@api_router.get("/version")
async def version() -> dict[str, str]:
    """Get API version information."""
    from app import __version__
    return {"version": __version__, "oscal_version": "1.1.3"}

# TODO: Include actual endpoint routers once implemented
# api_router.include_router(oscal.router, prefix="/oscal", tags=["OSCAL"])
# api_router.include_router(validation.router, prefix="/validate", tags=["Validation"])
# api_router.include_router(conversion.router, prefix="/convert", tags=["Conversion"])
# api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
# api_router.include_router(storage.router, prefix="/storage", tags=["Storage"])