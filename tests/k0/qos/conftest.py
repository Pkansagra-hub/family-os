"""Fixtures and utilities for QoS module testing."""

from __future__ import annotations

import pytest

from k0.qos import QoSContext, Scheduler, SchedulerProfile


@pytest.fixture
def basic_scheduler() -> Scheduler:
    """Scheduler with default profile."""
    return Scheduler()


@pytest.fixture
def configured_scheduler() -> Scheduler:
    """Scheduler with explicit limits for testing."""
    profile = SchedulerProfile(
        name="test",
        description="Test profile",
        port_limits={"command": 4, "query": 8, "sse": 2},
        default_port_limit=4,
    )
    return Scheduler(profile=profile)


@pytest.fixture
def strict_scheduler() -> Scheduler:
    """Scheduler with very tight limits for capacity testing."""
    profile = SchedulerProfile(
        name="strict",
        description="Strict test profile",
        port_limits={"command": 1, "query": 2, "sse": 1},
        default_port_limit=1,
    )
    return Scheduler(profile=profile)


@pytest.fixture
def qos_context(basic_scheduler: Scheduler) -> QoSContext:
    """QoS context with default budgets."""
    return QoSContext(scheduler=basic_scheduler, fanout_budget=5, top_k_budget=8)


@pytest.fixture
def qos_context_strict(strict_scheduler: Scheduler) -> QoSContext:
    """QoS context with minimal budgets."""
    return QoSContext(scheduler=strict_scheduler, fanout_budget=1, top_k_budget=1)


@pytest.fixture
def hardened_profile() -> SchedulerProfile:
    """Profile for AMBER band tightening."""
    return SchedulerProfile(
        name="hardened",
        description="Tightened for AMBER band",
        port_limits={"command": 2, "query": 3, "sse": 1},
        default_port_limit=2,
    )


@pytest.fixture
def relaxed_profile() -> SchedulerProfile:
    """Profile for GREEN band."""
    return SchedulerProfile(
        name="relaxed",
        description="Relaxed for GREEN band",
        port_limits={"command": 16, "query": 32, "sse": 8},
        default_port_limit=16,
    )
