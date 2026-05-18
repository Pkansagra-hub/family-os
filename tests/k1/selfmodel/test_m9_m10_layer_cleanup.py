"""M9/M10 -- risk catalog port, conscience port, narrow L3 ports, onboarding."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from k1.selfmodel.adapters.constitution_conscience_port import (
    ConstitutionConsciencePort,
)
from k1.selfmodel.adapters.fabric_risk_catalog import (
    FabricRiskCatalog,
    StaticRiskCatalog,
)
from k1.selfmodel.adapters.l3_ports import L3PortBundle
from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
from k1.selfmodel.contracts.conscience import ConscienceDigest
from k1.selfmodel.contracts.pattern import Goal, Habit
from k1.selfmodel.contracts.policy import RiskClass
from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot
from k1.selfmodel.service.bootstrap_constitution import (
    BOOTSTRAP_CONSTITUTION_ID_V1,
    BOOTSTRAP_VERSION_V1,
    ensure_bootstrap_constitution,
    load_bootstrap_yaml_v1,
)
from k1.selfmodel.service.self_model import SelfModelService

SEED_WRITER_ID = "selfmodel:self_model_service"


# =====================================================================
# M9.E1.I1 -- CapabilityContract carries risk_class / social_act
# =====================================================================
class TestFabricCapabilityMetadata:
    def test_roundtrip_via_from_dict(self) -> None:
        from k1.fabric.types import CapabilityContract

        c = CapabilityContract.from_dict(
            {
                "name": "send_message",
                "version": "1.0.0",
                "risk_class": "high",
                "social_act": "send_message",
            }
        )
        assert c.risk_class == "high"
        assert c.social_act == "send_message"
        d = c.to_dict()
        assert d["risk_class"] == "high"
        assert d["social_act"] == "send_message"

    def test_default_field_is_safety_sensitive(self) -> None:
        """CapabilityContract dataclass default is unchanged at safety_sensitive.
        Only the lookup-fallback (FAIL_CLOSED_DEFAULT) was lowered to LOW in
        M12.E2.I1; the dataclass default remains conservative so contracts
        constructed without a YAML still get a strict risk_class."""
        from k1.fabric.types import CapabilityContract

        c = CapabilityContract()
        assert c.risk_class == "safety_sensitive"
        assert c.social_act is None


# =====================================================================
# M9.E1.I2 -- IRiskCatalogPort + adapters
# =====================================================================
class TestFabricRiskCatalog:
    def test_lookup_from_contract_wins(self) -> None:
        contract = SimpleNamespace(risk_class="medium", social_act="assign_task")
        registry = SimpleNamespace(lookup=lambda name: contract if name == "assign_task" else None)
        cat = FabricRiskCatalog(registry)
        assert cat.get_risk("assign_task") == RiskClass.MEDIUM
        assert cat.get_social_act("assign_task") == "assign_task"

    def test_benign_contract_maps_to_low(self) -> None:
        contract = SimpleNamespace(risk_class="benign", social_act=None)
        registry = SimpleNamespace(
            lookup=lambda name: contract if name == "tool.read.tasks.list_tasks" else None
        )
        cat = FabricRiskCatalog(registry)
        assert cat.get_risk("tool.read.tasks.list_tasks") == RiskClass.LOW

    def test_falls_back_to_legacy_registry(self) -> None:
        registry = SimpleNamespace(lookup=lambda name: None)
        cat = FabricRiskCatalog(registry)
        # ``send_message`` is in the legacy registry as HIGH.
        assert cat.get_risk("send_message") == RiskClass.HIGH

    def test_canonical_name_falls_back_to_legacy_registry(self) -> None:
        registry = SimpleNamespace(lookup=lambda name: None)
        cat = FabricRiskCatalog(registry)
        assert cat.get_risk("tool.execute.tasks.create_task") == RiskClass.MEDIUM

    def test_unknown_capability_fails_open(self) -> None:
        """M12.E2.I1 — lookup-fallback lowered to LOW."""
        registry = SimpleNamespace(lookup=lambda name: None)
        cat = FabricRiskCatalog(registry)
        assert cat.get_risk("totally_unknown_xyz") == RiskClass.LOW
        assert cat.get_social_act("totally_unknown_xyz") is None

    def test_static_catalog_uses_extras(self) -> None:
        cat = StaticRiskCatalog(extra={"my_tool": RiskClass.LOW})
        assert cat.get_risk("my_tool") == RiskClass.LOW
        assert cat.get_risk("send_message") == RiskClass.HIGH
        assert cat.get_risk("nope") == RiskClass.LOW


class TestPolicyGateUsesRiskCatalog:
    @pytest.mark.anyio
    async def test_policy_gate_consults_injected_risk_catalog(self) -> None:
        from k1.concierge.llm.types import ToolCallResult
        from k1.selfmodel.adapters.concierge_policy_gate import ConciergePolicyGate
        from k1.selfmodel.contracts.situation import (
            ApplicableRules,
            Capabilities,
            SituationFrame,
            Visibility,
        )

        observed: list[str] = []

        class CaptureCat(StaticRiskCatalog):
            def get_risk(self, name: str) -> RiskClass:
                observed.append(name)
                return super().get_risk(name)

        frame = SituationFrame(
            actor_id="a1",
            situation_kind="caregiver_context_briefing",
            rules=ApplicableRules(),
            capabilities=Capabilities(),
            conscience=ConscienceDigest(),
            visibility=Visibility(),
        )

        gate = ConciergePolicyGate(
            actor_id="a1",
            frame_provider=lambda _tc: frame,
            risk_catalog=CaptureCat(),
        )
        await gate.evaluate(ToolCallResult(id="t1", name="recall_memory", arguments={}))
        assert "recall_memory" in observed

    @pytest.mark.anyio
    async def test_selfmodel_handle_forwards_injected_risk_catalog(self) -> None:
        from k1.concierge.llm.types import ToolCallResult
        from k1.selfmodel.contracts.situation import (
            ApplicableRules,
            Capabilities,
            SituationFrame,
            Visibility,
        )
        from k1.selfmodel.kernel.handle import build_self_model_handle

        observed: list[str] = []

        class CaptureCat(StaticRiskCatalog):
            def get_risk(self, name: str) -> RiskClass:
                observed.append(name)
                return super().get_risk(name)

        frame = SituationFrame(
            actor_id="a1",
            situation_kind="caregiver_context_briefing",
            rules=ApplicableRules(),
            capabilities=Capabilities(),
            conscience=ConscienceDigest(),
            visibility=Visibility(),
        )
        bundle = SimpleNamespace(
            composer=SimpleNamespace(compose=lambda *_args: frame),
            evaluator=None,
            capsule_builder=SimpleNamespace(),
            citation_builder=SimpleNamespace(),
        )

        handle = build_self_model_handle(
            bundle,  # type: ignore[arg-type]
            session_id="s1",
            actor_id="a1",
            risk_catalog=CaptureCat(),
        )

        assert handle.gate is not None
        await handle.gate.evaluate(ToolCallResult(id="t1", name="recall_memory", arguments={}))
        assert "recall_memory" in observed


# =====================================================================
# M9.E2.I1 -- v1 bootstrap loader
# =====================================================================
class TestBootstrapV1:
    def test_load_packaged_v1_yaml(self) -> None:
        body = load_bootstrap_yaml_v1()
        assert body["constitution_id"] == BOOTSTRAP_CONSTITUTION_ID_V1
        assert int(body["schema_version"]) == 1
        assert "conscience_rules" in body

    def test_ensure_bootstrap_writes_v1_when_requested(self) -> None:
        store = InMemoryProjectionStore()
        result = ensure_bootstrap_constitution(store, now_ms=1_000, schema_version=1)
        assert result.created is True
        assert result.snapshot.constitution_id == BOOTSTRAP_CONSTITUTION_ID_V1
        assert result.snapshot.version == BOOTSTRAP_VERSION_V1
        # Idempotent.
        again = ensure_bootstrap_constitution(store, now_ms=2_000, schema_version=1)
        assert again.created is False
        assert again.snapshot.constitution_id == BOOTSTRAP_CONSTITUTION_ID_V1


# =====================================================================
# M10.E1.I1 -- narrow L3 ports
# =====================================================================
class TestL3Ports:
    def _make(self) -> tuple[SelfModelService, InMemoryProjectionStore]:
        store = InMemoryProjectionStore()
        svc = SelfModelService(store=store)
        snap = K1SelfModelSnapshot(actor_id="alice", L1_core={"display_name": "Alice"})
        store.write_self(snap, writer_id=SEED_WRITER_ID)
        return svc, store

    def test_preference_adapter_roundtrip(self) -> None:
        svc, _ = self._make()
        bundle = L3PortBundle(svc)
        bundle.preferences.write_preferences("alice", {"theme": "dark"})
        assert bundle.preferences.read_preferences("alice") == {"theme": "dark"}

    def test_goal_adapter_roundtrip(self) -> None:
        svc, _ = self._make()
        bundle = L3PortBundle(svc)
        bundle.goals.write_goals("alice", (Goal(goal_id="g1", summary="run"),))
        out = bundle.goals.read_goals("alice")
        assert out[0].goal_id == "g1"

    def test_habit_adapter_roundtrip(self) -> None:
        svc, _ = self._make()
        bundle = L3PortBundle(svc)
        bundle.habits.write_habits(
            "alice", (Habit(habit_id="h1", summary="walk", cadence="daily"),)
        )
        out = bundle.habits.read_habits("alice")
        assert out[0].cadence == "daily"

    def test_communication_style_roundtrip(self) -> None:
        svc, _ = self._make()
        bundle = L3PortBundle(svc)
        bundle.communication_style.set_communication_style("alice", "brief")
        assert bundle.communication_style.read_communication_style("alice") == "brief"


# =====================================================================
# M10.E1.I2 -- IConsciencePort
# =====================================================================
class TestConsciencePort:
    def test_digest_for_v1_body(self) -> None:
        body = {
            "schema_version": 1,
            "conscience_rules": {
                "guardian": {
                    "forbidden": ["set_medication"],
                    "must_ask": ["send_message"],
                    "tier_floor": {"send_message": 2},
                },
            },
        }
        port = ConstitutionConsciencePort(
            role_for_actor=lambda _aid: "guardian",
            load_constitution_body=lambda: body,
        )
        d = port.get_digest("a1", T_ms=0)
        assert d.is_forbidden("set_medication")
        assert d.is_must_ask("send_message")
        assert d.tier_floor.get("send_message") == 2

    def test_empty_body_returns_default_allow_digest(self) -> None:
        port = ConstitutionConsciencePort(
            role_for_actor=lambda _aid: "member",
            load_constitution_body=lambda: {},
        )
        d = port.get_digest("a1", T_ms=0)
        assert d.forbidden_acts == ()
        assert d.must_ask_acts == ()


# =====================================================================
# M10.E2.I1 -- onboarding seed script
# =====================================================================
class TestOnboardingSeed:
    def test_apply_seed_anand_yaml(self) -> None:
        from scripts.onboarding_seed import apply_seed, load_seed

        store = InMemoryProjectionStore()
        svc = SelfModelService(store=store)
        seed = load_seed(Path("examples/seeds/anand.yaml"))
        actor_id = apply_seed(seed, service=svc, store=store)
        assert actor_id == "anand"
        shape = svc.get_pattern_shape("anand")
        assert shape.preferences.get("theme") == "dark"
        assert "hiking" in shape.hobbies
        assert any(g.goal_id == "g_run5k" for g in shape.goals)
        assert any(r.routine_id == "r_morning" for r in shape.routines)
        assert shape.communication_style == "brief"

    def test_three_seeds_render_distinct_capsules(self) -> None:
        from scripts.onboarding_seed import (
            apply_seed,
            load_seed,
            render_capsule_text,
        )

        capsules: list[str] = []
        for path, expected_actor in (
            (Path("examples/seeds/anand.yaml"), "anand"),
            (Path("examples/seeds/aarav_child.yaml"), "aarav"),
            (Path("examples/seeds/priya_guardian.yaml"), "priya"),
        ):
            store = InMemoryProjectionStore()
            svc = SelfModelService(store=store)
            seed = load_seed(path)
            actor_id = apply_seed(seed, service=svc, store=store)
            assert actor_id == expected_actor
            text = render_capsule_text(svc, actor_id, str(seed.get("role") or "member"))
            capsules.append(text)
        # All three must be distinct.
        assert len({c for c in capsules}) == 3


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
