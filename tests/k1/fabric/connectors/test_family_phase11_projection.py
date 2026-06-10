"""Phase 1.1 (Epics 9-10): GlobalProjectionStore projection for family connectors.

Validates ``register_definition_to_store`` for the enriched Calendar and Tasks
connectors: connector record (resource_kinds, policy, guide cards),
capabilities with registry-matching names, constitution load + structural
validation, ontology graph edges, and typed ``capability_type_index``
resolution.

Uses an isolated ``tmp_path`` store per test to avoid the shared fixed-path
pollution seen in the legacy store test fixtures.
"""

from __future__ import annotations

import pytest

from k1.fabric.constitution.loader import ConstitutionLoader
from k1.fabric.constitution.schema import validate_constitution
from k1.fabric.manifest_translator import register_definition_to_store
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.tools.family.calendar.definition import CALENDAR_DEFINITION
from k1.tools.family.chores.definition import CHORES_DEFINITION
from k1.tools.family.reminders.definition import REMINDERS_DEFINITION
from k1.tools.family.shopping.definition import SHOPPING_DEFINITION
from k1.tools.family.tasks.definition import TASKS_DEFINITION

# All five enriched Phase 1.1 connectors.
_ALL_DEFINITIONS = [
    CALENDAR_DEFINITION,
    TASKS_DEFINITION,
    REMINDERS_DEFINITION,
    CHORES_DEFINITION,
    SHOPPING_DEFINITION,
]


@pytest.fixture
def store(tmp_path):
    """A fresh GlobalProjectionStore with all 5 family connectors projected in."""
    s = GlobalProjectionStore(str(tmp_path / "gps.db"))
    s.open()
    for d in _ALL_DEFINITIONS:
        register_definition_to_store(d, s)
    yield s
    s.close()


# ── Connector record projection ────────────────────────────────────────


class TestConnectorProjection:
    def test_both_connectors_registered(self, store):
        ids = {c.connector_id for c in store.list_connectors()}
        assert ids == {
            "family.calendar",
            "family.tasks",
            "family.reminders",
            "family.chores",
            "family.shopping",
        }

    def test_calendar_connector_fields(self, store):
        c = store.get_connector("family.calendar")
        assert c.connector_type == "native"
        assert c.provider_type == "LOCAL"
        assert c.resource_kinds == ["calendar_event", "appointment"]
        gates = c.policy_declarations["operation_role_gates"]
        assert gates["create_event"] == ["parent", "child", "guardian"]
        assert gates["set_visibility"] == ["parent"]

    def test_tasks_connector_fields(self, store):
        c = store.get_connector("family.tasks")
        assert c.resource_kinds == ["task"]
        gates = c.policy_declarations["operation_role_gates"]
        # reopen_task gated even though the design's policy table omitted it.
        assert "reopen_task" in gates


# ── Capability names MUST match the CapabilityRegistry convention ──────


class TestCapabilityNames:
    def test_calendar_names_match_registry(self, store):
        caps = {c.capability_name for c in store.get_capabilities_by_connector("family.calendar")}
        assert "tool.execute.calendar.create_event" in caps
        assert "tool.read.calendar.list_events" in caps

    def test_tasks_names_match_registry(self, store):
        caps = {c.capability_name for c in store.get_capabilities_by_connector("family.tasks")}
        assert "tool.execute.tasks.create_task" in caps
        assert "tool.execute.tasks.complete_task" in caps

    def test_capability_modes_and_effects(self, store):
        by_name = {
            c.capability_name: c for c in store.get_capabilities_by_connector("family.calendar")
        }
        create = by_name["tool.execute.calendar.create_event"]
        assert create.invocation_mode == "execute"
        assert create.effect == "write"
        assert create.resource_kind == "calendar_event"
        list_ev = by_name["tool.read.calendar.list_events"]
        assert list_ev.invocation_mode == "read"
        assert list_ev.effect == "read"


# ── Constitution: store -> load -> structural validation ───────────────


class TestConstitutionProjection:
    def test_calendar_constitution_loads_and_validates(self, store):
        artifact = ConstitutionLoader(store).load("family.calendar")
        assert artifact is not None
        assert artifact.connector_id == "family.calendar"
        assert len(artifact.prerequisite_reads) == 3
        assert len(artifact.hil_gates) == 7
        assert any(r.resolution for r in artifact.conflict_analysis_rules)

    def test_tasks_constitution_loads_and_validates(self, store):
        artifact = ConstitutionLoader(store).load("family.tasks")
        assert artifact is not None
        assert artifact.connector_id == "family.tasks"
        assert {c.resource_kind for c in artifact.companion_resource_roles} == {
            "calendar_event",
            "chore",
        }

    def test_source_constitutions_are_schema_valid(self):
        # The declared dicts themselves pass structural validation.
        assert validate_constitution(CALENDAR_DEFINITION.constitution)
        assert validate_constitution(TASKS_DEFINITION.constitution)


# ── Typed resolution (capability_type_index + ontology graph) ──────────


class TestTypedResolution:
    def test_calendar_create_typed_lookup(self, store):
        res = store.lookup_capability_by_type("family", "calendar_event", "create", "write")
        names = {r["capability_name"] for r in res}
        assert "tool.execute.calendar.create_event" in names

    def test_tasks_complete_typed_lookup(self, store):
        res = store.lookup_capability_by_type("family", "task", "complete", "write")
        names = {r["capability_name"] for r in res}
        assert names == {"tool.execute.tasks.complete_task"}

    def test_calendar_concept_alias_resolves(self, store):
        res = store.resolve_concept("dentist", "family")
        assert any(r["canonical_concept"] == "appointment" for r in res)

    def test_schedule_operation_alias_resolves(self, store):
        res = store.resolve_operation("schedule")
        assert any(r["operation_family"] == "create" for r in res)

    def test_finish_operation_alias_resolves(self, store):
        res = store.resolve_operation("finish")
        assert any(r["operation_family"] == "complete" for r in res)


# ── Guide cards persistence ────────────────────────────────────────────


class TestGuideCards:
    def test_calendar_guide_cards_persisted(self, store):
        c = store.get_connector("family.calendar")
        ids = {g["guide_id"] for g in c.guide_cards}
        assert ids == {"family.calendar.guide.01", "family.calendar.guide.02"}

    def test_tasks_guide_cards_persisted(self, store):
        c = store.get_connector("family.tasks")
        ids = {g["guide_id"] for g in c.guide_cards}
        assert ids == {"family.tasks.guide.01", "family.tasks.guide.02"}


# ── All 5 connectors: parametrized coverage ────────────────────────────


_CONNECTOR_IDS = [
    "family.calendar",
    "family.tasks",
    "family.reminders",
    "family.chores",
    "family.shopping",
]


class TestAllConnectors:
    @pytest.mark.parametrize("definition", _ALL_DEFINITIONS, ids=lambda d: d.adapter_id)
    def test_source_constitution_is_schema_valid(self, definition):
        # Every connector's declared constitution passes structural validation
        # (including the `resolution` field on conflict_analysis_rules).
        artifact = validate_constitution(definition.constitution)
        assert artifact.connector_id == f"family.{definition.adapter_id}"

    @pytest.mark.parametrize("connector_id", _CONNECTOR_IDS)
    def test_constitution_loads_from_store(self, store, connector_id):
        artifact = ConstitutionLoader(store).load(connector_id)
        assert artifact is not None
        assert artifact.connector_id == connector_id
        assert len(artifact.prerequisite_reads) >= 1

    @pytest.mark.parametrize("definition", _ALL_DEFINITIONS, ids=lambda d: d.adapter_id)
    def test_policy_gates_reference_real_action_names(self, definition):
        # Every operation_role_gates key MUST be a real action on the
        # connector, otherwise PolicySelectorService cannot gate it.
        real_actions = {a.name for a in definition.actions}
        gates = (definition.policy_declarations or {}).get("operation_role_gates", {})
        unknown = set(gates) - real_actions
        assert not unknown, f"{definition.adapter_id}: policy gates unknown actions {unknown}"

    @pytest.mark.parametrize("definition", _ALL_DEFINITIONS, ids=lambda d: d.adapter_id)
    def test_capability_names_match_registry_convention(self, store, definition):
        # The store capability names must equal the CapabilityRegistry names
        # (tool.<read|execute>.<adapter_id>.<action_name>) so a resolver
        # binding dispatches through the existing NativeToolProvider.
        connector_id = f"family.{definition.adapter_id}"
        store_names = {c.capability_name for c in store.get_capabilities_by_connector(connector_id)}
        for action in definition.actions:
            prefix = "tool.read" if action.kind == "read" else "tool.execute"
            expected = f"{prefix}.{definition.adapter_id}.{action.name}"
            assert expected in store_names

    @pytest.mark.parametrize("definition", _ALL_DEFINITIONS, ids=lambda d: d.adapter_id)
    def test_guide_cards_persisted(self, store, definition):
        connector_id = f"family.{definition.adapter_id}"
        c = store.get_connector(connector_id)
        declared = {g["guide_id"] for g in (definition.guide_cards or [])}
        persisted = {g["guide_id"] for g in c.guide_cards}
        assert persisted == declared
        assert declared, f"{definition.adapter_id} should declare guide cards"


# ── Grounded typed resolution for the 3 new connectors ─────────────────


class TestNewConnectorTypedResolution:
    def test_reminder_create_typed_lookup(self, store):
        res = store.lookup_capability_by_type("family", "reminder", "create", "write")
        names = {r["capability_name"] for r in res}
        assert "tool.execute.reminders.create_reminder" in names

    def test_chore_assign_typed_lookup(self, store):
        res = store.lookup_capability_by_type("family", "chore", "assign", "write")
        names = {r["capability_name"] for r in res}
        assert "tool.execute.chores.assign_chore" in names

    def test_shopping_add_typed_lookup(self, store):
        res = store.lookup_capability_by_type("family", "shopping_item", "add", "write")
        names = {r["capability_name"] for r in res}
        assert "tool.execute.shopping.add_item" in names

    def test_buy_operation_alias_resolves_to_check(self, store):
        res = store.resolve_operation("buy")
        assert any(r["operation_family"] == "check" for r in res)

    def test_skip_operation_alias_resolves(self, store):
        res = store.resolve_operation("skip")
        assert any(r["operation_family"] == "skip" for r in res)
