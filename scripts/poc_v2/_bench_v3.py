"""Benchmark v3: calibrated confidence + proper false-confident split."""
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
            if "label_type" not in q: q["label_type"] = "hard_gold"
            if "acceptable_apps" not in q: q["acceptable_apps"] = []
            if "must_include_top3" not in q: q["must_include_top3"] = []
            queries.append(q)

print(f"Loaded {len(queries)} queries")
print("Loading router...")
t0 = time.monotonic()
ctx = create_context()
registry = NativeAppContractRegistry.compile(boundaries=ALL_BOUNDARIES, stubs=ALL_STUBS, family_docs=ctx.docs)
print(f"Ready ({(time.monotonic()-t0)*1000:.0f}ms)")

# ── Metrics ──
strict_correct = 0
acceptable_correct = 0
top3_recall = 0
acceptable_top3 = 0
must_include_pass = 0
leakage = 0
backend_fails = 0
total_ms = 0.0

# Confidence-split metrics
confident_total = 0
confident_correct = 0
ambiguous_total = 0
ambiguous_correct = 0
uncertain_total = 0
uncertain_correct = 0
# False confident: unacceptable top-1, split by margin
unacceptable_top1 = 0
false_confident_high_margin = 0   # unacceptable + margin > 0.15
ambiguous_wrong = 0                # unacceptable + margin < 0.08
uncertain_wrong = 0               # unacceptable + intermediate 0.08-0.15
# Confusable-pair stats
confusable_total = 0
confusable_acceptable = 0

by_tier = defaultdict(lambda: {"total": 0, "strict": 0, "accept": 0, "top3": 0, "accept_top3": 0, "must_include": 0, "unacc": 0, "fc_high": 0, "ambig_wrong": 0})
by_os = defaultdict(lambda: {"total": 0, "strict": 0, "unacc": 0})
by_pair = defaultdict(lambda: {"total": 0})
pair_samples = defaultdict(list)
confidence_dist = defaultdict(int)

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
    margin = results[0].margin if results else 0.0
    confidence = results[0].confidence if results else "uncertain"
    is_confusable = results[0].is_confusable_pair if results else False

    confidence_dist[confidence] += 1

    # Strict
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

    # Confidence-split
    if confidence == "confident":
        confident_total += 1
        if top1 == expected: confident_correct += 1
    elif confidence == "ambiguous":
        ambiguous_total += 1
        if top1 == expected: ambiguous_correct += 1
    else:
        uncertain_total += 1
        if top1 == expected: uncertain_correct += 1

    # False confident split
    if not top1_ok:
        unacceptable_top1 += 1
        if margin > 0.15:
            false_confident_high_margin += 1
        elif margin < 0.08:
            ambiguous_wrong += 1
        else:
            uncertain_wrong += 1

    # Confusable pair
    if is_confusable:
        confusable_total += 1
        if top1_ok:
            confusable_acceptable += 1

    # Leakage
    if top_ids:
        top_domain = ctx.os_domain_map.get(top1, "?")
        if top_domain not in active_os:
            leakage += 1

    # Backend safety
    for hint in q.get("backend_hints", []):
        h = hint.lower().replace(" ", "").replace("-", "")
        if top_ids and h in top1.lower().replace(".", "").replace("_", ""):
            if not top1.startswith(("family.", "health.", "finance.", "pharmaos.", "enterprise.")):
                backend_fails += 1

    # Tier
    bt = by_tier[tier]
    bt["total"] += 1
    if top1 == expected: bt["strict"] += 1
    if top1_ok: bt["accept"] += 1
    if expected in top3_set: bt["top3"] += 1
    if acceptable & top3_set: bt["accept_top3"] += 1
    if mi_ok: bt["must_include"] += 1
    if not top1_ok:
        bt["unacc"] += 1
        if margin > 0.15: bt["fc_high"] += 1
        elif margin < 0.08: bt["ambig_wrong"] += 1

    # OS
    os_d = ctx.os_domain_map.get(expected, "?")
    by_os[os_d]["total"] += 1
    if top1 == expected: by_os[os_d]["strict"] += 1
    if not top1_ok: by_os[os_d]["unacc"] += 1

    # Confusion pairs
    if top1 != expected:
        pair = tuple(sorted([expected, top1]))
        by_pair[pair]["total"] += 1
        if len(pair_samples[pair]) < 2:
            pair_samples[pair].append((utterance[:70], expected, top1, margin))

n = len(queries)

def pct(x, tot): return x/tot*100 if tot else 0

print(f"\n{'='*75}")
print(f"  NATIVE-APP ROUTER BENCHMARK v3 — {n} generated queries")
print(f"  with calibrated confidence + ambiguity gate")
print(f"{'='*75}")

print(f"\n  -- Core metrics --")
print(f"  Strict C@1:              {strict_correct:>5}/{n} = {strict_correct/n*100:.1f}%")
print(f"  Acceptable C@1:          {acceptable_correct:>5}/{n} = {acceptable_correct/n*100:.1f}%")
print(f"  Top-3 Recall:            {top3_recall:>5}/{n} = {top3_recall/n*100:.1f}%")
print(f"  Acceptable Top-3:        {acceptable_top3:>5}/{n} = {acceptable_top3/n*100:.1f}%")
print(f"  Must-Include Pass:       {must_include_pass:>5}/{n} = {must_include_pass/n*100:.1f}%")
print(f"  Active-OS Leakage:       {leakage}")
print(f"  Backend Safety Fails:    {backend_fails}")
print(f"  Avg Latency:             {total_ms/n:.1f}ms")

print(f"\n  -- Confidence split --")
print(f"  Confident:   {confident_total:>5} ({pct(confident_total,n):.1f}%)  C@1={pct(confident_correct,confident_total):.1f}%")
print(f"  Ambiguous:   {ambiguous_total:>5} ({pct(ambiguous_total,n):.1f}%)  C@1={pct(ambiguous_correct,ambiguous_total):.1f}%")
print(f"  Uncertain:   {uncertain_total:>5} ({pct(uncertain_total,n):.1f}%)  C@1={pct(uncertain_correct,uncertain_total):.1f}%")

print(f"\n  -- False-confident split (unacceptable top-1) --")
print(f"  Unacceptable Top-1:         {unacceptable_top1:>5} ({pct(unacceptable_top1,n):.1f}%)")
print(f"  ├─ False Confident (>0.12): {false_confident_high_margin:>5} ({pct(false_confident_high_margin,n):.1f}%)  high-margin real errors")
print(f"  ├─ Ambiguous Wrong   (<0.05): {ambiguous_wrong:>5} ({pct(ambiguous_wrong,n):.1f}%)  low-margin, confusable pair")
print(f"  └─ Uncertain Wrong  (0.05-0.12): {uncertain_wrong:>5} ({pct(uncertain_wrong,n):.1f}%)  intermediate")

print(f"\n  -- Confusable-pair stats --")
print(f"  Confusable pairs triggered: {confusable_total} ({pct(confusable_total,n):.1f}%)")
print(f"  Acceptable when confusable: {confusable_acceptable}/{confusable_total} = {pct(confusable_acceptable,confusable_total):.1f}%")

print(f"\n  -- By tier --")
print(f"  {'Tier':<20} {'#':>5} {'Strict':>7} {'Accept':>7} {'Top3':>7} {'AccT3':>7} {'Unacc':>6} {'FCHi':>5} {'AmbW':>5}")
print(f"  {'-'*75}")
for tier in sorted(by_tier.keys()):
    t = by_tier[tier]
    tot = t["total"]
    print(f"  {tier:<20} {tot:>5} {pct(t['strict'],tot):>6.1f}% {pct(t['accept'],tot):>6.1f}% {pct(t['top3'],tot):>6.1f}% {pct(t['accept_top3'],tot):>6.1f}% {pct(t['unacc'],tot):>5.1f}% {pct(t['fc_high'],tot):>4.1f}% {pct(t['ambig_wrong'],tot):>4.1f}%")

print(f"\n  -- By OS domain --")
print(f"  {'Domain':<15} {'#':>5} {'Strict':>8} {'Unacc':>7}")
for os_d in sorted(by_os.keys()):
    t = by_os[os_d]
    print(f"  {os_d:<15} {t['total']:>5} {pct(t['strict'],t['total']):>7.1f}% {pct(t['unacc'],t['total']):>6.1f}%")

print(f"\n  -- Top confusion pairs (with margin) --")
for pair, stats in sorted(by_pair.items(), key=lambda x: -x[1]["total"])[:12]:
    a, b = pair
    print(f"  {a} <-> {b}: {stats['total']} confusions")
    for utt, exp, got, margin in pair_samples[pair]:
        print(f"    \"{utt}\"  label={exp}  router={got}  margin={margin:.3f}")
