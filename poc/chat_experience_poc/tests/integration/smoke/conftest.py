"""
Pytest configuration for smoke tests

Provides shared fixtures and configuration for integration smoke tests.
"""

import asyncio
import logging

import pytest

# Configure logging for all smoke tests
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


@pytest.fixture(scope="session")
def event_loop():
    """
    Create event loop for async tests

    Session-scoped to reuse loop across tests for better performance.
    """
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def system_coordinator():
    """
    Provide SystemCoordinator instance

    Module-scoped to reuse across tests in same module.
    Note: Tests must handle initialization/cleanup themselves.
    """
    from system_coordinator import get_system_coordinator

    return get_system_coordinator()
