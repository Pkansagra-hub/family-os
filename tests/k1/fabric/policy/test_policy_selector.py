"""GAP-P1-002 — Tests for PolicySelectorService (Epic 4.1).

Policy gates on typed ``ResolvedIntentType`` (Fix 7), not loose strings.
"""

from __future__ import annotations

import pytest

from k1.fabric.policy.selector import PolicyBundle, PolicySelectorService
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

# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


def _connector(
    connector_id: str,
    *,
    policy: dict | None = None,
) -> ConnectorRecord:
    return ConnectorRecord(
        connector_id=connector_id,
        label=connector_id,
        connector_type="native",
        provider_type="LOCAL",
        version="1.0.0",
        admission_verdict="admitted",
        registration_type="static",
        policy_declarations=policy or {},
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


def _capability(
    capability_name: str,
    connector_id: str,
    *,
    invocation_mode: str = "execute",
    effect: str = "write",
    action_name: str = "create",
    safety_band_min: str = "GREEN",
) -> CapabilityRecord:
    return CapabilityRecord(
        capability_name=capability_name,
        connector_id=connector_id,
        invocation_mode=invocation_mode,
        action_name=action_name,
        effect=effect,
        resource_kind="calendar_event",
        description=f"{action_name} calendar_event",
        safety_band_min=safety_band_min,
        created_at="2026-01-01T00:00:00",
    )


@pytest.fixture
def store() -> GlobalProjectionStore:
    """GPS seeded with several connectors covering each policy scenario."""
    s = GlobalProjectionStore(db_path=":memory:")
    s.open()

    # Default-allow calendar
    s.upsert_connector(
        _connector(
            "family.calendar",
            policy={
                "write_requires_actor_role": [],
                "read_allowed_roles": [],
                "protected_resources": [],
                "hil_triggers": [],
            },
        )
    )
    s.upsert_capability(_capability("tool.execute.family.calendar.create", "family.calendar"))

    # Chores: write requires parent/guardian
    s.upsert_connector(
        _connector(
            "family.chores",
            policy={
                "write_requires_actor_role": ["parent", "guardian"],
                "read_allowed_roles": [],
            },
        )
    )
    s.upsert_capability(_capability("tool.execute.family.chores.create", "family.chores"))

    # Secure: capability requires AMBER band
    s.upsert_connector(_connector("family.secure", policy={}))
    s.upsert_capability(
        _capability(
            "tool.execute.family.secure.create",
            "family.secure",
            safety_band_min="AMBER",
        )
    )

    # Messaging: HIL trigger for child writes
    s.upsert_connector(
        _connector(
            "family.messaging",
            policy={
                "write_requires_actor_role": [],
                "hil_triggers": [
                    {
                        "condition": "write_operation AND actor_role == 'child'",
                        "prompt": "Ask a parent to confirm.",
                    }
                ],
            },
        )
    )
    s.upsert_capability(
        _capability(
            "tool.execute.family.messaging.send",
            "family.messaging",
            action_name="send",
        )
    )

    # Vault: protected resources require parent role
    s.upsert_connector(
        _connector(
            "family.vault",
            policy={
                "write_requires_actor_role": [],
                "protected_resources": [
                    {
                        "resource_id_pattern": "vault_parent_*",
                        "reason": "Sensitive.",
                        "required_role": "parent",
                    }
                ],
            },
        )
    )
    s.upsert_capability(
        _capability(
            "tool.read.family.vault.list",
            "family.vault",
            invocation_mode="read",
            effect="read",
            action_name="list",
        )
    )

    # Calendar-with-constitution: prerequisite_reads → allow_with_gate
    s.upsert_connector(_connector("family.planner", policy={}))
    s.upsert_capability(_capability("tool.execute.family.planner.create", "family.planner"))
    s.upsert_constitution(
        ConstitutionRecord(
            connector_id="family.planner",
            constitution_id="family.planner.v1",
            execution_phases=["read", "mutate"],
            prerequisite_reads=[
                {
                    "operation": "list",
                    "resource_kind": "calendar_event",
                    "reason": "Check conflicts.",
                    "required": True,
                    "timeout_ms": 5000,
                }
            ],
            verification_requirements=[{"method": "read_after_write", "required_for_submit": True}],
        )
    )

    return s


@pytest.fixture
def selector(store: GlobalProjectionStore) -> PolicySelectorService:
    return PolicySelectorService(store)


def _universe(*candidates: ResourceCandidate) -> ResourceUniverse:
    return ResourceUniverse(
        universe_id="uni-1",
        resource_candidates=list(candidates),
        person_candidates=[],
        unresolved=[],
        scope_proof=ScopeProof(
            scope_proof_id="scope-1",
            actor_id="actor-a",
            space_id="space-1",
        ),
        completeness="complete",
        freshness="fresh",
    )


def _candidate(connector_id: str, resource_id: str = "res-1") -> ResourceCandidate:
    return ResourceCandidate(
        resource_id=resource_id,
        label=resource_id,
        resource_kind="calendar_event",
        connector_id=connector_id,
        actor_permission="read_write",
        freshness_state="fresh",
    )


def _write_intent(connector_id: str, capability_name: str) -> ResolvedIntentType:
    return ResolvedIntentType(
        intent_id="i1",
        domain="family",
        resource_family="calendar_event",
        operation_family="create",
        effect="write",
        fallback_capabilities=[
            {"capability_name": capability_name, "connector_id": connector_id},
        ],
    )


def _read_intent(connector_id: str, capability_name: str) -> ResolvedIntentType:
    return ResolvedIntentType(
        intent_id="i1",
        domain="family",
        resource_family="calendar_event",
        operation_family="list",
        effect="read",
        fallback_capabilities=[
            {"capability_name": capability_name, "connector_id": connector_id},
        ],
    )


# ══════════════════════════════════════════════════════════════════════
# TestHappyPath
# ══════════════════════════════════════════════════════════════════════


class TestHappyPath:
    def test_default_allow_write(self, selector):
        universe = _universe(_candidate("family.calendar"))
        intents = [_write_intent("family.calendar", "tool.execute.family.calendar.create")]
        bundle = selector.select(universe, intents, "parent", "GREEN")
        assert isinstance(bundle, PolicyBundle)
        assert bundle.policy_verdict == "allow"
        assert bundle.deny_reason is None
        assert "family.calendar" in bundle.connector_ids


# ══════════════════════════════════════════════════════════════════════
# TestDenyRole
# ══════════════════════════════════════════════════════════════════════


class TestDenyRole:
    def test_child_write_denied(self, selector):
        universe = _universe(_candidate("family.chores"))
        intents = [_write_intent("family.chores", "tool.execute.family.chores.create")]
        bundle = selector.select(universe, intents, "child", "GREEN")
        assert bundle.policy_verdict == "deny"
        assert bundle.deny_reason == "role_not_allowed"
        assert any(g.gate_type == "role_check" for g in bundle.gates)

    def test_parent_write_allowed(self, selector):
        universe = _universe(_candidate("family.chores"))
        intents = [_write_intent("family.chores", "tool.execute.family.chores.create")]
        bundle = selector.select(universe, intents, "parent", "GREEN")
        assert bundle.policy_verdict == "allow"


# ══════════════════════════════════════════════════════════════════════
# TestDenyBand
# ══════════════════════════════════════════════════════════════════════


class TestDenyBand:
    def test_green_actor_amber_capability_denied(self, selector):
        universe = _universe(_candidate("family.secure"))
        intents = [_write_intent("family.secure", "tool.execute.family.secure.create")]
        bundle = selector.select(universe, intents, "parent", "GREEN")
        assert bundle.policy_verdict == "deny"
        assert bundle.deny_reason == "safety_band_below_capability_minimum"
        assert bundle.safety_mapping_evidence is not None
        assert bundle.safety_mapping_evidence["required_band"] == "AMBER"

    def test_amber_actor_amber_capability_allowed(self, selector):
        universe = _universe(_candidate("family.secure"))
        intents = [_write_intent("family.secure", "tool.execute.family.secure.create")]
        bundle = selector.select(universe, intents, "parent", "AMBER")
        assert bundle.policy_verdict == "allow"
        assert bundle.safety_mapping_evidence is None


# ══════════════════════════════════════════════════════════════════════
# TestHILTrigger
# ══════════════════════════════════════════════════════════════════════


class TestHILTrigger:
    def test_child_write_triggers_hil(self, selector):
        universe = _universe(_candidate("family.messaging"))
        intents = [_write_intent("family.messaging", "tool.execute.family.messaging.send")]
        bundle = selector.select(universe, intents, "child", "GREEN")
        assert bundle.policy_verdict == "needs_hil"
        assert len(bundle.hil_triggers) >= 1
        assert any(g.gate_type == "hil_trigger" for g in bundle.gates)

    def test_parent_write_no_hil(self, selector):
        universe = _universe(_candidate("family.messaging"))
        intents = [_write_intent("family.messaging", "tool.execute.family.messaging.send")]
        bundle = selector.select(universe, intents, "parent", "GREEN")
        assert bundle.policy_verdict == "allow"
        assert len(bundle.hil_triggers) == 0


# ══════════════════════════════════════════════════════════════════════
# TestProtectedRead
# ══════════════════════════════════════════════════════════════════════


class TestProtectedRead:
    def test_protected_resource_wrong_role_denied(self, selector):
        universe = _universe(_candidate("family.vault", resource_id="vault_parent_001"))
        intents = [_read_intent("family.vault", "tool.read.family.vault.list")]
        bundle = selector.select(universe, intents, "child", "GREEN")
        assert bundle.policy_verdict == "deny"
        assert bundle.deny_reason == "protected_resource"
        assert bundle.protected_read_policy is not None

    def test_protected_resource_correct_role_allowed(self, selector):
        universe = _universe(_candidate("family.vault", resource_id="vault_parent_001"))
        intents = [_read_intent("family.vault", "tool.read.family.vault.list")]
        bundle = selector.select(universe, intents, "parent", "GREEN")
        assert bundle.policy_verdict == "allow"

    def test_non_protected_resource_allowed(self, selector):
        universe = _universe(_candidate("family.vault", resource_id="vault_shared_001"))
        intents = [_read_intent("family.vault", "tool.read.family.vault.list")]
        bundle = selector.select(universe, intents, "child", "GREEN")
        assert bundle.policy_verdict == "allow"


# ══════════════════════════════════════════════════════════════════════
# TestDefaultAllow
# ══════════════════════════════════════════════════════════════════════


class TestDefaultAllow:
    def test_empty_role_lists_allow_all(self, selector):
        universe = _universe(_candidate("family.calendar"))
        intents = [_write_intent("family.calendar", "tool.execute.family.calendar.create")]
        for role in ("parent", "child", "guest", "admin"):
            bundle = selector.select(universe, intents, role, "GREEN")
            assert bundle.policy_verdict == "allow", f"role {role} should be allowed"


# ══════════════════════════════════════════════════════════════════════
# TestMissingConnectorSkip
# ══════════════════════════════════════════════════════════════════════


class TestMissingConnectorSkip:
    def test_unknown_connector_skipped(self, selector):
        universe = _universe(_candidate("family.nonexistent"))
        intents = [_write_intent("family.nonexistent", "tool.execute.family.nonexistent.create")]
        bundle = selector.select(universe, intents, "child", "GREEN")
        # No connector → no policy to enforce → no false deny
        assert bundle.policy_verdict == "allow"
        assert bundle.deny_reason is None

    def test_direct_candidate_empty_connector_skipped(self, selector):
        universe = _universe(_candidate("", resource_id="res_direct"))
        intents = [
            ResolvedIntentType(
                intent_id="i1",
                domain="family",
                resource_family="calendar_event",
                operation_family="create",
                effect="write",
            )
        ]
        bundle = selector.select(universe, intents, "child", "GREEN")
        assert bundle.policy_verdict == "allow"
        assert bundle.connector_ids == []


# ══════════════════════════════════════════════════════════════════════
# TestVerdictPrecedence
# ══════════════════════════════════════════════════════════════════════


class TestVerdictPrecedence:
    def test_allow_with_gate_for_prerequisite(self, selector):
        universe = _universe(_candidate("family.planner"))
        intents = [_write_intent("family.planner", "tool.execute.family.planner.create")]
        bundle = selector.select(universe, intents, "parent", "GREEN")
        assert bundle.policy_verdict == "allow_with_gate"
        assert any(g.gate_type == "precondition" for g in bundle.gates)

    def test_verifier_requirements_populated(self, selector):
        universe = _universe(_candidate("family.planner"))
        intents = [_write_intent("family.planner", "tool.execute.family.planner.create")]
        bundle = selector.select(universe, intents, "parent", "GREEN")
        assert "tool.execute.family.planner.create" in bundle.verifier_requirements
        assert (
            bundle.verifier_requirements["tool.execute.family.planner.create"] == "read_after_write"
        )

    def test_deny_beats_hil(self, selector):
        """A deny (role) on one connector beats a HIL on another."""
        universe = _universe(
            _candidate("family.chores"),
            _candidate("family.messaging"),
        )
        intents = [
            _write_intent("family.chores", "tool.execute.family.chores.create"),
            _write_intent("family.messaging", "tool.execute.family.messaging.send"),
        ]
        bundle = selector.select(universe, intents, "child", "GREEN")
        # chores denies child write; messaging triggers HIL — deny wins
        assert bundle.policy_verdict == "deny"

    def test_hil_beats_allow_with_gate(self, selector):
        """HIL on one connector beats a soft gate on another."""
        universe = _universe(
            _candidate("family.messaging"),
            _candidate("family.planner"),
        )
        intents = [
            _write_intent("family.messaging", "tool.execute.family.messaging.send"),
            _write_intent("family.planner", "tool.execute.family.planner.create"),
        ]
        bundle = selector.select(universe, intents, "child", "GREEN")
        # messaging triggers HIL; planner has soft gate — HIL wins
        assert bundle.policy_verdict == "needs_hil"
