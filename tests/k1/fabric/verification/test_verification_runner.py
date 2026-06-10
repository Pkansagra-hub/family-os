"""GAP-P1-006 — Tests for VerificationPlanRunner (Epic 4.2).

The runner reads its binding/observation via Protocol ports; tests supply
lightweight fakes that structurally satisfy ``BindingLike`` /
``ObservationLike``, plus a fake ``NativeReadbackPort``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from k1.fabric.constitution.loader import ConstitutionLoader
from k1.fabric.constitution.schema import (
    ConstitutionArtifact,
    VerificationRequirement,
)
from k1.fabric.stores.global_projection_store import (
    CapabilityRecord,
    ConnectorRecord,
    GlobalProjectionStore,
)
from k1.fabric.verification.runner import (
    ReadbackContext,
    ReadbackUnavailableError,
    VerificationPlanRunner,
)

# ──────────────────────────────────────────────────────────────────────
# Test doubles
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FakeBinding:
    binding_id: str = "bind-1"
    capability_name: str = "tool.execute.family.calendar.create"
    connector_id: str = "family.calendar"
    resource_id: str = "cal-1"
    verifier_ref: str | None = None


@dataclass(frozen=True)
class FakeObservation:
    invocation_id: str = "inv-1"
    structured_result: dict[str, Any] = field(default_factory=dict)


class FakeReadbackResult:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def data(self) -> dict[str, Any]:
        return self._data


class FakeProvider:
    """Fake NativeReadbackPort."""

    def __init__(
        self,
        data: dict[str, Any] | None = None,
        *,
        raise_unavailable: bool = False,
    ) -> None:
        self._data = data or {}
        self._raise = raise_unavailable
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def dispatch(
        self,
        capability_name: str,
        params: dict[str, Any],
        context: ReadbackContext,
    ) -> FakeReadbackResult:
        self.calls.append((capability_name, params))
        if self._raise:
            raise ReadbackUnavailableError(capability_name)
        return FakeReadbackResult(self._data)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def store() -> GlobalProjectionStore:
    s = GlobalProjectionStore(db_path=":memory:")
    s.open()
    s.upsert_connector(
        ConnectorRecord(
            connector_id="family.calendar",
            label="Calendar",
            connector_type="native",
            provider_type="LOCAL",
            version="1.0.0",
            admission_verdict="admitted",
            registration_type="static",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
        )
    )
    # Read capability used for read-after-write readback.
    s.upsert_capability(
        CapabilityRecord(
            capability_name="tool.read.family.calendar.get",
            connector_id="family.calendar",
            invocation_mode="read",
            action_name="get",
            effect="read",
            resource_kind="calendar_event",
            description="get calendar_event",
            created_at="2026-01-01T00:00:00",
        )
    )
    # Write capability with an output schema (for output_schema verification).
    s.upsert_capability(
        CapabilityRecord(
            capability_name="tool.execute.family.calendar.create",
            connector_id="family.calendar",
            invocation_mode="execute",
            action_name="create",
            effect="write",
            resource_kind="calendar_event",
            description="create calendar_event",
            created_at="2026-01-01T00:00:00",
            contract_json={"output_schema": {"required": ["event_id", "status"]}},
        )
    )
    return s


@pytest.fixture
def loader(store: GlobalProjectionStore) -> ConstitutionLoader:
    return ConstitutionLoader(store)


def _raw_constitution(method: str) -> ConstitutionArtifact:
    return ConstitutionArtifact(
        connector_id="family.calendar",
        constitution_id="family.calendar.v1",
        schema_version="1.0.0",
        execution_phases=["read", "mutate"],
        verification_requirements=[VerificationRequirement(method=method)],
    )


# ══════════════════════════════════════════════════════════════════════
# TestBuildPlan
# ══════════════════════════════════════════════════════════════════════


class TestBuildPlan:
    def test_read_after_write_plan(self, store, loader):
        runner = VerificationPlanRunner(FakeProvider(), store, loader)
        binding = FakeBinding()
        observation = FakeObservation(structured_result={"event_id": "evt-9", "title": "Dentist"})
        plan = runner.build_plan(binding, observation, _raw_constitution("read_after_write"))
        assert plan.verifier_method == "read_after_write"
        assert plan.readback_capability_ref == "tool.read.family.calendar.get"
        assert plan.readback_params["event_id"] == "evt-9"
        assert plan.readback_params["resource_id"] == "cal-1"

    def test_output_schema_plan(self, store, loader):
        runner = VerificationPlanRunner(FakeProvider(), store, loader)
        binding = FakeBinding()
        observation = FakeObservation(structured_result={"event_id": "evt-9", "status": "created"})
        plan = runner.build_plan(binding, observation, _raw_constitution("output_schema"))
        assert plan.verifier_method == "output_schema"
        assert plan.expected_resource_state["required_output_fields"] == ["event_id", "status"]

    def test_no_constitution_none_available(self, store, loader):
        runner = VerificationPlanRunner(FakeProvider(), store, loader)
        binding = FakeBinding()
        observation = FakeObservation(structured_result={"event_id": "evt-9"})
        plan = runner.build_plan(binding, observation, None)
        assert plan.verifier_method == "none_available"


# ══════════════════════════════════════════════════════════════════════
# TestReadAfterWriteSuccess
# ══════════════════════════════════════════════════════════════════════


class TestReadAfterWriteSuccess:
    def test_verified_when_readback_matches(self, store, loader):
        provider = FakeProvider(data={"found": True, "event_id": "evt-9", "title": "Dentist"})
        runner = VerificationPlanRunner(provider, store, loader)
        binding = FakeBinding()
        observation = FakeObservation(structured_result={"event_id": "evt-9", "title": "Dentist"})
        plan = runner.build_plan(binding, observation, _raw_constitution("read_after_write"))
        result = runner.run(plan)
        assert result.status == "verified"
        assert result.mismatch_summary is None
        assert provider.calls  # readback was dispatched

    def test_staleness_inconclusive(self, store, loader):
        provider = FakeProvider(data={"found": True, "event_id": "evt-9", "title": "Dentist"})
        runner = VerificationPlanRunner(provider, store, loader)
        binding = FakeBinding()
        observation = FakeObservation(structured_result={"event_id": "evt-9", "title": "Dentist"})
        plan = runner.build_plan(
            binding, observation, _raw_constitution("read_after_write"), max_staleness_ms=0
        )
        result = runner.run(plan)
        assert result.status == "inconclusive"


# ══════════════════════════════════════════════════════════════════════
# TestMismatch
# ══════════════════════════════════════════════════════════════════════


class TestMismatch:
    def test_failed_when_title_differs(self, store, loader):
        provider = FakeProvider(data={"found": True, "event_id": "evt-9", "title": "WRONG"})
        runner = VerificationPlanRunner(provider, store, loader)
        binding = FakeBinding()
        observation = FakeObservation(structured_result={"event_id": "evt-9", "title": "Dentist"})
        plan = runner.build_plan(binding, observation, _raw_constitution("read_after_write"))
        result = runner.run(plan)
        assert result.status == "failed"
        assert "title" in (result.mismatch_summary or "")

    def test_failed_when_not_found(self, store, loader):
        provider = FakeProvider(data={"found": False})
        runner = VerificationPlanRunner(provider, store, loader)
        binding = FakeBinding()
        observation = FakeObservation(structured_result={"event_id": "evt-9", "title": "Dentist"})
        plan = runner.build_plan(binding, observation, _raw_constitution("read_after_write"))
        result = runner.run(plan)
        assert result.status == "failed"


# ══════════════════════════════════════════════════════════════════════
# TestProviderUnavailable
# ══════════════════════════════════════════════════════════════════════


class TestProviderUnavailable:
    def test_unavailable_when_provider_raises(self, store, loader):
        provider = FakeProvider(raise_unavailable=True)
        runner = VerificationPlanRunner(provider, store, loader)
        binding = FakeBinding()
        observation = FakeObservation(structured_result={"event_id": "evt-9", "title": "Dentist"})
        plan = runner.build_plan(binding, observation, _raw_constitution("read_after_write"))
        result = runner.run(plan)
        assert result.status == "unavailable"
        assert result.recovery_directive == {"action": "block_and_submit"}


# ══════════════════════════════════════════════════════════════════════
# TestOutputSchema
# ══════════════════════════════════════════════════════════════════════


class TestOutputSchema:
    def test_verified_when_required_fields_present(self, store, loader):
        runner = VerificationPlanRunner(FakeProvider(), store, loader)
        binding = FakeBinding()
        observation = FakeObservation(structured_result={"event_id": "evt-9", "status": "created"})
        plan = runner.build_plan(binding, observation, _raw_constitution("output_schema"))
        result = runner.run(plan, observation)
        assert result.status == "verified"

    def test_failed_when_required_field_missing(self, store, loader):
        runner = VerificationPlanRunner(FakeProvider(), store, loader)
        binding = FakeBinding()
        observation = FakeObservation(structured_result={"event_id": "evt-9"})  # no status
        plan = runner.build_plan(binding, observation, _raw_constitution("output_schema"))
        result = runner.run(plan, observation)
        assert result.status == "failed"
        assert "status" in (result.mismatch_summary or "")


# ══════════════════════════════════════════════════════════════════════
# TestDegradedCompletion
# ══════════════════════════════════════════════════════════════════════


class TestDegradedCompletion:
    def test_degraded_verified_with_policy(self, store, loader):
        runner = VerificationPlanRunner(FakeProvider(), store, loader)
        binding = FakeBinding()
        observation = FakeObservation(structured_result={"event_id": "evt-9"})
        # No verification requirement → none_available; degraded policy set.
        plan = runner.build_plan(
            binding, observation, None, degraded_completion_policy="best_effort"
        )
        result = runner.run(plan)
        assert result.status == "degraded_verified"
        assert "best_effort" in (result.degraded_reason or "")


# ══════════════════════════════════════════════════════════════════════
# TestNoConstitution
# ══════════════════════════════════════════════════════════════════════


class TestNoConstitution:
    def test_skipped_by_policy_when_no_requirement_and_no_policy(self, store, loader):
        runner = VerificationPlanRunner(FakeProvider(), store, loader)
        binding = FakeBinding()
        observation = FakeObservation(structured_result={"event_id": "evt-9"})
        plan = runner.build_plan(binding, observation, None)
        result = runner.run(plan)
        assert result.status == "skipped_by_policy"
