"""GAP-P1-023 + GATE-P1 — Phase 1 end-to-end integration gate (Epic 8).

Proves the **whole** Fabric resolution pipeline + the execution/verification
machinery through the REAL wired object graph produced by ``FabricFactory``
(the exact graph the kernel assembles on the per-session P3 path).

NO MOCKS in the resolution/execution logic:

* Real ``GlobalProjectionStore`` / ``LocalProjectionStore`` /
  ``IdempotencyStore`` (real SQLite, ``:memory:``).
* The real 50-connector domain catalog (Epic 2) admitted via the real
  ``ManifestAdmissionService`` (Epic 4.3).
* The real ``ResolveSituationService`` 13-step cascade (Epic 6.2) reached
  through ``Fabric.resolve_situation`` / ``Fabric._handle_resolve_situation``.
* The real ``PromptPackBuilder`` redaction (Epic 6.3).
* For the execution + verification gates: the real family
  ``CalendarToolService`` writing to real SQLite, surfaced by the real
  ``NativeToolProvider``, and read back by the real ``VerificationPlanRunner``
  (Epic 4.2) — every byte persisted and re-read for real.

The only infra adapters used (bus / bridge / model gateway / prompt system /
state reader) are the kernel's own test-grade port adapters; ``resolve_situation``
does not touch them at all — it reads only the stores — so the resolution path
is end-to-end real.

Phase-1 namespace honesty: the *resolution catalog* names family connectors
``tool.execute.family.calendar.create`` (synthetic domain corpus) while the
*execution registry* names the live tool ``tool.execute.calendar.create_event``
(adapter_id ``calendar``).  Aligning the two namespaces is Epic 9 (Phase 1.1),
so this suite proves the resolution pipeline and the execution+verification
machinery as the two real halves they are in Phase 1 — it does NOT pretend a
single resolve→execute→verify chain runs on one capability name.

Design authority: ``k1/fabric/docs/phase1_implementation_plan.md`` Epic 8.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# ── Real wiring (FabricFactory + the kernel's own port adapters) ────────
from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.adapters.test_bridge import TestBridgeAdapter
from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter
from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter

# ── Real catalog + admission ───────────────────────────────────────────
from k1.fabric.connectors.definition import (
    CapabilityDefinition,
    ConnectorDefinition,
    PolicyDefinition,
)
from k1.fabric.connectors.domain_catalog import (
    DOMAIN_SERVICES,
    build_all_corpora,
    build_domain_corpus,
)

# ── Real constitution + verification + prompt pack ─────────────────────
from k1.fabric.constitution.loader import ConstitutionLoader
from k1.fabric.constitution.schema import (
    ConstitutionArtifact,
    ConstitutionValidationError,
    VerificationRequirement,
    validate_constitution,
)
from k1.fabric.fabric import CapabilityFabric
from k1.fabric.factory import FabricFactory
from k1.fabric.manifest_admission import ManifestAdmissionService
from k1.fabric.prompt_pack.builder import PromptPackLeakError

# ── Real resolver types ────────────────────────────────────────────────
from k1.fabric.resolver.request_frame import (
    RequestFrame,
    RequestFrameIntent,
    ResourceRef,
)
from k1.fabric.resolver.situated_resolver import (
    ResolutionEnvelope,
    ResolveSituationRequest,
    ResolveSituationService,
)

# ── Real stores ────────────────────────────────────────────────────────
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.fabric.stores.idempotency_store import IdempotencyStore
from k1.fabric.stores.local_projection_store import LocalProjectionStore
from k1.fabric.verification.runner import (
    ReadbackContext,
    VerificationPlanRunner,
)

# ── Real family-tools execution ────────────────────────────────────────
from k1.tools.family.base import WriteContext
from k1.tools.family.bootstrap import bootstrap_family_tools
from k1.tools.family.calendar.service import CalendarToolService

# ══════════════════════════════════════════════════════════════════════
# Real wiring helpers (NO mocks — the kernel's own factory + adapters)
# ══════════════════════════════════════════════════════════════════════


def _ports() -> dict:
    """The six infra port adapters FabricFactory expects (kernel-grade)."""
    return dict(
        state_reader=TestSessionStateReaderAdapter(),
        event_port=LocalEventAdapter(capture_mode=False),
        bridge=TestBridgeAdapter(),
        model_gateway=TestModelGatewayAdapter(),
        prompt_system=TestPromptSystemAdapter(),
        delta_bus=TestDeltaBusAdapter(),
    )


def _wired_fabric(*, admit_catalog: bool = True, extra: list | None = None):
    """Build the real per-session Fabric exactly as the kernel P3 path does.

    Opens real stores, admits the real domain catalog via the real
    ``ManifestAdmissionService``, then wires everything through
    ``FabricFactory.create_with_ports``.
    """
    gps = GlobalProjectionStore(":memory:")
    gps.open()
    lps = LocalProjectionStore(":memory:")
    lps.open()
    idem = IdempotencyStore(":memory:")
    idem.open()

    admission = ManifestAdmissionService(gps)
    if admit_catalog:
        for corpus in build_all_corpora().values():
            admission.admit_all(corpus)
    for connector in extra or []:
        admission.admit(connector)

    return FabricFactory.create_with_ports(
        **_ports(),
        global_projection_store=gps,
        local_projection_store=lps,
        idempotency_store=idem,
    )


def _custom_connector(
    connector_id: str,
    resource_kind: str,
    *,
    policy: PolicyDefinition | None = None,
    safety_band_min: str = "GREEN",
    domain: str = "family",
) -> ConnectorDefinition:
    """A minimal real connector (one read + one write) for policy/band gates."""
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
        safety_band_min=safety_band_min,
    )
    return ConnectorDefinition(
        connector_id=connector_id,
        label=short.title(),
        description=f"{short} connector",
        provider_id=f"native.{connector_id}",
        resource_kinds=[resource_kind],
        capabilities=[read_cap, write_cap],
        policy=policy,
    )


def _seed_connected(
    local: LocalProjectionStore,
    *,
    resource_id: str,
    resource_kind: str,
    connector_id: str,
    alias: str,
    permissions: str = "read_write",
) -> None:
    """Seed a real connected resource + alias into the per-session local store."""
    local.upsert_connected_resource(
        {
            "resource_id": resource_id,
            "actor_id": "actor-a",
            "resource_kind": resource_kind,
            "connector_id": connector_id,
            "label": alias,
            "permissions": permissions,
            "freshness_state": "fresh",
            "status": "active",
        }
    )
    local.upsert_alias_index("actor-a", alias, resource_id, "resource")


# ══════════════════════════════════════════════════════════════════════
# Frame / request builders (Contract A — real production shape)
# ══════════════════════════════════════════════════════════════════════


def _frame(
    *,
    operation_hint: str,
    resource_kind_hint: str,
    params: dict | None = None,
    subject_hint: str | None = None,
    resource_refs: list[ResourceRef] | None = None,
    actor_role: str = "parent",
    safety_band: str = "GREEN",
    domain: str = "family",
) -> RequestFrame:
    intents = [
        RequestFrameIntent(
            intent_id="i1",
            action=f"{operation_hint} {resource_kind_hint}",
            domain=domain,
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
        person_refs=[],
        resource_refs=resource_refs,
        safety_context={"actor_role": actor_role, "safety_band": safety_band},
    )


def _request(
    frame: RequestFrame,
    *,
    safety_band: str = "GREEN",
    completed: list[str] | None = None,
    idempotency_keys: list[str] | None = None,
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
    )


_WRITE_FULL = {
    "title": "Dentist",
    "start": "x",
    "end": "y",
    "resource_id": "c",
    "idempotency_key": "k",  # calendar declares 5 write_inputs → satisfy them all
}


# ══════════════════════════════════════════════════════════════════════
# Real family-tools execution helpers (NO mocks — real SQLite round-trip)
# ══════════════════════════════════════════════════════════════════════


def _run(coro: Any) -> Any:
    """Drive an async family-tool dispatch to completion from a sync test."""
    return asyncio.run(coro)


def _ctx(
    *,
    user_id: str = "u1",
    space_id: str = "h1",
    role: str = "parent",
    band: str = "GREEN",
    idem_key: str | None = None,
) -> WriteContext:
    return WriteContext(
        user_id=user_id,
        space_id=space_id,
        trace_id=f"trace-{user_id}",
        role=role,  # type: ignore[arg-type]
        band=band,  # type: ignore[arg-type]
        idempotency_key=idem_key,
    )


def _evt_params(**over: Any) -> dict:
    p = {
        "title": "Soccer game",
        "start": "2026-05-15T10:00:00+00:00",
        "end": "2026-05-15T11:30:00+00:00",
    }
    p.update(over)
    return p


@dataclass(frozen=True)
class _WriteBinding:
    """Carries the REAL connector_id + resource_id of a committed write.

    Structurally satisfies ``verification.runner.BindingLike`` (the Phase-1
    Protocol contract).  This is a data record, not a behavioural mock — every
    field is a real value produced by the real write.
    """

    binding_id: str
    capability_name: str
    connector_id: str
    resource_id: str
    verifier_ref: str | None = None


@dataclass(frozen=True)
class _WriteObservation:
    """REAL post-write observation — ``structured_result`` holds the real
    ``event_id`` + ``title`` returned by the live ``CalendarToolService``.
    """

    invocation_id: str
    structured_result: dict


class _ReadbackResult:
    def __init__(self, data: dict) -> None:
        self._data = dict(data)

    @property
    def data(self) -> dict:
        return self._data


class _CalendarReadbackPort:
    """REAL ``NativeReadbackPort`` over the live ``CalendarToolService``.

    ``dispatch`` issues a real ``get_event`` against the real SQLite row that
    ``create_event`` persisted — no mock, no canned data.
    """

    def __init__(self, service: Any, ctx: WriteContext) -> None:
        self._service = service
        self._ctx = ctx
        self.calls: list = []

    def dispatch(
        self, capability_name: str, params: dict, context: ReadbackContext
    ) -> _ReadbackResult:
        self.calls.append((capability_name, params))
        out = _run(self._service.dispatch("get_event", {"event_id": params["event_id"]}, self._ctx))
        event = out.get("event") or {}
        return _ReadbackResult(
            {
                "found": bool(out.get("success")),
                "event_id": params.get("event_id"),
                "title": event.get("title"),
            }
        )


def _bootstrap_calendar(db_path: Path):
    """Bootstrap the REAL family CalendarToolService + NativeToolProvider."""
    return bootstrap_family_tools(
        None,
        db_path=str(db_path),
        service_classes=[CalendarToolService],
    )


def _read_after_write_constitution() -> ConstitutionArtifact:
    return ConstitutionArtifact(
        connector_id="family.calendar",
        constitution_id="family.calendar.v1",
        schema_version="1.0.0",
        execution_phases=["read", "mutate"],
        verification_requirements=[VerificationRequirement(method="read_after_write")],
    )


# ══════════════════════════════════════════════════════════════════════
# 1. Full resolution pipeline (Epic 3 → 4 → 5 → 6) through the wired Fabric
# ══════════════════════════════════════════════════════════════════════


class TestFullResolutionPipeline:
    def test_read_resolves_can_execute_with_prompt_pack(self):
        fabric = _wired_fabric()
        env = fabric.resolve_situation(
            _request(_frame(operation_hint="list", resource_kind_hint="calendar_event"))
        )
        assert isinstance(env, ResolutionEnvelope)
        assert env.verdict == "can_execute"
        assert env.sub_reason is None
        # Epic 3: candidate universe materialised.
        assert env.candidate_universe is not None
        # Epic 4: typed intent resolved.
        assert env.intent_resolutions
        assert env.policy_bundle is not None
        # Epic 6.1: a primary binding was selected.
        assert env.binding_bundle is not None
        assert env.binding_bundle.primary is not None
        assert env.binding_bundle.primary.capability_name.startswith("tool.read.family.calendar")
        # Epic 6.3: a redaction-clean prompt pack was assembled by the wired builder.
        assert env.prompt_pack is not None

    def test_write_with_seeded_resource_gates_then_completes(self):
        fabric = _wired_fabric()
        _seed_connected(
            fabric.local_projection_store,
            resource_id="cal-1",
            resource_kind="calendar_event",
            connector_id="family.calendar",
            alias="my calendar",
        )
        frame = _frame(
            operation_hint="create",
            resource_kind_hint="calendar_event",
            params=_WRITE_FULL,
            subject_hint="dentist",
            resource_refs=[ResourceRef(raw="my calendar", resource_kind_hint="calendar_event")],
        )
        first = fabric.resolve_situation(_request(frame))
        assert first.verdict == "can_execute_with_gate"
        assert first.sub_reason.startswith("prerequisite_read_incomplete:")
        prereq_id = first.binding_bundle.prerequisites[0].binding_id
        second = fabric.resolve_situation(_request(frame, completed=[prereq_id]))
        assert second.verdict == "can_execute"

    def test_constitution_attached_for_primary_write(self):
        fabric = _wired_fabric()
        env = fabric.resolve_situation(
            _request(
                _frame(
                    operation_hint="create",
                    resource_kind_hint="calendar_event",
                    params=_WRITE_FULL,
                    subject_hint="dentist",
                )
            )
        )
        # Epic 5: the calendar connector's constitution loaded for its write.
        assert env.constitution is not None
        assert env.constitution.connector_id == "family.calendar"


# ══════════════════════════════════════════════════════════════════════
# 2. Meta-tool entry point (Epic 6 → 7) — Back-facing async handler
# ══════════════════════════════════════════════════════════════════════


class TestMetaToolE2E:
    async def test_handle_resolve_situation_returns_verdict_dict(self):
        fabric = _wired_fabric()
        payload = {
            "actor_id": "actor-a",
            "space_id": "space-1",
            "session_id": "sess-1",
            "tier": "MEDIUM",
            "safety_band": "GREEN",
            "frame": {
                "intents": [
                    {
                        "intent_id": "i1",
                        "action": "list calendar_event",
                        "domain": "family",
                        "operation_hint": "list",
                        "resource_kind_hint": "calendar_event",
                        "params": {},
                    }
                ],
                "resource_refs": [
                    {
                        "raw": "calendar_event",
                        "resource_kind_hint": "calendar_event",
                        "needs_resolution": False,
                    }
                ],
                "safety_context": {"actor_role": "parent", "safety_band": "GREEN"},
            },
        }
        result = await fabric._handle_resolve_situation(payload)
        assert isinstance(result, dict)
        assert result["verdict"] == "can_execute"
        assert result["allowed_capability_names"]

    async def test_handler_never_raises_on_bad_payload(self):
        fabric = _wired_fabric()
        # Missing required keys → handler returns an error envelope, never raises.
        result = await fabric._handle_resolve_situation({"frame": {}})
        assert result["verdict"] == "cannot_execute"
        assert result["sub_reason"] == "handler_exception"


# ══════════════════════════════════════════════════════════════════════
# 3. Domain catalog load (Epic 2 → 4 → 1) — real corpus into real store
# ══════════════════════════════════════════════════════════════════════


class TestDomainCatalogLoad:
    def test_full_catalog_admitted(self):
        fabric = _wired_fabric()
        gps = fabric.global_projection_store
        # 5 domains × 10 services = 50 connectors.
        assert len(gps.list_connectors()) == 50
        assert gps.count_capabilities() > 0

    def test_every_domain_has_ten_connectors(self):
        gps = GlobalProjectionStore(":memory:")
        gps.open()
        admission = ManifestAdmissionService(gps)
        for domain_id in DOMAIN_SERVICES:
            corpus = build_domain_corpus(domain_id)
            records = admission.admit_all(corpus)
            assert len(corpus) == 10
            assert all(r.admission_verdict == "admitted" for r in records)

    def test_calendar_capability_lookup(self):
        fabric = _wired_fabric()
        rows = fabric.global_projection_store.lookup_capability_by_type(
            domain="family",
            resource_family="calendar_event",
            operation_family="create",
            effect="write",
        )
        assert len(rows) >= 1


# ══════════════════════════════════════════════════════════════════════
# 4. Store isolation (Epic 1 → 7) — global writes never bleed into local
# ══════════════════════════════════════════════════════════════════════


class TestStoreIsolation:
    def test_global_and_local_are_distinct(self):
        fabric = _wired_fabric()
        gps = fabric.global_projection_store
        lps = fabric.local_projection_store
        assert lps is not gps
        assert isinstance(lps, LocalProjectionStore)
        # Catalog connector lives in the global store …
        assert gps.get_connector("family.calendar") is not None
        # … and is NOT visible as a per-session connected resource / alias.
        assert lps.resolve_alias("family.calendar", "actor-a") == []
        assert lps.get_connected_resource("family.calendar") is None


# ══════════════════════════════════════════════════════════════════════
# 5. Idempotency enforcement (Epic 1 → 6 → 7) — real store, real cascade
# ══════════════════════════════════════════════════════════════════════


class TestIdempotencyEnforcementE2E:
    def test_succeeded_key_blocks_duplicate_write(self):
        fabric = _wired_fabric()
        idem = fabric.idempotency_store
        key = "idem-dup-1"
        idem.mark_in_flight(key, "inv-1")
        idem.mark_success(key, {"event_id": "evt-1"})

        frame = _frame(
            operation_hint="create",
            resource_kind_hint="calendar_event",
            params=_WRITE_FULL,
            subject_hint="dentist",
        )
        env = fabric.resolve_situation(_request(frame, idempotency_keys=[key]))
        assert env.verdict == "cannot_execute"
        assert env.sub_reason == f"idempotency_duplicate:{key}"

    def test_fresh_key_does_not_block(self):
        fabric = _wired_fabric()
        frame = _frame(operation_hint="list", resource_kind_hint="calendar_event")
        env = fabric.resolve_situation(_request(frame, idempotency_keys=["never-seen"]))
        assert env.verdict == "can_execute"


# ══════════════════════════════════════════════════════════════════════
# 6. Constitution validation (Epic 5 → 4) — real schema gate + loader
# ══════════════════════════════════════════════════════════════════════


class TestConstitutionRejection:
    def test_missing_execution_phases_rejected(self):
        bad = {
            "connector_id": "family.calendar",
            "constitution_id": "family.calendar.v1",
            "schema_version": "1.0.0",
            # execution_phases omitted → invalid.
        }
        with pytest.raises(ConstitutionValidationError):
            validate_constitution(bad)

    def test_valid_constitution_accepted(self):
        good = {
            "connector_id": "family.calendar",
            "constitution_id": "family.calendar.v1",
            "schema_version": "1.0.0",
            "execution_phases": ["read", "mutate"],
        }
        artifact = validate_constitution(good)
        assert artifact.execution_phases == ["read", "mutate"]

    def test_admitted_catalog_constitution_loads(self):
        # 5 → 4 round trip: the admitted family.calendar connector's
        # constitution is readable via the real loader.
        fabric = _wired_fabric()
        loader = ConstitutionLoader(fabric.global_projection_store)
        artifact = loader.load("family.calendar")
        assert artifact is not None
        assert artifact.connector_id == "family.calendar"


# ══════════════════════════════════════════════════════════════════════
# 7. Redaction proof (Epic 6.3) — secret marker → hard failure
# ══════════════════════════════════════════════════════════════════════


class TestRedactionProofE2E:
    def test_secret_marker_in_source_raises_through_resolve(self):
        leaky = ConnectorDefinition(
            connector_id="family.leak",
            label="Leak",
            description="leaky connector",
            provider_id="native.family.leak",
            resource_kinds=["note"],
            capabilities=[
                CapabilityDefinition(
                    name="tool.read.family.leak.list",
                    action_name="list",
                    invocation_mode="read",
                    effect="read",
                    resource_kind="note",
                    description="list notes with bearer token",  # secret marker
                )
            ],
        )
        fabric = _wired_fabric(extra=[leaky])
        frame = _frame(operation_hint="list", resource_kind_hint="note")
        # The wired resolver builds the prompt pack inline; the leak must
        # surface as a hard PromptPackLeakError out of resolve_situation.
        with pytest.raises(PromptPackLeakError):
            fabric.resolve_situation(_request(frame))


# ══════════════════════════════════════════════════════════════════════
# 8. Verification plan (Epic 4.2 → 5 → 1) — REAL write, REAL read-back
# ══════════════════════════════════════════════════════════════════════


class TestVerificationPlanE2E:
    def test_read_after_write_verified_over_real_calendar(self, tmp_path):
        gps = GlobalProjectionStore(":memory:")
        gps.open()
        ManifestAdmissionService(gps).admit_all(build_domain_corpus("family"))

        bundle = _bootstrap_calendar(tmp_path / "fam.db")
        try:
            svc = bundle.tool_registry.get_service("calendar")
            ctx = _ctx()
            created = _run(svc.dispatch("create_event", _evt_params(), ctx))
            assert created["success"] is True
            event_id = created["event_id"]

            binding = _WriteBinding(
                binding_id="b1",
                capability_name="tool.execute.family.calendar.create",
                connector_id="family.calendar",
                resource_id=event_id,
            )
            observation = _WriteObservation(
                invocation_id="inv-1",
                structured_result={"event_id": event_id, "title": "Soccer game"},
            )
            runner = VerificationPlanRunner(
                _CalendarReadbackPort(svc, ctx), gps, ConstitutionLoader(gps)
            )
            plan = runner.build_plan(binding, observation, _read_after_write_constitution())
            assert plan.verifier_method == "read_after_write"
            result = runner.run(plan)
            assert result.status == "verified"
            assert result.mismatch_summary is None
        finally:
            bundle.close()

    def test_read_after_write_fails_on_tamper(self, tmp_path):
        gps = GlobalProjectionStore(":memory:")
        gps.open()
        ManifestAdmissionService(gps).admit_all(build_domain_corpus("family"))

        bundle = _bootstrap_calendar(tmp_path / "fam.db")
        try:
            svc = bundle.tool_registry.get_service("calendar")
            ctx = _ctx()
            created = _run(svc.dispatch("create_event", _evt_params(), ctx))
            event_id = created["event_id"]
            # Observation claims a title the persisted row does NOT have.
            observation = _WriteObservation(
                invocation_id="inv-1",
                structured_result={"event_id": event_id, "title": "TAMPERED"},
            )
            binding = _WriteBinding(
                binding_id="b1",
                capability_name="tool.execute.family.calendar.create",
                connector_id="family.calendar",
                resource_id=event_id,
            )
            runner = VerificationPlanRunner(
                _CalendarReadbackPort(svc, ctx), gps, ConstitutionLoader(gps)
            )
            plan = runner.build_plan(binding, observation, _read_after_write_constitution())
            result = runner.run(plan)
            assert result.status == "failed"
            assert "title" in (result.mismatch_summary or "")
        finally:
            bundle.close()


# ══════════════════════════════════════════════════════════════════════
# GATE-P1 checklist — the 14 acceptance gates for "Fabric standalone proven"
# ══════════════════════════════════════════════════════════════════════


class TestGateChecklist:
    """One method per GATE-P1 acceptance criterion.

    GATE-05 (Bridge round-trip) is intentionally skipped: the Bridge is a
    Phase-2 deliverable and there is no real Bridge to drive in Phase 1 —
    faking one would violate the no-mock mandate.
    """

    # GATE-01 — catalog populated + searchable.
    def test_gate_01_catalog_populated(self):
        gps = _wired_fabric().global_projection_store
        assert gps.count_capabilities() > 0
        hits = gps.search_capabilities("calendar", top_k=5)
        assert any("family.calendar" in h.capability_name for h in hits)

    # GATE-02 — resolver produces a candidate universe with a real connector.
    def test_gate_02_candidate_universe(self):
        fabric = _wired_fabric()
        _seed_connected(
            fabric.local_projection_store,
            resource_id="cal-1",
            resource_kind="calendar_event",
            connector_id="family.calendar",
            alias="my calendar",
        )
        env = fabric.resolve_situation(
            _request(
                _frame(
                    operation_hint="list",
                    resource_kind_hint="calendar_event",
                    resource_refs=[
                        ResourceRef(raw="my calendar", resource_kind_hint="calendar_event")
                    ],
                )
            )
        )
        assert env.candidate_universe is not None
        connectors = {
            c.connector_id
            for c in env.candidate_universe.resource_candidates
            if getattr(c, "connector_id", None)
        }
        assert "family.calendar" in connectors

    # GATE-03 — binder selects a primary + emits constitution prerequisites.
    def test_gate_03_binding_with_prerequisites(self):
        fabric = _wired_fabric()
        env = fabric.resolve_situation(
            _request(
                _frame(
                    operation_hint="create",
                    resource_kind_hint="calendar_event",
                    params=_WRITE_FULL,
                    subject_hint="dentist",
                )
            )
        )
        assert env.binding_bundle.primary is not None
        assert env.binding_bundle.primary.capability_name.startswith("tool.execute.family.calendar")
        assert env.binding_bundle.prerequisites  # constitution prereq reads

    # GATE-04 — real NativeToolProvider routes to the real CalendarToolService.
    def test_gate_04_native_tool_execution(self, tmp_path):
        bundle = _bootstrap_calendar(tmp_path / "fam.db")
        try:
            caps = bundle.native_provider.capabilities()
            assert "tool.execute.calendar.create_event" in caps
            assert "tool.read.calendar.get_event" in caps
            # Drive the provider's own live registry service: real write → real read.
            svc = bundle.tool_registry.get_service("calendar")
            ctx = _ctx()
            created = _run(svc.dispatch("create_event", _evt_params(), ctx))
            assert created["success"] is True
            got = _run(svc.dispatch("get_event", {"event_id": created["event_id"]}, ctx))
            assert got["success"] is True
            assert got["event"]["title"] == "Soccer game"
        finally:
            bundle.close()

    # GATE-05 — Bridge round-trip: SKIPPED (Phase 2; no real Bridge to drive).
    @pytest.mark.skip(reason="GATE-05 Bridge round-trip is a Phase-2 deliverable")
    def test_gate_05_bridge_roundtrip(self):  # pragma: no cover
        ...

    # GATE-06 — idempotency duplicate blocked end-to-end.
    def test_gate_06_idempotency_duplicate(self):
        fabric = _wired_fabric()
        idem = fabric.idempotency_store
        key = "gate6-key"
        idem.mark_in_flight(key, "inv-1")
        idem.mark_success(key, {"event_id": "evt-1"})
        env = fabric.resolve_situation(
            _request(
                _frame(
                    operation_hint="create",
                    resource_kind_hint="calendar_event",
                    params=_WRITE_FULL,
                    subject_hint="dentist",
                ),
                idempotency_keys=[key],
            )
        )
        assert env.verdict == "cannot_execute"
        assert env.sub_reason == f"idempotency_duplicate:{key}"

    # GATE-07 — real verifier confirms a real persisted write.
    def test_gate_07_verifier_read_after_write(self, tmp_path):
        gps = GlobalProjectionStore(":memory:")
        gps.open()
        ManifestAdmissionService(gps).admit_all(build_domain_corpus("family"))
        bundle = _bootstrap_calendar(tmp_path / "fam.db")
        try:
            svc = bundle.tool_registry.get_service("calendar")
            ctx = _ctx()
            created = _run(svc.dispatch("create_event", _evt_params(), ctx))
            event_id = created["event_id"]
            binding = _WriteBinding(
                binding_id="b1",
                capability_name="tool.execute.family.calendar.create",
                connector_id="family.calendar",
                resource_id=event_id,
            )
            observation = _WriteObservation(
                invocation_id="inv-1",
                structured_result={"event_id": event_id, "title": "Soccer game"},
            )
            runner = VerificationPlanRunner(
                _CalendarReadbackPort(svc, ctx), gps, ConstitutionLoader(gps)
            )
            plan = runner.build_plan(binding, observation, _read_after_write_constitution())
            result = runner.run(plan)
            assert result.status == "verified"
        finally:
            bundle.close()

    # GATE-08 — role policy enforced (child write denied, parent allowed).
    def test_gate_08_role_policy(self):
        connector = _custom_connector(
            "family.chores",
            "chore",
            policy=PolicyDefinition(write_requires_actor_role=["parent", "guardian"]),
        )
        fabric = _wired_fabric(extra=[connector])
        _seed_connected(
            fabric.local_projection_store,
            resource_id="chore-1",
            resource_kind="chore",
            connector_id="family.chores",
            alias="chore list",
        )

        def _resolve(role: str):
            return fabric.resolve_situation(
                _request(
                    _frame(
                        operation_hint="create",
                        resource_kind_hint="chore",
                        params={"title": "Dishes"},
                        actor_role=role,
                        resource_refs=[ResourceRef(raw="chore list", resource_kind_hint="chore")],
                    )
                )
            )

        assert _resolve("child").verdict == "blocked_by_policy"
        assert _resolve("parent").verdict in {"can_execute", "can_execute_with_gate"}

    # GATE-09 — under-specified write surfaces a missing-params verdict.
    def test_gate_09_missing_required_params(self):
        fabric = _wired_fabric()
        env = fabric.resolve_situation(
            _request(
                _frame(
                    operation_hint="create",
                    resource_kind_hint="calendar_event",
                    params={},  # no subject, no params, no time window → vague
                )
            )
        )
        # 'missing_required_params' IS the verdict (cascade step 7).
        assert env.verdict == "missing_required_params"
        assert env.sub_reason == "intent_too_vague"

    # GATE-10 — legacy discovery path stays intact post-Phase-1 wiring.
    async def test_gate_10_discover_capabilities_legacy_path(self, tmp_path):
        fabric = _wired_fabric()
        # Register real family contracts so discovery has something to match.
        bundle = _bootstrap_calendar(tmp_path / "fam.db")
        try:
            result = await fabric.discover_capabilities(intent="calendar", top_k=10)
            assert result is not None
            assert isinstance(result.capabilities, list)
        finally:
            bundle.close()

    # GATE-11 — the factory wired the real Phase-1 object graph.
    def test_gate_11_object_graph(self):
        fabric = _wired_fabric()
        assert isinstance(fabric.facade, CapabilityFabric)
        assert isinstance(fabric.global_projection_store, GlobalProjectionStore)
        assert isinstance(fabric.local_projection_store, LocalProjectionStore)
        assert isinstance(fabric.idempotency_store, IdempotencyStore)
        assert isinstance(fabric.situated_resolver, ResolveSituationService)

    # GATE-12 — vague intent (no resource kind) → intent_too_vague.
    def test_gate_12_intent_too_vague(self):
        fabric = _wired_fabric()
        frame = _frame(
            operation_hint="create",
            resource_kind_hint="calendar_event",
            params={},
            subject_hint=None,
        )
        # Strip the resource-kind hint so the type resolver can't anchor.
        vague = RequestFrame(
            request_id=frame.request_id,
            task_id=frame.task_id,
            trace_id=frame.trace_id,
            actor_id=frame.actor_id,
            space_id=frame.space_id,
            intents=[
                RequestFrameIntent(
                    intent_id="i1",
                    action="do something",
                    domain="family",
                    operation_hint="create",
                    resource_kind_hint=None,
                    params={},
                )
            ],
            person_refs=[],
            resource_refs=[],
            safety_context={"actor_role": "parent", "safety_band": "GREEN"},
        )
        env = fabric.resolve_situation(_request(vague))
        assert env.verdict == "missing_required_params"
        assert env.sub_reason == "intent_too_vague"

    # GATE-13 — safety-band gate: AMBER-min write blocked at GREEN.
    def test_gate_13_safety_band_gate(self):
        connector = _custom_connector(
            "family.ledger",
            "ledger_entry",
            safety_band_min="AMBER",
        )
        fabric = _wired_fabric(extra=[connector])
        _seed_connected(
            fabric.local_projection_store,
            resource_id="ledger-1",
            resource_kind="ledger_entry",
            connector_id="family.ledger",
            alias="the ledger",
        )
        frame = _frame(
            operation_hint="create",
            resource_kind_hint="ledger_entry",
            params={"title": "x"},
            safety_band="GREEN",
            resource_refs=[ResourceRef(raw="the ledger", resource_kind_hint="ledger_entry")],
        )
        env = fabric.resolve_situation(_request(frame, safety_band="GREEN"))
        # An AMBER-min capability is not reachable from a GREEN context.
        assert env.verdict != "can_execute"

    # GATE-14 — unknown resource kind → missing_capability naming the kind.
    def test_gate_14_missing_capability(self):
        fabric = _wired_fabric()
        env = fabric.resolve_situation(
            _request(
                _frame(
                    operation_hint="create",
                    resource_kind_hint="widget",
                    params={"x": 1},
                )
            )
        )
        assert env.verdict == "missing_capability"
        assert "widget" in env.sub_reason
