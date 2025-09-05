"""
Database configuration and session management.

Provides async database session handling with SQLAlchemy for PostgreSQL
and dependency injection for FastAPI endpoints.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

logger = structlog.get_logger()

# Global engine and session factory
_engine = None
_async_session_factory = None


def get_database_url() -> str:
    """Get the database URL from settings or environment."""
    settings = get_settings()
    
    # Use database_url if explicitly set
    if settings.database_url:
        return settings.database_url
    
    # Build from components
    return (
        f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )


def create_engine():
    """Create the database engine."""
    global _engine
    
    if _engine is not None:
        return _engine
    
    database_url = get_database_url()
    settings = get_settings()
    
    _engine = create_async_engine(
        database_url,
        echo=settings.debug,  # Log SQL in debug mode
        poolclass=NullPool if settings.debug else None,  # Disable pooling in debug
        pool_pre_ping=True,
        pool_recycle=3600,  # Recycle connections after 1 hour
        connect_args={
            "command_timeout": 30,
            "server_settings": {
                "application_name": "oscal-compliance-factory",
            },
        },
    )
    
    return _engine


def create_session_factory():
    """Create the async session factory."""
    global _async_session_factory
    
    if _async_session_factory is not None:
        return _async_session_factory
    
    engine = create_engine()
    _async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
        autocommit=False,
    )
    
    return _async_session_factory


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Create an async database session.
    
    This is a context manager that ensures the session is properly closed.
    """
    session_factory = create_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for getting a database session.
    
    This is used with Depends() in FastAPI endpoints.
    """
    async with get_async_session() as session:
        yield session


async def init_database():
    """
    Initialize the database.
    
    This creates tables and performs any necessary setup.
    Should be called during application startup.
    """
    from app.models import Base
    
    engine = create_engine()
    
    # Create all tables
    async with engine.begin() as conn:
        logger.info("Creating database tables")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")


async def close_database():
    """
    Close database connections.
    
    Should be called during application shutdown.
    """
    global _engine, _async_session_factory
    
    if _engine is not None:
        logger.info("Closing database engine")
        await _engine.dispose()
        _engine = None
    
    _async_session_factory = None
    logger.info("Database connections closed")


async def check_database_health() -> dict:
    """
    Check database connectivity and return health status.
    
    Returns:
        Dict with health information
    """
    try:
        async with get_async_session() as session:
            # Simple query to check connectivity
            result = await session.execute("SELECT 1 as health_check")
            row = result.first()
            
            if row and row.health_check == 1:
                return {
                    "status": "healthy",
                    "database": "postgresql",
                    "connection": "ok",
                }
            else:
                return {
                    "status": "unhealthy",
                    "database": "postgresql",
                    "connection": "failed",
                    "error": "Invalid query result",
                }
                
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "database": "postgresql",
            "connection": "failed",
            "error": str(e),
        }