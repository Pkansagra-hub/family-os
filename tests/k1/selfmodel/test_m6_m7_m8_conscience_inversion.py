"""M6/M7/M8 — conscience inversion, typed user content, gate hardening.

Tests the inverted constitutional model:
* M6: ``ConscienceDigest`` contract + composer always populates it.
* M7: Typed ``L3PatternShape``, typed writers, ``SelfView`` projection,
  and capsule blocks (``[self]/[preferences]/[hobbies]/[goals]/...``).
* M8: Conscience-aware ``PolicyEvaluator``, fail-closed risk default,
  and wrapper-tool unwrapping in ``ConciergePolicyGate``.
"""

from __future__ import annotations

import pytest

from k1.selfmodel.contracts.conscience import (
    ConscienceBucket,
    ConscienceDigest,
    SocialAct,
)
from k1.selfmodel.contracts.constitution_body import (
    get_conscience_bucket,
    is_v1_schema,
)
from k1.selfmodel.contracts.pattern import (
    Goal,
    Habit,
    L3PatternShape,
    coerce_l3,
)
from k1.selfmodel.contracts.policy import (
    FreshnessState,
    PolicyDecision,
    PolicyRequest,
    ReasonCode,
    RiskClass,
)
from k1.selfmodel.contracts.risk_class_registry import (
    FAIL_CLOSED_DEFAULT,
    get_risk_class,
    reset_unknown_warnings,
)
from k1.selfmodel.contracts.situation import (
    ApplicableRules,
    Capabilities,
    SelfView,
    SituationFrame,
    Visibility,
)
from k1.selfmodel.service.policy_evaluator import PolicyEvaluator


# =====================================================================
# M6.E2 — ConscienceDigest contract
# =====================================================================
class TestConscienceDigest:
    def test_default_is_empty_default_allow(self) -> None:
        d = ConscienceDigest()
        assert d.forbidden_acts == ()
        assert d.must_ask_acts == ()
        assert d.is_forbidden("anything") is False
        assert d.is_must_ask("anything") is False

    def test_is_forbidden_and_must_ask(self) -> None:
        d = ConscienceDigest(
            forbidden_acts=("set_medication",),
            must_ask_acts=("send_message",),
        )
        assert d.is_forbidden("set_medication") is True
        assert d.is_forbidden("send_message") is False
        assert d.is_must_ask("send_message") is True

    def test_to_json_roundtrip(self) -> None:
        d = ConscienceDigest(
            forbidden_acts=("a",),
            must_ask_acts=("b",),
            risk_overrides={"c": "high"},
            tier_floor={"d": 2},
            protections=("p1",),
        )
        j = d.to_json()
        assert j["forbidden_acts"] == ["a"]
        assert j["must_ask_acts"] == ["b"]
        assert j["risk_overrides"] == {"c": "high"}
        assert j["tier_floor"] == {"d": 2}
        assert j["protections"] == ["p1"]

    def test_social_act_shape(self) -> None:
        a = SocialAct(act_id="share_loc", display_name="Share location", category="privacy")
        assert a.act_id == "share_loc"
        assert a.category == "privacy"

    def test_bucket_defaults(self) -> None:
        b = ConscienceBucket()
        assert b.forbidden == ()
        assert b.must_ask == ()


# =====================================================================
# M6.E4 — get_conscience_bucket dispatches v0/v1
# =====================================================================
class TestConsciencBucketDispatch:
    def test_v0_derives_from_autonomy_rules(self) -> None:
        body = {
            "autonomy_rules": {
                "guardian": {
                    "can": ["recall_memory"],
                    "must_ask": ["send_message"],
                    "cannot": ["set_medication"],
                },
            },
            "authority_rules": {"send_message": 2, "set_medication": 3},
        }
        bucket = get_conscience_bucket(body, role="guardian")
        assert "set_medication" in bucket.forbidden
        assert "send_message" in bucket.must_ask
        assert bucket.tier_floor.get("send_message") == 2
        assert bucket.tier_floor.get("set_medication") == 3

    def test_v1_reads_native_conscience_rules(self) -> None:
        body = {
            "schema_version": 1,
            "conscience_rules": {
                "child": {
                    "forbidden": ["make_payment"],
                    "must_ask": ["send_message"],
                    "tier_floor": {"send_message": 2},
                    "risk_overrides": {"send_message": "high"},
                },
            },
        }
        assert is_v1_schema(body) is True
        bucket = get_conscience_bucket(body, role="child")
        assert bucket.forbidden == ("make_payment",)
        assert bucket.must_ask == ("send_message",)
        assert bucket.tier_floor == {"send_message": 2}
        assert bucket.risk_overrides == {"send_message": "high"}

    def test_unknown_role_returns_empty(self) -> None:
        body = {"schema_version": 1, "conscience_rules": {}}
        bucket = get_conscience_bucket(body, role="ghost")
        assert bucket.forbidden == ()
        assert bucket.must_ask == ()


# =====================================================================
# M7.E1 — L3PatternShape contract + coerce_l3 migration
# =====================================================================
class TestL3PatternShape:
    def test_default_is_empty(self) -> None:
        shape = L3PatternShape()
        assert shape.is_empty() is True

    def test_to_json_roundtrip(self) -> None:
        shape = L3PatternShape(
            preferences={"theme": "dark"},
            hobbies=("hiking",),
            goals=(Goal(goal_id="g1", summary="run 5k"),),
            habits=(Habit(habit_id="h1", summary="read", cadence="daily"),),
            communication_style="brief",
        )
        j = shape.to_json()
        assert j["preferences"] == {"theme": "dark"}
        assert j["hobbies"] == ["hiking"]
        assert j["goals"][0]["goal_id"] == "g1"
        assert j["habits"][0]["cadence"] == "daily"
        assert j["communication_style"] == "brief"

    def test_coerce_from_legacy_dict(self) -> None:
        legacy = {
            "preferences": {"theme": "dark"},
            "hobbies": ["hiking", "reading"],
            "goals": [{"goal_id": "g1", "summary": "run 5k"}],
        }
        shape = coerce_l3(legacy)
        assert shape.preferences == {"theme": "dark"}
        assert shape.hobbies == ("hiking", "reading")
        assert shape.goals[0].goal_id == "g1"

    def test_coerce_none_returns_empty(self) -> None:
        assert coerce_l3(None).is_empty() is True

    def test_merged_with_preferences(self) -> None:
        shape = L3PatternShape(preferences={"theme": "dark"})
        new = shape.merged_with("preferences", {"font": "mono"})
        assert new.preferences == {"theme": "dark", "font": "mono"}

    def test_merged_with_unknown_kind_returns_self(self) -> None:
        shape = L3PatternShape()
        same = shape.merged_with("unknown_bucket", {"x": 1})
        assert same is shape


# =====================================================================
# M12.E2.I1 — fail-OPEN risk default (was M8.E2 fail-closed)
# =====================================================================
class TestFailClosedRisk:
    def test_default_is_low(self) -> None:
        assert FAIL_CLOSED_DEFAULT == RiskClass.LOW

    def test_unmapped_tool_fails_open(self) -> None:
        reset_unknown_warnings()
        assert get_risk_class("ghost_tool_x") == RiskClass.LOW

    def test_legacy_safety_sensitive_default_via_arg(self) -> None:
        reset_unknown_warnings()
        assert (
            get_risk_class("ghost_tool_y", default=RiskClass.SAFETY_SENSITIVE)
            == RiskClass.SAFETY_SENSITIVE
        )


# =====================================================================
# M8.E1 — PolicyEvaluator conscience-first path
# =====================================================================
def _frame_with_conscience(
    *,
    forbidden: tuple[str, ...] = (),
    must_ask: tuple[str, ...] = (),
    tier_floor: dict[str, int] | None = None,
    risk_overrides: dict[str, str] | None = None,
) -> SituationFrame:
    return SituationFrame(
        actor_id="a1",
        situation_kind="caregiver_context_briefing",
        rules=ApplicableRules(),
        capabilities=Capabilities(),  # legacy field — empty; conscience drives decisions
        conscience=ConscienceDigest(
            forbidden_acts=forbidden,
            must_ask_acts=must_ask,
            tier_floor=dict(tier_floor or {}),
            risk_overrides=dict(risk_overrides or {}),
        ),
        visibility=Visibility(),
    )


class TestConscienceFirstEvaluator:
    def test_unmentioned_act_default_allow(self) -> None:
        frame = _frame_with_conscience()
        ev = PolicyEvaluator()
        v = ev.evaluate(
            PolicyRequest(actor_id="a1", tool_name="random_act", risk_class=RiskClass.LOW),
            frame,
            freshness_state=FreshnessState.FRESH,
        )
        assert v.decision == PolicyDecision.ALLOW

    def test_forbidden_act_denied(self) -> None:
        frame = _frame_with_conscience(forbidden=("set_medication",))
        ev = PolicyEvaluator()
        v = ev.evaluate(
            PolicyRequest(actor_id="a1", tool_name="set_medication", risk_class=RiskClass.LOW),
            frame,
        )
        assert v.decision == PolicyDecision.DENY
        assert v.reason == ReasonCode.CAPABILITY_NOT_GRANTED

    def test_must_ask_upgrades_allow_to_confirmation(self) -> None:
        frame = _frame_with_conscience(must_ask=("send_message",))
        ev = PolicyEvaluator()
        v = ev.evaluate(
            PolicyRequest(actor_id="a1", tool_name="send_message", risk_class=RiskClass.LOW),
            frame,
        )
        assert v.decision == PolicyDecision.REQUIRE_CONFIRMATION
        assert v.reason == ReasonCode.NEEDS_CONFIRMATION

    def test_tier_floor_requires_identity(self) -> None:
        frame = _frame_with_conscience(tier_floor={"set_medication": 3})
        ev = PolicyEvaluator()
        v = ev.evaluate(
            PolicyRequest(actor_id="a1", tool_name="set_medication", risk_class=RiskClass.LOW),
            frame,
            current_tier=1,
        )
        assert v.decision == PolicyDecision.REQUIRE_IDENTITY
        assert v.requires_tier == 3

    def test_risk_override_bumps_baseline(self) -> None:
        # baseline LOW + FRESH → ALLOW; override to SAFETY_SENSITIVE +
        # FRESH → ALLOW (still allowed by matrix). Use STALE to flip.
        frame = _frame_with_conscience(risk_overrides={"send_message": "safety_sensitive"})
        ev = PolicyEvaluator()
        v = ev.evaluate(
            PolicyRequest(actor_id="a1", tool_name="send_message", risk_class=RiskClass.LOW),
            frame,
            freshness_state=FreshnessState.STALE,
        )
        # SAFETY_SENSITIVE × STALE → DEFER_OFFLINE per default matrix.
        assert v.decision == PolicyDecision.DEFER_OFFLINE


# =====================================================================
# M7.E2 — typed L3 writers + SelfView projection through composer
# =====================================================================
class TestTypedL3WritersAndComposer:
    def test_self_model_typed_writers_persist(self) -> None:
        from k1.selfmodel.adapters.memory_projection_store import (
            InMemoryProjectionStore,
        )
        from k1.selfmodel.contracts.space_graph import RoutineRef
        from k1.selfmodel.service.self_model import SelfModelService

        store = InMemoryProjectionStore()
        svc = SelfModelService(store=store)
        # Seed identity-only snapshot.
        from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot

        snap = K1SelfModelSnapshot(actor_id="alice", L1_core={"display_name": "Alice"})
        store.write_self(snap, writer_id="selfmodel:self_model_service")

        svc.write_preferences("alice", {"theme": "dark"})
        svc.write_hobbies("alice", ("hiking", "reading"))
        svc.write_goals("alice", (Goal(goal_id="g1", summary="run 5k"),))
        svc.write_routines(
            "alice", (RoutineRef(routine_id="r1", name="morning", schedule="07:00"),)
        )
        svc.set_communication_style("alice", "brief")

        shape = svc.get_pattern_shape("alice")
        assert shape.preferences == {"theme": "dark"}
        assert shape.hobbies == ("hiking", "reading")
        assert shape.goals[0].goal_id == "g1"
        assert shape.routines[0].routine_id == "r1"
        assert shape.communication_style == "brief"


# =====================================================================
# M8 — wrapper unwrapping in policy gate
# =====================================================================
class TestWrapperUnwrap:
    def test_resolve_effective_tool_for_invoke_capability(self) -> None:
        from k1.concierge.llm.types import ToolCallResult
        from k1.selfmodel.adapters.concierge_policy_gate import (
            _resolve_effective_tool,
        )

        tc = ToolCallResult(
            id="t1",
            name="invoke_capability",
            arguments={"capability_name": "send_message", "payload": {}},
        )
        effective, unwrapped = _resolve_effective_tool(tc)
        assert effective == "send_message"
        assert unwrapped is True

    def test_resolve_passthrough_for_non_wrapper(self) -> None:
        from k1.concierge.llm.types import ToolCallResult
        from k1.selfmodel.adapters.concierge_policy_gate import (
            _resolve_effective_tool,
        )

        tc = ToolCallResult(id="t1", name="recall_memory", arguments={})
        effective, unwrapped = _resolve_effective_tool(tc)
        assert effective == "recall_memory"
        assert unwrapped is False


# =====================================================================
# M7 capsule — SelfView block rendering
# =====================================================================
class TestCapsuleSelfBlock:
    def test_self_block_rendered_when_self_view_present(self) -> None:
        from k1.selfmodel.service.capsule_builder import GroundingCapsuleBuilder

        sv = SelfView(
            actor_id="a1",
            display_name="Alice",
            role="guardian",
            communication_style="brief",
            preferences={"theme": "dark"},
            hobbies=("hiking",),
            goals=(Goal(goal_id="g1", summary="run 5k"),),
        )
        frame = SituationFrame(
            actor_id="a1",
            situation_kind="caregiver_context_briefing",
            self_view=sv,
            conscience=ConscienceDigest(forbidden_acts=("set_medication",)),
        )
        cap = GroundingCapsuleBuilder().build(frame)
        text = cap.as_prompt_text()
        assert "[self]" in text
        assert "name=Alice" in text
        assert "[preferences]" in text
        assert "theme=dark" in text
        assert "[hobbies]" in text
        assert "hiking" in text
        assert "[goals]" in text
        assert "[conscience]" in text
        assert "set_medication" in text
        assert "[context]" in text
        assert "communication_style=brief" in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
