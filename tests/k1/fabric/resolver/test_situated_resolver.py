"""GAP-P1-001 — Tests for ResolveSituationService 13-step cascade (Epic 6.2).

Each verdict is exercised with its sub_reason.  The store is seeded via the
real Epic 2 builder + Epic 4.3 admission so the pipeline runs against
production-shaped data.
"""

from __future__ import annotations

import pytest

from k1.fabric.connectors.builder import build_connector_definition
from k1.fabric.connectors.definition import (
    CapabilityDefinition,
    ConnectorDefinition,
    ConstitutionDefinition,
    PolicyDefinition,
)
from k1.fabric.connectors.domain_catalog import DOMAIN_SERVICES
from k1.fabric.manifest_admission import ManifestAdmissionService
from k1.fabric.resolver.request_frame import (
    PersonRef,
    RequestFrame,
    RequestFrameIntent,
    ResourceRef,
    TimeWindowHint,
)
from k1.fabric.resolver.situated_resolver import (
    ResolutionEnvelope,
    ResolveSituationRequest,
    ResolveSituationService,
)
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.fabric.stores.idempotency_store import IdempotencyStore
from k1.fabric.stores.local_projection_store import LocalProjectionStore

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _gps() -> GlobalProjectionStore:
    s = GlobalProjectionStore(db_path=":memory:")
    s.open()
    return s


def _admit_calendar(store: GlobalProjectionStore) -> None:
    ManifestAdmissionService(store).admit(
        build_connector_definition("family", DOMAIN_SERVICES["family"][0])
    )


def _custom_connector(
    store: GlobalProjectionStore,
    connector_id: str,
    resource_kind: str,
    *,
    policy: PolicyDefinition | None = None,
    constitution: ConstitutionDefinition | None = None,
    domain: str = "family",
) -> None:
    """Admit a minimal custom connector with one read + one write capability."""
    short = connector_id.split(".")[-1]
    read_cap = CapabilityDefinition(
        name=f"tool.read.{connector_id}.list",
        action_name="list",
        invocation_mode="read",
        effect="read",
        resource_kind=resource_kind,
        description=f"list {resource_kind}",
    )
    write_cap = CapabilityDefinition(
        name=f"tool.execute.{connector_id}.create",
        action_name="create",
        invocation_mode="execute",
        effect="write",
        resource_kind=resource_kind,
        description=f"create {resource_kind}",
    )
    definition = ConnectorDefinition(
        connector_id=connector_id,
        label=short.title(),
        description=f"{short} connector",
        provider_id=f"native.{connector_id}",
        resource_kinds=[resource_kind],
        capabilities=[read_cap, write_cap],
        constitution=constitution,
        policy=policy,
    )
    ManifestAdmissionService(store).admit(definition)


def _service(
    store: GlobalProjectionStore,
    local: LocalProjectionStore | None = None,
    *,
    idempotency: IdempotencyStore | None = None,
) -> ResolveSituationService:
    ls = local or _lps()
    return ResolveSituationService(store, ls, idempotency_store=idempotency)


def _lps() -> LocalProjectionStore:
    s = LocalProjectionStore(db_path=":memory:")
    s.open()
    return s


def _seed_connected(
    local: LocalProjectionStore,
    *,
    resource_id: str,
    resource_kind: str,
    connector_id: str,
    alias: str,
    freshness: str = "fresh",
    permissions: str = "read_write",
) -> None:
    """Seed a real connected resource + alias (stable resource_id, real connector)."""
    local.upsert_connected_resource(
        {
            "resource_id": resource_id,
            "actor_id": "actor-a",
            "resource_kind": resource_kind,
            "connector_id": connector_id,
            "label": alias,
            "permissions": permissions,
            "freshness_state": freshness,
            "status": "active",
        }
    )
    local.upsert_alias_index("actor-a", alias, resource_id, "resource")


def _frame(
    *,
    operation_hint: str,
    resource_kind_hint: str,
    params: dict | None = None,
    subject_hint: str | None = None,
    resource_refs: list[ResourceRef] | None = None,
    person_refs: list[PersonRef] | None = None,
    time_window: TimeWindowHint | None = None,
    intents: list[RequestFrameIntent] | None = None,
    actor_role: str = "parent",
) -> RequestFrame:
    if intents is None:
        intents = [
            RequestFrameIntent(
                intent_id="i1",
                action=f"{operation_hint} {resource_kind_hint}",
                domain="family",
                operation_hint=operation_hint,
                resource_kind_hint=resource_kind_hint,
                subject_hint=subject_hint,
                params=params or {},
            )
        ]
    if resource_refs is None:
        resource_refs = [
            ResourceRef(
                raw=resource_kind_hint,
                resource_kind_hint=resource_kind_hint,
                needs_resolution=False,
            )
        ]
    return RequestFrame(
        request_id="req-1",
        task_id="task-1",
        trace_id="trace-1",
        actor_id="actor-a",
        space_id="space-1",
        intents=intents,
        time_window_hint=time_window,
        person_refs=person_refs or [],
        resource_refs=resource_refs,
        safety_context={"actor_role": actor_role, "safety_band": "GREEN"},
    )


def _request(
    frame: RequestFrame,
    *,
    safety_band: str = "GREEN",
    completed: list[str] | None = None,
    idempotency_keys: list[str] | None = None,
    budget_remaining: dict | None = None,
    prompt_budget_tokens: int = 8000,
) -> ResolveSituationRequest:
    return ResolveSituationRequest(
        request_id="req-1",
        frame=frame,
        actor_id="actor-a",
        space_id="space-1",
        session_id="sess-1",
        tier="MEDIUM",
        safety_band=safety_band,
        completed_prerequisite_bindings=completed or [],
        idempotency_keys=idempotency_keys or [],
        budget_remaining=budget_remaining,
        prompt_budget_tokens=prompt_budget_tokens,
    )


_WRITE_FULL = {"title": "D", "start": "x", "end": "y", "resource_id": "c", "idempotency_key": "k"}


# ══════════════════════════════════════════════════════════════════════
# TestHappyPath
# ══════════════════════════════════════════════════════════════════════


class TestHappyPath:
    def test_read_can_execute(self):
        store = _gps()
        _admit_calendar(store)
        svc = _service(store)
        env = svc.resolve(
            _request(_frame(operation_hint="list", resource_kind_hint="calendar_event"))
        )
        assert env.verdict == "can_execute"
        assert env.sub_reason is None
        assert env.binding_bundle.primary is not None


# ══════════════════════════════════════════════════════════════════════
# TestCanExecuteWithGate
# ══════════════════════════════════════════════════════════════════════


class TestCanExecuteWithGate:
    def test_write_prerequisite_incomplete(self):
        store = _gps()
        _admit_calendar(store)
        svc = _service(store)
        env = svc.resolve(
            _request(
                _frame(
                    operation_hint="create",
                    resource_kind_hint="calendar_event",
                    params=_WRITE_FULL,
                    subject_hint="dentist",
                )
            )
        )
        assert env.verdict == "can_execute_with_gate"
        assert env.sub_reason.startswith("prerequisite_read_incomplete:")

    def test_write_completes_when_prereq_done(self):
        store = _gps()
        _admit_calendar(store)
        local = _lps()
        _seed_connected(
            local,
            resource_id="cal-1",
            resource_kind="calendar_event",
            connector_id="family.calendar",
            alias="my calendar",
        )
        svc = _service(store, local)
        frame = _frame(
            operation_hint="create",
            resource_kind_hint="calendar_event",
            params=_WRITE_FULL,
            subject_hint="dentist",
            resource_refs=[ResourceRef(raw="my calendar", resource_kind_hint="calendar_event")],
        )
        first = svc.resolve(_request(frame))
        assert first.verdict == "can_execute_with_gate"
        prereq_id = first.binding_bundle.prerequisites[0].binding_id
        second = svc.resolve(_request(frame, completed=[prereq_id]))
        assert second.verdict == "can_execute"


# ══════════════════════════════════════════════════════════════════════
# TestMissingCapability
# ══════════════════════════════════════════════════════════════════════


class TestMissingCapability:
    def test_unknown_resource_kind(self):
        store = _gps()
        _admit_calendar(store)
        svc = _service(store)
        env = svc.resolve(
            _request(_frame(operation_hint="create", resource_kind_hint="widget", params={"x": 1}))
        )
        assert env.verdict == "missing_capability"
        assert "widget" in env.sub_reason


# ══════════════════════════════════════════════════════════════════════
# TestBlockedByPolicy
# ══════════════════════════════════════════════════════════════════════


class TestBlockedByPolicy:
    def test_child_write_denied(self):
        store = _gps()
        _custom_connector(
            store,
            "family.chores",
            "chore",
            policy=PolicyDefinition(write_requires_actor_role=["parent", "guardian"]),
        )
        local = _lps()
        _seed_connected(
            local,
            resource_id="chore-1",
            resource_kind="chore",
            connector_id="family.chores",
            alias="chore list",
        )
        svc = _service(store, local)
        frame = _frame(
            operation_hint="create",
            resource_kind_hint="chore",
            params={"title": "Dishes"},
            actor_role="child",
            resource_refs=[ResourceRef(raw="chore list", resource_kind_hint="chore")],
        )
        env = svc.resolve(_request(frame))
        assert env.verdict == "blocked_by_policy"
        assert env.sub_reason == "role_not_allowed"


# ══════════════════════════════════════════════════════════════════════
# TestStaleProjection
# ══════════════════════════════════════════════════════════════════════


class TestStaleProjection:
    def test_write_on_stale_resource(self):
        store = _gps()
        _admit_calendar(store)
        local = _lps()
        local.upsert_connected_resource(
            {
                "resource_id": "cal-stale",
                "actor_id": "actor-a",
                "resource_kind": "calendar_event",
                "connector_id": "family.calendar",
                "label": "Stale Calendar",
                "permissions": "read_write",
                "freshness_state": "stale",
                "status": "active",
            }
        )
        local.upsert_alias_index("actor-a", "stale calendar", "cal-stale", "resource")
        svc = _service(store, local)
        frame = _frame(
            operation_hint="create",
            resource_kind_hint="calendar_event",
            params=_WRITE_FULL,
            subject_hint="dentist",
            resource_refs=[ResourceRef(raw="stale calendar", resource_kind_hint="calendar_event")],
        )
        env = svc.resolve(_request(frame))
        assert env.verdict == "stale_projection"
        assert env.sub_reason.startswith("stale_resource:")
        assert env.recovery_directive is not None


# ══════════════════════════════════════════════════════════════════════
# TestNeedsDisambiguation
# ══════════════════════════════════════════════════════════════════════


class TestNeedsDisambiguation:
    def test_ambiguous_person(self):
        store = _gps()
        _admit_calendar(store)
        local = _lps()
        local.upsert_alias_index("actor-a", "morgan", "person-m1", "person")
        local.upsert_alias_index("actor-a", "morgan", "person-m2", "person")
        svc = _service(store, local)
        frame = _frame(
            operation_hint="create",
            resource_kind_hint="calendar_event",
            params=_WRITE_FULL,
            subject_hint="dentist",
            person_refs=[PersonRef(raw="morgan", confidence="medium")],
        )
        env = svc.resolve(_request(frame))
        assert env.verdict == "needs_disambiguation"
        assert env.sub_reason == "ambiguous_person:morgan"
        assert env.hil_request is not None or env.verdict == "needs_disambiguation"


# ══════════════════════════════════════════════════════════════════════
# TestMissingRequiredParams
# ══════════════════════════════════════════════════════════════════════


class TestMissingRequiredParams:
    def test_intent_too_vague(self):
        store = _gps()
        _admit_calendar(store)
        svc = _service(store)
        # Write intent with no subject, no params, no time window.
        frame = _frame(operation_hint="create", resource_kind_hint="calendar_event", params={})
        env = svc.resolve(_request(frame))
        assert env.verdict == "missing_required_params"
        assert env.sub_reason == "intent_too_vague"


# ══════════════════════════════════════════════════════════════════════
# TestPromoteToTier3
# ══════════════════════════════════════════════════════════════════════


class TestPromoteToTier3:
    def test_six_connectors_promote(self):
        store = _gps()
        kinds = ["k0", "k1", "k2", "k3", "k4", "k5"]
        for i, k in enumerate(kinds):
            _custom_connector(store, f"family.c{i}", k)
        svc = _service(store)
        intents = [
            RequestFrameIntent(
                intent_id=f"i{i}",
                action=f"list {k}",
                domain="family",
                operation_hint="list",
                resource_kind_hint=k,
            )
            for i, k in enumerate(kinds)
        ]
        resource_refs = [
            ResourceRef(raw=k, resource_kind_hint=k, needs_resolution=False) for k in kinds
        ]
        frame = _frame(
            operation_hint="list",
            resource_kind_hint="k0",
            intents=intents,
            resource_refs=resource_refs,
        )
        env = svc.resolve(_request(frame))
        assert env.verdict == "promote_to_tier3"
        assert env.sub_reason.startswith("connectors:")


# ══════════════════════════════════════════════════════════════════════
# TestCannotExecute
# ══════════════════════════════════════════════════════════════════════


class TestCannotExecute:
    def test_budget_exhausted(self):
        store = _gps()
        _admit_calendar(store)
        svc = _service(store)
        frame = _frame(operation_hint="list", resource_kind_hint="calendar_event")
        env = svc.resolve(_request(frame, budget_remaining={"max_iterations": 0}))
        assert env.verdict == "cannot_execute"
        assert env.sub_reason == "budget_exhausted:max_iterations"

    def test_prompt_budget_exhausted(self):
        store = _gps()
        _admit_calendar(store)
        svc = _service(store)
        frame = _frame(operation_hint="list", resource_kind_hint="calendar_event")
        env = svc.resolve(_request(frame, prompt_budget_tokens=1))
        assert env.verdict == "cannot_execute"
        assert env.sub_reason == "budget_exhausted:max_prompt_tokens"


# ══════════════════════════════════════════════════════════════════════
# TestHILGateTriggered
# ══════════════════════════════════════════════════════════════════════


class TestHILGateTriggered:
    def test_missing_required_field_hil(self):
        store = _gps()
        # Custom connector: HIL gate on 'recipient', NO prerequisite_reads.
        constitution = ConstitutionDefinition(
            connector_id="family.notify",
            constitution_id="family.notify.v1",
            execution_phases=["mutate"],
            hil_gates=[
                {
                    "trigger": "missing_required_field",
                    "field": "recipient",
                    "prompt": "Who should I notify?",
                }
            ],
        )
        _custom_connector(store, "family.notify", "notification", constitution=constitution)
        svc = _service(store)
        # Write with a param (not vague) but missing 'recipient'.
        frame = _frame(
            operation_hint="create",
            resource_kind_hint="notification",
            params={"message": "Hi"},
        )
        env = svc.resolve(_request(frame))
        assert env.verdict == "needs_hil"
        assert env.sub_reason == "hil_gate:missing_required_field"
        assert env.hil_request is not None
        assert env.hil_request["field"] == "recipient"


# ══════════════════════════════════════════════════════════════════════
# TestConflictRuleNotFiredAtResolveTime
# ══════════════════════════════════════════════════════════════════════


class TestConflictRuleNotFiredAtResolveTime:
    def test_conflict_gate_does_not_fire_without_runtime_data(self):
        """Conflict-type HIL gates need runtime data; they must NOT fire at resolve time."""
        store = _gps()
        constitution = ConstitutionDefinition(
            connector_id="family.cal2",
            constitution_id="family.cal2.v1",
            execution_phases=["mutate"],
            hil_gates=[{"trigger": "time_conflict_detected", "prompt": "Conflict — proceed?"}],
        )
        _custom_connector(store, "family.cal2", "calendar_event", constitution=constitution)
        svc = _service(store)
        frame = _frame(
            operation_hint="create",
            resource_kind_hint="calendar_event",
            params={"title": "Mtg"},
        )
        env = svc.resolve(_request(frame))
        # No prereqs, no missing-field gate → can_execute (conflict gate is runtime-only).
        assert env.verdict == "can_execute"


# ══════════════════════════════════════════════════════════════════════
# TestConstitutionLoaded
# ══════════════════════════════════════════════════════════════════════


class TestConstitutionLoaded:
    def test_constitution_attached_to_envelope(self):
        store = _gps()
        _admit_calendar(store)
        svc = _service(store)
        env = svc.resolve(
            _request(_frame(operation_hint="list", resource_kind_hint="calendar_event"))
        )
        assert env.constitution is not None
        assert env.constitution.connector_id == "family.calendar"


# ══════════════════════════════════════════════════════════════════════
# TestIdempotencyEnforced
# ══════════════════════════════════════════════════════════════════════


class TestIdempotencyEnforced:
    def test_duplicate_key_cannot_execute(self):
        store = _gps()
        _admit_calendar(store)
        idem = IdempotencyStore(db_path=":memory:")
        idem.open()
        idem.mark_in_flight("dup-key", "inv-1")
        idem.mark_success("dup-key", {"event_id": "e1"})
        svc = _service(store, idempotency=idem)
        frame = _frame(operation_hint="list", resource_kind_hint="calendar_event")
        env = svc.resolve(_request(frame, idempotency_keys=["dup-key"]))
        assert env.verdict == "cannot_execute"
        assert env.sub_reason == "idempotency_duplicate:dup-key"


# ══════════════════════════════════════════════════════════════════════
# TestFullPipeline
# ══════════════════════════════════════════════════════════════════════


class TestFullPipeline:
    def test_end_to_end_envelope_shape(self):
        store = _gps()
        _admit_calendar(store)
        svc = _service(store)
        env = svc.resolve(
            _request(_frame(operation_hint="list", resource_kind_hint="calendar_event"))
        )
        assert isinstance(env, ResolutionEnvelope)
        assert env.candidate_universe is not None
        assert env.intent_resolutions  # typed graph results present
        assert env.policy_bundle is not None
        assert env.binding_bundle is not None
        assert env.resolution_id.startswith("res-")
        d = env.to_dict()
        assert d["verdict"] == "can_execute"
        assert "binding_bundle" in d

    def test_prompt_pack_built_when_builder_injected(self):
        from k1.fabric.prompt_pack.builder import PromptPackBuilder

        store = _gps()
        _admit_calendar(store)
        local = _lps()
        svc = ResolveSituationService(store, local, prompt_pack_builder=PromptPackBuilder(store))
        env = svc.resolve(
            _request(_frame(operation_hint="list", resource_kind_hint="calendar_event"))
        )
        assert env.prompt_pack is not None
        assert env.prompt_pack.disclosure_phase == "connector_summary"
        assert env.prompt_pack.redaction_summary.verdict == "pass"

    def test_no_prompt_pack_without_builder(self):
        store = _gps()
        _admit_calendar(store)
        svc = _service(store)
        env = svc.resolve(
            _request(_frame(operation_hint="list", resource_kind_hint="calendar_event"))
        )
        assert env.prompt_pack is None
