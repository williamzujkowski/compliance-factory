"""
Main FastAPI application for the OSCAL Compliance Factory.

This service provides OSCAL validation, conversion, and compliance checking
capabilities aligned with FedRAMP 20x requirements.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.api.routes import api_router
from app.core.exceptions import ComplianceFactoryException


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup and shutdown events."""
    settings = get_settings()
    logger = structlog.get_logger()
    
    # Startup
    logger.info("Starting OSCAL Compliance Factory API", version=settings.version)
    
    # Initialize database connection
    # await init_db()
    
    # Initialize MinIO/S3 storage
    # await init_storage()
    
    # Verify OSCAL CLI availability
    # await verify_oscal_cli()
    
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down OSCAL Compliance Factory API")
    # Cleanup resources here if needed


def create_application() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()
    setup_logging()
    
    app = FastAPI(
        title="OSCAL Compliance Factory",
        description="""
        A containerized OSCAL compliance factory that ingests legacy SSPs, 
        authors/edits in Markdown/GUI, validates with oscal-cli + FedRAMP constraints,
        generates printables, and publishes artifacts to S3-compatible storage.
        
        ## Key Features
        
        * **OSCAL 1.1.3 Support**: Full validation and conversion
        * **FedRAMP 20x Alignment**: Registry-constrained validation
        * **Document Processing**: DOCX/PDF → OSCAL mapping
        * **Printable Generation**: SSP/SAP/SAR/POA&M outputs
        * **S3 Publishing**: Versioned artifact management
        * **Cloud.gov Ready**: Concourse CI/CD integration
        """,
        version=settings.version,
        openapi_url=f"{settings.api_v1_str}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    
    # Add middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_hosts or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    if settings.allowed_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.allowed_hosts,
        )
    
    # Add exception handlers
    @app.exception_handler(ComplianceFactoryException)
    async def compliance_exception_handler(
        request: Request, exc: ComplianceFactoryException
    ) -> JSONResponse:
        """Handle custom compliance factory exceptions."""
        logger = structlog.get_logger()
        logger.error(
            "Compliance factory error",
            error=str(exc),
            status_code=exc.status_code,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            },
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle unexpected exceptions."""
        logger = structlog.get_logger()
        logger.error(
            "Unexpected error",
            error=str(exc),
            error_type=type(exc).__name__,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "details": str(exc) if settings.debug else None,
            },
        )
    
    # Include routers
    app.include_router(api_router, prefix=settings.api_v1_str)
    
    return app


# Create the application instance
app = create_application()


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with basic service information."""
    settings = get_settings()
    return {
        "service": "OSCAL Compliance Factory",
        "version": settings.version,
        "description": "Containerized OSCAL compliance tooling with FedRAMP 20x support",
        "docs_url": "/docs",
        "openapi_url": f"{settings.api_v1_str}/openapi.json",
    }


@app.get("/healthz")
async def health_check() -> dict[str, str]:
    """Health check endpoint for container orchestration."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_config=None,  # Use our custom logging setup
    )