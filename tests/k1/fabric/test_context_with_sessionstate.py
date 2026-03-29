"""
Epic 6.3.7 -- Test context builder with real SessionState (FAB-08 128K ceiling).

Covers:
  - ContextBuilder 6-step pipeline exercised through fabric.execute().
  - SessionState populated via TestSessionStateReaderAdapter (pre-loaded).
  - Required/optional context sections fetched and packaged into ExecutionContext.
  - Token budget applied with 128K ceiling (FAB-08).
  - Graceful degradation: missing sections, empty state, partial context.
  - Budget compression levels triggered by oversized context.
  - Prompt resolution integrated with SessionState sections.
  - Multiple capabilities with different context requirements share state.

NO MOCKS -- all tests use FabricFactory.create_for_testing() with real adapters.

References:
  - fabric-implementation-plan.md Epic 6.3.7
  - fabric_discussion.md Section 12 (Context Assembly)
  - FAB-008 (Single Writer -- read-only context)
  - FAB-08 (128K token ceiling)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.fabric.core.context_budget import (
    TOKEN_CEILING,
    CompressionLevel,
    ContextBudget,
    ContextBudgetConfig,
)
from k1.fabric.core.context_builder import ContextBuilder, ContextBuilderConfig
from k1.fabric.events import TOPIC_CAPABILITY_COMPLETED  # noqa: F401
from k1.fabric.factory import FabricFactory
from k1.fabric.types import CapabilityContract, CapabilityRequest, InputSpec, Tier
from tests.k1.fabric.helpers import (
    assert_capability_result_success,
    register_contract_with_provider,
    wait_for_event,
)

# ---------------------------------------------------------------------------
# Fixtures directory (for YAML contracts)
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Shared session sections (realistic K1 SessionState data)
# ---------------------------------------------------------------------------

SESSION_ID = "sess-ctx-test-001"

BELIEFS_ACTIVE = {
    "facts": [
        {"text": "The sky is blue", "confidence": 0.95},
        {"text": "User prefers Italian food", "confidence": 0.88},
    ],
}

CONTROL = {
    "safety_band": "GREEN",
    "user_preferences": {
        "language": "en",
        "units": "metric",
    },
}

PERSONA = {
    "name": "FamilyAI",
    "style": "warm and supportive",
    "bio": "A family assistant helping with daily life.",
}

AFFECTIVE_NOW = {
    "emotion": "calm",
    "intensity": 0.3,
    "valence": 0.6,
}

COGNITIVE = {
    "load": "low",
    "complexity_tier": "LOW",
    "attention_budget": 0.8,
}

HISTORY_RECENT = {
    "turns": [
        {"user": "What's the weather?", "assistant": "It's sunny today."},
        {"user": "Book a restaurant", "assistant": "Looking for options..."},
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_state_reader(fabric: Any) -> TestSessionStateReaderAdapter:
    """Access the TestSessionStateReaderAdapter from a Fabric instance."""
    return fabric.facade._provider_factory._port_deps.get("state_reader")


def _get_context_builder(fabric: Any) -> ContextBuilder:
    """Access the ContextBuilder from a Fabric instance."""
    return fabric.facade._context_builder


def _populate_state(state_reader: TestSessionStateReaderAdapter) -> None:
    """Pre-load all standard session sections."""
    state_reader.load_many(
        SESSION_ID,
        {
            "beliefs_active": BELIEFS_ACTIVE,
            "control": CONTROL,
            "persona": PERSONA,
            "affective_now": AFFECTIVE_NOW,
            "cognitive": COGNITIVE,
            "history_recent": HISTORY_RECENT,
        },
    )


def _make_context_contract(
    name: str = "tool.execute.ctx_test",
    *,
    required_context: list[str] | None = None,
    optional_context: list[str] | None = None,
    provider_type: str = "MCP",
    provider_id: str = "mcp-ctx-test",
) -> CapabilityContract:
    """Create a contract with specific context requirements."""
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=["TEST"],
        description="Context test capability",
        capabilities=[name],
        provider_type=provider_type,
        provider_id=provider_id,
        required_context=required_context or [],
        optional_context=optional_context or [],
        required_inputs=[InputSpec(name="query", type="STRING", description="Test query input")],
        output={"type": "object"},
    )


def _ctx_request(
    capability_name: str,
    params: dict | None = None,
    session_id: str = SESSION_ID,
) -> CapabilityRequest:
    """Build a request with session_id for context tests."""
    return CapabilityRequest(
        capability_name=capability_name,
        params=params or {"query": "test"},
        tier=Tier.LOW.value,
        caller="test-context",
        session_id=session_id,
    )


# =========================================================================
# 6.3.7a -- ContextBuilder reads SessionState sections
# =========================================================================


class TestContextBuilderReadsSessionState:
    """
    Verify ContextBuilder reads pre-loaded SessionState via state_reader.
    Tests the 6-step pipeline at the ContextBuilder level (unit-integration).
    """

    def test_required_sections_fetched(self) -> None:
        """Required context sections are read from SessionState."""
        reader = TestSessionStateReaderAdapter()
        _populate_state(reader)

        builder = ContextBuilder(state_reader=reader)
        contract = _make_context_contract(
            required_context=["beliefs_active", "control"],
        )
        result = builder.build(
            contract=contract,
            params={"query": "hello"},
            session_id=SESSION_ID,
            trace_id="tr-req-001",
        )

        ctx = result.context
        assert "beliefs_active" in ctx.session_sections
        assert "control" in ctx.session_sections
        assert ctx.session_sections["beliefs_active"] == BELIEFS_ACTIVE
        assert ctx.session_sections["control"] == CONTROL
        assert len(result.missing_required) == 0

    def test_optional_sections_fetched_when_present(self) -> None:
        """Optional sections are included when available."""
        reader = TestSessionStateReaderAdapter()
        _populate_state(reader)

        builder = ContextBuilder(state_reader=reader)
        contract = _make_context_contract(
            required_context=["control"],
            optional_context=["persona", "affective_now"],
        )
        result = builder.build(
            contract=contract,
            session_id=SESSION_ID,
        )

        ctx = result.context
        assert "persona" in ctx.session_sections
        assert "affective_now" in ctx.session_sections
        assert len(result.missing_optional) == 0

    def test_missing_optional_section_skipped(self) -> None:
        """Missing optional sections are skipped without error."""
        reader = TestSessionStateReaderAdapter()
        reader.load(SESSION_ID, "control", CONTROL)

        builder = ContextBuilder(state_reader=reader)
        contract = _make_context_contract(
            required_context=["control"],
            optional_context=["persona", "telemetry"],
        )
        result = builder.build(
            contract=contract,
            session_id=SESSION_ID,
        )

        assert "control" in result.context.session_sections
        assert "persona" in result.missing_optional
        assert "telemetry" in result.missing_optional
        assert len(result.missing_required) == 0

    def test_missing_required_section_reported(self) -> None:
        """Missing required sections are reported but build continues."""
        reader = TestSessionStateReaderAdapter()
        reader.load(SESSION_ID, "control", CONTROL)

        builder = ContextBuilder(state_reader=reader)
        contract = _make_context_contract(
            required_context=["control", "beliefs_active", "nonexistent"],
        )
        result = builder.build(
            contract=contract,
            session_id=SESSION_ID,
        )

        assert "control" in result.context.session_sections
        assert "beliefs_active" in result.missing_required
        assert "nonexistent" in result.missing_required

    def test_no_state_reader_graceful_degradation(self) -> None:
        """No state reader -> all sections missing, build succeeds."""
        builder = ContextBuilder(state_reader=None)
        contract = _make_context_contract(
            required_context=["beliefs_active"],
            optional_context=["persona"],
        )
        result = builder.build(contract=contract, session_id=SESSION_ID)

        assert result.context.session_sections == {}
        assert "beliefs_active" in result.missing_required
        assert "persona" in result.missing_optional

    def test_empty_state_returns_all_missing(self) -> None:
        """State reader with no sections -> all declared sections missing."""
        reader = TestSessionStateReaderAdapter()

        builder = ContextBuilder(state_reader=reader)
        contract = _make_context_contract(
            required_context=["beliefs_active", "control"],
            optional_context=["persona"],
        )
        result = builder.build(
            contract=contract,
            session_id=SESSION_ID,
        )

        assert "beliefs_active" in result.missing_required
        assert "control" in result.missing_required
        assert "persona" in result.missing_optional

    def test_params_injected_alongside_session(self) -> None:
        """Request params injected into context alongside session sections."""
        reader = TestSessionStateReaderAdapter()
        _populate_state(reader)

        builder = ContextBuilder(state_reader=reader)
        contract = _make_context_contract(
            required_context=["control"],
        )
        result = builder.build(
            contract=contract,
            params={"location": "Seattle", "units": "metric"},
            session_id=SESSION_ID,
        )

        ctx = result.context
        assert ctx.params["location"] == "Seattle"
        assert ctx.params["units"] == "metric"
        assert "control" in ctx.session_sections

    def test_trace_id_propagated(self) -> None:
        """Trace ID flows from build() args into ExecutionContext."""
        reader = TestSessionStateReaderAdapter()
        builder = ContextBuilder(state_reader=reader)
        contract = _make_context_contract()

        result = builder.build(
            contract=contract,
            trace_id="tr-propagate-001",
            session_id=SESSION_ID,
        )
        assert result.context.trace_id == "tr-propagate-001"

    def test_session_snapshot_via_get_snapshot(self) -> None:
        """TestSessionStateReaderAdapter.get_snapshot() returns all sections."""
        reader = TestSessionStateReaderAdapter()
        _populate_state(reader)

        snapshot = reader.get_snapshot(SESSION_ID)
        assert snapshot.has_section("beliefs_active")
        assert snapshot.has_section("control")
        assert snapshot.has_section("persona")
        assert snapshot.has_section("affective_now")
        assert snapshot.has_section("cognitive")
        assert snapshot.has_section("history_recent")
        assert snapshot.session_id == SESSION_ID


# =========================================================================
# 6.3.7b -- Token budget enforcement (FAB-08: 128K ceiling)
# =========================================================================


class TestTokenBudget:
    """
    Verify token budget with 128K ceiling is enforced via ContextBuilder.
    """

    def test_small_context_under_budget(self) -> None:
        """Small context stays under 128K budget without compression."""
        reader = TestSessionStateReaderAdapter()
        reader.load(SESSION_ID, "control", CONTROL)

        builder = ContextBuilder(state_reader=reader)
        contract = _make_context_contract(required_context=["control"])
        result = builder.build(
            contract=contract,
            session_id=SESSION_ID,
        )

        assert result.budget.total_tokens > 0
        assert result.budget.total_tokens <= TOKEN_CEILING
        assert result.budget.compression_applied == CompressionLevel.NONE
        assert not result.budget.over_budget

    def test_128k_ceiling_constant(self) -> None:
        """FAB-08: TOKEN_CEILING is exactly 128,000."""
        assert TOKEN_CEILING == 128_000

    def test_budget_compression_drops_optional_sections(self) -> None:
        """L1 compression drops optional sections when budget exceeded."""
        config = ContextBuilderConfig(
            budget_config=ContextBudgetConfig(ceiling=30, response_headroom=5),
        )
        reader = TestSessionStateReaderAdapter()
        reader.load(SESSION_ID, "control", {"status": "active"})
        reader.load(SESSION_ID, "persona", {"bio": "x" * 400})

        builder = ContextBuilder(state_reader=reader, config=config)
        contract = _make_context_contract(
            required_context=["control"],
            optional_context=["persona"],
        )
        result = builder.build(
            contract=contract,
            session_id=SESSION_ID,
        )

        # persona should be dropped at L1
        assert "persona" not in result.context.session_sections
        assert "persona" in result.budget.sections_dropped

    def test_budget_compression_truncates_history(self) -> None:
        """L2 compression truncates history_recent turns."""
        config = ContextBuilderConfig(
            budget_config=ContextBudgetConfig(ceiling=50, response_headroom=5),
        )
        reader = TestSessionStateReaderAdapter()
        # 20 large turns
        big_history = {
            "turns": [
                {"user": f"msg-{i} " + "x" * 40, "assistant": f"reply-{i} " + "y" * 40}
                for i in range(20)
            ]
        }
        reader.load(SESSION_ID, "history_recent", big_history)

        builder = ContextBuilder(state_reader=reader, config=config)
        contract = _make_context_contract(
            required_context=["history_recent"],
        )
        result = builder.build(
            contract=contract,
            session_id=SESSION_ID,
        )

        hr = result.context.session_sections.get("history_recent", {})
        remaining = hr.get("turns", [])
        assert result.budget.compression_applied.value >= CompressionLevel.L2_TRUNCATE_HISTORY.value
        assert len(remaining) <= config.budget_config.max_history_turns

    def test_execution_context_frozen(self) -> None:
        """ExecutionContext is frozen (immutable) after build."""
        reader = TestSessionStateReaderAdapter()
        _populate_state(reader)

        builder = ContextBuilder(state_reader=reader)
        contract = _make_context_contract(required_context=["control"])
        result = builder.build(
            contract=contract,
            session_id=SESSION_ID,
        )

        with pytest.raises(AttributeError):
            result.context.trace_id = "mutated"  # type: ignore[misc]

    def test_assembly_time_tracked(self) -> None:
        """assembly_ms is recorded (non-negative)."""
        reader = TestSessionStateReaderAdapter()
        _populate_state(reader)

        builder = ContextBuilder(state_reader=reader)
        contract = _make_context_contract(required_context=["control"])
        result = builder.build(
            contract=contract,
            session_id=SESSION_ID,
        )
        assert result.assembly_ms >= 0.0

    def test_effective_budget_with_headroom(self) -> None:
        """Effective budget = ceiling - response_headroom."""
        config = ContextBudgetConfig(ceiling=128_000, response_headroom=4_000)
        budget = ContextBudget(config)
        assert budget.effective_budget == 124_000


# =========================================================================
# 6.3.7c -- Context through fabric.execute() (end-to-end)
# =========================================================================


class TestContextViaFabricExecute:
    """
    Verify context building works end-to-end through fabric.execute().
    SessionState is pre-loaded, request carries session_id, context is
    built internally and passed to the provider.
    """

    async def test_execute_with_session_state(self) -> None:
        """fabric.execute() builds context from pre-loaded SessionState."""
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )

        # Access the state reader and pre-load sections
        state_reader = _get_state_reader(fabric)
        _populate_state(state_reader)

        # Default TestMCPTransport returns success for any tool
        request = _ctx_request(
            "tool.execute.restaurant_booking",
            params={"restaurant_name": "Chez Alice", "date": "2026-01-15"},
        )
        result = await fabric.execute(request)

        assert_capability_result_success(result, expected_provider="mcp-opentable")

    async def test_execute_emits_completed_event(self) -> None:
        """Capability completed event emitted after context-built execution."""
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )

        state_reader = _get_state_reader(fabric)
        _populate_state(state_reader)

        request = _ctx_request("tool.execute.restaurant_booking")
        result = await fabric.execute(request)

        assert result.success is True
        events = wait_for_event(fabric.event_port, TOPIC_CAPABILITY_COMPLETED)
        assert len(events) >= 1

    async def test_execute_without_session_state_still_succeeds(self) -> None:
        """Execution succeeds even without pre-loaded SessionState (graceful)."""
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )

        # Do NOT populate state -- empty state reader
        request = _ctx_request("tool.execute.restaurant_booking")
        result = await fabric.execute(request)

        # Should succeed -- context builder degrades gracefully
        assert_capability_result_success(result)

    async def test_context_builder_has_state_reader(self) -> None:
        """Fabric's ContextBuilder has state_reader connected."""
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )

        builder = _get_context_builder(fabric)
        assert builder.has_state_reader is True

    async def test_different_sessions_isolated(self) -> None:
        """Different session_ids read different SessionState sections."""
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )

        state_reader = _get_state_reader(fabric)
        state_reader.load("sess-A", "control", {"mode": "session-A"})
        state_reader.load("sess-B", "control", {"mode": "session-B"})

        builder = _get_context_builder(fabric)
        contract = _make_context_contract(required_context=["control"])

        result_a = builder.build(contract=contract, session_id="sess-A")
        result_b = builder.build(contract=contract, session_id="sess-B")

        assert result_a.context.session_sections["control"]["mode"] == "session-A"
        assert result_b.context.session_sections["control"]["mode"] == "session-B"


# =========================================================================
# 6.3.7d -- Context with programmatic contracts
# =========================================================================


class TestContextProgrammaticContracts:
    """
    Register contracts programmatically with required_context,
    then execute via fabric to verify context flow.
    """

    async def test_execute_with_required_context_contract(self) -> None:
        """Programmatic contract with required_context works via fabric.execute()."""
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )

        contract = _make_context_contract(
            name="tool.execute.ctx_prog_test",
            required_context=["beliefs_active", "control"],
            provider_type="MCP",
            provider_id="mcp-ctx-prog",
        )
        register_contract_with_provider(fabric, contract)

        state_reader = _get_state_reader(fabric)
        _populate_state(state_reader)

        # Default TestMCPTransport returns success for any tool
        request = _ctx_request("tool.execute.ctx_prog_test")
        result = await fabric.execute(request)

        assert_capability_result_success(result, expected_provider="mcp-ctx-prog")

    async def test_execute_with_optional_context_contract(self) -> None:
        """Programmatic contract with optional_context succeeds when sections present."""
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )

        contract = _make_context_contract(
            name="tool.execute.ctx_opt_test",
            required_context=["control"],
            optional_context=["persona", "affective_now"],
            provider_type="MCP",
            provider_id="mcp-ctx-opt",
        )
        register_contract_with_provider(fabric, contract)

        state_reader = _get_state_reader(fabric)
        _populate_state(state_reader)

        # Default TestMCPTransport returns success for any tool
        request = _ctx_request("tool.execute.ctx_opt_test")
        result = await fabric.execute(request)

        assert_capability_result_success(result, expected_provider="mcp-ctx-opt")

    async def test_execute_with_missing_optional_context(self) -> None:
        """Execution succeeds even when optional context sections are missing."""
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )

        contract = _make_context_contract(
            name="tool.execute.ctx_partial",
            required_context=["control"],
            optional_context=["nonexistent_section"],
            provider_type="MCP",
            provider_id="mcp-ctx-partial",
        )
        register_contract_with_provider(fabric, contract)

        state_reader = _get_state_reader(fabric)
        state_reader.load(SESSION_ID, "control", CONTROL)

        # Default TestMCPTransport returns success for any tool
        request = _ctx_request("tool.execute.ctx_partial")
        result = await fabric.execute(request)

        assert_capability_result_success(result, expected_provider="mcp-ctx-partial")


# =========================================================================
# 6.3.7e -- State reader operations
# =========================================================================


class TestStateReaderOperations:
    """
    Verify TestSessionStateReaderAdapter operations used by ContextBuilder.
    """

    def test_load_and_read_single_section(self) -> None:
        """load() + read_section() round-trip."""
        reader = TestSessionStateReaderAdapter()
        reader.load("s1", "control", {"mode": "auto"})

        data = reader.read_section("s1", "control")
        assert data == {"mode": "auto"}

    def test_load_many_sections(self) -> None:
        """load_many() populates multiple sections at once."""
        reader = TestSessionStateReaderAdapter()
        reader.load_many(
            "s1",
            {
                "control": CONTROL,
                "beliefs_active": BELIEFS_ACTIVE,
            },
        )

        assert reader.read_section("s1", "control") == CONTROL
        assert reader.read_section("s1", "beliefs_active") == BELIEFS_ACTIVE

    def test_read_missing_section_returns_none(self) -> None:
        """read_section() returns None for non-loaded sections."""
        reader = TestSessionStateReaderAdapter()
        assert reader.read_section("s1", "nonexistent") is None

    def test_read_sections_multiple(self) -> None:
        """read_sections() returns multiple sections in one call."""
        reader = TestSessionStateReaderAdapter()
        _populate_state(reader)

        sections = reader.read_sections(SESSION_ID, ["control", "persona"])
        assert "control" in sections
        assert "persona" in sections

    def test_section_count(self) -> None:
        """section_count() reflects loaded sections."""
        reader = TestSessionStateReaderAdapter()
        _populate_state(reader)

        assert reader.section_count(SESSION_ID) == 6
        assert reader.section_count("other-session") == 0

    def test_clear_removes_all(self) -> None:
        """clear() empties all sections."""
        reader = TestSessionStateReaderAdapter()
        _populate_state(reader)

        reader.clear()
        assert reader.section_count() == 0

    def test_remove_section(self) -> None:
        """remove() deletes a specific section."""
        reader = TestSessionStateReaderAdapter()
        reader.load("s1", "control", CONTROL)

        assert reader.remove("s1", "control") is True
        assert reader.read_section("s1", "control") is None
        assert reader.remove("s1", "control") is False
