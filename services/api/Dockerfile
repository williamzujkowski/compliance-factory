# Use Python 3.12 slim image for optimal security and size
FROM python:3.12-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies including oscal-cli
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    build-essential \
    libpq-dev \
    openjdk-17-jdk \
    && rm -rf /var/lib/apt/lists/*

# Install oscal-cli (Java-based tool)
WORKDIR /opt
RUN wget -O oscal-cli.zip https://github.com/usnistgov/OSCAL/releases/latest/download/oscal-cli.zip && \
    unzip oscal-cli.zip && \
    rm oscal-cli.zip && \
    chmod +x oscal-cli

# Add oscal-cli to PATH
ENV PATH="/opt/oscal-cli:$PATH"

# Install uv for fast Python package management
RUN pip install uv==0.8.15

# Create app user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies
RUN uv venv && \
    . .venv/bin/activate && \
    uv pip install -e .

# Copy application code
COPY app/ ./app/
COPY migrations/ ./migrations/

# Create necessary directories
RUN mkdir -p /app/workspace /app/.oscal && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Expose port
EXPOSE 8000

# Default command
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Development stage with additional tools
FROM base as development

USER root

# Install development dependencies
RUN . .venv/bin/activate && \
    uv pip install -e ".[dev]"

# Install additional dev tools
RUN apt-get update && apt-get install -y \
    vim \
    less \
    tree \
    && rm -rf /var/lib/apt/lists/*

USER appuser

# Override command for development (with auto-reload)
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production stage optimized for size and security
FROM base as production

# Run final security cleanup
USER root
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

USER appuser

# Production command
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]