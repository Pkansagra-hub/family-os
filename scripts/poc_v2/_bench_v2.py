"""Benchmark v2: proper scoring with acceptable_apps + confusion families."""
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
            if "label_type" not in q:
                q["label_type"] = "hard_gold"
            if "acceptable_apps" not in q:
                q["acceptable_apps"] = []
            if "must_include_top3" not in q:
                q["must_include_top3"] = []
            queries.append(q)

print(f"Loaded {len(queries)} queries")
print("Loading router...")
t0 = time.monotonic()
ctx = create_context()
registry = NativeAppContractRegistry.compile(boundaries=ALL_BOUNDARIES, stubs=ALL_STUBS, family_docs=ctx.docs)
print(f"Ready ({(time.monotonic()-t0)*1000:.0f}ms)")

strict_correct = 0
acceptable_correct = 0
top3_recall = 0
acceptable_top3 = 0
must_include_pass = 0
false_confident = 0
leakage = 0
backend_fails = 0
total_ms = 0.0

by_tier = defaultdict(lambda: {"total": 0, "strict": 0, "accept": 0, "top3": 0, "accept_top3": 0, "must_include": 0, "false_conf": 0})
by_os = defaultdict(lambda: {"total": 0, "strict": 0})
by_pair = defaultdict(lambda: {"total": 0})
pair_samples = defaultdict(list)

for q in queries:
    utterance = q["utterance"]
    expected = q["expected_native_app"]
    active_os = q.get("active_os_set", {"family"})
    tier = q.get("tier", "?")
    acceptable = set(q.get("acceptable_apps", []) or [])
    must_include = set(q.get("must_include_top3", []) or [])
    acceptable.add(expected)

    t1 = time.monotonic()
    results = route_to_native_app(utterance, active_os, ctx, registry, top_k=5, use_schema=True)
    ms = (time.monotonic() - t1) * 1000
    total_ms += ms

    top_ids = [r.connector_id for r in results]
    top1 = top_ids[0] if top_ids else "?"
    top3_set = set(top_ids[:3])

    if top1 == expected:
        strict_correct += 1
    top1_ok = top1 in acceptable
    if top1_ok:
        acceptable_correct += 1
    if expected in top3_set:
        top3_recall += 1
    if acceptable & top3_set:
        acceptable_top3 += 1
    mi_ok = must_include.issubset(top3_set) if must_include else True
    if mi_ok:
        must_include_pass += 1
    if not top1_ok:
        false_confident += 1

    if top_ids:
        top_domain = ctx.os_domain_map.get(top1, "?")
        if top_domain not in active_os:
            leakage += 1

    for hint in q.get("backend_hints", []):
        h = hint.lower().replace(" ", "").replace("-", "")
        if top_ids and h in top1.lower().replace(".", "").replace("_", ""):
            if not top1.startswith(("family.", "health.", "finance.", "pharmaos.", "enterprise.")):
                backend_fails += 1

    bt = by_tier[tier]
    bt["total"] += 1
    if top1 == expected: bt["strict"] += 1
    if top1_ok: bt["accept"] += 1
    if expected in top3_set: bt["top3"] += 1
    if acceptable & top3_set: bt["accept_top3"] += 1
    if mi_ok: bt["must_include"] += 1
    if not top1_ok: bt["false_conf"] += 1

    os_d = ctx.os_domain_map.get(expected, "?")
    by_os[os_d]["total"] += 1
    if top1 == expected:
        by_os[os_d]["strict"] += 1

    if top1 != expected:
        pair = tuple(sorted([expected, top1]))
        by_pair[pair]["total"] += 1
        if len(pair_samples[pair]) < 2:
            pair_samples[pair].append((utterance[:70], expected, top1))

n = len(queries)

def pct(x, tot):
    return x/tot*100 if tot else 0

print(f"\n{'='*70}")
print(f"  NATIVE-APP ROUTER BENCHMARK — {n} generated queries")
print(f"{'='*70}")

print(f"\n  -- Core metrics --")
print(f"  Strict C@1:              {strict_correct:>5}/{n} = {strict_correct/n*100:.1f}%")
print(f"  Acceptable C@1:          {acceptable_correct:>5}/{n} = {acceptable_correct/n*100:.1f}%")
print(f"  Top-3 Recall:            {top3_recall:>5}/{n} = {top3_recall/n*100:.1f}%")
print(f"  Acceptable Top-3:        {acceptable_top3:>5}/{n} = {acceptable_top3/n*100:.1f}%")
print(f"  Must-Include Pass:       {must_include_pass:>5}/{n} = {must_include_pass/n*100:.1f}%")
print(f"  False Confident Wrong:   {false_confident:>5}/{n} = {false_confident/n*100:.1f}%")
print(f"  Active-OS Leakage:       {leakage}")
print(f"  Backend Safety Fails:    {backend_fails}")
print(f"  Avg Latency:             {total_ms/n:.1f}ms")

print(f"\n  -- By tier --")
print(f"  {'Tier':<20} {'#':>5} {'Strict':>7} {'Accept':>7} {'Top3':>7} {'AccT3':>7} {'MI':>5} {'False':>6}")
print(f"  {'-'*70}")
for tier in sorted(by_tier.keys()):
    t = by_tier[tier]
    tot = t["total"]
    print(f"  {tier:<20} {tot:>5} {pct(t['strict'],tot):>6.1f}% {pct(t['accept'],tot):>6.1f}% {pct(t['top3'],tot):>6.1f}% {pct(t['accept_top3'],tot):>6.1f}% {pct(t['must_include'],tot):>4.1f}% {pct(t['false_conf'],tot):>5.1f}%")

print(f"\n  -- By OS domain --")
for os_d in sorted(by_os.keys()):
    t = by_os[os_d]
    print(f"  {os_d:<15} {t['total']:>5}  Strict C@1={pct(t['strict'],t['total']):.1f}%")

print(f"\n  -- Top confusion pairs --")
for pair, stats in sorted(by_pair.items(), key=lambda x: -x[1]["total"])[:15]:
    a, b = pair
    print(f"  {a} <-> {b}: {stats['total']} confusions")
    for utt, exp, got in pair_samples[pair]:
        print(f"    \"{utt}\"  label={exp}  router={got}")

print(f"\n  -- Ambiguous tier --")
ambig = [q for q in queries if q.get("tier") == "ambiguous"]
ambig_with_acc = [q for q in ambig if q.get("acceptable_apps")]
print(f"  Total ambiguous: {len(ambig)}")
print(f"  With acceptable_apps: {len(ambig_with_acc)}")
