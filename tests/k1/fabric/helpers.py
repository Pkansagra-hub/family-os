"""
Test helpers for k1.fabric test suite (Epic 6.1.3).

Provides utility functions used across all test modules.
ALL helpers use real adapters and real contracts. NO MOCKS.

Functions:
  load_fixture_contract   -- Load a YAML fixture by name via parse_contract()
  create_n_contracts      -- Generate N valid CapabilityContract instances
  assert_capability_result_success -- Assert a CapabilityResult is successful
  assert_capability_result_failure -- Assert a CapabilityResult failed with error code
  wait_for_event          -- Wait for a specific event on LocalEventAdapter

References:
  - fabric-implementation-plan.md Milestone 6, Epic 6.1.3
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.contracts import ContractUnion, parse_contract
from k1.fabric.types import (
    Availability,
    CapabilityContract,
    CapabilityResult,
    InputSpec,
    ProviderConfig,
    SafetyBand,
)

# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Available fixture names (without .yaml extension)
FIXTURE_NAMES = [
    "restaurant_booking",
    "weather_api",
    "invitation_sender",
    "health_summarizer",
    "invitation_drafter_v1",
    "weekly_health_check",
]


# ---------------------------------------------------------------------------
# load_fixture_contract
# ---------------------------------------------------------------------------


def load_fixture_contract(name: str) -> ContractUnion:
    """
    Load a sample YAML contract from the fixtures directory.

    Uses the real parse_contract() facade (auto-detection + validation).
    This proves the fixture YAML is schema-valid on every test run.

    Args:
        name: Fixture name without extension (e.g. 'restaurant_booking').

    Returns:
        Parsed contract dataclass (CapabilityContract, AgentContract,
        PromptContract, or WorkflowContract).

    Raises:
        FileNotFoundError: Fixture file does not exist.
        ContractParseError: YAML is invalid or unrecognized type.
        ContractValidationError: Fixture fails schema validation.
    """
    path = FIXTURES_DIR / f"{name}.yaml"
    if not path.exists():
        available = [p.stem for p in FIXTURES_DIR.glob("*.yaml")]
        raise FileNotFoundError(
            f"Fixture '{name}' not found at {path}. " f"Available: {sorted(available)}"
        )
    return parse_contract(path)


# ---------------------------------------------------------------------------
# create_n_contracts
# ---------------------------------------------------------------------------


def create_n_contracts(
    n: int,
    *,
    domain: Optional[str] = None,
    provider_type: str = "MCP",
    safety_band: str = SafetyBand.GREEN.value,
    availability: str = Availability.ONLINE.value,
) -> List[CapabilityContract]:
    """
    Generate N valid CapabilityContract instances for bulk testing.

    Each contract has a unique name following the tool.execute.<name>
    convention. Useful for registry stress tests and retrieval ranking.

    Args:
        n: Number of contracts to generate (must be > 0).
        domain: Optional domain tag. If None, uses 'TEST_DOMAIN'.
        provider_type: Provider type for all contracts (default 'MCP').
        safety_band: Safety band for all contracts (default 'GREEN').
        availability: Availability for all contracts (default 'ONLINE').

    Returns:
        List of N distinct CapabilityContract instances.
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")

    effective_domain = domain or "TEST_DOMAIN"
    contracts: List[CapabilityContract] = []

    for i in range(n):
        contract = CapabilityContract(
            name=f"tool.execute.test_cap_{i:04d}",
            version="1.0.0",
            domain=[effective_domain],
            description=f"Auto-generated test capability {i}",
            capabilities=[f"test_action_{i}"],
            limitations=[],
            required_inputs=[
                InputSpec(name="input_a", type="STRING", description="Test input A"),
            ],
            output={"type": "object"},
            provider_type=provider_type,
            provider_id=f"test-provider-{i:04d}",
            safety_band_min=safety_band,
            availability=availability,
        )
        contracts.append(contract)

    return contracts


# ---------------------------------------------------------------------------
# register_contract_with_provider
# ---------------------------------------------------------------------------


def register_contract_with_provider(fabric: Any, contract: Any) -> None:
    """
    Register a contract AND its provider in a Fabric instance.

    When contracts are registered programmatically (after factory construction),
    _auto_register_providers() has already run. This helper bridges the gap by
    also inserting a ProviderConfig into the ProviderRegistry so that the
    Resolver can find the provider during execution.

    Args:
        fabric: The Fabric container instance.
        contract: The CapabilityContract to register.
    """
    # Step 1: Register the contract in CapabilityRegistry (+ emit event)
    fabric.register(contract)

    # Step 2: Also register the provider in ProviderRegistry
    provider_id = getattr(contract, "provider_id", "")
    if not provider_id:
        return

    provider_registry = fabric.facade._resolver._provider_matcher._provider_registry
    if provider_registry.contains(provider_id):
        return

    provider_type = getattr(contract, "provider_type", "MCP")
    config = ProviderConfig(
        provider_id=provider_id,
        provider_type=provider_type,
        endpoint=f"local://{provider_id}",
        max_execution_ms=30000 if provider_type != "WASM" else 5000,
    )
    provider_registry.register_provider(provider_id, config)


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def assert_capability_result_success(
    result: CapabilityResult,
    *,
    expected_provider: Optional[str] = None,
) -> None:
    """
    Assert that a CapabilityResult represents a successful execution.

    Checks:
      - result.success is True
      - result.data is not None
      - result.error is None
      - Optional: provider_id matches expected

    Args:
        result: The CapabilityResult to check.
        expected_provider: If provided, assert provider_id matches.

    Raises:
        AssertionError: If any check fails.
    """
    assert result.success is True, (
        f"Expected success=True, got success=False. "
        f"Error: {result.error.to_dict() if result.error else 'None'}"
    )
    assert result.data is not None, "Expected data to be set on successful result"
    assert result.error is None, (
        f"Expected no error on successful result, got: "
        f"{result.error.to_dict() if result.error else 'None'}"
    )
    if expected_provider is not None:
        assert result.provider_id == expected_provider, (
            f"Expected provider_id='{expected_provider}', " f"got '{result.provider_id}'"
        )


def assert_capability_result_failure(
    result: CapabilityResult,
    error_code: str,
    *,
    retriable: Optional[bool] = None,
) -> None:
    """
    Assert that a CapabilityResult represents a failed execution.

    Checks:
      - result.success is False
      - result.error is not None
      - result.error.code matches error_code
      - Optional: error.retriable matches expected

    Args:
        result: The CapabilityResult to check.
        error_code: Expected error code string.
        retriable: If provided, assert error.retriable matches.

    Raises:
        AssertionError: If any check fails.
    """
    assert result.success is False, (
        f"Expected success=False, got success=True with data: " f"{result.data}"
    )
    assert result.error is not None, "Expected error to be set on failed result"
    assert result.error.code == error_code, (
        f"Expected error.code='{error_code}', got '{result.error.code}' "
        f"(message: {result.error.message})"
    )
    if retriable is not None:
        assert result.error.retriable is retriable, (
            f"Expected error.retriable={retriable}, " f"got {result.error.retriable}"
        )


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------


def wait_for_event(
    adapter: LocalEventAdapter,
    event_type: str,
    timeout_ms: int = 1000,
    *,
    min_count: int = 1,
) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Wait for a specific event to appear in the LocalEventAdapter captured events.

    Polls the adapter's captured events until at least min_count events
    of the given type are found, or timeout is reached.

    Args:
        adapter: LocalEventAdapter with capture_mode enabled.
        event_type: Event topic to wait for (e.g. 'k1.capability.invoked.v1').
        timeout_ms: Maximum wait time in milliseconds (default 1000).
        min_count: Minimum number of matching events required (default 1).

    Returns:
        List of matching (topic, payload) tuples.

    Raises:
        TimeoutError: If min_count events not found within timeout.
    """
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    poll_interval = 0.005  # 5ms

    while time.monotonic() < deadline:
        captured = adapter.get_captured(topic=event_type)
        if len(captured) >= min_count:
            return captured
        time.sleep(poll_interval)

    # Final check after deadline
    captured = adapter.get_captured(topic=event_type)
    if len(captured) >= min_count:
        return captured

    # Build diagnostic message
    all_captured = adapter.get_captured()
    all_topics = sorted({t for t, _ in all_captured})
    raise TimeoutError(
        f"Timed out waiting for {min_count} event(s) on '{event_type}' "
        f"after {timeout_ms}ms. Found {len(captured)} matching event(s). "
        f"All captured topics: {all_topics} ({len(all_captured)} total events)"
    )
