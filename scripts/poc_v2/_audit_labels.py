"""Audit: where does router disagree with generated labels?"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.poc_v2.context_factory import create_context
from scripts.poc_v2.boundary_contracts import ALL_BOUNDARIES
from scripts.poc_v2.native_app_stubs import ALL_STUBS
from scripts.poc_v2.contract_compiler import NativeAppContractRegistry
from scripts.poc_v2.router import route_to_native_app

ctx = create_context()
registry = NativeAppContractRegistry.compile(boundaries=ALL_BOUNDARIES, stubs=ALL_STUBS, family_docs=ctx.docs)

gen_path = Path(__file__).resolve().parent.parent.parent / "data" / "poc_v2" / "generated_bench_queries.jsonl"

disagreements = []
total = 0
label_gravity = {}  # expected_app -> router_top1
with open(gen_path, encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        q = json.loads(line)
        total += 1
        active_os = set(q.get("active_os_set", ["family"]))
        results = route_to_native_app(q["utterance"], active_os, ctx, registry, top_k=3, use_schema=True)
        top1 = results[0].connector_id if results else "?"
        expected = q["expected_native_app"]

        if top1 != expected:
            top3 = [r.connector_id for r in results]
            pair = f"{expected} -> {top1}"
            label_gravity[pair] = label_gravity.get(pair, 0) + 1
            disagreements.append({
                "utterance": q["utterance"][:80],
                "expected": expected,
                "router_top1": top1,
                "router_top3": top3,
                "tier": q.get("tier", "?"),
                "rationale": q.get("rationale", "")[:80],
            })

print(f"Total: {total}")
print(f"Router disagrees with label: {len(disagreements)} ({len(disagreements)/total*100:.1f}%)")
print()

# Top label-gravity patterns
print("=== Top label-gravity patterns (expected -> router_top1) ===")
for pair, count in sorted(label_gravity.items(), key=lambda x: -x[1])[:20]:
    print(f"  {pair}: {count}")

# Show sample disagreements by pattern
print("\n=== Sample disagreements ===")
shown = set()
for d in disagreements:
    pattern = f"{d['expected']} -> {d['router_top1']}"
    if pattern not in shown:
        shown.add(pattern)
        print(f"\n  [{d['tier']}] \"{d['utterance']}\"")
        print(f"  Label: {d['expected']} | Router: {d['router_top1']}")
        print(f"  Top-3: {d['router_top3']}")
        print(f"  Rationale: {d['rationale']}")
    if len(shown) >= 25:
        break
