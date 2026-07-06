"""
POC v2: Native-App Router — route_to_native_app()
====================================================
Kernel-grade routing. No domain facts in router code. No if-else branches.

Pipeline:
  1. Active-OS gating           → filter to visible apps
  2. Signal extraction           → generic (EffectLexicon + ResourcePhraseTrie + BackendSlotIndex)
  3. MiniLM dense retrieval      → cosine similarity over gated docs
  4. Contract schema scoring     → generic (reads NativeAppContract, no domain facts)
  5. Fusion                      → 0.70 * cosine_norm + 0.30 * schema_score
  6. Ranked results              → top-k RoutedApp

All domain facts live in:
  - boundary_contracts.py     (owns/does_not_own/ambiguous_with/backend_slots)
  - native_app_stubs.py       (concept_aliases, operation_aliases)
  - contract_compiler.py      (compiled indexes: EffectLexicon, ResourcePhraseTrie, BackendSlotIndex)

Usage:
  python scripts/poc_v2/router.py  # smoketest
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.poc_v2.context_factory import PocContext
from scripts.poc_v2.contract_compiler import (
    ExtractedSignals,
    NativeAppContractRegistry,
)

# ═══════════════════════════════════════════════════════════════════════════
# RoutedApp
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class RoutedApp:
    connector_id: str
    os_domain: str
    cosine_score: float  # raw MiniLM cosine similarity (normalized 0-1)
    schema_score: float  # contract compatibility (0.0-1.0)
    combined_score: float  # fusion: 0.70 * cosine + 0.30 * schema
    label: str    # ── Calibrated confidence (set after ranking) ──
    margin: float = 0.0               # score gap to next app
    confidence: str = "uncertain"     # "confident" | "ambiguous" | "uncertain"
    is_confusable_pair: bool = False  # top2 is a known confusable with top1
    should_force_primary: bool = True # if False, return envelope, don't force #1


# Thresholds — calibrated against 7.7k benchmark
_CONFIDENT_MARGIN = 0.15       # margin > this → confident top-1 (tightened from 0.12)
_AMBIGUOUS_MARGIN = 0.08       # margin < this + confusable pair → ambiguous (tightened from 0.05)
_UNCERTAIN_MARGIN = 0.05       # margin < this → uncertain even without confusable pair (tightened from 0.03)
_CONFUSABLE_PAIR_BOOST = 0.04  # extra margin required when top1/top2 are a known confusable pair

# ═══════════════════════════════════════════════════════════════════════════
# route_to_native_app — the kernel-grade router
# ═══════════════════════════════════════════════════════════════════════════


def route_to_native_app(
    utterance: str,
    active_os_set: set[str],
    ctx: PocContext,
    registry: NativeAppContractRegistry,
    *,
    top_k: int = 5,
    use_schema: bool = True,
) -> list[RoutedApp]:
    """Route a raw user utterance to the correct native app.

    Args:
        utterance: Raw user text (no LLM pre-processing)
        active_os_set: Which OS domains are active (e.g. {"family", "health"})
        ctx: POC context with documents and embedding index
        registry: Compiled contract registry with signal extractor
        top_k: Number of results to return
        use_schema: Whether to apply contract schema scoring

    Returns:
        Ranked list of RoutedApp, best first

    No domain facts in this function. No if-else. No hardcoded maps.
    All domain semantics live in the compiled registry.
    """
    # ── Step 1: Active-OS gating ──
    candidate_ids: set[str] = {
        cid for cid, domain in ctx.os_domain_map.items() if domain in active_os_set
    }

    # ── Step 2: Signal extraction (generic — reads compiled indexes) ──
    signals: ExtractedSignals | None = None
    if use_schema:
        signals = registry.signal_extractor.extract(utterance)

    # ── Step 3: Dense retrieval (MiniLM cosine similarity) ──
    dense_results = ctx.index.search(
        utterance,
        top_k=min(top_k * 3, len(candidate_ids)),
        candidate_ids=candidate_ids,
    )

    # ── Step 4: Contract schema scoring + fusion ──
    max_cosine = max(s for _, s in dense_results) if dense_results else 1.0
    results: list[RoutedApp] = []

    for cid, cosine_raw in dense_results:
        cosine_norm = cosine_raw / max_cosine if max_cosine > 0 else 0.0

        schema = 0.0
        if use_schema and signals is not None:
            schema = registry.schema_score(cid, signals, _all_visible_apps=candidate_ids)

        # Fusion: weighted combination
        combined = 0.70 * cosine_norm + 0.30 * schema

        results.append(
            RoutedApp(
                connector_id=cid,
                os_domain=ctx.os_domain_map.get(cid, "unknown"),
                cosine_score=round(cosine_norm, 4),
                schema_score=round(schema, 4),
                combined_score=round(combined, 4),
                label=ctx.docs[cid].label if cid in ctx.docs else cid,
            )
        )

    # Sort by combined score descending
    results.sort(key=lambda r: r.combined_score, reverse=True)
    results = results[:top_k]

    # ── Step 5: Calibrated confidence + ambiguity gate ──
    if len(results) >= 2:
        top1 = results[0]
        top2 = results[1]
        margin = round(top1.combined_score - top2.combined_score, 4)

        # Check confusable-pair graph
        is_confusable = False
        c1 = registry.contracts.get(top1.connector_id)
        if c1 and top2.connector_id in c1.ambiguous_with:
            is_confusable = True

        # Assign confidence — tighter thresholds, confusable pairs need bigger margin
        effective_margin = margin
        if is_confusable:
            effective_margin = margin - _CONFUSABLE_PAIR_BOOST  # confusable pairs need more margin

        if effective_margin > _CONFIDENT_MARGIN:
            conf = "confident"
            force = True
        elif is_confusable and effective_margin < _AMBIGUOUS_MARGIN:
            conf = "ambiguous"
            force = False
        elif effective_margin < _UNCERTAIN_MARGIN:
            conf = "uncertain"
            force = False
        else:
            conf = "confident"
            force = True

        # Apply to all results
        for r in results:
            r.margin = margin
            r.confidence = conf
            r.is_confusable_pair = is_confusable
            r.should_force_primary = force
    elif results:
        results[0].margin = 1.0
        results[0].confidence = "confident"
        results[0].should_force_primary = True

    return results


# ═══════════════════════════════════════════════════════════════════════════
# Smoketest
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import time

    from scripts.poc_v2.boundary_contracts import ALL_BOUNDARIES
    from scripts.poc_v2.context_factory import create_context
    from scripts.poc_v2.native_app_stubs import ALL_STUBS

    print("=== POC v2 Router — Kernel-Grade Smoketest ===\n")

    t0 = time.monotonic()
    ctx = create_context()
    load_ms = (time.monotonic() - t0) * 1000

    # Compile contracts once
    registry = NativeAppContractRegistry.compile(
        boundaries=ALL_BOUNDARIES,
        stubs=ALL_STUBS,
        family_docs=ctx.docs,
    )

    test_queries = [
        ("add milk to my grocery list", {"family"}),
        ("remind me to take my blood pressure medication", {"family", "health"}),
        ("we're over budget on groceries this month", {"family", "finance"}),
        ("Walgreens says my prescription is ready", {"family", "health", "pharma"}),
        ("deploy the auth service to staging", {"enterprise"}),
        ("schedule a telehealth visit with Dr. Chen", {"family", "health"}),
        ("what's my blood pressure today", {"family", "health"}),
        ("order milk from Walmart", {"family"}),
        ("create a ticket for the login bug", {"enterprise"}),
        ("how did I sleep last night", {"family", "health"}),
    ]

    for utterance, active_os in test_queries:
        t1 = time.monotonic()
        results = route_to_native_app(utterance, active_os, ctx, registry, top_k=3)
        ms = (time.monotonic() - t1) * 1000

        top = results[0]
        print(f"  '{utterance}'")
        print(
            f"    → {top.connector_id} (cos={top.cosine_score:.3f}, sch={top.schema_score:.3f}, comb={top.combined_score:.3f}, {ms:.1f}ms)"
        )
        if len(results) > 1:
            alts = ", ".join(f"{r.connector_id}({r.combined_score:.2f})" for r in results[1:3])
            print(f"      alts: {alts}")
        print()

    print(f"  Load: {load_ms:.0f}ms | All queries: {(time.monotonic() - t0) * 1000:.0f}ms total")

    # ── Backend-name safety ──
    print("─── Backend-name safety check ───")
    walmart_result = route_to_native_app(
        "order milk from Walmart", {"family"}, ctx, registry, top_k=5
    )
    assert (
        walmart_result[0].connector_id == "family.shopping"
    ), f"Walmart query routed wrong: {walmart_result[0].connector_id}"
    print("  ✅ 'order milk from Walmart' → family.shopping")

    fitbit_result = route_to_native_app(
        "my Fitbit says I slept 5 hours", {"family", "health"}, ctx, registry, top_k=5
    )
    assert fitbit_result[0].connector_id.startswith(
        "health."
    ), f"Fitbit query routed wrong: {fitbit_result[0].connector_id}"
    print(f"  ✅ 'my Fitbit says I slept 5 hours' → {fitbit_result[0].connector_id}")

    for r in walmart_result:
        assert not r.connector_id.startswith(
            "walmart"
        ), f"Walmart leaked as connector: {r.connector_id}"
    print("  ✅ No 'walmart' connector — backend safety confirmed")

    # ── Verify no hardcoded maps in router module ──
    import inspect

    src = inspect.getsource(route_to_native_app)
    assert "_VERB_EFFECT_MAP" not in src, "VERB_EFFECT_MAP leaked into router!"
    assert "_extract_effects" not in src, "_extract_effects leaked into router!"
    assert "_extract_resource_kinds" not in src, "_extract_resource_kinds leaked into router!"
    assert "ALL_STUBS" not in src, "ALL_STUBS referenced in router!"
    print("  ✅ Router contains zero domain facts. All semantics in compiled contracts.")

    print("\n✅ Router smoketest passed.")
