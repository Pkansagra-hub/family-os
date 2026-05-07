"""ConstraintResolver tests (Epic 7.1.4) with factory-backed real adapters.

All integration tests obtain ConstraintResolver from
OrchestratorFactory.create_standalone() and script behavior through
real in-memory adapters:
  - MockFabricAdapter
  - TestDeltaAdapter
  - TestEventAdapter

No fake adapter classes are used.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from k1.hil.types import OverrideResponse
from k1.orchestrator.adapters.mock_fabric_adapter import MockFabricAdapter
from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter
from k1.orchestrator.adapters.test_event_adapter import TestEventAdapter
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.orchestration.constraint_resolver import (
    HIGH_TIER_TIME_BUDGET_MS,
    ConstraintResolver,
    _derive_category,
    _name_similarity,
    _safety_band_rank,
    build_options,
    format_constraint_question,
)
from k1.orchestrator.types import (
    CapabilityCheck,
    CommittedPlan,
    PlanStep,
    RegistryEntry,
)


async def _svc():
    service = await OrchestratorFactory.create_standalone()
    resolver: ConstraintResolver = service._constraint_resolver  # type: ignore[assignment]
    fabric: MockFabricAdapter = service._fabric_port  # type: ignore[assignment]
    delta: TestDeltaAdapter = service._delta_port  # type: ignore[assignment]
    event: TestEventAdapter = service._event_port  # type: ignore[assignment]
    return service, resolver, fabric, delta, event


def _entry(
    name: str,
    *,
    safety_band_min: str = "GREEN",
    availability: str = "AVAILABLE",
    estimated_duration_ms: Optional[int] = None,
) -> RegistryEntry:
    return RegistryEntry(
        name=name,
        provider_type="tool",
        safety_band_min=safety_band_min,
        availability=availability,
        estimated_duration_ms=estimated_duration_ms,
    )


def _step(
    sid: str,
    capability: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    timeout_ms: Optional[int] = None,
    safety_band_min: Optional[str] = None,
) -> PlanStep:
    return PlanStep(
        id=sid,
        capability=capability,
        params=params or {},
        timeout_ms=timeout_ms,
        safety_band_min=safety_band_min,
    )


def _plan(
    steps: List[PlanStep],
    *,
    deps: Optional[Dict[str, List[str]]] = None,
    estimated_duration_ms: Optional[int] = None,
    plan_id: str = "plan-1",
    request_id: str = "req-1",
    trace_id: str = "trace-1",
) -> CommittedPlan:
    return CommittedPlan(
        plan_id=plan_id,
        request_id=request_id,
        intent="test-intent",
        steps=steps,
        dependencies=deps or {},
        estimated_duration_ms=estimated_duration_ms,
        trace_id=trace_id,
    )


class TestValidate:
    @pytest.mark.asyncio
    async def test_all_capabilities_available_is_valid(self) -> None:
        _, resolver, fabric, _, _ = await _svc()
        fabric.register_capability("tool.read.lookup", _entry("tool.read.lookup"))
        fabric.register_capability("tool.write.save", _entry("tool.write.save"))

        result = await resolver.validate(
            _plan(
                [
                    _step("s1", "tool.read.lookup"),
                    _step("s2", "tool.write.save"),
                ]
            )
        )

        assert result.valid is True
        assert result.errors == []
        assert result.hil_required is False
        assert result.hil_response is None

    @pytest.mark.asyncio
    async def test_missing_capability_triggers_hil_request(self) -> None:
        _, resolver, _, delta, _ = await _svc()

        result = await resolver.validate(_plan([_step("s1", "tool.missing.action")]))

        assert result.valid is False
        assert result.hil_required is True
        # Without an injected hil_port the resolver returns a timed_out abort
        # OverrideResponse, which the validate() flow surfaces.
        assert result.hil_response is not None
        assert result.hil_response.timed_out is True

    @pytest.mark.asyncio
    async def test_auto_resolution_with_alternative(self) -> None:
        _, resolver, fabric, _, _ = await _svc()
        # Missing: tool.calendar.search ; alternative: tool.calendar.find
        fabric.register_capability("tool.calendar.find", _entry("tool.calendar.find"))

        result = await resolver.validate(_plan([_step("s1", "tool.calendar.search")]))

        assert result.valid is True
        assert result.hil_required is False
        assert len(result.alternatives_applied) == 1
        assert result.alternatives_applied[0].replacement_capability == "tool.calendar.find"

    @pytest.mark.asyncio
    async def test_partial_resolution_still_invalid(self) -> None:
        _, resolver, fabric, _, _ = await _svc()
        fabric.register_capability("tool.calendar.find", _entry("tool.calendar.find"))

        result = await resolver.validate(
            _plan(
                [
                    _step("s1", "tool.calendar.search"),
                    _step("s2", "tool.email.send"),
                ]
            )
        )

        assert result.valid is False
        assert result.hil_required is True
        assert any("tool.email.send" in e for e in result.errors)


class TestCheckCapabilities:
    @pytest.mark.asyncio
    async def test_deduplicates_registry_queries(self) -> None:
        _, resolver, fabric, _, _ = await _svc()
        fabric.register_capability("tool.shared.cap", _entry("tool.shared.cap"))

        checks = await resolver.check_capabilities(
            [
                _step("s1", "tool.shared.cap"),
                _step("s2", "tool.shared.cap"),
                _step("s3", "tool.shared.cap"),
            ]
        )

        assert checks == []
        assert fabric.call_log == []  # only registry paths used here

    @pytest.mark.asyncio
    async def test_missing_capabilities_return_checks(self) -> None:
        _, resolver, fabric, _, _ = await _svc()
        fabric.register_capability("tool.exists", _entry("tool.exists"))
        fabric.register_capability("tool.calendar.find", _entry("tool.calendar.find"))

        checks = await resolver.check_capabilities(
            [
                _step("s1", "tool.exists"),
                _step("s2", "tool.calendar.search"),
            ]
        )

        assert len(checks) == 1
        assert checks[0].step_id == "s2"
        assert checks[0].capability == "tool.calendar.search"
        assert checks[0].available is False
        assert "tool.calendar.find" in checks[0].alternatives


class TestTimeBudget:
    @pytest.mark.asyncio
    async def test_time_pressure_when_over_budget(self) -> None:
        _, resolver, fabric, _, _ = await _svc()
        fabric.register_capability("tool.a", _entry("tool.a"))

        result = await resolver.validate(
            _plan([_step("s1", "tool.a")], estimated_duration_ms=HIGH_TIER_TIME_BUDGET_MS + 1)
        )

        assert result.time_pressure is True
        assert any("time budget" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_exact_budget_is_not_pressure(self) -> None:
        _, resolver, fabric, _, _ = await _svc()
        fabric.register_capability("tool.a", _entry("tool.a"))

        result = await resolver.validate(
            _plan([_step("s1", "tool.a")], estimated_duration_ms=HIGH_TIER_TIME_BUDGET_MS)
        )

        assert result.time_pressure is False


class TestFindAlternatives:
    @pytest.mark.asyncio
    async def test_same_category_candidates_filtered_by_safety(self) -> None:
        _, resolver, fabric, _, _ = await _svc()
        fabric.register_capability(
            "tool.calendar.find", _entry("tool.calendar.find", safety_band_min="GREEN")
        )
        fabric.register_capability(
            "tool.calendar.list", _entry("tool.calendar.list", safety_band_min="AMBER")
        )
        fabric.register_capability(
            "tool.email.send", _entry("tool.email.send", safety_band_min="GREEN")
        )

        alts = await resolver.find_alternatives(
            "tool.calendar.search",
            _step("s1", "tool.calendar.search", safety_band_min="GREEN"),
        )

        ids = {a.capability_id for a in alts}
        assert "tool.calendar.find" in ids
        assert "tool.calendar.list" not in ids  # less strict than GREEN
        assert "tool.email.send" not in ids  # different category

    @pytest.mark.asyncio
    async def test_returns_top_scored_sorted(self) -> None:
        _, resolver, fabric, _, _ = await _svc()
        for name in [
            "tool.cal.search_v2",
            "tool.cal.search_plus",
            "tool.cal.lookup",
            "tool.cal.x",
        ]:
            fabric.register_capability(name, _entry(name))

        alts = await resolver.find_alternatives("tool.cal.search", _step("s1", "tool.cal.search"))

        assert len(alts) <= 3
        for i in range(len(alts) - 1):
            assert alts[i].score >= alts[i + 1].score


class TestResolveIteratively:
    @pytest.mark.asyncio
    async def test_empty_checks_resolves_immediately(self) -> None:
        _, resolver, _, _, _ = await _svc()
        result = await resolver.resolve_iteratively(_plan([_step("s1", "cap.a")]), [])
        assert result.resolved is True
        assert result.cycles_used == 0

    @pytest.mark.asyncio
    async def test_substitutes_all_steps_sharing_missing_capability(self) -> None:
        _, resolver, fabric, _, _ = await _svc()
        fabric.register_capability("tool.cal.find", _entry("tool.cal.find"))

        plan = _plan(
            [
                _step("s1", "tool.cal.search"),
                _step("s2", "tool.cal.search"),
            ]
        )
        checks = [
            CapabilityCheck(step_id="s1", capability="tool.cal.search", available=False),
            CapabilityCheck(step_id="s2", capability="tool.cal.search", available=False),
        ]

        rr = await resolver.resolve_iteratively(plan, checks)

        assert rr.resolved is True
        assert rr.modified_plan is not None
        assert all(s.capability == "tool.cal.find" for s in rr.modified_plan.steps)
        assert len(rr.alternatives_applied) == 2


class TestHILFallback:
    @pytest.mark.asyncio
    async def test_trigger_hil_fallback_returns_timed_out_when_no_hil_port(self) -> None:
        """Standalone factory wires _NullHILAdapter; trigger returns timed_out abort."""
        _, resolver, _, _, _ = await _svc()
        unresolved = [CapabilityCheck(step_id="s1", capability="tool.x", available=False)]
        plan = _plan([_step("s1", "tool.x")], trace_id="trace-hil")

        response = await resolver.trigger_hil_fallback(unresolved, plan)

        assert isinstance(response, OverrideResponse)
        assert response.timed_out is True


class TestHelpers:
    def test_derive_category(self) -> None:
        assert _derive_category("tool.calendar.search") == "tool.calendar"
        assert _derive_category("agent.summarize") == "agent"
        assert _derive_category("single") == "single"

    def test_safety_rank(self) -> None:
        assert _safety_band_rank("GREEN") == 1
        assert _safety_band_rank("AMBER") == 2
        assert _safety_band_rank("RED") == 3
        assert _safety_band_rank("unknown") == 999

    def test_name_similarity_bounds(self) -> None:
        assert _name_similarity("a", "a") == 1.0
        assert _name_similarity("", "") == 1.0
        assert _name_similarity("a", "") == 0.0
        assert 0.0 < _name_similarity("tool.cal.search", "tool.cal.find") < 1.0

    def test_format_constraint_question(self) -> None:
        text = format_constraint_question(
            [
                CapabilityCheck(
                    step_id="s1", capability="cap.a", available=False, alternatives=["cap.b"]
                )
            ]
        )
        assert "cap.a" in text
        assert "cap.b" in text
        assert "How would you like to proceed?" in text

    def test_build_options(self) -> None:
        opts = build_options(
            [
                CapabilityCheck(
                    step_id="s1", capability="cap.a", available=False, alternatives=["cap.b"]
                )
            ]
        )
        assert opts[0] == "Skip step 's1'"
        assert "cap.b" in opts[1]
        assert opts[-1] == "Cancel plan"
