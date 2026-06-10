"""GAP-P1-008 — Tests for ConstitutionArtifact schema (5.1) + ConstitutionLoader (5.2)."""

from __future__ import annotations

import dataclasses

import pytest

from k1.fabric.connectors.definition import ConstitutionDefinition
from k1.fabric.constitution.loader import ConstitutionLoader
from k1.fabric.constitution.schema import (
    CompanionResourceRole,
    ConflictRule,
    ConstitutionArtifact,
    ConstitutionValidationError,
    HILGate,
    MutationStep,
    PrerequisiteRead,
    VerificationRequirement,
    validate_constitution,
    validate_constitution_semantics,
)
from k1.fabric.stores.global_projection_store import (
    ConnectorRecord,
    ConstitutionRecord,
    GlobalProjectionStore,
)

# ──────────────────────────────────────────────────────────────────────
# Fixtures / data
# ──────────────────────────────────────────────────────────────────────

_VALID: dict = {
    "connector_id": "family.calendar",
    "constitution_id": "family.calendar.v1",
    "schema_version": "1.0.0",
    "execution_phases": ["read", "mutate"],
    "prerequisite_reads": [
        {
            "operation": "list",
            "resource_kind": "calendar_event",
            "reason": "Check conflicts before create.",
            "required": True,
            "timeout_ms": 5000,
        }
    ],
    "conflict_analysis_rules": [
        {
            "check": "time_overlap",
            "with_resource_kinds": ["calendar_event"],
            "description": "No overlap.",
        }
    ],
    "companion_resource_roles": [
        {"resource_kind": "task", "role": "conflict_source", "description": ""}
    ],
    "hil_gates": [
        {
            "trigger": "missing_required_field",
            "field": "end",
            "prompt": "What time should this end?",
            "options": [],
        }
    ],
    "mutation_sequencing": [
        {"order": 1, "phase": "read", "operation": "list", "description": ""},
        {"order": 2, "phase": "mutate", "operation": "create", "description": ""},
    ],
    "verification_requirements": [{"method": "read_after_write", "required_for_submit": True}],
    "precondition_summary": "List calendar before create.",
    "companion_resource_summary": None,
    "hil_trigger_summary": "HIL on missing end time.",
    "degradation_policy": "Retry once then degrade.",
}

_KNOWN_RKS = {"calendar_event", "task"}


@pytest.fixture
def store() -> GlobalProjectionStore:
    s = GlobalProjectionStore(db_path=":memory:")
    s.open()
    return s


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


def _record_from_valid(connector_id: str = "family.calendar") -> ConstitutionRecord:
    d = dict(_VALID)
    d["connector_id"] = connector_id
    d["constitution_id"] = f"{connector_id}.v1"
    return ConstitutionRecord(
        connector_id=connector_id,
        constitution_id=d["constitution_id"],
        schema_version=d["schema_version"],
        execution_phases=d["execution_phases"],
        prerequisite_reads=d["prerequisite_reads"],
        conflict_analysis_rules=d["conflict_analysis_rules"],
        hil_gates=d["hil_gates"],
        mutation_sequencing=d["mutation_sequencing"],
        verification_requirements=d["verification_requirements"],
        companion_resource_roles=d["companion_resource_roles"],
        precondition_summary=d["precondition_summary"],
        companion_resource_summary=d["companion_resource_summary"],
        hil_trigger_summary=d["hil_trigger_summary"],
        degradation_policy=d["degradation_policy"],
    )


# ══════════════════════════════════════════════════════════════════════
# TestStructuralValidation
# ══════════════════════════════════════════════════════════════════════


class TestStructuralValidation:
    def test_valid_full_constitution(self):
        artifact = validate_constitution(_VALID)
        assert isinstance(artifact, ConstitutionArtifact)
        assert artifact.connector_id == "family.calendar"
        assert len(artifact.prerequisite_reads) == 1
        assert isinstance(artifact.prerequisite_reads[0], PrerequisiteRead)
        assert len(artifact.mutation_sequencing) == 2

    def test_missing_connector_id(self):
        bad = {k: v for k, v in _VALID.items() if k != "connector_id"}
        with pytest.raises(ConstitutionValidationError):
            validate_constitution(bad)

    def test_missing_execution_phases(self):
        bad = {k: v for k, v in _VALID.items() if k != "execution_phases"}
        with pytest.raises(ConstitutionValidationError):
            validate_constitution(bad)

    def test_wrong_type_prerequisite_reads(self):
        bad = dict(_VALID)
        bad["prerequisite_reads"] = "not a list"
        with pytest.raises(ConstitutionValidationError):
            validate_constitution(bad)

    def test_schema_version_not_semver(self):
        bad = dict(_VALID)
        bad["schema_version"] = "1.0"
        with pytest.raises(ConstitutionValidationError):
            validate_constitution(bad)

    def test_timeout_ms_below_minimum(self):
        bad = dict(_VALID)
        bad["prerequisite_reads"] = [
            {
                "operation": "list",
                "resource_kind": "calendar_event",
                "reason": "x",
                "timeout_ms": 500,  # below 1000 minimum
            }
        ]
        with pytest.raises(ConstitutionValidationError):
            validate_constitution(bad)

    def test_empty_execution_phases(self):
        bad = dict(_VALID)
        bad["execution_phases"] = []
        with pytest.raises(ConstitutionValidationError):
            validate_constitution(bad)

    def test_extra_unknown_field(self):
        bad = dict(_VALID)
        bad["surprise"] = "boom"
        with pytest.raises(ConstitutionValidationError):
            validate_constitution(bad)


# ══════════════════════════════════════════════════════════════════════
# TestSemanticValidation
# ══════════════════════════════════════════════════════════════════════


class TestSemanticValidation:
    def test_all_resource_kinds_valid(self):
        artifact = validate_constitution(_VALID)
        violations = validate_constitution_semantics(artifact, _KNOWN_RKS)
        assert violations == []

    def test_one_unknown_resource_kind(self):
        artifact = validate_constitution(_VALID)
        violations = validate_constitution_semantics(artifact, {"calendar_event"})
        # 'task' (companion) is now unknown
        assert any("task" in v for v in violations)

    def test_mutation_step_undeclared_phase(self):
        bad = dict(_VALID)
        bad["mutation_sequencing"] = [{"order": 1, "phase": "teleport", "operation": "list"}]
        artifact = validate_constitution(bad)
        violations = validate_constitution_semantics(artifact, _KNOWN_RKS)
        assert any("teleport" in v for v in violations)

    def test_verifier_method_unknown(self):
        bad = dict(_VALID)
        bad["verification_requirements"] = [{"method": "telepathy"}]
        artifact = validate_constitution(bad)
        violations = validate_constitution_semantics(artifact, _KNOWN_RKS)
        assert any("telepathy" in v for v in violations)

    def test_empty_known_resource_kinds_all_fail(self):
        artifact = validate_constitution(_VALID)
        violations = validate_constitution_semantics(artifact, set())
        # prerequisite (calendar_event), conflict (calendar_event), companion (task)
        assert len(violations) >= 3

    def test_multiple_violations_returned(self):
        bad = dict(_VALID)
        bad["mutation_sequencing"] = [{"order": 1, "phase": "teleport", "operation": "list"}]
        bad["verification_requirements"] = [{"method": "telepathy"}]
        artifact = validate_constitution(bad)
        violations = validate_constitution_semantics(artifact, set())
        assert len(violations) >= 2


# ══════════════════════════════════════════════════════════════════════
# TestSubTypeRoundtrip
# ══════════════════════════════════════════════════════════════════════


class TestSubTypeRoundtrip:
    def test_prerequisite_read_roundtrip(self):
        d = {
            "operation": "list",
            "resource_kind": "calendar_event",
            "reason": "x",
            "required": False,
            "timeout_ms": 3000,
        }
        pr = PrerequisiteRead.from_dict(d)
        assert pr.required is False
        assert pr.timeout_ms == 3000
        assert pr.to_dict() == d

    def test_hil_gate_with_options(self):
        d = {
            "trigger": "time_conflict_detected",
            "prompt": "Conflict — proceed?",
            "field": None,
            "options": ["Create anyway", "Cancel"],
        }
        g = HILGate.from_dict(d)
        assert g.options == ["Create anyway", "Cancel"]
        assert g.field is None
        assert g.to_dict()["options"] == ["Create anyway", "Cancel"]

    def test_mutation_step_ordering(self):
        d = {"order": 3, "phase": "mutate", "operation": "create", "description": "x"}
        s = MutationStep.from_dict(d)
        assert s.order == 3
        assert s.to_dict() == d

    def test_verification_requirement_required_for_submit(self):
        d = {"method": "read_after_write", "description": "verify", "required_for_submit": True}
        v = VerificationRequirement.from_dict(d)
        assert v.required_for_submit is True
        assert v.to_dict() == d


# ══════════════════════════════════════════════════════════════════════
# TestCoherence
# ══════════════════════════════════════════════════════════════════════


class TestCoherence:
    def test_constitution_definition_to_artifact(self):
        definition = ConstitutionDefinition(
            connector_id="family.calendar",
            constitution_id="family.calendar.v1",
            schema_version="1.0.0",
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
        data = dataclasses.asdict(definition)
        artifact = validate_constitution(data)
        assert artifact.connector_id == "family.calendar"
        assert artifact.prerequisite_reads[0].resource_kind == "calendar_event"

    def test_constitution_record_to_artifact(self, store):
        _connector(store, "family.calendar")
        store.upsert_constitution(_record_from_valid("family.calendar"))
        loader = ConstitutionLoader(store)
        artifact = loader.load("family.calendar")
        assert artifact is not None
        assert artifact.constitution_id == "family.calendar.v1"

    def test_artifact_to_dict_idempotent(self):
        artifact = validate_constitution(_VALID)
        d1 = artifact.to_dict()
        artifact2 = validate_constitution(d1)
        d2 = artifact2.to_dict()
        assert d1 == d2


# ══════════════════════════════════════════════════════════════════════
# TestConstitutionLoader
# ══════════════════════════════════════════════════════════════════════


class TestConstitutionLoader:
    def test_load_existing(self, store):
        _connector(store, "family.calendar")
        store.upsert_constitution(_record_from_valid("family.calendar"))
        loader = ConstitutionLoader(store)
        artifact = loader.load("family.calendar")
        assert artifact is not None
        assert len(artifact.prerequisite_reads) == 1
        assert isinstance(artifact.hil_gates[0], HILGate)

    def test_load_missing_returns_none(self, store):
        loader = ConstitutionLoader(store)
        assert loader.load("family.ghost") is None

    def test_load_with_semantic_passes(self, store):
        _connector(store, "family.calendar")
        store.upsert_constitution(_record_from_valid("family.calendar"))
        loader = ConstitutionLoader(store)
        artifact = loader.load("family.calendar", known_resource_kinds=_KNOWN_RKS)
        assert artifact is not None

    def test_load_with_semantic_raises_on_unknown(self, store):
        _connector(store, "family.calendar")
        store.upsert_constitution(_record_from_valid("family.calendar"))
        loader = ConstitutionLoader(store)
        with pytest.raises(ConstitutionValidationError):
            loader.load("family.calendar", known_resource_kinds={"calendar_event"})

    def test_load_after_upsert_sees_update(self, store):
        _connector(store, "family.calendar")
        store.upsert_constitution(_record_from_valid("family.calendar"))
        loader = ConstitutionLoader(store)
        first = loader.load("family.calendar")
        assert first.degradation_policy == "Retry once then degrade."
        updated = _record_from_valid("family.calendar")
        updated = dataclasses.replace(updated, degradation_policy="No retry.")
        store.upsert_constitution(updated)
        second = loader.load("family.calendar")
        assert second.degradation_policy == "No retry."

    def test_load_all_skips_invalid(self, store):
        _connector(store, "family.calendar")
        store.upsert_constitution(_record_from_valid("family.calendar"))
        _connector(store, "family.broken")
        broken = _record_from_valid("family.broken")
        broken = dataclasses.replace(broken, schema_version="not-semver")
        store.upsert_constitution(broken)
        loader = ConstitutionLoader(store)
        artifacts = loader.load_all()
        ids = {a.connector_id for a in artifacts}
        assert "family.calendar" in ids
        assert "family.broken" not in ids

    def test_convenience_methods(self, store):
        _connector(store, "family.calendar")
        store.upsert_constitution(_record_from_valid("family.calendar"))
        loader = ConstitutionLoader(store)
        assert len(loader.get_prerequisite_reads("family.calendar")) == 1
        assert all(
            isinstance(v, VerificationRequirement)
            for v in loader.get_verification_requirements("family.calendar")
        )
        assert all(isinstance(g, HILGate) for g in loader.get_hil_gates("family.calendar"))
        assert all(
            isinstance(r, ConflictRule) for r in loader.get_conflict_rules("family.calendar")
        )
        seq = loader.get_mutation_sequence("family.calendar")
        assert [s.order for s in seq] == [1, 2]  # sorted by order

    def test_json_roundtrip(self, store):
        _connector(store, "family.calendar")
        store.upsert_constitution(_record_from_valid("family.calendar"))
        loader = ConstitutionLoader(store)
        artifact = loader.load("family.calendar")
        again = validate_constitution(artifact.to_dict())
        assert again.to_dict() == artifact.to_dict()
