"""``onboarding_seed`` -- seed a household with one actor (M10.E2.I1).

Usage::

    python scripts/onboarding_seed.py \\
        --household HH1 --actor anand --yaml examples/seeds/anand.yaml \\
        [--db ./data/family.sqlite3] [--print-capsule]

What it does:

1. Loads the seed YAML (``actor_id``, ``role``, ``core``, ``identity``,
   ``pattern``).
2. Opens (or creates) a projection store. By default the script uses
   the in-memory store -- pass ``--db PATH`` to use SQLite.
3. Writes the L1/L2 snapshot via ``store.write_self``.
4. Calls each typed L3 writer on
   :class:`SelfModelService` for every populated bucket in
   ``pattern``.
5. Optionally renders the grounding capsule for the seeded actor and
   prints it to stdout for human review.

The script is intentionally synchronous and side-effect-only -- it
does not start the full kernel. Anything beyond a single actor's L1/
L2/L3 (relations, family routines, constitution amendments) is
out of scope; do that through the regular admin flow.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from k1.selfmodel.adapters.l3_ports import L3PortBundle
from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
from k1.selfmodel.contracts.family_model import RoutineRef
from k1.selfmodel.contracts.pattern import Goal, Habit
from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot
from k1.selfmodel.service.self_model import SelfModelService

logger = logging.getLogger("onboarding_seed")

SEED_WRITER_ID = "selfmodel:self_model_service"


# ---------------------------------------------------------------------
# YAML coercion
# ---------------------------------------------------------------------
def _coerce_goals(items: list[dict[str, Any]] | None) -> tuple[Goal, ...]:
    if not items:
        return ()
    out: list[Goal] = []
    for it in items:
        out.append(
            Goal(
                goal_id=str(it.get("goal_id") or it.get("id") or ""),
                summary=str(it.get("summary") or ""),
                horizon=str(it.get("horizon") or ""),
                status=str(it.get("status") or "active"),
            )
        )
    return tuple(out)


def _coerce_habits(items: list[dict[str, Any]] | None) -> tuple[Habit, ...]:
    if not items:
        return ()
    out: list[Habit] = []
    for it in items:
        out.append(
            Habit(
                habit_id=str(it.get("habit_id") or it.get("id") or ""),
                summary=str(it.get("summary") or ""),
                cadence=str(it.get("cadence") or ""),
            )
        )
    return tuple(out)


def _coerce_routines(items: list[dict[str, Any]] | None) -> tuple[RoutineRef, ...]:
    if not items:
        return ()
    out: list[RoutineRef] = []
    for it in items:
        out.append(
            RoutineRef(
                routine_id=str(it.get("routine_id") or it.get("id") or ""),
                name=str(it.get("name") or ""),
                schedule=str(it.get("schedule") or ""),
            )
        )
    return tuple(out)


def _coerce_strings(items: list[Any] | None) -> tuple[str, ...]:
    if not items:
        return ()
    return tuple(str(x) for x in items if x is not None)


# ---------------------------------------------------------------------
# Seed application
# ---------------------------------------------------------------------
def load_seed(path: Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    parsed = yaml.safe_load(text) or {}
    if not isinstance(parsed, dict):
        raise ValueError(f"seed must parse to dict, got {type(parsed).__name__}")
    if "actor_id" not in parsed:
        raise ValueError("seed missing required key: actor_id")
    return parsed


def apply_seed(
    seed: dict[str, Any],
    *,
    service: SelfModelService,
    store: Any,
    now_ms: int | None = None,
) -> str:
    """Write the seed to the store. Returns the resolved actor_id."""
    actor_id = str(seed["actor_id"])
    core = dict(seed.get("core") or {})
    identity = dict(seed.get("identity") or {})
    pattern = dict(seed.get("pattern") or {})
    composed_at = int(now_ms if now_ms is not None else time.time() * 1000)

    snapshot = K1SelfModelSnapshot(
        actor_id=actor_id,
        L1_core=core,
        L2_identity=identity,
        L3_pattern={},
        composed_at_ms=composed_at,
    )
    res = store.write_self(snapshot, writer_id=SEED_WRITER_ID)
    if not res.accepted:
        raise RuntimeError(f"projection store rejected seed write: {res.reason!r}")

    bundle = L3PortBundle(service)

    if isinstance(pattern.get("preferences"), dict):
        bundle.preferences.write_preferences(actor_id, dict(pattern["preferences"]))

    hobbies = _coerce_strings(pattern.get("hobbies"))
    if hobbies:
        bundle.hobbies.write_hobbies(actor_id, hobbies)

    likes = _coerce_strings(pattern.get("likes"))
    if likes:
        bundle.hobbies.write_likes(actor_id, likes)

    dislikes = _coerce_strings(pattern.get("dislikes"))
    if dislikes:
        bundle.hobbies.write_dislikes(actor_id, dislikes)

    goals = _coerce_goals(pattern.get("goals"))
    if goals:
        bundle.goals.write_goals(actor_id, goals)

    habits = _coerce_habits(pattern.get("habits"))
    if habits:
        bundle.habits.write_habits(actor_id, habits)

    routines = _coerce_routines(pattern.get("routines"))
    if routines:
        bundle.routines.write_routines(actor_id, routines)

    style = pattern.get("communication_style")
    if isinstance(style, str) and style:
        bundle.communication_style.set_communication_style(actor_id, style)

    logger.info(
        "onboarding_seed: wrote actor=%s buckets=%d",
        actor_id,
        sum(
            1
            for v in (
                pattern.get("preferences"),
                hobbies,
                likes,
                dislikes,
                goals,
                habits,
                routines,
                style,
            )
            if v
        ),
    )
    return actor_id


def render_capsule_text(service: SelfModelService, actor_id: str, role: str) -> str:
    """Render the grounding capsule for the seeded actor (review aid)."""
    from k1.selfmodel.contracts.conscience import ConscienceDigest
    from k1.selfmodel.contracts.pattern import coerce_l3
    from k1.selfmodel.contracts.situation import (
        ApplicableRules,
        Capabilities,
        SelfView,
        SituationFrame,
        Visibility,
    )
    from k1.selfmodel.service.capsule_builder import GroundingCapsuleBuilder

    res = service.get(actor_id)
    if res is None:
        return "(no snapshot found for actor)"
    snap = res.snapshot
    pattern = coerce_l3(snap.L3_pattern)
    self_view = SelfView(
        actor_id=actor_id,
        display_name=str(snap.L1_core.get("display_name") or actor_id),
        role=role,
        age_band=str(snap.L2_identity.get("age_band") or ""),
        pronouns=str(snap.L2_identity.get("pronouns") or ""),
        language=str(snap.L2_identity.get("language") or snap.L1_core.get("language") or ""),
        communication_style=pattern.communication_style,
        preferences=dict(pattern.preferences),
        hobbies=pattern.hobbies,
        goals=pattern.goals,
        routines=pattern.routines,
        habits=pattern.habits,
        likes=pattern.likes,
        dislikes=pattern.dislikes,
    )
    frame = SituationFrame(
        actor_id=actor_id,
        situation_kind="onboarding_review",
        rules=ApplicableRules(),
        capabilities=Capabilities(),
        self_view=self_view,
        conscience=ConscienceDigest(),
        visibility=Visibility(),
    )
    capsule = GroundingCapsuleBuilder().build(frame)
    return capsule.as_prompt_text()


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed a household actor's L1/L2/L3 from YAML.")
    parser.add_argument(
        "--household", required=True, help="Household id (label only; not persisted in V1)."
    )
    parser.add_argument("--actor", required=True, help="Actor id (must match the YAML's actor_id).")
    parser.add_argument("--yaml", required=True, type=Path, help="Path to seed YAML.")
    parser.add_argument(
        "--print-capsule", action="store_true", help="Render the grounding capsule after seeding."
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    seed = load_seed(args.yaml)
    if seed["actor_id"] != args.actor:
        logger.error(
            "seed actor_id=%s does not match --actor=%s",
            seed["actor_id"],
            args.actor,
        )
        return 2

    store = InMemoryProjectionStore()
    service = SelfModelService(store=store)
    actor_id = apply_seed(seed, service=service, store=store)
    logger.info("seeded actor=%s in household=%s", actor_id, args.household)

    if args.print_capsule:
        role = str(seed.get("role") or "member")
        print("\n" + "=" * 72)
        print(f"GROUNDING CAPSULE for {actor_id} (role={role})")
        print("=" * 72)
        print(render_capsule_text(service, actor_id, role))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
