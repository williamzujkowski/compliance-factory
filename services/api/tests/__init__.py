"""
Test package for the OSCAL Compliance Factory API.

This package contains comprehensive tests for all API functionality including:
- Unit tests for individual services and utilities
- Integration tests for API endpoints and workflows
- Performance and security tests
- Test fixtures and utilities

Test Organization:
- unit/: Unit tests for individual components
- integration/: Integration tests for API endpoints
- fixtures/: Shared test data and fixtures
- conftest.py: Pytest configuration and fixtures
- test_runner.py: Test execution utilities

Usage:
    # Run all tests
    python -m pytest tests/

    # Run specific test categories
    python tests/test_runner.py unit
    python tests/test_runner.py integration
    python tests/test_runner.py all

    # Generate test report
    python tests/test_runner.py report
"""

__version__ = "0.1.0"

# Test markers for categorizing tests
MARKERS = {
    "unit": "Unit tests for individual components",
    "integration": "Integration tests for API endpoints", 
    "security": "Security-focused tests",
    "slow": "Tests that take longer to run",
    "oscal": "Tests related to OSCAL functionality",
}

# Test configuration constants
TEST_CONFIG = {
    "timeout": 30,  # Default test timeout in seconds
    "database_url": "sqlite+aiosqlite:///:memory:",
    "test_files_dir": "fixtures",
    "coverage_threshold": 75,  # Minimum coverage percentage
}

# Common test utilities
def pytest_configure(config):
    """Configure pytest with custom markers."""
    for marker, description in MARKERS.items():
        config.addinivalue_line("markers", f"{marker}: {description}")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on path."""
    import pytest
    
    for item in items:
        # Add unit marker for tests in unit/ directory
        if "unit/" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        
        # Add integration marker for tests in integration/ directory
        elif "integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        
        # Add OSCAL marker for OSCAL-related tests
        if any(keyword in str(item.fspath).lower() for keyword in ["oscal", "validation", "fedramp"]):
            item.add_marker(pytest.mark.oscal)
        
        # Add security marker for security tests
        if any(keyword in str(item.fspath).lower() for keyword in ["security", "auth"]):
            item.add_marker(pytest.mark.security)