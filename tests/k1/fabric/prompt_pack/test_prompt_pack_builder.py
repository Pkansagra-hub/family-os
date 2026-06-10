"""GAP-P1-011 — Tests for PromptPackBuilder (Epic 6.3)."""

from __future__ import annotations

import pytest

from k1.fabric.connectors.builder import build_connector_definition
from k1.fabric.connectors.definition import (
    CapabilityDefinition,
    ConnectorDefinition,
)
from k1.fabric.connectors.domain_catalog import DOMAIN_SERVICES
from k1.fabric.manifest_admission import ManifestAdmissionService
from k1.fabric.prompt_pack.builder import (
    PHASE_ALLOWED_FIELDS,
    ConstitutionCard,
    PromptPack,
    PromptPackBuilder,
    PromptPackLeakError,
    PromptPackPhaseError,
    SchemaCard,
    ToolNameCard,
    redaction_check,
)
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
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.fabric.stores.local_projection_store import LocalProjectionStore

# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


def _gps() -> GlobalProjectionStore:
    s = GlobalProjectionStore(db_path=":memory:")
    s.open()
    return s


def _lps() -> LocalProjectionStore:
    s = LocalProjectionStore(db_path=":memory:")
    s.open()
    return s


def _frame(
    *,
    operation_hint: str = "list",
    resource_kind_hint: str = "calendar_event",
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


def _request(frame: RequestFrame) -> ResolveSituationRequest:
    return ResolveSituationRequest(
        request_id="req-1",
        frame=frame,
        actor_id="actor-a",
        space_id="space-1",
        session_id="sess-1",
        tier="MEDIUM",
        safety_band="GREEN",
    )


def _resolve(store, local=None, frame=None) -> ResolutionEnvelope:
    ls = local or _lps()
    svc = ResolveSituationService(store, ls)
    return svc.resolve(_request(frame or _frame()))


@pytest.fixture
def read_envelope() -> ResolutionEnvelope:
    store = _gps()
    ManifestAdmissionService(store).admit(
        build_connector_definition("family", DOMAIN_SERVICES["family"][0])
    )
    return _resolve(store)


@pytest.fixture
def builder() -> PromptPackBuilder:
    store = _gps()
    ManifestAdmissionService(store).admit(
        build_connector_definition("family", DOMAIN_SERVICES["family"][0])
    )
    return PromptPackBuilder(store)


def _build_env_and_builder(frame: RequestFrame | None = None, local=None):
    store = _gps()
    ManifestAdmissionService(store).admit(
        build_connector_definition("family", DOMAIN_SERVICES["family"][0])
    )
    ls = local or _lps()
    svc = ResolveSituationService(store, ls)
    env = svc.resolve(_request(frame or _frame()))
    return env, PromptPackBuilder(store)


# ══════════════════════════════════════════════════════════════════════
# TestPromptPackShape
# ══════════════════════════════════════════════════════════════════════


class TestPromptPackShape:
    def test_build_returns_prompt_pack(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(env, disclosure_phase="connector_summary")
        assert isinstance(pack, PromptPack)
        assert pack.prompt_pack_id.startswith("prompt-pack-")
        assert pack.disclosure_phase == "connector_summary"
        assert pack.redaction_summary.verdict == "pass"

    def test_react_state_ready_for_can_execute(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(env, disclosure_phase="connector_summary")
        assert pack.react_state == "ready_to_execute"

    def test_unknown_phase_raises(self):
        env, builder = _build_env_and_builder()
        with pytest.raises(PromptPackPhaseError):
            builder.build(env, disclosure_phase="bogus_phase")

    def test_schema_binding_requires_committed(self):
        env, builder = _build_env_and_builder()
        with pytest.raises(PromptPackPhaseError):
            builder.build(env, disclosure_phase="schema_binding")


# ══════════════════════════════════════════════════════════════════════
# TestStagedDisclosure
# ══════════════════════════════════════════════════════════════════════


class TestStagedDisclosure:
    def test_loop_start_only_summary_and_markers(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(env, disclosure_phase="loop_start")
        assert pack.tool_name_cards == []
        assert pack.policy_cards == []
        assert pack.connector_constitution_cards == []

    def test_connector_summary_has_cards(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(env, disclosure_phase="connector_summary")
        assert pack.connector_constitution_cards  # present
        assert pack.tool_name_cards  # present

    def test_tool_name_selection_no_constitution_cards(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(env, disclosure_phase="tool_name_selection")
        assert pack.connector_constitution_cards == []
        assert pack.tool_name_cards  # tool cards still present
        assert pack.decision_surface  # decision surface present

    def test_execution_only_tool_calls(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(env, disclosure_phase="execution")
        assert pack.connector_constitution_cards == []
        assert pack.policy_cards == []
        assert pack.tool_name_cards == []


# ══════════════════════════════════════════════════════════════════════
# TestRedactionProof
# ══════════════════════════════════════════════════════════════════════


class TestRedactionProof:
    def test_redaction_check_flags_secret_key(self):
        result = redaction_check({"api_key": "abc"})
        assert result["verdict"] == "fail"
        assert "api_key" in result["fields_with_leaks"]

    def test_redaction_check_flags_secret_value(self):
        result = redaction_check({"note": "here is a bearer xyz"})
        assert result["verdict"] == "fail"

    def test_redaction_check_passes_clean(self):
        result = redaction_check(
            {"verdict": "can_execute", "tool": "tool.read.family.calendar.list"}
        )
        assert result["verdict"] == "pass"

    def test_max_prompt_tokens_exception(self):
        # "max_prompt_tokens" contains no secret marker but is whitelisted anyway.
        result = redaction_check({"max_prompt_tokens": 8000})
        assert result["verdict"] == "pass"

    def test_source_leak_raises(self):
        # Custom connector whose capability description contains a secret marker.
        store = _gps()
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
        ManifestAdmissionService(store).admit(leaky)
        ls = _lps()
        svc = ResolveSituationService(store, ls)
        frame = _frame(operation_hint="list", resource_kind_hint="note")
        env = svc.resolve(_request(frame))
        builder = PromptPackBuilder(store)
        with pytest.raises(PromptPackLeakError):
            builder.build(env, disclosure_phase="connector_summary")


# ══════════════════════════════════════════════════════════════════════
# TestConstitutionCards
# ══════════════════════════════════════════════════════════════════════


class TestConstitutionCards:
    def test_constitution_card_from_typed_loader(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(env, disclosure_phase="connector_summary")
        cards = pack.connector_constitution_cards
        assert any(c.connector_id == "family.calendar" for c in cards)
        cal = next(c for c in cards if c.connector_id == "family.calendar")
        assert isinstance(cal, ConstitutionCard)
        assert cal.preconditions  # calendar has prerequisite_reads
        assert cal.verification_requirement in ("read_after_write", "output_schema", "none")

    def test_card_label_from_connector(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(env, disclosure_phase="connector_summary")
        cal = next(
            c for c in pack.connector_constitution_cards if c.connector_id == "family.calendar"
        )
        assert cal.label == "Calendar"


# ══════════════════════════════════════════════════════════════════════
# TestToolNameCards
# ══════════════════════════════════════════════════════════════════════


class TestToolNameCards:
    def test_tool_name_cards_present(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(env, disclosure_phase="connector_summary")
        assert pack.tool_name_cards
        assert all(isinstance(c, ToolNameCard) for c in pack.tool_name_cards)

    def test_primary_capability_in_cards(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(env, disclosure_phase="connector_summary")
        names = {c.capability_name for c in pack.tool_name_cards}
        assert "tool.read.family.calendar.list" in names


# ══════════════════════════════════════════════════════════════════════
# TestPolicyCards
# ══════════════════════════════════════════════════════════════════════


class TestPolicyCards:
    def test_policy_card_present(self):
        # Policy cards come from connectors the policy evaluated → needs a real
        # connected resource (direct candidates have connector_id="").
        store = _gps()
        ManifestAdmissionService(store).admit(
            build_connector_definition("family", DOMAIN_SERVICES["family"][0])
        )
        local = _lps()
        local.upsert_connected_resource(
            {
                "resource_id": "cal-1",
                "actor_id": "actor-a",
                "resource_kind": "calendar_event",
                "connector_id": "family.calendar",
                "label": "My Calendar",
                "permissions": "read_write",
                "freshness_state": "fresh",
                "status": "active",
            }
        )
        local.upsert_alias_index("actor-a", "my calendar", "cal-1", "resource")
        svc = ResolveSituationService(store, local)
        frame = _frame(
            operation_hint="list",
            resource_kind_hint="calendar_event",
            resource_refs=[ResourceRef(raw="my calendar", resource_kind_hint="calendar_event")],
        )
        env = svc.resolve(_request(frame))
        builder = PromptPackBuilder(store)
        pack = builder.build(env, disclosure_phase="connector_summary")
        assert pack.policy_cards
        assert pack.policy_cards[0].connector_id == "family.calendar"


# ══════════════════════════════════════════════════════════════════════
# TestGuideCards
# ══════════════════════════════════════════════════════════════════════


class TestGuideCards:
    def test_guide_cards_empty_in_phase1(self):
        # Phase 1 connectors carry no guide cards (populated in Phase 1.1).
        env, builder = _build_env_and_builder()
        pack = builder.build(env, disclosure_phase="connector_summary")
        assert pack.guide_cards == []


# ══════════════════════════════════════════════════════════════════════
# TestSchemaCards
# ══════════════════════════════════════════════════════════════════════


class TestSchemaCards:
    def test_schema_cards_only_for_committed(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(
            env,
            disclosure_phase="schema_binding",
            committed_tool_names=["tool.read.family.calendar.list"],
        )
        assert len(pack.selected_schema_cards) == 1
        card = pack.selected_schema_cards[0]
        assert isinstance(card, SchemaCard)
        assert card.capability_name == "tool.read.family.calendar.list"
        assert card.input_schema["type"] == "object"

    def test_non_committed_excluded(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(
            env,
            disclosure_phase="schema_binding",
            committed_tool_names=["tool.read.family.calendar.list"],
        )
        names = {c.capability_name for c in pack.selected_schema_cards}
        assert "tool.execute.family.calendar.create" not in names


# ══════════════════════════════════════════════════════════════════════
# TestStaleCardPolicy
# ══════════════════════════════════════════════════════════════════════


class TestStaleCardPolicy:
    def test_stale_card_flagged_not_hidden(self):
        store = _gps()
        ManifestAdmissionService(store).admit(
            build_connector_definition("family", DOMAIN_SERVICES["family"][0])
        )
        local = _lps()
        local.upsert_connected_resource(
            {
                "resource_id": "cal-stale",
                "actor_id": "actor-a",
                "resource_kind": "calendar_event",
                "connector_id": "family.calendar",
                "label": "Stale Cal",
                "permissions": "read_write",
                "freshness_state": "stale",
                "status": "active",
            }
        )
        local.upsert_alias_index("actor-a", "stale cal", "cal-stale", "resource")
        svc = ResolveSituationService(store, local)
        frame = _frame(
            operation_hint="list",
            resource_kind_hint="calendar_event",
            resource_refs=[ResourceRef(raw="stale cal", resource_kind_hint="calendar_event")],
        )
        env = svc.resolve(_request(frame))
        builder = PromptPackBuilder(store)
        pack = builder.build(env, disclosure_phase="connector_summary")
        cal = next(
            (c for c in pack.connector_constitution_cards if c.connector_id == "family.calendar"),
            None,
        )
        assert cal is not None  # NOT hidden
        assert cal.stale is True  # flagged


# ══════════════════════════════════════════════════════════════════════
# TestForbiddenActionGating
# ══════════════════════════════════════════════════════════════════════


class TestForbiddenActionGating:
    def test_forbidden_tools_listed_in_connector_summary(self):
        # Write with incomplete prereq → primary write not in allowed → forbidden.
        env, builder = _build_env_and_builder(
            frame=_frame(
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
            )
        )
        pack = builder.build(env, disclosure_phase="connector_summary")
        # The create capability is not allowed until prereq done → appears forbidden.
        assert any("create" in f for f in pack.forbidden_tool_calls)


# ══════════════════════════════════════════════════════════════════════
# TestRenderBudget
# ══════════════════════════════════════════════════════════════════════


class TestRenderBudget:
    def test_render_produces_markdown(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(env, disclosure_phase="connector_summary")
        text = builder.render(pack)
        assert "## Situated Execution Update" in text
        assert "Phase: connector_summary" in text

    def test_render_respects_budget(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(env, disclosure_phase="connector_summary")
        text = builder.render(pack, budget_tokens=5)
        assert "[truncated]" in text

    def test_render_redaction_clean(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(env, disclosure_phase="connector_summary")
        # Should not raise.
        text = builder.render(pack)
        assert isinstance(text, str)


# ══════════════════════════════════════════════════════════════════════
# TestPhaseFieldWhitelist
# ══════════════════════════════════════════════════════════════════════


class TestPhaseFieldWhitelist:
    def test_all_six_phases_defined(self):
        for phase in (
            "loop_start",
            "connector_summary",
            "tool_name_selection",
            "schema_binding",
            "execution",
            "post_execution",
        ):
            assert phase in PHASE_ALLOWED_FIELDS

    def test_schema_binding_only_schema_and_tools(self):
        allowed = PHASE_ALLOWED_FIELDS["schema_binding"]
        assert allowed == {"selected_schema_cards", "allowed_tool_calls"}

    def test_post_execution_phase_builds(self):
        env, builder = _build_env_and_builder()
        pack = builder.build(env, disclosure_phase="post_execution")
        assert pack.candidate_summary  # allowed
        assert pack.tool_name_cards == []  # not allowed
