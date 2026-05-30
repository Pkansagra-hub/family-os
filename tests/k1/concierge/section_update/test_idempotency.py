"""M1.I4 idempotency and stale-plan behavior."""

from __future__ import annotations

from k1.concierge.section_update.idempotency import (
    SectionUpdateIdempotencyStore,
    build_mutation_idempotency_key,
    build_plan_idempotency_key,
)
from k1.concierge.section_update.plan_compiler import CompileStatus, PlanCompiler
from k1.concierge.section_update.types import SectionMutation, SectionUpdatePlan


def _plan(session_id: str = "session-1", turn_id: str = "turn-1") -> SectionUpdatePlan:
    return SectionUpdatePlan(
        plan_id=f"plan:{session_id}:{turn_id}",
        session_id=session_id,
        turn_id=turn_id,
        snapshot_version="snap-1",
        classifier_version="classifier-v1",
        mutations=[
            SectionMutation(
                section="beliefs_active",
                operation="add_fact",
                data={"subject": "user", "predicate": "likes", "obj": "tea"},
                confidence=0.8,
                reason="Durable user preference.",
                commit_class="next_turn_continuity",
            )
        ],
    )


def test_plan_idempotency_key_is_stable_and_session_scoped() -> None:
    key1 = build_plan_idempotency_key(
        session_id="s1",
        turn_id="t1",
        snapshot_version="snap",
        classifier_version="v1",
    )
    key2 = build_plan_idempotency_key(
        session_id="s1",
        turn_id="t1",
        snapshot_version="snap",
        classifier_version="v1",
    )
    key3 = build_plan_idempotency_key(
        session_id="s2",
        turn_id="t1",
        snapshot_version="snap",
        classifier_version="v1",
    )

    assert key1 == key2
    assert key1 != key3


def test_mutation_idempotency_key_changes_with_payload() -> None:
    key1 = build_mutation_idempotency_key(
        plan_idempotency_key="p",
        index=0,
        section="beliefs_active",
        operation="add_fact",
        data={"obj": "tea"},
    )
    key2 = build_mutation_idempotency_key(
        plan_idempotency_key="p",
        index=0,
        section="beliefs_active",
        operation="add_fact",
        data={"obj": "coffee"},
    )

    assert key1 != key2


def test_duplicate_compile_returns_no_batch_on_second_attempt() -> None:
    store = SectionUpdateIdempotencyStore()
    compiler = PlanCompiler(idempotency_store=store)
    plan = _plan()

    first = compiler.compile(plan)
    second = compiler.compile(plan)

    assert first.status == CompileStatus.COMPILED
    assert first.batch_request is not None
    assert second.status == CompileStatus.DUPLICATE
    assert second.batch_request is None
    assert len(store) == 1


def test_idempotency_key_uses_session_plus_turn_not_turn_alone() -> None:
    store = SectionUpdateIdempotencyStore()
    compiler = PlanCompiler(idempotency_store=store)

    first = compiler.compile(_plan(session_id="s1", turn_id="same-turn"))
    second = compiler.compile(_plan(session_id="s2", turn_id="same-turn"))

    assert first.status == CompileStatus.COMPILED
    assert second.status == CompileStatus.COMPILED
    assert len(store) == 2


def test_stale_compile_is_remembered_for_duplicate_retry() -> None:
    store = SectionUpdateIdempotencyStore()
    compiler = PlanCompiler(idempotency_store=store)
    plan = _plan()

    first = compiler.compile(plan, current_snapshot_version="newer")
    second = compiler.compile(plan, current_snapshot_version="newer")

    assert first.status == CompileStatus.STALE
    assert second.status == CompileStatus.DUPLICATE
    assert second.batch_request is None
