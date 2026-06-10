"""GAP-P1-009 — Negative-path tests for ResolveSituationService (Epic 6.2).

Focused on error verdicts carrying actionable sub_reasons.
"""

from __future__ import annotations

from k1.fabric.connectors.builder import build_connector_definition
from k1.fabric.connectors.domain_catalog import DOMAIN_SERVICES
from k1.fabric.manifest_admission import ManifestAdmissionService
from k1.fabric.resolver.request_frame import (
    RequestFrame,
    RequestFrameIntent,
    ResourceRef,
)
from k1.fabric.resolver.situated_resolver import (
    ResolveSituationRequest,
    ResolveSituationService,
)
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.fabric.stores.local_projection_store import LocalProjectionStore

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _setup() -> ResolveSituationService:
    store = GlobalProjectionStore(db_path=":memory:")
    store.open()
    ManifestAdmissionService(store).admit(
        build_connector_definition("family", DOMAIN_SERVICES["family"][0])
    )
    local = LocalProjectionStore(db_path=":memory:")
    local.open()
    return ResolveSituationService(store, local)


def _frame(
    *,
    operation_hint: str,
    resource_kind_hint: str,
    params: dict | None = None,
    subject_hint: str | None = None,
    resource_refs: list[ResourceRef] | None = None,
) -> RequestFrame:
    return RequestFrame(
        request_id="req-1",
        task_id="task-1",
        trace_id="trace-1",
        actor_id="actor-a",
        space_id="space-1",
        intents=[
            RequestFrameIntent(
                intent_id="i1",
                action=f"{operation_hint} {resource_kind_hint}",
                domain="family",
                operation_hint=operation_hint,
                resource_kind_hint=resource_kind_hint,
                subject_hint=subject_hint,
                params=params or {},
            )
        ],
        resource_refs=(
            resource_refs
            if resource_refs is not None
            else [
                ResourceRef(
                    raw=resource_kind_hint,
                    resource_kind_hint=resource_kind_hint,
                    needs_resolution=False,
                )
            ]
        ),
        safety_context={"actor_role": "parent", "safety_band": "GREEN"},
    )


def _request(frame: RequestFrame, **kw) -> ResolveSituationRequest:
    return ResolveSituationRequest(
        request_id="req-1",
        frame=frame,
        actor_id="actor-a",
        space_id="space-1",
        session_id="sess-1",
        tier="MEDIUM",
        safety_band="GREEN",
        **kw,
    )


# ══════════════════════════════════════════════════════════════════════
# Negative paths
# ══════════════════════════════════════════════════════════════════════


class TestMissingCapabilityError:
    def test_unknown_resource_kind_includes_kind(self):
        svc = _setup()
        env = svc.resolve(
            _request(
                _frame(operation_hint="create", resource_kind_hint="spaceship", params={"x": 1})
            )
        )
        assert env.verdict == "missing_capability"
        assert "spaceship" in env.sub_reason


class TestResourceNotFound:
    def test_unresolved_resource_ref(self):
        svc = _setup()
        frame = _frame(
            operation_hint="list",
            resource_kind_hint="calendar_event",
            resource_refs=[
                ResourceRef(raw="nonexistent calendar", resource_kind_hint="calendar_event")
            ],
        )
        env = svc.resolve(_request(frame))
        assert env.verdict == "missing_required_params"
        assert env.sub_reason.startswith("resource_not_found:")


class TestIncompleteWorldProjection:
    def test_partial_completeness_recorded(self):
        svc = _setup()
        frame = _frame(
            operation_hint="list",
            resource_kind_hint="calendar_event",
            resource_refs=[ResourceRef(raw="ghost", resource_kind_hint="calendar_event")],
        )
        env = svc.resolve(_request(frame))
        assert env.candidate_universe.completeness in ("partial", "unknown")


class TestStaleProjectionRefresh:
    def test_stale_write_emits_refresh_directive(self):
        store = GlobalProjectionStore(db_path=":memory:")
        store.open()
        ManifestAdmissionService(store).admit(
            build_connector_definition("family", DOMAIN_SERVICES["family"][0])
        )
        local = LocalProjectionStore(db_path=":memory:")
        local.open()
        local.upsert_connected_resource(
            {
                "resource_id": "cal-stale",
                "actor_id": "actor-a",
                "resource_kind": "calendar_event",
                "connector_id": "family.calendar",
                "label": "Stale",
                "permissions": "read_write",
                "freshness_state": "stale",
                "status": "active",
            }
        )
        local.upsert_alias_index("actor-a", "stale cal", "cal-stale", "resource")
        svc = ResolveSituationService(store, local)
        frame = _frame(
            operation_hint="create",
            resource_kind_hint="calendar_event",
            params={
                "title": "D",
                "start": "x",
                "end": "y",
                "resource_id": "c",
                "idempotency_key": "k",
            },
            subject_hint="dentist",
            resource_refs=[ResourceRef(raw="stale cal", resource_kind_hint="calendar_event")],
        )
        env = svc.resolve(_request(frame))
        assert env.verdict == "stale_projection"
        assert env.recovery_directive is not None
        assert env.recovery_directive["action"] == "refresh_projection"
        assert "cal-stale" in env.recovery_directive["resource_ids"]


class TestBudgetExhausted:
    def test_budget_field_name_in_sub_reason(self):
        svc = _setup()
        frame = _frame(operation_hint="list", resource_kind_hint="calendar_event")
        env = svc.resolve(_request(frame, budget_remaining={"max_fabric_calls": 0}))
        assert env.verdict == "cannot_execute"
        assert env.sub_reason == "budget_exhausted:max_fabric_calls"


class TestIntentTooVague:
    def test_vague_write_missing_required_params(self):
        svc = _setup()
        frame = _frame(operation_hint="create", resource_kind_hint="calendar_event", params={})
        env = svc.resolve(_request(frame))
        assert env.verdict == "missing_required_params"
        assert env.sub_reason == "intent_too_vague"
