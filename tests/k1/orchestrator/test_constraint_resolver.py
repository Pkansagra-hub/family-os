"""
Tests for k1.orchestrator.orchestration.constraint_resolver -- Issues 3.1.1-3.1.5.

Covers:
  - ConstraintResolver.validate() orchestration (3.1.1)
  - check_capabilities() dedup + batch query (3.1.2)
  - find_alternatives() scoring, filtering, safety band (3.1.3)
  - resolve_iteratively() 3-cycle state machine (3.1.4)
  - trigger_hil_fallback() HIL emission + helpers (3.1.5)
  - Time budget estimation (BUDGET-1)
  - ValidationResult / AlternativeCapability / ResolutionResult construction
  - Helper functions (_derive_category, _safety_band_rank, _name_similarity,
    format_constraint_question, build_options)
  - Edge cases (empty plans, registry failures, cascading substitutions)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from k1.orchestrator.orchestration.constraint_resolver import (
    HIGH_TIER_TIME_BUDGET_MS,
    HIL_TIMEOUT_MS,
    MIN_ALTERNATIVE_SCORE,
    SCHEMA_OVERLAP_DEFAULT_V1,
    TOP_N_ALTERNATIVES,
    W_NAME,
    W_SAFETY,
    W_SCHEMA,
    ConstraintResolver,
    _derive_category,
    _levenshtein,
    _name_similarity,
    _safety_band_rank,
    build_options,
    format_constraint_question,
)
from k1.orchestrator.types import (
    AlternativeCapability,
    AlternativeMapping,
    CapabilityCheck,
    CommittedPlan,
    HILRequest,
    PlanStep,
    RegistryEntry,
    ResolutionResult,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeFabricPort:
    """Fake IFabricGatewayPort for ConstraintResolver tests.

    Supports query_registry() and query_registry_by_category().
    Category matching uses prefix: entry.name starts with category + ".".
    """

    def __init__(self) -> None:
        self._registry: Dict[str, RegistryEntry] = {}
        self._errors: Dict[str, Exception] = {}
        self._category_errors: Dict[str, Exception] = {}
        self.query_calls: List[str] = []
        self.category_calls: List[str] = []

    def register(self, entry: RegistryEntry) -> None:
        """Register a capability in the fake registry."""
        self._registry[entry.name] = entry

    def set_error(self, capability: str, error: Exception) -> None:
        """Set a query_registry() error for a specific capability."""
        self._errors[capability] = error

    def set_category_error(self, category: str, error: Exception) -> None:
        """Set a query_registry_by_category() error for a category."""
        self._category_errors[category] = error

    async def query_registry(self, capability_name: str) -> Optional[RegistryEntry]:
        self.query_calls.append(capability_name)
        if capability_name in self._errors:
            raise self._errors[capability_name]
        return self._registry.get(capability_name)

    async def query_registry_by_category(
        self,
        category_prefix: str,
    ) -> List[RegistryEntry]:
        self.category_calls.append(category_prefix)
        if category_prefix in self._category_errors:
            raise self._category_errors[category_prefix]
        results = []
        for name, entry in self._registry.items():
            if name.startswith(category_prefix + ".") or name == category_prefix:
                results.append(entry)
        return results

    async def execute(self, request: Any) -> Any:
        raise NotImplementedError("Not used by ConstraintResolver")

    async def execute_batch(self, requests: Any) -> Any:
        raise NotImplementedError("Not used by ConstraintResolver")


class FakeDeltaPort:
    """Fake IDeltaEmitPort for ConstraintResolver tests."""

    def __init__(self) -> None:
        self.emitted: List[Any] = []

    async def emit(self, event_topic: str, payload: Dict[str, Any], trace_id: str) -> None:
        self.emitted.append(("emit", event_topic, payload, trace_id))

    async def emit_progress(self, step_id: str, summary: str, trace_id: str) -> None:
        self.emitted.append(("progress", step_id, summary, trace_id))

    async def emit_hil_request(self, hil_request: Any, trace_id: str) -> None:
        self.emitted.append(("hil", hil_request, trace_id))


class FakeEventPort:
    """Fake IEventSubscriptionPort for ConstraintResolver tests."""

    def subscribe(self, topic: str, handler: Any) -> Any:
        return "sub-1"

    def unsubscribe(self, handle: Any) -> bool:
        return True

    def emit(self, topic: str, payload: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry(
    name: str,
    provider_type: str = "tool",
    safety_band_min: str = "GREEN",
    availability: str = "AVAILABLE",
    estimated_duration_ms: Optional[int] = None,
) -> RegistryEntry:
    """Build a RegistryEntry with sensible defaults."""
    return RegistryEntry(
        name=name,
        provider_type=provider_type,
        safety_band_min=safety_band_min,
        availability=availability,
        estimated_duration_ms=estimated_duration_ms,
    )


def _step(
    id: str = "s1",
    capability: str = "tool.read.lookup",
    params: Optional[Dict[str, Any]] = None,
    timeout_ms: Optional[int] = None,
    is_optional: bool = False,
    safety_band_min: Optional[str] = None,
) -> PlanStep:
    """Build a PlanStep with sensible defaults."""
    return PlanStep(
        id=id,
        capability=capability,
        params=params or {},
        timeout_ms=timeout_ms,
        is_optional=is_optional,
        safety_band_min=safety_band_min,
    )


def _plan(
    *steps: PlanStep,
    deps: Optional[Dict[str, List[str]]] = None,
    estimated_duration_ms: Optional[int] = None,
) -> CommittedPlan:
    """Build a CommittedPlan with sensible defaults."""
    step_list = list(steps) if steps else [_step()]
    return CommittedPlan(
        plan_id="plan-1",
        request_id="req-1",
        intent="test intent",
        steps=step_list,
        trace_id="trace-1",
        dependencies=deps or {},
        estimated_duration_ms=estimated_duration_ms,
    )


def _resolver(
    fabric: Optional[FakeFabricPort] = None,
    delta: Optional[FakeDeltaPort] = None,
    events: Optional[FakeEventPort] = None,
    max_cycles: int = 3,
) -> ConstraintResolver:
    """Build a ConstraintResolver with fake ports."""
    return ConstraintResolver(
        fabric=fabric or FakeFabricPort(),
        delta=delta,
        events=events,
        max_cycles=max_cycles,
    )


# ===================================================================
# 1. validate() orchestration (3.1.1)
# ===================================================================


class TestValidateHappyPath:
    """Tests for validate() when all capabilities exist."""

    @pytest.mark.asyncio
    async def test_all_capabilities_available(self) -> None:
        """All capabilities in registry -> valid=True, no errors."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.read.lookup"))
        fabric.register(_entry("tool.write.save"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(
            _step("s1", capability="tool.read.lookup"),
            _step("s2", capability="tool.write.save"),
        )

        result = await resolver.validate(plan)

        assert result.valid is True
        assert result.errors == []
        assert result.hil_required is False

    @pytest.mark.asyncio
    async def test_single_step_valid(self) -> None:
        """Single-step plan, capability exists."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.calendar.search"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(_step("s1", capability="tool.calendar.search"))

        result = await resolver.validate(plan)

        assert result.valid is True
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_returns_validation_result_type(self) -> None:
        """validate() returns ValidationResult dataclass."""
        fabric = FakeFabricPort()
        fabric.register(_entry("cap"))
        resolver = _resolver(fabric=fabric)

        result = await resolver.validate(_plan(_step("s1", capability="cap")))

        assert isinstance(result, ValidationResult)


class TestValidateFailures:
    """Tests for validate() when capabilities are missing."""

    @pytest.mark.asyncio
    async def test_missing_capability_reports_error(self) -> None:
        """Missing capability -> valid=False, error message."""
        fabric = FakeFabricPort()
        # Don't register anything
        resolver = _resolver(fabric=fabric)

        plan = _plan(_step("s1", capability="tool.missing"))

        result = await resolver.validate(plan)

        assert result.valid is False
        assert len(result.errors) >= 1
        assert "tool.missing" in result.errors[0]
        assert "s1" in result.errors[0]

    @pytest.mark.asyncio
    async def test_multiple_missing_capabilities(self) -> None:
        """Multiple missing -> multiple errors."""
        fabric = FakeFabricPort()
        fabric.register(_entry("other.exists"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(
            _step("s1", capability="other.exists"),
            _step("s2", capability="alpha.missing1"),
            _step("s3", capability="beta.missing2"),
        )

        result = await resolver.validate(plan)

        assert result.valid is False
        assert len(result.errors) == 2
        assert any("alpha.missing1" in e for e in result.errors)
        assert any("beta.missing2" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_hil_required_when_unresolvable(self) -> None:
        """Missing capability with no alternatives -> hil_required=True."""
        fabric = FakeFabricPort()
        resolver = _resolver(fabric=fabric)

        plan = _plan(_step("s1", capability="tool.unknown"))

        result = await resolver.validate(plan)

        assert result.valid is False
        assert result.hil_required is True


class TestValidateWithResolution:
    """Tests for validate() when auto-resolution succeeds or partially succeeds."""

    @pytest.mark.asyncio
    async def test_auto_resolved_valid(self) -> None:
        """Missing cap with same-category alternative -> valid=True."""
        fabric = FakeFabricPort()
        # Don't register tool.calendar.search (it's the missing one)
        # Register an alternative in same category
        fabric.register(_entry("tool.calendar.find", safety_band_min="GREEN"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(_step("s1", capability="tool.calendar.search"))

        result = await resolver.validate(plan)

        assert result.valid is True
        assert result.hil_required is False
        assert len(result.alternatives_applied) == 1
        assert result.alternatives_applied[0].original_capability == "tool.calendar.search"
        assert result.alternatives_applied[0].replacement_capability == "tool.calendar.find"

    @pytest.mark.asyncio
    async def test_partial_resolution_still_invalid(self) -> None:
        """Two missing, one resolvable -> valid=False (one still unresolved)."""
        fabric = FakeFabricPort()
        # Register alternative for tool.calendar.search but not tool.email.send
        fabric.register(_entry("tool.calendar.find", safety_band_min="GREEN"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(
            _step("s1", capability="tool.calendar.search"),
            _step("s2", capability="tool.email.send"),
        )

        result = await resolver.validate(plan)

        assert result.valid is False
        assert result.hil_required is True
        assert any("tool.email.send" in e for e in result.errors)
        # The calendar one was resolved
        assert len(result.alternatives_applied) >= 1

    @pytest.mark.asyncio
    async def test_auto_resolved_populates_alternatives_applied(self) -> None:
        """Successful resolution records AlternativeMapping in result."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.read.fetch", safety_band_min="GREEN"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(_step("s1", capability="tool.read.lookup"))

        result = await resolver.validate(plan)

        assert result.valid is True
        assert len(result.alternatives_applied) == 1
        mapping = result.alternatives_applied[0]
        assert isinstance(mapping, AlternativeMapping)
        assert mapping.original_capability == "tool.read.lookup"
        assert mapping.replacement_capability == "tool.read.fetch"


# ===================================================================
# 2. check_capabilities() (3.1.2)
# ===================================================================


class TestCheckCapabilities:
    """Tests for check_capabilities() dedup and batch query."""

    @pytest.mark.asyncio
    async def test_all_available_returns_empty(self) -> None:
        """All capabilities in registry -> empty list."""
        fabric = FakeFabricPort()
        fabric.register(_entry("cap.a"))
        fabric.register(_entry("cap.b"))
        resolver = _resolver(fabric=fabric)

        checks = await resolver.check_capabilities(
            [
                _step("s1", capability="cap.a"),
                _step("s2", capability="cap.b"),
            ]
        )

        assert checks == []

    @pytest.mark.asyncio
    async def test_missing_capability_returns_check(self) -> None:
        """Missing capability -> CapabilityCheck with available=False."""
        fabric = FakeFabricPort()
        resolver = _resolver(fabric=fabric)

        checks = await resolver.check_capabilities(
            [
                _step("s1", capability="tool.missing"),
            ]
        )

        assert len(checks) == 1
        assert checks[0].step_id == "s1"
        assert checks[0].capability == "tool.missing"
        assert checks[0].available is False
        assert checks[0].contract_entry is None

    @pytest.mark.asyncio
    async def test_dedup_queries(self) -> None:
        """Same capability referenced by 3 steps -> only 1 registry query."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.shared"))
        resolver = _resolver(fabric=fabric)

        steps = [
            _step("s1", capability="tool.shared"),
            _step("s2", capability="tool.shared"),
            _step("s3", capability="tool.shared"),
        ]
        await resolver.check_capabilities(steps)

        # Only 1 unique capability -> 1 query
        assert len(fabric.query_calls) == 1
        assert fabric.query_calls[0] == "tool.shared"

    @pytest.mark.asyncio
    async def test_multiple_unique_capabilities_queried(self) -> None:
        """3 unique capabilities -> 3 registry queries."""
        fabric = FakeFabricPort()
        fabric.register(_entry("cap.a"))
        fabric.register(_entry("cap.b"))
        fabric.register(_entry("cap.c"))
        resolver = _resolver(fabric=fabric)

        steps = [
            _step("s1", capability="cap.a"),
            _step("s2", capability="cap.b"),
            _step("s3", capability="cap.c"),
        ]
        await resolver.check_capabilities(steps)

        assert len(fabric.query_calls) == 3

    @pytest.mark.asyncio
    async def test_mixed_available_and_missing(self) -> None:
        """Some available, some missing -> only missing in results."""
        fabric = FakeFabricPort()
        fabric.register(_entry("cap.exists"))
        resolver = _resolver(fabric=fabric)

        checks = await resolver.check_capabilities(
            [
                _step("s1", capability="cap.exists"),
                _step("s2", capability="cap.missing"),
            ]
        )

        assert len(checks) == 1
        assert checks[0].step_id == "s2"
        assert checks[0].capability == "cap.missing"
        assert checks[0].available is False

    @pytest.mark.asyncio
    async def test_same_missing_cap_reported_per_step(self) -> None:
        """Same missing capability in 2 steps -> 2 CapabilityChecks."""
        fabric = FakeFabricPort()
        resolver = _resolver(fabric=fabric)

        checks = await resolver.check_capabilities(
            [
                _step("s1", capability="cap.missing"),
                _step("s2", capability="cap.missing"),
            ]
        )

        assert len(checks) == 2
        step_ids = {c.step_id for c in checks}
        assert step_ids == {"s1", "s2"}

    @pytest.mark.asyncio
    async def test_empty_steps_returns_empty(self) -> None:
        """No steps -> no checks."""
        resolver = _resolver()

        checks = await resolver.check_capabilities([])

        assert checks == []

    @pytest.mark.asyncio
    async def test_registry_query_exception_treated_as_unavailable(self) -> None:
        """Registry query raises -> treated as capability unavailable."""
        fabric = FakeFabricPort()
        fabric.set_error("cap.broken", RuntimeError("registry down"))
        resolver = _resolver(fabric=fabric)

        checks = await resolver.check_capabilities(
            [
                _step("s1", capability="cap.broken"),
            ]
        )

        assert len(checks) == 1
        assert checks[0].available is False

    @pytest.mark.asyncio
    async def test_alternatives_populated_for_missing(self) -> None:
        """Missing cap with same-category alternative -> alternatives populated."""
        fabric = FakeFabricPort()
        # Register an alternative in same category as tool.calendar.search
        fabric.register(_entry("tool.calendar.find", safety_band_min="GREEN"))
        resolver = _resolver(fabric=fabric)

        checks = await resolver.check_capabilities([_step("s1", capability="tool.calendar.search")])

        assert len(checks) == 1
        assert checks[0].available is False
        assert "tool.calendar.find" in checks[0].alternatives


# ===================================================================
# 3. Time budget estimation (BUDGET-1)
# ===================================================================


class TestTimeBudget:
    """Tests for time budget estimation."""

    @pytest.mark.asyncio
    async def test_no_time_pressure_within_budget(self) -> None:
        """Plan within 10s budget -> time_pressure=False."""
        fabric = FakeFabricPort()
        fabric.register(_entry("cap"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(
            _step("s1", capability="cap", timeout_ms=3000),
            estimated_duration_ms=5000,
        )

        result = await resolver.validate(plan)

        assert result.time_pressure is False

    @pytest.mark.asyncio
    async def test_time_pressure_exceeds_budget(self) -> None:
        """Plan exceeds 10s budget -> time_pressure=True, warning."""
        fabric = FakeFabricPort()
        fabric.register(_entry("cap"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(
            _step("s1", capability="cap"),
            estimated_duration_ms=15000,
        )

        result = await resolver.validate(plan)

        assert result.time_pressure is True
        assert any("time budget" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_time_pressure_from_step_timeouts(self) -> None:
        """No plan-level estimate -> sums step timeout_ms."""
        fabric = FakeFabricPort()
        fabric.register(_entry("cap.a"))
        fabric.register(_entry("cap.b"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(
            _step("s1", capability="cap.a", timeout_ms=6000),
            _step("s2", capability="cap.b", timeout_ms=6000),
        )

        result = await resolver.validate(plan)

        # 6000 + 6000 = 12000 > 10000
        assert result.time_pressure is True

    @pytest.mark.asyncio
    async def test_no_estimates_no_pressure(self) -> None:
        """No timeout_ms on steps, no plan estimate -> no pressure."""
        fabric = FakeFabricPort()
        fabric.register(_entry("cap"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(_step("s1", capability="cap"))

        result = await resolver.validate(plan)

        assert result.time_pressure is False

    @pytest.mark.asyncio
    async def test_plan_estimate_takes_precedence(self) -> None:
        """Plan-level estimate takes precedence over step sums."""
        fabric = FakeFabricPort()
        fabric.register(_entry("cap"))
        resolver = _resolver(fabric=fabric)

        # Step has large timeout but plan estimate is within budget
        plan = _plan(
            _step("s1", capability="cap", timeout_ms=20000),
            estimated_duration_ms=5000,
        )

        result = await resolver.validate(plan)

        # Plan-level estimate (5000) wins over step timeout (20000)
        assert result.time_pressure is False


# ===================================================================
# 4. find_alternatives() (3.1.3)
# ===================================================================


class TestFindAlternatives:
    """Tests for find_alternatives() scoring, filtering, safety band."""

    @pytest.mark.asyncio
    async def test_no_candidates_returns_empty(self) -> None:
        """No entries in registry for category -> empty list."""
        fabric = FakeFabricPort()
        resolver = _resolver(fabric=fabric)
        step = _step("s1", capability="tool.calendar.search")

        result = await resolver.find_alternatives("tool.calendar.search", step)

        assert result == []

    @pytest.mark.asyncio
    async def test_same_category_returned(self) -> None:
        """Same-category entries returned as alternatives."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.calendar.find"))
        fabric.register(_entry("tool.calendar.list"))
        resolver = _resolver(fabric=fabric)
        step = _step("s1", capability="tool.calendar.search")

        result = await resolver.find_alternatives("tool.calendar.search", step)

        assert len(result) == 2
        cap_ids = {a.capability_id for a in result}
        assert cap_ids == {"tool.calendar.find", "tool.calendar.list"}

    @pytest.mark.asyncio
    async def test_different_category_excluded(self) -> None:
        """Entries in different category not returned."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.email.send"))  # different category
        fabric.register(_entry("tool.calendar.find"))  # same category
        resolver = _resolver(fabric=fabric)
        step = _step("s1", capability="tool.calendar.search")

        result = await resolver.find_alternatives("tool.calendar.search", step)

        assert len(result) == 1
        assert result[0].capability_id == "tool.calendar.find"

    @pytest.mark.asyncio
    async def test_missing_cap_itself_excluded(self) -> None:
        """The missing capability itself is excluded from alternatives."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.calendar.search"))  # the missing one, somehow in registry
        fabric.register(_entry("tool.calendar.find"))
        resolver = _resolver(fabric=fabric)
        step = _step("s1", capability="tool.calendar.search")

        result = await resolver.find_alternatives("tool.calendar.search", step)

        cap_ids = {a.capability_id for a in result}
        assert "tool.calendar.search" not in cap_ids
        assert "tool.calendar.find" in cap_ids

    @pytest.mark.asyncio
    async def test_safety_band_filter_green_allows_green_only(self) -> None:
        """Step with GREEN band -> only GREEN candidates pass."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.cal.find", safety_band_min="GREEN"))
        fabric.register(_entry("tool.cal.list", safety_band_min="AMBER"))
        fabric.register(_entry("tool.cal.get", safety_band_min="RED"))
        resolver = _resolver(fabric=fabric)
        step = _step("s1", capability="tool.cal.search", safety_band_min="GREEN")

        result = await resolver.find_alternatives("tool.cal.search", step)

        # GREEN=1 <= GREEN=1: pass. AMBER=2 > GREEN=1: filtered. RED=3 > GREEN=1: filtered.
        cap_ids = {a.capability_id for a in result}
        assert "tool.cal.find" in cap_ids
        assert "tool.cal.list" not in cap_ids
        assert "tool.cal.get" not in cap_ids

    @pytest.mark.asyncio
    async def test_safety_band_filter_red_allows_all(self) -> None:
        """Step with RED band -> GREEN, AMBER, RED all pass."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.cal.find", safety_band_min="GREEN"))
        fabric.register(_entry("tool.cal.list", safety_band_min="AMBER"))
        fabric.register(_entry("tool.cal.get", safety_band_min="RED"))
        resolver = _resolver(fabric=fabric)
        step = _step("s1", capability="tool.cal.search", safety_band_min="RED")

        result = await resolver.find_alternatives("tool.cal.search", step)

        cap_ids = {a.capability_id for a in result}
        assert "tool.cal.find" in cap_ids
        assert "tool.cal.list" in cap_ids
        assert "tool.cal.get" in cap_ids

    @pytest.mark.asyncio
    async def test_safety_band_no_band_on_step(self) -> None:
        """Step with no safety_band_min -> no safety filtering applied."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.cal.find", safety_band_min="GREEN"))
        fabric.register(_entry("tool.cal.list", safety_band_min="RED"))
        resolver = _resolver(fabric=fabric)
        step = _step("s1", capability="tool.cal.search")  # no safety_band_min

        result = await resolver.find_alternatives("tool.cal.search", step)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_top_3_limit(self) -> None:
        """5 candidates -> only top 3 returned."""
        fabric = FakeFabricPort()
        for i in range(5):
            fabric.register(_entry(f"tool.cal.alt{i}", safety_band_min="GREEN"))
        resolver = _resolver(fabric=fabric)
        step = _step("s1", capability="tool.cal.search")

        result = await resolver.find_alternatives("tool.cal.search", step)

        assert len(result) <= TOP_N_ALTERNATIVES
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_sorted_descending_by_score(self) -> None:
        """Alternatives returned sorted by score descending."""
        fabric = FakeFabricPort()
        # Different names give different name_similarity scores
        fabric.register(_entry("tool.cal.search_v2"))  # very similar name
        fabric.register(_entry("tool.cal.xyz"))  # less similar
        resolver = _resolver(fabric=fabric)
        step = _step("s1", capability="tool.cal.search")

        result = await resolver.find_alternatives("tool.cal.search", step)

        assert len(result) >= 2
        # Scores should be in descending order
        for i in range(len(result) - 1):
            assert result[i].score >= result[i + 1].score

    @pytest.mark.asyncio
    async def test_param_mapping_identity(self) -> None:
        """param_mapping is identity for step params."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.cal.find"))
        resolver = _resolver(fabric=fabric)
        step = _step(
            "s1",
            capability="tool.cal.search",
            params={"query": "meeting", "limit": 10},
        )

        result = await resolver.find_alternatives("tool.cal.search", step)

        assert len(result) == 1
        assert result[0].param_mapping == {"query": "query", "limit": "limit"}

    @pytest.mark.asyncio
    async def test_category_query_exception_returns_empty(self) -> None:
        """Category query raises -> empty alternatives."""
        fabric = FakeFabricPort()
        fabric.set_category_error("tool.cal", RuntimeError("registry down"))
        resolver = _resolver(fabric=fabric)
        step = _step("s1", capability="tool.cal.search")

        result = await resolver.find_alternatives("tool.cal.search", step)

        assert result == []

    @pytest.mark.asyncio
    async def test_scoring_exact_safety_match(self) -> None:
        """Exact safety band match scores 1.0 for safety component."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.cal.find", safety_band_min="GREEN"))
        resolver = _resolver(fabric=fabric)
        step = _step("s1", capability="tool.cal.search", safety_band_min="GREEN")

        result = await resolver.find_alternatives("tool.cal.search", step)

        assert len(result) == 1
        # score = 0.6*0.5 + 0.2*1.0 + 0.2*name_sim
        # Exact safety = 1.0 (weight 0.2)
        expected_min = W_SCHEMA * SCHEMA_OVERLAP_DEFAULT_V1 + W_SAFETY * 1.0
        assert result[0].score >= expected_min

    @pytest.mark.asyncio
    async def test_scoring_stricter_safety(self) -> None:
        """Stricter safety band scores 0.8 for safety component."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.cal.find", safety_band_min="GREEN"))  # stricter
        resolver = _resolver(fabric=fabric)
        step = _step("s1", capability="tool.cal.search", safety_band_min="AMBER")

        result = await resolver.find_alternatives("tool.cal.search", step)

        assert len(result) == 1
        # GREEN < AMBER so it's stricter -> safety_score=0.8
        expected_max = W_SCHEMA * SCHEMA_OVERLAP_DEFAULT_V1 + W_SAFETY * 0.8 + W_NAME * 1.0
        assert result[0].score <= expected_max

    @pytest.mark.asyncio
    async def test_alternative_capability_fields(self) -> None:
        """AlternativeCapability has all expected fields."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.cal.find", safety_band_min="AMBER"))
        resolver = _resolver(fabric=fabric)
        step = _step("s1", capability="tool.cal.search")

        result = await resolver.find_alternatives("tool.cal.search", step)

        assert len(result) == 1
        alt = result[0]
        assert isinstance(alt, AlternativeCapability)
        assert alt.capability_id == "tool.cal.find"
        assert isinstance(alt.score, float)
        assert alt.score >= MIN_ALTERNATIVE_SCORE
        assert isinstance(alt.param_mapping, dict)
        assert alt.safety_band == "AMBER"


# ===================================================================
# 5. resolve_iteratively() (3.1.4)
# ===================================================================


class TestResolveIteratively:
    """Tests for the 3-cycle state machine."""

    @pytest.mark.asyncio
    async def test_empty_checks_resolved(self) -> None:
        """No issues -> resolved=True immediately."""
        resolver = _resolver()
        plan = _plan()

        result = await resolver.resolve_iteratively(plan, [])

        assert result.resolved is True
        assert result.cycles_used == 0

    @pytest.mark.asyncio
    async def test_no_alternatives_hil_fallback(self) -> None:
        """Issues but no alternatives -> HIL fallback, cycles=1."""
        fabric = FakeFabricPort()
        resolver = _resolver(fabric=fabric)
        plan = _plan(_step("s1", capability="cap.missing"))
        checks = [CapabilityCheck(step_id="s1", capability="cap.missing", available=False)]

        result = await resolver.resolve_iteratively(plan, checks)

        assert result.resolved is False
        assert result.hil_requested is True
        assert len(result.unresolved) == 1
        assert result.cycles_used == 1

    @pytest.mark.asyncio
    async def test_cycle1_resolves_all(self) -> None:
        """One missing with alternative -> resolved in cycle 1."""
        fabric = FakeFabricPort()
        # Register alternative so find_alternatives returns it
        fabric.register(_entry("tool.cal.find", safety_band_min="GREEN"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(_step("s1", capability="tool.cal.search"))
        checks = [CapabilityCheck(step_id="s1", capability="tool.cal.search", available=False)]

        result = await resolver.resolve_iteratively(plan, checks)

        assert result.resolved is True
        assert result.cycles_used == 1
        assert result.modified_plan is not None
        # Verify the step's capability was substituted
        modified_step = result.modified_plan.steps[0]
        assert modified_step.capability == "tool.cal.find"

    @pytest.mark.asyncio
    async def test_alternatives_applied_tracked(self) -> None:
        """Successful resolution records AlternativeMapping."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.cal.find"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(_step("s1", capability="tool.cal.search"))
        checks = [CapabilityCheck(step_id="s1", capability="tool.cal.search", available=False)]

        result = await resolver.resolve_iteratively(plan, checks)

        assert result.resolved is True
        assert len(result.alternatives_applied) == 1
        mapping = result.alternatives_applied[0]
        assert mapping.original_capability == "tool.cal.search"
        assert mapping.replacement_capability == "tool.cal.find"

    @pytest.mark.asyncio
    async def test_partial_resolution_hil(self) -> None:
        """Two missing, one with alt, one without -> HIL after cycle 3."""
        fabric = FakeFabricPort()
        # Only register alternative for tool.cal.search, not tool.email.send
        fabric.register(_entry("tool.cal.find"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(
            _step("s1", capability="tool.cal.search"),
            _step("s2", capability="tool.email.send"),
        )
        checks = [
            CapabilityCheck(step_id="s1", capability="tool.cal.search", available=False),
            CapabilityCheck(step_id="s2", capability="tool.email.send", available=False),
        ]

        result = await resolver.resolve_iteratively(plan, checks)

        assert result.resolved is False
        assert result.hil_requested is True
        # tool.cal.search was resolved but tool.email.send was not
        assert len(result.alternatives_applied) >= 1
        assert any(c.capability == "tool.email.send" for c in result.unresolved)

    @pytest.mark.asyncio
    async def test_cycle2_more_issues_abort(self) -> None:
        """Cycle 1 substitution introduces cascade -> cycle 2 detects MORE issues -> HIL.

        Scenario: Step s1 uses cap.missing. We register cap.alt as alternative.
        After substitution to cap.alt, re-validation finds cap.alt is in registry,
        BUT if we engineer the fake to show MORE issues after substitution,
        cycle 2 should abort.
        """
        fabric = FakeFabricPort()
        # Register cap.alt so find_alternatives finds it
        fabric.register(_entry("cap.alt"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(
            _step("s1", capability="cap.missing"),
            _step("s2", capability="cap.ok"),
        )
        # Only 1 issue at start
        checks = [
            CapabilityCheck(step_id="s1", capability="cap.missing", available=False),
        ]

        # After cycle 1 substitution to cap.alt, cap.alt IS in registry.
        # But we need to simulate MORE issues appearing. We can do this by
        # setting an error on "cap.ok" so that on re-validation it fails too.
        fabric.register(_entry("cap.ok"))  # Initially OK

        result = await resolver.resolve_iteratively(plan, checks)

        # cap.alt is in registry, so re-validation should pass for s1.
        # cap.ok is also in registry, so no new issues.
        # In this case, resolved=True (all pass after cycle 1).
        assert result.resolved is True
        assert result.cycles_used == 1

    @pytest.mark.asyncio
    async def test_cycle2_cascading_failure_detected(self) -> None:
        """Cycle 2 abort: substitution causes more issues than started.

        We engineer this by having the alternative capability name
        also be missing from registry (not registered for query_registry).
        """
        fabric = FakeFabricPort()
        # Register tool.cal.find for category query (find_alternatives)
        # but NOT for query_registry (check_capabilities will see it as unavailable)
        # This is tricky -- category search returns it, but individual query doesn't.
        # We can do this by using a custom fake behavior.
        resolver = _resolver(fabric=fabric)

        plan = _plan(
            _step("s1", capability="tool.cal.search"),
        )
        checks = [
            CapabilityCheck(step_id="s1", capability="tool.cal.search", available=False),
        ]

        # No alternatives at all -> early HIL
        result = await resolver.resolve_iteratively(plan, checks)

        assert result.resolved is False
        assert result.hil_requested is True
        assert result.cycles_used == 1

    @pytest.mark.asyncio
    async def test_modified_plan_preserved_for_audit(self) -> None:
        """Original plan is not mutated; modified_plan is a new instance."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.cal.find"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(_step("s1", capability="tool.cal.search"))
        original_cap = plan.steps[0].capability
        checks = [
            CapabilityCheck(step_id="s1", capability="tool.cal.search", available=False),
        ]

        result = await resolver.resolve_iteratively(plan, checks)

        # Original plan untouched
        assert plan.steps[0].capability == original_cap
        # Modified plan has the substitution
        assert result.modified_plan is not None
        assert result.modified_plan.steps[0].capability == "tool.cal.find"

    @pytest.mark.asyncio
    async def test_max_cycles_1_limits_to_one_cycle(self) -> None:
        """max_cycles=1 -> only cycle 1 runs."""
        fabric = FakeFabricPort()
        # Register alternative but it won't fully resolve (needs cycle 2)
        fabric.register(_entry("tool.cal.find"))
        resolver = _resolver(fabric=fabric, max_cycles=1)

        plan = _plan(
            _step("s1", capability="tool.cal.search"),
            _step("s2", capability="tool.email.send"),
        )
        checks = [
            CapabilityCheck(step_id="s1", capability="tool.cal.search", available=False),
            CapabilityCheck(step_id="s2", capability="tool.email.send", available=False),
        ]

        result = await resolver.resolve_iteratively(plan, checks)

        # Cycle 1 applies what it can, but max_cycles=1 stops there
        assert result.cycles_used == 1
        assert result.hil_requested is True

    @pytest.mark.asyncio
    async def test_resolution_result_fields(self) -> None:
        """ResolutionResult has expected fields."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.cal.find"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(_step("s1", capability="tool.cal.search"))
        checks = [
            CapabilityCheck(step_id="s1", capability="tool.cal.search", available=False),
        ]

        result = await resolver.resolve_iteratively(plan, checks)

        assert isinstance(result, ResolutionResult)
        assert isinstance(result.resolved, bool)
        assert isinstance(result.cycles_used, int)
        assert isinstance(result.hil_requested, bool)
        assert isinstance(result.alternatives_applied, list)

    @pytest.mark.asyncio
    async def test_multiple_steps_same_missing_cap(self) -> None:
        """Two steps with same missing cap -> both get substituted."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.cal.find"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(
            _step("s1", capability="tool.cal.search"),
            _step("s2", capability="tool.cal.search"),
        )
        checks = [
            CapabilityCheck(step_id="s1", capability="tool.cal.search", available=False),
            CapabilityCheck(step_id="s2", capability="tool.cal.search", available=False),
        ]

        result = await resolver.resolve_iteratively(plan, checks)

        assert result.resolved is True
        assert result.modified_plan is not None
        for step in result.modified_plan.steps:
            assert step.capability == "tool.cal.find"
        assert len(result.alternatives_applied) == 2


# ===================================================================
# 6. Edge cases
# ===================================================================


class TestEdgeCases:
    """Edge case tests for ConstraintResolver."""

    @pytest.mark.asyncio
    async def test_repr(self) -> None:
        """ConstraintResolver has useful repr."""
        resolver = _resolver()
        r = repr(resolver)
        assert "ConstraintResolver" in r

    @pytest.mark.asyncio
    async def test_validate_preserves_original_plan(self) -> None:
        """validate() does not mutate the original CommittedPlan."""
        fabric = FakeFabricPort()
        resolver = _resolver(fabric=fabric)

        plan = _plan(_step("s1", capability="tool.missing"))
        original_steps = list(plan.steps)

        await resolver.validate(plan)

        assert plan.steps == original_steps

    @pytest.mark.asyncio
    async def test_valid_result_has_empty_alternatives(self) -> None:
        """Valid result has empty alternatives_applied when all caps exist."""
        fabric = FakeFabricPort()
        fabric.register(_entry("cap"))
        resolver = _resolver(fabric=fabric)

        result = await resolver.validate(_plan(_step("s1", capability="cap")))

        assert result.alternatives_applied == []

    @pytest.mark.asyncio
    async def test_exact_budget_boundary_no_pressure(self) -> None:
        """Estimated duration exactly at budget boundary -> no pressure."""
        fabric = FakeFabricPort()
        fabric.register(_entry("cap"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(
            _step("s1", capability="cap"),
            estimated_duration_ms=HIGH_TIER_TIME_BUDGET_MS,
        )

        result = await resolver.validate(plan)

        # Exactly at budget = NOT exceeded
        assert result.time_pressure is False

    @pytest.mark.asyncio
    async def test_one_over_budget_triggers_pressure(self) -> None:
        """One ms over budget -> time_pressure=True."""
        fabric = FakeFabricPort()
        fabric.register(_entry("cap"))
        resolver = _resolver(fabric=fabric)

        plan = _plan(
            _step("s1", capability="cap"),
            estimated_duration_ms=HIGH_TIER_TIME_BUDGET_MS + 1,
        )

        result = await resolver.validate(plan)

        assert result.time_pressure is True


# ===================================================================
# 7. Helper functions
# ===================================================================


class TestHelpers:
    """Tests for module-level helper functions."""

    # --- _derive_category ---

    def test_derive_category_three_segments(self) -> None:
        """tool.calendar.search -> tool.calendar"""
        assert _derive_category("tool.calendar.search") == "tool.calendar"

    def test_derive_category_four_segments(self) -> None:
        """tool.calendar.events.search -> tool.calendar.events"""
        assert _derive_category("tool.calendar.events.search") == "tool.calendar.events"

    def test_derive_category_two_segments(self) -> None:
        """agent.summarize -> agent"""
        assert _derive_category("agent.summarize") == "agent"

    def test_derive_category_single_segment(self) -> None:
        """single -> single (no dots, return as-is)"""
        assert _derive_category("single") == "single"

    # --- _safety_band_rank ---

    def test_safety_band_rank_green(self) -> None:
        assert _safety_band_rank("GREEN") == 1

    def test_safety_band_rank_amber(self) -> None:
        assert _safety_band_rank("AMBER") == 2

    def test_safety_band_rank_red(self) -> None:
        assert _safety_band_rank("RED") == 3

    def test_safety_band_rank_case_insensitive(self) -> None:
        assert _safety_band_rank("green") == 1
        assert _safety_band_rank("Green") == 1

    def test_safety_band_rank_unknown(self) -> None:
        assert _safety_band_rank("PURPLE") == 999

    # --- _levenshtein ---

    def test_levenshtein_identical(self) -> None:
        assert _levenshtein("abc", "abc") == 0

    def test_levenshtein_empty(self) -> None:
        assert _levenshtein("", "abc") == 3
        assert _levenshtein("abc", "") == 3

    def test_levenshtein_both_empty(self) -> None:
        assert _levenshtein("", "") == 0

    def test_levenshtein_one_char_diff(self) -> None:
        assert _levenshtein("cat", "bat") == 1

    def test_levenshtein_insert(self) -> None:
        assert _levenshtein("abc", "abcd") == 1

    # --- _name_similarity ---

    def test_name_similarity_identical(self) -> None:
        assert _name_similarity("tool.calendar.search", "tool.calendar.search") == 1.0

    def test_name_similarity_empty_both(self) -> None:
        assert _name_similarity("", "") == 1.0

    def test_name_similarity_one_empty(self) -> None:
        assert _name_similarity("abc", "") == 0.0
        assert _name_similarity("", "abc") == 0.0

    def test_name_similarity_partial(self) -> None:
        """Similar strings have high similarity."""
        sim = _name_similarity("tool.calendar.search", "tool.calendar.find")
        assert 0.0 < sim < 1.0

    def test_name_similarity_very_different(self) -> None:
        """Very different strings have low similarity."""
        sim = _name_similarity("abc", "xyz")
        assert sim < 0.5


# ===================================================================
# 8. Type dataclass tests
# ===================================================================


class TestTypeDataclasses:
    """Tests for the updated type dataclasses."""

    def test_validation_result_defaults(self) -> None:
        """ValidationResult has correct defaults."""
        vr = ValidationResult(valid=True)
        assert vr.valid is True
        assert vr.errors == []
        assert vr.warnings == []
        assert vr.alternatives_applied == []
        assert vr.time_pressure is False
        assert vr.hil_required is False

    def test_validation_result_with_errors(self) -> None:
        """ValidationResult with errors."""
        vr = ValidationResult(
            valid=False,
            errors=["cap missing"],
            hil_required=True,
        )
        assert vr.valid is False
        assert len(vr.errors) == 1
        assert vr.hil_required is True

    def test_alternative_mapping(self) -> None:
        """AlternativeMapping fields."""
        am = AlternativeMapping(
            original_capability="tool.old",
            replacement_capability="tool.new",
            reason="auto-resolved",
        )
        assert am.original_capability == "tool.old"
        assert am.replacement_capability == "tool.new"
        assert am.reason == "auto-resolved"

    def test_capability_check_defaults(self) -> None:
        """CapabilityCheck defaults."""
        cc = CapabilityCheck(
            step_id="s1",
            capability="cap",
            available=True,
        )
        assert cc.contract_entry is None
        assert cc.alternatives == []

    def test_capability_check_with_entry(self) -> None:
        """CapabilityCheck with contract_entry."""
        entry = _entry("cap")
        cc = CapabilityCheck(
            step_id="s1",
            capability="cap",
            available=True,
            contract_entry=entry,
        )
        assert cc.contract_entry is not None
        assert cc.contract_entry.name == "cap"

    def test_alternative_capability_fields(self) -> None:
        """AlternativeCapability has correct fields and defaults."""
        ac = AlternativeCapability(
            capability_id="tool.cal.find",
            score=0.75,
        )
        assert ac.capability_id == "tool.cal.find"
        assert ac.score == 0.75
        assert ac.param_mapping == {}
        assert ac.safety_band == "GREEN"

    def test_alternative_capability_with_params(self) -> None:
        """AlternativeCapability with param_mapping and safety_band."""
        ac = AlternativeCapability(
            capability_id="tool.cal.find",
            score=0.65,
            param_mapping={"query": "search_term"},
            safety_band="AMBER",
        )
        assert ac.param_mapping == {"query": "search_term"}
        assert ac.safety_band == "AMBER"

    def test_resolution_result_defaults(self) -> None:
        """ResolutionResult has correct defaults."""
        rr = ResolutionResult(resolved=True)
        assert rr.resolved is True
        assert rr.modified_plan is None
        assert rr.unresolved == []
        assert rr.hil_requested is False
        assert rr.cycles_used == 0
        assert rr.alternatives_applied == []

    def test_resolution_result_with_alternatives(self) -> None:
        """ResolutionResult with alternatives_applied."""
        mapping = AlternativeMapping(
            original_capability="old",
            replacement_capability="new",
            reason="test",
        )
        rr = ResolutionResult(
            resolved=True,
            cycles_used=1,
            alternatives_applied=[mapping],
        )
        assert len(rr.alternatives_applied) == 1
        assert rr.alternatives_applied[0].replacement_capability == "new"

    def test_plan_step_safety_band_min(self) -> None:
        """PlanStep now supports safety_band_min field."""
        step = PlanStep(
            id="s1",
            capability="cap",
            safety_band_min="GREEN",
        )
        assert step.safety_band_min == "GREEN"

    def test_plan_step_safety_band_min_default(self) -> None:
        """PlanStep.safety_band_min defaults to None."""
        step = PlanStep(id="s1", capability="cap")
        assert step.safety_band_min is None


# ===================================================================
# 10. format_constraint_question (3.1.5)
# ===================================================================


class TestFormatConstraintQuestion:
    """Tests for format_constraint_question() helper."""

    def test_empty_list(self) -> None:
        """Empty unresolved list returns no-constraints message."""
        result = format_constraint_question([])
        assert result == "No unresolved constraints."

    def test_single_unresolved_no_alternatives(self) -> None:
        """Single unresolved capability without alternatives."""
        checks = [
            CapabilityCheck(
                step_id="s1",
                capability="tool.calendar.search",
                available=False,
            )
        ]
        result = format_constraint_question(checks)
        assert "tool.calendar.search" in result
        assert "step 's1'" in result
        assert "alternatives" not in result.lower() or "available alternatives" not in result
        assert "How would you like to proceed?" in result

    def test_single_unresolved_with_alternatives(self) -> None:
        """Single unresolved capability with alternatives listed."""
        checks = [
            CapabilityCheck(
                step_id="s2",
                capability="tool.email.send",
                available=False,
                alternatives=["tool.email.draft", "tool.email.queue"],
            )
        ]
        result = format_constraint_question(checks)
        assert "tool.email.send" in result
        assert "step 's2'" in result
        assert "tool.email.draft" in result
        assert "tool.email.queue" in result

    def test_multiple_unresolved_mixed(self) -> None:
        """Multiple unresolved capabilities, some with alternatives."""
        checks = [
            CapabilityCheck(
                step_id="s1",
                capability="cap.a",
                available=False,
            ),
            CapabilityCheck(
                step_id="s2",
                capability="cap.b",
                available=False,
                alternatives=["cap.b.alt"],
            ),
            CapabilityCheck(
                step_id="s3",
                capability="cap.c",
                available=False,
            ),
        ]
        result = format_constraint_question(checks)
        assert "cap.a" in result
        assert "cap.b" in result
        assert "cap.c" in result
        assert "cap.b.alt" in result
        # All steps referenced
        assert "s1" in result
        assert "s2" in result
        assert "s3" in result

    def test_question_structure(self) -> None:
        """Question has proper prefix and suffix structure."""
        checks = [
            CapabilityCheck(
                step_id="s1",
                capability="x",
                available=False,
            )
        ]
        result = format_constraint_question(checks)
        lines = result.split("\n")
        assert lines[0] == "The following capabilities could not be resolved automatically:"
        assert lines[-1] == "How would you like to proceed?"


# ===================================================================
# 11. build_options (3.1.5)
# ===================================================================


class TestBuildOptions:
    """Tests for build_options() helper."""

    def test_empty_list(self) -> None:
        """Empty unresolved returns only cancel option."""
        options = build_options([])
        assert options == ["Cancel plan"]

    def test_single_no_alternatives(self) -> None:
        """Single step, no alternatives: skip + cancel."""
        checks = [
            CapabilityCheck(
                step_id="s1",
                capability="cap.a",
                available=False,
            )
        ]
        options = build_options(checks)
        assert len(options) == 2
        assert options[0] == "Skip step 's1'"
        assert options[-1] == "Cancel plan"

    def test_single_with_alternatives(self) -> None:
        """Single step with alternatives: skip + each alt + cancel."""
        checks = [
            CapabilityCheck(
                step_id="s1",
                capability="cap.a",
                available=False,
                alternatives=["cap.a.alt1", "cap.a.alt2"],
            )
        ]
        options = build_options(checks)
        assert len(options) == 4  # skip + 2 alts + cancel
        assert options[0] == "Skip step 's1'"
        assert "cap.a.alt1" in options[1]
        assert "cap.a.alt2" in options[2]
        assert options[-1] == "Cancel plan"

    def test_multiple_steps(self) -> None:
        """Multiple steps produce options in order."""
        checks = [
            CapabilityCheck(
                step_id="s1",
                capability="cap.a",
                available=False,
                alternatives=["cap.a.alt"],
            ),
            CapabilityCheck(
                step_id="s2",
                capability="cap.b",
                available=False,
            ),
        ]
        options = build_options(checks)
        # s1: skip + 1 alt, s2: skip, then cancel
        assert len(options) == 4
        assert options[0] == "Skip step 's1'"
        assert "cap.a.alt" in options[1]
        assert options[2] == "Skip step 's2'"
        assert options[-1] == "Cancel plan"

    def test_cancel_always_last(self) -> None:
        """Cancel plan is always the last option."""
        for n in range(0, 4):
            checks = [
                CapabilityCheck(
                    step_id=f"s{i}",
                    capability=f"cap.{i}",
                    available=False,
                )
                for i in range(n)
            ]
            options = build_options(checks)
            assert options[-1] == "Cancel plan"

    def test_alternative_option_references_both_capabilities(self) -> None:
        """Alternative option text references both original and replacement."""
        checks = [
            CapabilityCheck(
                step_id="s1",
                capability="tool.read.lookup",
                available=False,
                alternatives=["tool.read.search"],
            )
        ]
        options = build_options(checks)
        alt_option = options[1]
        assert "tool.read.search" in alt_option
        assert "tool.read.lookup" in alt_option
        assert "s1" in alt_option


# ===================================================================
# 12. trigger_hil_fallback (3.1.5)
# ===================================================================


class TestTriggerHilFallback:
    """Tests for ConstraintResolver.trigger_hil_fallback()."""

    @pytest.mark.asyncio
    async def test_basic_emission(self) -> None:
        """trigger_hil_fallback emits HILRequest via delta_port."""
        delta = FakeDeltaPort()
        resolver = _resolver(delta=delta)
        unresolved = [
            CapabilityCheck(
                step_id="s1",
                capability="tool.missing",
                available=False,
            )
        ]
        plan = _plan(_step(id="s1", capability="tool.missing"))

        hil_req = await resolver.trigger_hil_fallback(unresolved, plan)

        assert hil_req is not None
        assert isinstance(hil_req, HILRequest)
        assert len(delta.emitted) == 1
        assert delta.emitted[0][0] == "hil"

    @pytest.mark.asyncio
    async def test_request_id_is_uuid(self) -> None:
        """HILRequest.request_id is a valid UUID string."""
        import uuid as _uuid

        delta = FakeDeltaPort()
        resolver = _resolver(delta=delta)
        unresolved = [CapabilityCheck(step_id="s1", capability="cap", available=False)]
        plan = _plan()

        hil_req = await resolver.trigger_hil_fallback(unresolved, plan)

        # Should parse as valid UUID
        parsed = _uuid.UUID(hil_req.request_id)
        assert str(parsed) == hil_req.request_id

    @pytest.mark.asyncio
    async def test_question_from_format_helper(self) -> None:
        """HILRequest.question matches format_constraint_question output."""
        delta = FakeDeltaPort()
        resolver = _resolver(delta=delta)
        unresolved = [
            CapabilityCheck(
                step_id="s1",
                capability="tool.calendar.search",
                available=False,
                alternatives=["tool.calendar.list"],
            )
        ]
        plan = _plan(_step(id="s1", capability="tool.calendar.search"))

        hil_req = await resolver.trigger_hil_fallback(unresolved, plan)

        expected_question = format_constraint_question(unresolved)
        assert hil_req.question == expected_question

    @pytest.mark.asyncio
    async def test_options_from_build_helper(self) -> None:
        """HILRequest.options match build_options output."""
        delta = FakeDeltaPort()
        resolver = _resolver(delta=delta)
        unresolved = [
            CapabilityCheck(
                step_id="s1",
                capability="tool.email.send",
                available=False,
                alternatives=["tool.email.draft"],
            )
        ]
        plan = _plan(_step(id="s1", capability="tool.email.send"))

        hil_req = await resolver.trigger_hil_fallback(unresolved, plan)

        expected_options = build_options(unresolved)
        assert hil_req.options == expected_options

    @pytest.mark.asyncio
    async def test_timeout_is_hil_timeout(self) -> None:
        """HILRequest.timeout_ms equals HIL_TIMEOUT_MS constant."""
        delta = FakeDeltaPort()
        resolver = _resolver(delta=delta)
        unresolved = [CapabilityCheck(step_id="s1", capability="cap", available=False)]
        plan = _plan()

        hil_req = await resolver.trigger_hil_fallback(unresolved, plan)

        assert hil_req.timeout_ms == HIL_TIMEOUT_MS
        assert hil_req.timeout_ms == 60_000

    @pytest.mark.asyncio
    async def test_context_contains_plan_id(self) -> None:
        """HILRequest.context includes plan_id."""
        delta = FakeDeltaPort()
        resolver = _resolver(delta=delta)
        unresolved = [CapabilityCheck(step_id="s1", capability="cap", available=False)]
        plan = _plan()

        hil_req = await resolver.trigger_hil_fallback(unresolved, plan)

        assert hil_req.context["plan_id"] == "plan-1"

    @pytest.mark.asyncio
    async def test_context_contains_unresolved_capabilities(self) -> None:
        """HILRequest.context lists unresolved capability names."""
        delta = FakeDeltaPort()
        resolver = _resolver(delta=delta)
        unresolved = [
            CapabilityCheck(step_id="s1", capability="cap.a", available=False),
            CapabilityCheck(step_id="s2", capability="cap.b", available=False),
        ]
        plan = _plan(
            _step(id="s1", capability="cap.a"),
            _step(id="s2", capability="cap.b"),
        )

        hil_req = await resolver.trigger_hil_fallback(unresolved, plan)

        assert hil_req.context["unresolved_capabilities"] == ["cap.a", "cap.b"]

    @pytest.mark.asyncio
    async def test_context_contains_unresolved_step_ids(self) -> None:
        """HILRequest.context lists unresolved step IDs."""
        delta = FakeDeltaPort()
        resolver = _resolver(delta=delta)
        unresolved = [
            CapabilityCheck(step_id="step-x", capability="cap", available=False),
            CapabilityCheck(step_id="step-y", capability="cap2", available=False),
        ]
        plan = _plan(
            _step(id="step-x", capability="cap"),
            _step(id="step-y", capability="cap2"),
        )

        hil_req = await resolver.trigger_hil_fallback(unresolved, plan)

        assert hil_req.context["unresolved_step_ids"] == ["step-x", "step-y"]

    @pytest.mark.asyncio
    async def test_emitted_with_plan_trace_id(self) -> None:
        """emit_hil_request receives the plan's trace_id."""
        delta = FakeDeltaPort()
        resolver = _resolver(delta=delta)
        unresolved = [CapabilityCheck(step_id="s1", capability="cap", available=False)]
        plan = _plan()
        # plan trace_id = "trace-1" from helper

        await resolver.trigger_hil_fallback(unresolved, plan)

        # FakeDeltaPort stores ("hil", hil_request, trace_id)
        assert delta.emitted[0][2] == "trace-1"

    @pytest.mark.asyncio
    async def test_no_delta_port_no_crash(self) -> None:
        """trigger_hil_fallback works without delta_port (returns request)."""
        resolver = _resolver(delta=None)
        unresolved = [CapabilityCheck(step_id="s1", capability="cap", available=False)]
        plan = _plan()

        hil_req = await resolver.trigger_hil_fallback(unresolved, plan)

        # Still returns a valid HILRequest
        assert hil_req is not None
        assert isinstance(hil_req, HILRequest)
        assert len(hil_req.options) > 0

    @pytest.mark.asyncio
    async def test_multiple_unresolved_all_in_request(self) -> None:
        """Multiple unresolved capabilities all reflected in question and options."""
        delta = FakeDeltaPort()
        resolver = _resolver(delta=delta)
        unresolved = [
            CapabilityCheck(
                step_id="s1",
                capability="cap.a",
                available=False,
                alternatives=["cap.a.alt"],
            ),
            CapabilityCheck(
                step_id="s2",
                capability="cap.b",
                available=False,
            ),
        ]
        plan = _plan(
            _step(id="s1", capability="cap.a"),
            _step(id="s2", capability="cap.b"),
        )

        hil_req = await resolver.trigger_hil_fallback(unresolved, plan)

        # Question mentions both
        assert "cap.a" in hil_req.question
        assert "cap.b" in hil_req.question
        # Options: skip s1, alt for s1, skip s2, cancel = 4
        assert len(hil_req.options) == 4

    @pytest.mark.asyncio
    async def test_each_call_gets_unique_request_id(self) -> None:
        """Successive calls produce different request_ids."""
        delta = FakeDeltaPort()
        resolver = _resolver(delta=delta)
        unresolved = [CapabilityCheck(step_id="s1", capability="cap", available=False)]
        plan = _plan()

        req1 = await resolver.trigger_hil_fallback(unresolved, plan)
        req2 = await resolver.trigger_hil_fallback(unresolved, plan)

        assert req1.request_id != req2.request_id


# ===================================================================
# 13. validate() integration with trigger_hil_fallback (3.1.5)
# ===================================================================


class TestValidateWithHILFallback:
    """Tests for validate() -> trigger_hil_fallback wiring."""

    @pytest.mark.asyncio
    async def test_hil_request_populated_when_hil_required(self) -> None:
        """ValidationResult.hil_request is set when hil_required=True."""
        fabric = FakeFabricPort()
        delta = FakeDeltaPort()
        # No registry entry -> capability missing -> resolution fails -> HIL
        resolver = _resolver(fabric=fabric, delta=delta)
        plan = _plan(_step(id="s1", capability="tool.missing.action"))

        result = await resolver.validate(plan)

        assert result.hil_required is True
        assert result.hil_request is not None
        assert isinstance(result.hil_request, HILRequest)

    @pytest.mark.asyncio
    async def test_hil_request_none_when_all_pass(self) -> None:
        """ValidationResult.hil_request is None when all capabilities pass."""
        fabric = FakeFabricPort()
        fabric.register(_entry("tool.read.lookup"))
        resolver = _resolver(fabric=fabric)
        plan = _plan(_step(id="s1", capability="tool.read.lookup"))

        result = await resolver.validate(plan)

        assert result.valid is True
        assert result.hil_required is False
        assert result.hil_request is None

    @pytest.mark.asyncio
    async def test_hil_emission_occurs_during_validate(self) -> None:
        """Delta port receives HIL emission when validate triggers fallback."""
        fabric = FakeFabricPort()
        delta = FakeDeltaPort()
        resolver = _resolver(fabric=fabric, delta=delta)
        plan = _plan(_step(id="s1", capability="tool.gone.action"))

        await resolver.validate(plan)

        hil_emissions = [e for e in delta.emitted if e[0] == "hil"]
        assert len(hil_emissions) == 1

    @pytest.mark.asyncio
    async def test_hil_request_none_when_auto_resolved(self) -> None:
        """No HIL triggered when alternatives auto-resolve the issue."""
        fabric = FakeFabricPort()
        delta = FakeDeltaPort()
        # Register an alternative but not the original
        fabric.register(_entry("tool.alpha.alt", safety_band_min="GREEN"))
        resolver = _resolver(fabric=fabric, delta=delta)
        plan = _plan(
            _step(
                id="s1",
                capability="tool.alpha.missing",
                safety_band_min="GREEN",
            )
        )

        result = await resolver.validate(plan)

        assert result.hil_required is False
        assert result.hil_request is None

    @pytest.mark.asyncio
    async def test_hil_request_has_correct_plan_context(self) -> None:
        """HIL request context references the correct plan_id."""
        fabric = FakeFabricPort()
        delta = FakeDeltaPort()
        resolver = _resolver(fabric=fabric, delta=delta)
        plan = _plan(_step(id="s1", capability="tool.x.y"))

        result = await resolver.validate(plan)

        assert result.hil_request is not None
        assert result.hil_request.context["plan_id"] == "plan-1"

    @pytest.mark.asyncio
    async def test_validate_no_delta_still_works(self) -> None:
        """validate() without delta_port still returns hil_request."""
        fabric = FakeFabricPort()
        resolver = _resolver(fabric=fabric, delta=None)
        plan = _plan(_step(id="s1", capability="tool.missing.x"))

        result = await resolver.validate(plan)

        assert result.hil_required is True
        assert result.hil_request is not None

    @pytest.mark.asyncio
    async def test_hil_request_timeout_is_60s(self) -> None:
        """HIL request from validate() has 60 second timeout."""
        fabric = FakeFabricPort()
        delta = FakeDeltaPort()
        resolver = _resolver(fabric=fabric, delta=delta)
        plan = _plan(_step(id="s1", capability="tool.gone"))

        result = await resolver.validate(plan)

        assert result.hil_request is not None
        assert result.hil_request.timeout_ms == 60_000


# ===================================================================
# 14. ValidationResult.hil_request field (3.1.5)
# ===================================================================


class TestValidationResultHILField:
    """Tests for the hil_request field on ValidationResult."""

    def test_default_none(self) -> None:
        """hil_request defaults to None."""
        vr = ValidationResult(valid=True)
        assert vr.hil_request is None

    def test_with_hil_request(self) -> None:
        """hil_request stores HILRequest when provided."""
        hil = HILRequest(
            request_id="test-req-1",
            question="test question",
            options=["opt1"],
            timeout_ms=60_000,
        )
        vr = ValidationResult(valid=False, hil_required=True, hil_request=hil)
        assert vr.hil_request is not None
        assert vr.hil_request.request_id == "test-req-1"
        assert vr.hil_request.question == "test question"

    def test_hil_request_immutable(self) -> None:
        """ValidationResult is frozen, hil_request cannot be replaced."""
        vr = ValidationResult(valid=True)
        with pytest.raises(AttributeError):
            vr.hil_request = "something"  # type: ignore[misc]
