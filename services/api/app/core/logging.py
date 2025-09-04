"""Structured logging configuration using structlog."""

import sys
from typing import Any

import structlog
from structlog import testing

from app.core.config import get_settings


def setup_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()
    
    # Configure structlog
    if settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    
    structlog.configure(
        processors=[
            # Add log level to event dict
            structlog.stdlib.add_log_level,
            # Add logger name to event dict  
            structlog.stdlib.add_logger_name,
            # Add timestamp
            structlog.processors.TimeStamper(fmt="iso"),
            # Perform %-style string formatting
            structlog.stdlib.PositionalArgumentsFormatter(),
            # Add stack info if available
            structlog.processors.StackInfoRenderer(),
            # Add exception info if available
            structlog.processors.format_exc_info,
            # Render the final event dict
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


def configure_test_logging() -> None:
    """Configure logging for testing with predictable output."""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            testing.LogCapture.processor,
        ],
        wrapper_class=testing.LogCapture,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )