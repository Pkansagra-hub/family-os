"""K1 Phase-9 algebra probe (M11.E1.I3 — bonus).

Drives **live Gemini** through the full ``S ∩ F ∩ C`` algebra and the
constitution-amendment lifecycle, with PASS/FAIL per scenario:

| Scenario              | Algebra element        | What it proves                                             |
| --------------------- | ---------------------- | ---------------------------------------------------------- |
| guardian_self         | ``S(actor)``           | LLM grounds in actor's hobbies/goals                       |
| guardian_family_view  | ``S ∩ F``              | LLM names household relations the guardian may see         |
| child_self            | ``S(child)``           | LLM uses child's communication style + age band            |
| child_family_view     | ``S ∩ F`` (child role) | Child sees guardian display name but NOT sibling hobbies   |
| guardian_constitution | ``S ∩ C``              | Guardian conscience: must_ask `pickup_change`              |
| child_constitution    | ``S ∩ C`` (stricter)   | Child conscience: forbidden `modify_constitution`          |
| family_constitution   | ``F ∩ C``              | LLM honors visibility_rules when describing the family     |
| amendment_lifecycle   | ``C → C'``             | New forbidden act blocks an action that was just allowed   |
| union_self_family     | ``S ∪ F`` (rendered)   | Capsule contains both ``[self]`` and ``[family]`` sections |

All scenarios call **live** Gemini for the LLM-grounded ones and
**PolicyEvaluator** for the policy-grounded ones. Output JSON written
to ``data/kernel_probe_phase9_algebra.json``.

Run::

    python scripts/kernel_probe_phase9_algebra.py            # live (default)
    python scripts/kernel_probe_phase9_algebra.py --offline  # skip LLM scenarios
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(ROOT))

from k1.selfmodel.adapters.memory_projection_store import (  # noqa: E402
    InMemoryProjectionStore,
)
from k1.selfmodel.contracts.conscience import ConscienceDigest  # noqa: E402
from k1.selfmodel.contracts.constitution_body import (  # noqa: E402
    get_conscience_bucket,
)
from k1.selfmodel.contracts.family_model import (  # noqa: E402
    FamilyMemberRef,
    FamilySelfModelSnapshot,
    RelationshipEdge,
)
from k1.selfmodel.contracts.pattern import coerce_l3  # noqa: E402
from k1.selfmodel.contracts.policy import (  # noqa: E402
    FreshnessState,
    PolicyDecision,
    PolicyRequest,
    ReasonCode,
    RiskClass,
)
from k1.selfmodel.contracts.situation import (  # noqa: E402
    ApplicableRules,
    Capabilities,
    ProjectedSelf,
    RelationsSubset,
    SelfView,
    SituationFrame,
    Visibility,
)
from k1.selfmodel.service.capsule_builder import GroundingCapsuleBuilder  # noqa: E402
from k1.selfmodel.service.constitution import ConstitutionService  # noqa: E402
from k1.selfmodel.service.family_model import (  # noqa: E402
    FAMILY_MODEL_WRITER_ID,
    FamilyModelService,
)
from k1.selfmodel.service.policy_evaluator import PolicyEvaluator  # noqa: E402
from k1.selfmodel.service.self_model import (  # noqa: E402
    SelfModelService,
)
from scripts.kernel_probe_phase9_v2 import LiveGeminiLLM, _load_dotenv  # noqa: E402
from scripts.onboarding_seed import apply_seed, load_seed  # noqa: E402

logger = logging.getLogger("kernel_probe_phase9_algebra")

DEFAULT_REPORT = ROOT / "data" / "kernel_probe_phase9_algebra.json"
SEED_DIR = ROOT / "examples" / "seeds"
FAMILY_SPACE = "fs:home_household"
CONSTITUTION_ID = "c:home_household:v0"


# =====================================================================
# Records
# =====================================================================
@dataclass
class ProbeRecord:
    name: str
    algebra: str
    expected: str
    observed: dict[str, Any] = field(default_factory=dict)
    passed: bool = False
    notes: str = ""


# =====================================================================
# Bundle setup — three-actor household
# =====================================================================
def _seed_actor(svc: SelfModelService, store: Any, path: Path) -> tuple[str, str, SelfView]:
    seed = load_seed(path)
    actor_id = apply_seed(seed, service=svc, store=store)
    role = str(seed.get("role") or "member")
    snap = svc.get(actor_id).snapshot  # type: ignore[union-attr]
    pattern = coerce_l3(snap.L3_pattern)
    view = SelfView(
        actor_id=actor_id,
        display_name=str(snap.L1_core.get("display_name") or actor_id),
        role=role,
        age_band=str(snap.L2_identity.get("age_band") or ""),
        pronouns=str(snap.L2_identity.get("pronouns") or ""),
        language=str(snap.L2_identity.get("language") or ""),
        communication_style=pattern.communication_style,
        preferences=dict(pattern.preferences),
        hobbies=pattern.hobbies,
        likes=pattern.likes,
        dislikes=pattern.dislikes,
        goals=pattern.goals,
        routines=pattern.routines,
        habits=pattern.habits,
    )
    return actor_id, role, view


def _build_v0_constitution_body() -> dict[str, Any]:
    """V0 constitution body — guardian/child autonomy + visibility rules."""
    return {
        "visibility_rules": {
            "guardian": {
                "guardian": ["display_name", "role"],
                "child": ["display_name", "role", "age_band"],
            },
            "child": {
                "guardian": ["display_name", "role"],
                "child": ["display_name"],  # siblings: name only
            },
        },
        "autonomy_rules": {
            "guardian": {
                "can": ["recall_memory", "create_reminder", "set_routine"],
                "must_ask": ["pickup_change", "send_message"],
                "cannot": ["prescribe_medication"],
            },
            "child": {
                "can": ["complete_chore", "create_reminder"],
                "must_ask": ["leave_house"],
                "cannot": ["modify_constitution", "send_message", "prescribe_medication"],
            },
        },
        "authority_rules": {
            "pickup_change": 2,
            "set_routine": 2,
            "send_message": 2,
        },
    }


def _amended_v0_body() -> dict[str, Any]:
    """V0' = V0 + new forbidden act for guardians."""
    body = _build_v0_constitution_body()
    body["autonomy_rules"]["guardian"]["cannot"] = [
        "prescribe_medication",
        "share_location_external",  # newly forbidden
    ]
    return body


def _make_frame(
    actor_id: str,
    self_view: SelfView,
    role: str,
    body: dict[str, Any],
    family: FamilySelfModelSnapshot | None = None,
) -> SituationFrame:
    bucket = get_conscience_bucket(body, role=role)
    digest = ConscienceDigest(
        forbidden_acts=bucket.forbidden,
        must_ask_acts=bucket.must_ask,
        risk_overrides=dict(bucket.risk_overrides),
        tier_floor=dict(bucket.tier_floor),
    )
    visible_members: tuple[str, ...] = ()
    visible_attrs: dict[str, tuple[str, ...]] = {}
    projected_others: list[ProjectedSelf] = []
    adjacent_edges: list[RelationshipEdge] = []
    if family is not None:
        # Compute visibility per role (visibility_rules[actor_role][peer_role]).
        rules = body.get("visibility_rules", {}).get(role, {})
        ids: list[str] = []
        for m in family.members:
            if m.member_id == actor_id:
                continue
            attrs = rules.get(m.role)
            if not attrs:
                continue
            ids.append(m.member_id)
            visible_attrs[m.member_id] = tuple(attrs)
            attr_map: dict[str, object] = {}
            for k in attrs:
                if k == "display_name":
                    attr_map["display_name"] = m.display_name
                elif k == "role":
                    attr_map["role"] = m.role
                elif k == "age_band":
                    attr_map["age_band"] = m.age_band
            projected_others.append(
                ProjectedSelf(
                    member_id=m.member_id,
                    display_name=m.display_name if "display_name" in attrs else "",
                    role=m.role if "role" in attrs else "",
                    visible_attributes=attr_map,
                )
            )
        visible_members = tuple(ids)
        adjacent_edges = [
            e for e in family.relations if e.from_member == actor_id or e.to_member == actor_id
        ]
    return SituationFrame(
        actor_id=actor_id,
        situation_kind="caregiver_context_briefing",
        rules=ApplicableRules(constitution_version="v0"),
        capabilities=Capabilities(),
        self_view=self_view,
        conscience=digest,
        relations=RelationsSubset(
            edges=tuple(adjacent_edges),
            projected_others=tuple(projected_others),
        ),
        visibility=Visibility(can_see_members=visible_members, can_see_attributes=visible_attrs),
    )


# =====================================================================
# Scenarios — LLM-grounded
# =====================================================================
def _llm_scenario(
    *,
    name: str,
    algebra: str,
    expected: str,
    needles: list[str],
    prompt: str,
    capsule_text: str,
    llm: LiveGeminiLLM | None,
) -> ProbeRecord:
    rec = ProbeRecord(name=name, algebra=algebra, expected=expected)
    if llm is None:
        rec.notes = "skipped (offline mode)"
        return rec
    reply = llm.reply(prompt, capsule_text=capsule_text)
    matches = [n for n in needles if n and n.lower() in (reply or "").lower()]
    rec.observed = {"reply": reply, "needles": needles, "matched": matches}
    rec.passed = bool(matches)
    rec.notes = (
        f"matched {len(matches)}/{len(needles)} needles: {matches}"
        if matches
        else f"no needles found in reply (looked for {needles})"
    )
    return rec


def _negative_llm_scenario(
    *,
    name: str,
    algebra: str,
    expected: str,
    forbidden_needles: list[str],
    prompt: str,
    capsule_text: str,
    llm: LiveGeminiLLM | None,
) -> ProbeRecord:
    """PASS iff none of forbidden_needles appears in the LLM reply."""
    rec = ProbeRecord(name=name, algebra=algebra, expected=expected)
    if llm is None:
        rec.notes = "skipped (offline mode)"
        return rec
    reply = llm.reply(prompt, capsule_text=capsule_text)
    leaked = [n for n in forbidden_needles if n and n.lower() in (reply or "").lower()]
    rec.observed = {"reply": reply, "forbidden_needles": forbidden_needles, "leaked": leaked}
    rec.passed = not leaked
    rec.notes = "no forbidden tokens leaked" if not leaked else f"LEAK: {leaked} appeared in reply"
    return rec


# =====================================================================
# Driver
# =====================================================================
def run_probe(*, offline: bool) -> dict[str, Any]:
    # ── Wire stores + services ──
    store = InMemoryProjectionStore(allowed_writers=None)
    sm = SelfModelService(store)
    fm = FamilyModelService(store)
    cs = ConstitutionService(store, constitution_id=CONSTITUTION_ID)

    # ── Seed three actors ──
    anand_id, anand_role, anand_view = _seed_actor(sm, store, SEED_DIR / "anand.yaml")
    aarav_id, aarav_role, aarav_view = _seed_actor(sm, store, SEED_DIR / "aarav_child.yaml")
    priya_id, priya_role, priya_view = _seed_actor(sm, store, SEED_DIR / "priya_guardian.yaml")

    # ── Build family graph ──
    members = (
        FamilyMemberRef(
            member_id=anand_id, display_name="Anand", role=anand_role, age_band="adult"
        ),
        FamilyMemberRef(
            member_id=priya_id, display_name="Priya", role=priya_role, age_band="adult"
        ),
        FamilyMemberRef(
            member_id=aarav_id, display_name="Aarav", role=aarav_role, age_band="child"
        ),
    )
    edges = (
        RelationshipEdge(from_member=anand_id, to_member=aarav_id, kind="parent_of"),
        RelationshipEdge(from_member=priya_id, to_member=aarav_id, kind="parent_of"),
        RelationshipEdge(from_member=anand_id, to_member=priya_id, kind="partner_of"),
    )
    family = FamilySelfModelSnapshot(
        family_space_id=FAMILY_SPACE,
        members=members,
        relations=edges,
        composed_at_ms=int(time.time() * 1000),
    )
    store.write_family(family, writer_id=FAMILY_MODEL_WRITER_ID)

    # ── Constitutions ──
    body_v0 = _build_v0_constitution_body()
    body_v1 = _amended_v0_body()

    # ── LLM client (live unless --offline) ──
    llm: LiveGeminiLLM | None = None
    if not offline:
        _load_dotenv()
        llm = LiveGeminiLLM()

    capsule_builder = GroundingCapsuleBuilder()
    evaluator = PolicyEvaluator()

    # ── Frames per actor ──
    anand_frame = _make_frame(anand_id, anand_view, anand_role, body_v0, family=family)
    aarav_frame = _make_frame(aarav_id, aarav_view, aarav_role, body_v0, family=family)

    anand_capsule = capsule_builder.build(anand_frame).as_prompt_text()
    aarav_capsule = capsule_builder.build(aarav_frame).as_prompt_text()

    records: list[ProbeRecord] = []

    # 1) S(guardian) — guardian self grounding
    records.append(
        _llm_scenario(
            name="guardian_self",
            algebra="S(actor)",
            expected="LLM mentions one of guardian's hobbies or goals.",
            needles=["hiking", "reading", "cooking", "5k", "books"],
            prompt="What do you know about me as a person? Keep it brief.",
            capsule_text=anand_capsule,
            llm=llm,
        )
    )

    # 2) S ∩ F (guardian) — names household relations
    records.append(
        _llm_scenario(
            name="guardian_family_view",
            algebra="S n F",
            expected="LLM names other family members visible to the guardian.",
            needles=["aarav", "priya"],
            prompt="Who else is in my household? Use names if you can see them.",
            capsule_text=anand_capsule,
            llm=llm,
        )
    )

    # 3) S(child) — child self grounding
    records.append(
        _llm_scenario(
            name="child_self",
            algebra="S(child)",
            expected="LLM acknowledges the child's age band or one of their hobbies.",
            needles=["chess", "minor", "child", "school"],
            prompt="What do you know about me? Reply briefly.",
            capsule_text=aarav_capsule,
            llm=llm,
        )
    )

    # 4) Negative: child can't see guardian's hobbies (only display_name + role)
    records.append(
        _negative_llm_scenario(
            name="child_family_view_no_leak",
            algebra="S n F (child role)",
            expected="LLM does not surface guardian-private L3 attributes (hobbies/goals).",
            forbidden_needles=[
                "filter coffee",
                "long-form essays",
                "5k in under 28 minutes",
            ],
            prompt="Tell me about my parents — their hobbies and goals.",
            capsule_text=aarav_capsule,
            llm=llm,
        )
    )

    # 5) S ∩ C (guardian conscience) — must_ask for pickup_change
    rec = ProbeRecord(
        name="guardian_constitution_must_ask",
        algebra="S n C",
        expected="PolicyEvaluator returns REQUIRE_CONFIRMATION for guardian's pickup_change.",
    )
    v = evaluator.evaluate(
        PolicyRequest(actor_id=anand_id, tool_name="pickup_change", risk_class=RiskClass.LOW),
        anand_frame,
        freshness_state=FreshnessState.FRESH,
        current_tier=2,
    )
    rec.observed = {"decision": v.decision.value, "reason": v.reason.value if v.reason else None}
    rec.passed = v.decision == PolicyDecision.REQUIRE_CONFIRMATION
    rec.notes = f"decision={v.decision.value}"
    records.append(rec)

    # 6) S ∩ C (child conscience, stricter) — forbidden modify_constitution
    rec = ProbeRecord(
        name="child_constitution_forbidden",
        algebra="S n C (child role)",
        expected="PolicyEvaluator returns DENY for child invoking modify_constitution.",
    )
    v = evaluator.evaluate(
        PolicyRequest(actor_id=aarav_id, tool_name="modify_constitution", risk_class=RiskClass.LOW),
        aarav_frame,
    )
    rec.observed = {"decision": v.decision.value, "reason": v.reason.value if v.reason else None}
    rec.passed = v.decision == PolicyDecision.DENY and v.reason == ReasonCode.CAPABILITY_NOT_GRANTED
    rec.notes = f"decision={v.decision.value}"
    records.append(rec)

    # 7) F ∩ C — visibility-rule LLM check (positive: guardian view sees other guardian)
    records.append(
        _llm_scenario(
            name="family_constitution_visibility",
            algebra="F n C",
            expected="LLM honors C.visibility_rules - names co-guardian by display_name.",
            needles=["priya"],
            prompt="What is the name of my co-guardian, if any?",
            capsule_text=anand_capsule,
            llm=llm,
        )
    )

    # 8) Constitution amendment lifecycle
    pre = ProbeRecord(
        name="amendment_pre_allow",
        algebra="C (v0)",
        expected="Before amendment: share_location_external is ALLOW (default-allow).",
    )
    v = evaluator.evaluate(
        PolicyRequest(actor_id=anand_id, tool_name="share_location_external"),
        anand_frame,
    )
    pre.observed = {"decision": v.decision.value}
    pre.passed = v.decision == PolicyDecision.ALLOW
    pre.notes = f"decision={v.decision.value}"
    records.append(pre)

    anand_frame_v1 = _make_frame(anand_id, anand_view, anand_role, body_v1, family=family)
    post = ProbeRecord(
        name="amendment_post_deny",
        algebra="C (v0 -> v1)",
        expected="After amendment adds forbidden act: same call now DENY.",
    )
    v = evaluator.evaluate(
        PolicyRequest(actor_id=anand_id, tool_name="share_location_external"),
        anand_frame_v1,
    )
    post.observed = {"decision": v.decision.value, "reason": v.reason.value if v.reason else None}
    post.passed = (
        v.decision == PolicyDecision.DENY and v.reason == ReasonCode.CAPABILITY_NOT_GRANTED
    )
    post.notes = f"decision={v.decision.value}"
    records.append(post)

    # 9) S ∪ F union surfaced in capsule (structural, not LLM)
    union = ProbeRecord(
        name="union_self_family_capsule",
        algebra="S u F (rendered)",
        expected="Rendered capsule contains both [self] and [family] sections.",
    )
    has_self = "[self]" in anand_capsule
    has_family = "[household]" in anand_capsule or "[family]" in anand_capsule
    union.observed = {"has_self_block": has_self, "has_family_block": has_family}
    union.passed = has_self and has_family
    union.notes = f"self={has_self} family/household={has_family}"
    records.append(union)

    return {
        "schema_version": 1,
        "mode": "offline" if offline else "live",
        "actor_ids": {"guardian": anand_id, "child": aarav_id, "co_guardian": priya_id},
        "capsules": {"guardian": anand_capsule, "child": aarav_capsule},
        "records": [asdict(r) for r in records],
        "summary": {
            "total": len(records),
            "passed": sum(1 for r in records if r.passed),
            "failed": sum(1 for r in records if not r.passed and "skipped" not in r.notes),
            "skipped": sum(1 for r in records if "skipped" in r.notes),
        },
    }


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument(
        "--offline", action="store_true", help="Skip live LLM scenarios (for CI smoke runs)."
    )
    ap.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    report = run_probe(offline=args.offline)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print()
    print("=" * 78)
    print(
        f"  M11 ALGEBRA probe ({report['mode']}): "
        f"passed={report['summary']['passed']}/{report['summary']['total']}  "
        f"failed={report['summary']['failed']}  skipped={report['summary']['skipped']}"
    )
    print("=" * 78)
    for rec in report["records"]:
        if "skipped" in rec["notes"]:
            marker = "SKIP"
        else:
            marker = "PASS" if rec["passed"] else "FAIL"
        print(f"  [{marker}] {rec['name']:36s} {rec['algebra']:24s} {rec['notes']}")
        reply = rec.get("observed", {}).get("reply") or ""
        if reply:
            head = reply[:240].replace("\n", " ")
            print(f"        > {head}{'…' if len(reply) > 240 else ''}")
    print()
    print(f"  JSON written: {args.out}")
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
