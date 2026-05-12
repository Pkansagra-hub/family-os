"""Composer benchmark — p95 ≤ 5 ms on the in-memory store (M1.E2.I1).

Marked ``@pytest.mark.perf`` so a fast CI lane can skip it. Uses a
representative four-member household and walks all 13 V0 situations.
"""

from __future__ import annotations

import statistics
import time

import pytest

from k1.selfmodel.contracts.space_graph import RelationshipEdge
from k1.selfmodel.contracts.situations import SITUATION_KINDS

from tests.k1.selfmodel.service._helpers import (
    T0_MS,
    build_bundle,
    make_actor,
    make_constitution,
    make_family,
    make_member,
    v0_body,
)

pytestmark = pytest.mark.perf

P95_BUDGET_MS = 5.0


def _bundle():
    actors = (
        make_actor("g1", role="guardian", consent_family=("name", "role_in_family", "schedule")),
        make_actor("g2", role="guardian", consent_family=("name", "role_in_family")),
        make_actor("c1", role="child", consent_family=("name", "role_in_family", "age_band", "schedule")),
        make_actor("c2", role="child", consent_family=("name", "role_in_family", "age_band")),
    )
    fam = make_family(
        members=(
            make_member("g1", role="guardian"),
            make_member("g2", role="guardian"),
            make_member("c1", role="child"),
            make_member("c2", role="child"),
        ),
        edges=(
            RelationshipEdge("g1", "c1", "parent_of"),
            RelationshipEdge("g1", "c2", "parent_of"),
            RelationshipEdge("g2", "c1", "parent_of"),
            RelationshipEdge("g2", "c2", "parent_of"),
            RelationshipEdge("g1", "g2", "spouse_of"),
            RelationshipEdge("c1", "c2", "sibling_of"),
        ),
    )
    return build_bundle(
        actors=actors,
        family=fam,
        constitution=make_constitution(body=v0_body()),
    )


def test_composer_p95_under_budget() -> None:
    bundle = _bundle()
    kinds = sorted(SITUATION_KINDS)

    # Warm-up — exclude from the measurement.
    for _ in range(50):
        bundle.composer.compose("g1", T0_MS, "d1", kinds[0])

    samples_ms: list[float] = []
    for _ in range(500):
        for kind in kinds:
            t0 = time.perf_counter()
            bundle.composer.compose("g1", T0_MS, "d1", kind)
            samples_ms.append((time.perf_counter() - t0) * 1000.0)

    samples_ms.sort()
    p50 = statistics.median(samples_ms)
    p95 = samples_ms[int(0.95 * len(samples_ms)) - 1]
    p99 = samples_ms[int(0.99 * len(samples_ms)) - 1]
    print(
        f"\ncomposer p50={p50:.3f}ms p95={p95:.3f}ms p99={p99:.3f}ms "
        f"n={len(samples_ms)}"
    )
    assert p95 < P95_BUDGET_MS, (
        f"composer p95 budget exceeded: {p95:.3f}ms >= {P95_BUDGET_MS}ms"
    )
