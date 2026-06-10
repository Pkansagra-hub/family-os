"""GAP-P1-020 — Tests for CapabilityBinderService (Epic 6.1)."""

from __future__ import annotations

import pytest

from k1.fabric.constitution.loader import ConstitutionLoader
from k1.fabric.policy.selector import PolicyBundle
from k1.fabric.resolver.capability_binder import (
    UNIVERSAL_ACTION_MAP,
    BindingBundle,
    CapabilityBinderService,
)
from k1.fabric.resolver.capability_type_resolver import ResolvedIntentType
from k1.fabric.resolver.resource_projection import (
    ResourceCandidate,
    ResourceUniverse,
    ScopeProof,
)
from k1.fabric.stores.global_projection_store import (
    CapabilityRecord,
    ConnectorRecord,
    ConstitutionRecord,
    GlobalProjectionStore,
)
from k1.fabric.stores.local_projection_store import LocalProjectionStore

# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


def _connector(store: GlobalProjectionStore, connector_id: str) -> None:
    store.upsert_connector(
        ConnectorRecord(
            connector_id=connector_id,
            label=connector_id,
            connector_type="native",
            provider_type="LOCAL",
            version="1.0.0",
            admission_verdict="admitted",
            registration_type="static",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
        )
    )


def _capability(
    store: GlobalProjectionStore,
    capability_name: str,
    connector_id: str,
    *,
    invocation_mode: str,
    effect: str,
    action_name: str,
    resource_kind: str = "calendar_event",
    description: str = "",
    domain: str = "family",
) -> None:
    store.upsert_capability(
        CapabilityRecord(
            capability_name=capability_name,
            connector_id=connector_id,
            invocation_mode=invocation_mode,
            action_name=action_name,
            effect=effect,
            resource_kind=resource_kind,
            description=description or f"{action_name} {resource_kind}",
            created_at="2026-01-01T00:00:00",
        )
    )
    op_family = action_name
    type_effect = effect
    store.upsert_capability_type_index(
        capability_name=capability_name,
        connector_id=connector_id,
        domain=domain,
        resource_family=resource_kind,
        operation_family=op_family,
        effect=type_effect,
    )


@pytest.fixture
def store() -> GlobalProjectionStore:
    s = GlobalProjectionStore(db_path=":memory:")
    s.open()
    _connector(s, "family.calendar")
    _capability(
        s,
        "tool.read.family.calendar.list",
        "family.calendar",
        invocation_mode="read",
        effect="read",
        action_name="list",
        description="list calendar events",
    )
    _capability(
        s,
        "tool.execute.family.calendar.create",
        "family.calendar",
        invocation_mode="execute",
        effect="write",
        action_name="create",
        description="create calendar event",
    )
    return s


@pytest.fixture
def local_store() -> LocalProjectionStore:
    s = LocalProjectionStore(db_path=":memory:")
    s.open()
    return s


@pytest.fixture
def binder(store, local_store) -> CapabilityBinderService:
    return CapabilityBinderService(store, local_store)


@pytest.fixture
def loader(store) -> ConstitutionLoader:
    return ConstitutionLoader(store)


def _allow_bundle() -> PolicyBundle:
    return PolicyBundle(
        policy_id="p1",
        connector_ids=["family.calendar"],
        intent_types=[],
        actor_role="parent",
        safety_band="GREEN",
        roles_allowed={},
        gates=[],
        hil_triggers=[],
        protected_read_policy=None,
        guide_refs=[],
        verifier_requirements={},
        policy_verdict="allow",
        deny_reason=None,
        safety_mapping_evidence=None,
    )


def _deny_bundle() -> PolicyBundle:
    b = _allow_bundle()
    return PolicyBundle(
        **{**b.__dict__, "policy_verdict": "deny", "deny_reason": "role_not_allowed"}
    )


def _universe(*candidates: ResourceCandidate) -> ResourceUniverse:
    return ResourceUniverse(
        universe_id="uni-1",
        resource_candidates=list(candidates),
        person_candidates=[],
        unresolved=[],
        scope_proof=ScopeProof(scope_proof_id="s-1", actor_id="actor-a", space_id="space-1"),
        completeness="complete",
        freshness="fresh",
    )


def _candidate(
    connector_id: str = "family.calendar",
    *,
    resource_id: str = "cal-1",
    resource_kind: str = "calendar_event",
    freshness: str = "fresh",
) -> ResourceCandidate:
    return ResourceCandidate(
        resource_id=resource_id,
        label=resource_id,
        resource_kind=resource_kind,
        connector_id=connector_id,
        actor_permission="read_write",
        freshness_state=freshness,
    )


def _intent(
    operation_family: str,
    effect: str,
    *,
    resource_family: str = "calendar_event",
    fallback: list[dict] | None = None,
    confidence: str = "high",
) -> ResolvedIntentType:
    return ResolvedIntentType(
        intent_id="i1",
        domain="family",
        resource_family=resource_family,
        operation_family=operation_family,
        effect=effect,
        confidence=confidence,
        fallback_capabilities=fallback or [],
    )


# ══════════════════════════════════════════════════════════════════════
# TestTypedIntentBinding (Pass 1)
# ══════════════════════════════════════════════════════════════════════


class TestTypedIntentBinding:
    def test_typed_intent_binds_directly(self, binder):
        intent = _intent(
            "create",
            "write",
            fallback=[
                {
                    "capability_name": "tool.execute.family.calendar.create",
                    "connector_id": "family.calendar",
                    "effect": "write",
                }
            ],
        )
        bundle = binder.bind(
            [intent],
            _universe(_candidate()),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
        )
        assert bundle.primary is not None
        assert bundle.primary.capability_name == "tool.execute.family.calendar.create"
        assert bundle.primary.source == "typed_intent"


# ══════════════════════════════════════════════════════════════════════
# TestExactMatchBinding (Pass 2)
# ══════════════════════════════════════════════════════════════════════


class TestExactMatchBinding:
    def test_exact_match_when_no_typed(self, binder):
        intent = _intent("create", "write", fallback=[])
        bundle = binder.bind(
            [intent],
            _universe(_candidate()),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
        )
        assert bundle.primary is not None
        assert bundle.primary.source == "exact_match"
        assert bundle.primary.capability_name == "tool.execute.family.calendar.create"


# ══════════════════════════════════════════════════════════════════════
# TestBM25FallbackBinding (Pass 3)
# ══════════════════════════════════════════════════════════════════════


class TestBM25FallbackBinding:
    def test_bm25_when_no_typed_or_exact(self, binder):
        # resource_kind mismatch defeats exact match → BM25 falls back on action text
        intent = _intent("create", "write", resource_family="", fallback=[])
        candidate = _candidate(resource_kind="")
        bundle = binder.bind(
            [intent],
            _universe(candidate),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
            intent_actions=["create calendar event"],
        )
        assert bundle.primary is not None
        assert bundle.primary.source == "bm25_search"


# ══════════════════════════════════════════════════════════════════════
# TestPassPrecedence
# ══════════════════════════════════════════════════════════════════════


class TestPassPrecedence:
    def test_typed_preferred_over_exact(self, binder):
        intent = _intent(
            "create",
            "write",
            fallback=[
                {
                    "capability_name": "tool.execute.family.calendar.create",
                    "connector_id": "family.calendar",
                    "effect": "write",
                }
            ],
        )
        bundle = binder.bind(
            [intent],
            _universe(_candidate()),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
            intent_actions=["create calendar event"],
        )
        assert bundle.primary.source == "typed_intent"


# ══════════════════════════════════════════════════════════════════════
# TestRolePropagation
# ══════════════════════════════════════════════════════════════════════


class TestRolePropagation:
    def test_primary_role_assigned(self, binder):
        intent = _intent("list", "read", fallback=[])
        bundle = binder.bind(
            [intent],
            _universe(_candidate()),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
        )
        assert bundle.primary is not None
        assert bundle.primary.role == "primary"

    def test_write_primary_gets_verifier_ref(self, binder):
        intent = _intent("create", "write", fallback=[])
        bundle = binder.bind(
            [intent],
            _universe(_candidate()),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
        )
        assert bundle.primary.verifier_ref is not None
        assert "family.calendar" in bundle.primary.verifier_ref


# ══════════════════════════════════════════════════════════════════════
# TestCompanionDiscovery
# ══════════════════════════════════════════════════════════════════════


class TestCompanionDiscovery:
    def test_companion_from_constitution(self, store, binder, loader):
        # Add a companion connector + read cap for resource_kind "task".
        _connector(store, "family.tasks")
        _capability(
            store,
            "tool.read.family.tasks.list",
            "family.tasks",
            invocation_mode="read",
            effect="read",
            action_name="list",
            resource_kind="task",
            domain="family",
        )
        store.upsert_constitution(
            ConstitutionRecord(
                connector_id="family.calendar",
                constitution_id="family.calendar.v1",
                execution_phases=["read", "mutate"],
                companion_resource_roles=[
                    {"resource_kind": "task", "role": "conflict_source", "description": ""}
                ],
            )
        )
        intent = _intent("create", "write", fallback=[])
        # The companion read cap is on family.calendar connector in this candidate,
        # but find_capabilities filters by candidate.connector_id; companions use
        # the same connector_id. Register a calendar 'task' read for the lookup.
        _capability(
            store,
            "tool.read.family.calendar.list_tasks",
            "family.calendar",
            invocation_mode="read",
            effect="read",
            action_name="list",
            resource_kind="task",
            domain="family",
        )
        bundle = binder.bind(
            [intent],
            _universe(_candidate()),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
            constitution_loader=loader,
        )
        assert any(c.resource_kind == "task" for c in bundle.companions)


# ══════════════════════════════════════════════════════════════════════
# TestPrerequisiteDiscovery
# ══════════════════════════════════════════════════════════════════════


class TestPrerequisiteDiscovery:
    def test_prerequisite_from_constitution(self, store, binder, loader):
        store.upsert_constitution(
            ConstitutionRecord(
                connector_id="family.calendar",
                constitution_id="family.calendar.v1",
                execution_phases=["read", "mutate"],
                prerequisite_reads=[
                    {
                        "operation": "list",
                        "resource_kind": "calendar_event",
                        "reason": "check conflicts",
                        "required": True,
                        "timeout_ms": 5000,
                    }
                ],
            )
        )
        intent = _intent("create", "write", fallback=[])
        bundle = binder.bind(
            [intent],
            _universe(_candidate()),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
            constitution_loader=loader,
        )
        assert len(bundle.prerequisites) >= 1
        assert bundle.prerequisites[0].invocation_mode == "read"


# ══════════════════════════════════════════════════════════════════════
# TestPolicyBlock
# ══════════════════════════════════════════════════════════════════════


class TestPolicyBlock:
    def test_deny_produces_unbound_policy_block(self, binder):
        intent = _intent("create", "write", fallback=[])
        bundle = binder.bind(
            [intent],
            _universe(_candidate()),
            _deny_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
        )
        assert bundle.primary is None
        assert any(r.reason == "policy_block" for r in bundle.unbound_roles)


# ══════════════════════════════════════════════════════════════════════
# TestStaleResourceBlock
# ══════════════════════════════════════════════════════════════════════


class TestStaleResourceBlock:
    def test_stale_write_unbound(self, binder):
        intent = _intent("create", "write", fallback=[])
        candidate = _candidate(freshness="stale")
        bundle = binder.bind(
            [intent],
            _universe(candidate),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
        )
        assert any(r.reason == "stale_projection" for r in bundle.unbound_roles)

    def test_stale_read_still_binds(self, binder):
        intent = _intent("list", "read", fallback=[])
        candidate = _candidate(freshness="stale")
        bundle = binder.bind(
            [intent],
            _universe(candidate),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
        )
        # Reads on stale resources are still allowed.
        assert bundle.primary is not None


# ══════════════════════════════════════════════════════════════════════
# TestMissingCapability
# ══════════════════════════════════════════════════════════════════════


class TestMissingCapability:
    def test_no_match_unbound_missing_capability(self, binder):
        intent = _intent("create", "write", resource_family="widget", fallback=[])
        candidate = _candidate(resource_kind="widget")
        bundle = binder.bind(
            [intent],
            _universe(candidate),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
        )
        assert bundle.primary is None
        assert any(r.reason == "missing_capability" for r in bundle.unbound_roles)


# ══════════════════════════════════════════════════════════════════════
# TestBindingDedup
# ══════════════════════════════════════════════════════════════════════


class TestBindingDedup:
    def test_duplicate_bindings_deduped(self, binder):
        # Two identical intents → same (connector, cap, resource, actor, session)
        intent = _intent(
            "create",
            "write",
            fallback=[
                {
                    "capability_name": "tool.execute.family.calendar.create",
                    "connector_id": "family.calendar",
                    "effect": "write",
                }
            ],
        )
        bundle = binder.bind(
            [intent, intent],
            _universe(_candidate()),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
        )
        binding_ids = [b.binding_id for b in bundle.all_bindings]
        assert len(binding_ids) == len(set(binding_ids))


# ══════════════════════════════════════════════════════════════════════
# TestToolSelectionCommit
# ══════════════════════════════════════════════════════════════════════


class TestToolSelectionCommit:
    def test_valid_commit(self, binder):
        intent = _intent("create", "write", fallback=[])
        bundle = binder.bind(
            [intent],
            _universe(_candidate()),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
        )
        commit = binder.commit_tool_selection(bundle, ["tool.execute.family.calendar.create"])
        assert commit.accepted is True
        assert commit.rejected_tool_names == []

    def test_rejected_unknown_tool(self, binder):
        intent = _intent("create", "write", fallback=[])
        bundle = binder.bind(
            [intent],
            _universe(_candidate()),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
        )
        commit = binder.commit_tool_selection(bundle, ["tool.execute.family.ghost.create"])
        assert commit.accepted is False
        assert "tool.execute.family.ghost.create" in commit.rejected_tool_names


# ══════════════════════════════════════════════════════════════════════
# TestBindingBundleRoles
# ══════════════════════════════════════════════════════════════════════


class TestBindingBundleRoles:
    def test_roles_separated(self, store, binder, loader):
        store.upsert_constitution(
            ConstitutionRecord(
                connector_id="family.calendar",
                constitution_id="family.calendar.v1",
                execution_phases=["read", "mutate"],
                prerequisite_reads=[
                    {
                        "operation": "list",
                        "resource_kind": "calendar_event",
                        "reason": "check",
                        "required": True,
                        "timeout_ms": 5000,
                    }
                ],
                verification_requirements=[{"method": "read_after_write"}],
            )
        )
        intent = _intent("create", "write", fallback=[])
        bundle = binder.bind(
            [intent],
            _universe(_candidate()),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
            constitution_loader=loader,
        )
        assert bundle.primary is not None
        assert bundle.primary.role == "primary"
        assert all(p.role == "prerequisite" for p in bundle.prerequisites)
        # all_bindings ordering: primary first
        assert bundle.all_bindings[0].role == "primary"

    def test_allowed_capability_names(self, binder):
        intent = _intent("create", "write", fallback=[])
        bundle = binder.bind(
            [intent],
            _universe(_candidate()),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
        )
        assert "tool.execute.family.calendar.create" in bundle.allowed_capability_names


# ══════════════════════════════════════════════════════════════════════
# TestInvocationModeEffectMapping
# ══════════════════════════════════════════════════════════════════════


class TestInvocationModeEffectMapping:
    def test_universal_action_map(self):
        assert UNIVERSAL_ACTION_MAP["list"] == ("read", "read")
        assert UNIVERSAL_ACTION_MAP["create"] == ("execute", "write")
        assert UNIVERSAL_ACTION_MAP["update"] == ("execute", "write")
        assert UNIVERSAL_ACTION_MAP["delete"] == ("execute", "delete")
        assert UNIVERSAL_ACTION_MAP["send"] == ("execute", "write")

    def test_mode_effect_from_intent(self, binder):
        intent = _intent("create", "write", fallback=[])
        bundle = binder.bind(
            [intent],
            _universe(_candidate()),
            _allow_bundle(),
            actor_id="actor-a",
            session_id="sess-1",
        )
        assert bundle.primary.invocation_mode == "execute"
        assert bundle.primary.effect == "write"
