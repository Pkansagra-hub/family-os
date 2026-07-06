"""Benchmark + audit: run all generated queries through router, print results."""
import json, sys, time
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.poc_v2.context_factory import create_context
from scripts.poc_v2.boundary_contracts import ALL_BOUNDARIES
from scripts.poc_v2.native_app_stubs import ALL_STUBS
from scripts.poc_v2.contract_compiler import NativeAppContractRegistry
from scripts.poc_v2.router import route_to_native_app

gen_path = Path(__file__).resolve().parent.parent.parent / "data" / "poc_v2" / "generated_bench_queries.jsonl"
queries = []
with open(gen_path, encoding="utf-8") as f:
    for line in f:
        if line.strip():
            q = json.loads(line)
            if isinstance(q.get("active_os_set"), list):
                q["active_os_set"] = set(q["active_os_set"])
            queries.append(q)

print(f"Loaded {len(queries)} queries")
print("Loading router...")
t0 = time.monotonic()
ctx = create_context()
registry = NativeAppContractRegistry.compile(boundaries=ALL_BOUNDARIES, stubs=ALL_STUBS, family_docs=ctx.docs)
print(f"Ready ({(time.monotonic()-t0)*1000:.0f}ms)")

# Stats
correct, top3, leakage, backend_fails = 0, 0, 0, 0
by_tier: dict = defaultdict(lambda: {"total": 0, "correct": 0, "top3": 0})
by_os: dict = defaultdict(lambda: {"total": 0, "correct": 0})
label_gravity: dict = defaultdict(int)  # "expected -> router_top1"
total_ms = 0.0

for q in queries:
    utterance = q["utterance"]
    expected = q["expected_native_app"]
    active_os = q.get("active_os_set", {"family"})
    tier = q.get("tier", "?")

    t1 = time.monotonic()
    results = route_to_native_app(utterance, active_os, ctx, registry, top_k=5, use_schema=True)
    ms = (time.monotonic() - t1) * 1000
    total_ms += ms

    top_ids = [r.connector_id for r in results]
    top1 = top_ids[0] if top_ids else "?"

    if top1 == expected:
        correct += 1
    if expected in top_ids[:3]:
        top3 += 1

    if top_ids:
        top_domain = ctx.os_domain_map.get(top1, "?")
        if top_domain not in active_os:
            leakage += 1

    for hint in q.get("backend_hints", []):
        h = hint.lower().replace(" ", "").replace("-", "")
        if top_ids and h in top1.lower().replace(".", "").replace("_", ""):
            if not top1.startswith(("family.", "health.", "finance.", "pharmaos.", "enterprise.")):
                backend_fails += 1

    by_tier[tier]["total"] += 1
    if top1 == expected:
        by_tier[tier]["correct"] += 1
    if expected in top_ids[:3]:
        by_tier[tier]["top3"] += 1

    os_d = ctx.os_domain_map.get(expected, "?")
    by_os[os_d]["total"] += 1
    if top1 == expected:
        by_os[os_d]["correct"] += 1

    if top1 != expected:
        label_gravity[f"{expected} -> {top1}"] += 1

n = len(queries)

# === REPORT ===
print(f"\n{'='*70}")
print(f"  GENERATED BENCHMARK — {n} queries")
print(f"{'='*70}")
print(f"  C@1:  {correct}/{n} = {correct/n*100:.1f}%")
print(f"  C@3:  {top3}/{n} = {top3/n*100:.1f}%")
print(f"  Leak: {leakage}/{n}  |  Backend fails: {backend_fails}  |  Avg: {total_ms/n:.1f}ms")
print(f"{'='*70}")

print(f"\n  {'Tier':<20} {'#':>5} {'C@1':>7} {'C@3':>7}")
print(f"  {'-'*42}")
for tier in sorted(by_tier.keys()):
    t = by_tier[tier]
    p1 = t["correct"]/t["total"]*100 if t["total"] else 0
    p3 = t["top3"]/t["total"]*100 if t["total"] else 0
    print(f"  {tier:<20} {t['total']:>5} {p1:>6.1f}% {p3:>6.1f}%")

print(f"\n  {'OS Domain':<15} {'#':>5} {'C@1':>7}")
print(f"  {'-'*30}")
for os_d in sorted(by_os.keys()):
    t = by_os[os_d]
    p1 = t["correct"]/t["total"]*100 if t["total"] else 0
    print(f"  {os_d:<15} {t['total']:>5} {p1:>6.1f}%")

print(f"\n  Top label-gravity (expected -> router_top1):")
for pair, count in sorted(label_gravity.items(), key=lambda x: -x[1])[:12]:
    print(f"    {pair}: {count}")
