"""
POC v2: Schema Delta Report — old vs new schema scoring
==========================================================
Diagnostic: which queries regressed after the kernel refactor?

Usage:
  python scripts/poc_v2/debug_schema_delta.py
"""

from __future__ import annotations

import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.poc_v2.bench_queries import ALL_QUERIES
from scripts.poc_v2.boundary_contracts import ALL_BOUNDARIES
from scripts.poc_v2.context_factory import create_context
from scripts.poc_v2.contract_compiler import NativeAppContractRegistry
from scripts.poc_v2.native_app_stubs import ALL_STUBS
from scripts.poc_v2.router import route_to_native_app


@dataclass
class DeltaRow:
    query_id: str
    utterance: str
    tier: str
    expected: str
    old_top1: str
    old_top3: list[str]
    new_top1: str
    new_top3: list[str]
    old_correct: bool
    new_correct: bool
    status: str  # "ok→ok" | "ok→wrong" | "wrong→ok" | "wrong→wrong" | "top3_lost"
    old_schema_signals: str
    new_schema_signals: str


def run_delta() -> list[DeltaRow]:
    """Run both old and new schema scoring on all 120 queries, compare."""
    ctx = create_context()
    registry = NativeAppContractRegistry.compile(
        boundaries=ALL_BOUNDARIES,
        stubs=ALL_STUBS,
        family_docs=ctx.docs,
    )

    rows: list[DeltaRow] = []

    for q in ALL_QUERIES:
        utterance = q["utterance"]
        active_os = q["active_os_set"]
        expected = q["expected_native_app"]
        tier = q["tier"]

        # ── Old: raw MiniLM (no schema) ──
        old_results = route_to_native_app(
            utterance,
            active_os,
            ctx,
            registry,
            top_k=5,
            use_schema=False,
        )
        old_top1 = old_results[0].connector_id if old_results else "?"
        old_top3 = [r.connector_id for r in old_results[:3]]
        old_correct = old_top1 == expected

        # ── New: MiniLM + compiled schema ──
        new_results = route_to_native_app(
            utterance,
            active_os,
            ctx,
            registry,
            top_k=5,
            use_schema=True,
        )
        new_top1 = new_results[0].connector_id if new_results else "?"
        new_top3 = [r.connector_id for r in new_results[:3]]
        new_correct = new_top1 == expected

        # ── Signal extraction ──
        signals = registry.signal_extractor.extract(utterance)

        # ── Status ──
        if old_correct and new_correct:
            status = "ok->ok"
        elif old_correct and not new_correct:
            status = "ok->wrong"
        elif not old_correct and new_correct:
            status = "wrong->ok"
        elif not old_correct and not new_correct:
            # Check if expected fell out of top-3
            if expected in old_top3 and expected not in new_top3:
                status = "top3_lost"
            else:
                status = "wrong->wrong"
        else:
            status = "?"

        rows.append(
            DeltaRow(
                query_id=q["id"],
                utterance=utterance[:80],
                tier=tier,
                expected=expected,
                old_top1=old_top1,
                old_top3=old_top3,
                new_top1=new_top1,
                new_top3=new_top3,
                old_correct=old_correct,
                new_correct=new_correct,
                status=status,
                old_schema_signals="",
                new_schema_signals=f"eff={signals.effects} res={signals.resources} bk={[s for s,_ in signals.backend_hints]}",
            )
        )

    return rows


def print_delta_report(rows: list[DeltaRow]) -> None:
    """Print diagnostic delta report."""
    by_status = defaultdict(list)
    for r in rows:
        by_status[r.status].append(r)
    by_tier = defaultdict(list)
    for r in rows:
        by_tier[r.tier].append(r)

    print(f"\n{'='*80}")
    print(f"  SCHEMA DELTA REPORT — Old (raw MiniLM) vs New (compiled schema)")
    print(f"{'='*80}")

    # ── Summary ──
    total = len(rows)
    old_ok = sum(1 for r in rows if r.old_correct)
    new_ok = sum(1 for r in rows if r.new_correct)
    print(f"\n  Overall: {old_ok}->{new_ok} C@1  (delta: {new_ok - old_ok:+d})")
    for status in ["ok->wrong", "wrong->ok", "top3_lost", "wrong->wrong", "ok->ok"]:
        count = len(by_status.get(status, []))
        if count > 0:
            print(f"    {status}: {count}")

    # ── Per-tier breakdown ──
    print(f"  {'-'*76}")
    print(
        f"  {'Tier':<28} {'#':>4} {'Old C@1':>8} {'New C@1':>8} {'Delta':>6} {'Lost':>5} {'Gained':>5}"
    )
    print(f"  {'-'*76}")
    for tier in [
        "tier1_family",
        "tier2_health",
        "tier3_finance",
        "tier4_pharma",
        "tier5_enterprise",
        "tier6_backend",
    ]:
        tier_rows = by_tier.get(tier, [])
        if not tier_rows:
            continue
        n = len(tier_rows)
        old_c = sum(1 for r in tier_rows if r.old_correct)
        new_c = sum(1 for r in tier_rows if r.new_correct)
        lost = sum(1 for r in tier_rows if r.status == "ok->wrong")
        gained = sum(1 for r in tier_rows if r.status == "wrong->ok")
        delta = new_c - old_c
        print(
            f"  {tier:<28} {n:>4} {old_c/n*100:>7.1f}% {new_c/n*100:>7.1f}% {delta:>+5}  {lost:>4}  {gained:>4}"
        )

    # ── Regressions (ok→wrong) ──
    regressions = by_status.get("ok->wrong", [])
    if regressions:
        print(f"\n{'='*80}")
        print(f"  REGRESSIONS — old correct, new wrong ({len(regressions)} queries)")
        print(f"{'='*80}")
        for r in sorted(regressions, key=lambda x: x.tier):
            print(f"\n  [{r.query_id}] {r.tier}")
            print(f"    utterance:  '{r.utterance}'")
            print(f"    expected:   {r.expected}")
            print(f"    old top-3:  {r.old_top3}")
            print(f"    new top-3:  {r.new_top3}")
            print(f"    new signals: {r.new_schema_signals}")
            # Show what the new top-1's contract looks like
            new_top_contract = ALL_BOUNDARIES.get(r.new_top1)
            if new_top_contract:
                print(f"    new #1 owns:  {new_top_contract.owns_resources[:6]}")
                print(f"    new #1 NOT:   {new_top_contract.does_not_own_resources[:4]}")
            exp_contract = ALL_BOUNDARIES.get(r.expected)
            if exp_contract:
                print(f"    expected owns: {exp_contract.owns_resources[:6]}")

    # ── Improvements (wrong→ok) ──
    improvements = by_status.get("wrong->ok", [])
    if improvements:
        print(f"\n{'='*80}")
        print(f"  IMPROVEMENTS — old wrong, new correct ({len(improvements)} queries)")
        print(f"{'='*80}")
        for r in sorted(improvements, key=lambda x: x.tier)[:10]:
            print(f"\n  [{r.query_id}] {r.tier}")
            print(f"    utterance:  '{r.utterance}'")
            print(f"    expected:   {r.expected}")
            print(f"    old top-3:  {r.old_top3}")
            print(f"    new top-3:  {r.new_top3}")
            print(f"    new signals: {r.new_schema_signals}")

    # ── Top-3 losses ──
    top3_lost = by_status.get("top3_lost", [])
    if top3_lost:
        print(f"\n{'='*80}")
        print(f"  TOP-3 LOST — expected fell out of top-3 ({len(top3_lost)} queries)")
        print(f"{'='*80}")
        for r in sorted(top3_lost, key=lambda x: x.tier):
            print(f"\n  [{r.query_id}] {r.tier}")
            print(f"    utterance:  '{r.utterance}'")
            print(f"    expected:   {r.expected}")
            print(f"    old top-3:  {r.old_top3}")
            print(f"    new top-3:  {r.new_top3}")
            print(f"    new signals: {r.new_schema_signals}")

    # ── Pharma/Enterprise regression detail ──
    print(f"\n{'='*80}")
    print(f"  PHARMA + ENTERPRISE REGRESSION DEEP DIVE")
    print(f"{'='*80}")
    for tier in ["tier4_pharma", "tier5_enterprise"]:
        tier_rows = [r for r in by_tier.get(tier, []) if r.status in ("ok->wrong", "top3_lost")]
        if tier_rows:
            print(f"\n  --- {tier} ({len(tier_rows)} problem queries) ---")
            for r in tier_rows:
                print(f"\n    [{r.query_id}] status={r.status}")
                print(f"      utterance: '{r.utterance}'")
                print(f"      expected:  {r.expected}")
                print(f"      old #1:    {r.old_top1}  (correct={r.old_correct})")
                print(f"      new #1:    {r.new_top1}  (correct={r.new_correct})")

    # ── Signal statistics ──
    print(f"\n{'='*80}")
    print(f"  SIGNAL DISTRIBUTION (all 120 queries)")
    print(f"{'='*80}")
    eff_counts: dict[str, int] = defaultdict(int)
    res_counts: dict[str, int] = defaultdict(int)
    bk_counts: dict[str, int] = defaultdict(int)
    for r in rows:
        # Parse signals from new_schema_signals string
        sig = r.new_schema_signals
        if "eff=" in sig:
            eff_part = sig.split("eff=")[1].split(" res=")[0]
            for e in eff_part.strip("{}").split(", "):
                if e:
                    eff_counts[e] += 1
        if "res=" in sig:
            res_part = sig.split("res=")[1].split(" bk=")[0]
            for res in res_part.strip("{}").split(", "):
                if res:
                    res_counts[res] += 1
        if "bk=" in sig:
            bk_part = sig.split("bk=")[1].strip("[]")
            if bk_part:
                bk_counts[bk_part] += 1

    print(f"\n  Top effects detected:")
    for eff, count in sorted(eff_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"    {eff}: {count}")

    print(f"\n  Top resources detected:")
    for res, count in sorted(res_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"    {res}: {count}")

    print(f"\n  Backend hints detected:")
    for bk, count in sorted(bk_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"    {bk}: {count}")


if __name__ == "__main__":
    print("Running schema delta diagnostic...")
    t0 = time.monotonic()
    rows = run_delta()
    print(f"  Analyzed {len(rows)} queries in {(time.monotonic() - t0)*1000:.0f}ms")
    print_delta_report(rows)
