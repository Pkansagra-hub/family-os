"""Diagnose false-confident: what patterns cause high-margin wrongs?"""
import json, sys, time
from collections import defaultdict
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

# Collect false-confident (high-margin >0.12, unacceptable top-1)
fc_wrongs = []
with open(gen_path, encoding="utf-8") as f:
    for line in f:
        if not line.strip(): continue
        q = json.loads(line)
        active_os = set(q.get("active_os_set", ["family"]))
        results = route_to_native_app(q["utterance"], active_os, ctx, registry, top_k=5, use_schema=True)
        top1 = results[0]
        expected = q["expected_native_app"]
        acceptable = set(q.get("acceptable_apps", []) or []) | {expected}

        if top1.connector_id not in acceptable and top1.margin > 0.12:
            signals = registry.signal_extractor.extract(q["utterance"])
            fc_wrongs.append({
                "utterance": q["utterance"][:90],
                "expected": expected,
                "router_top1": top1.connector_id,
                "margin": top1.margin,
                "cosine": top1.cosine_score,
                "schema": top1.schema_score,
                "effects": signals.effects,
                "resources": signals.resources,
                "backends": signals.backend_hints,
            })

print(f"False-confident (margin>0.12, unacceptable): {len(fc_wrongs)}")

# Group by expected->router pattern
by_pattern = defaultdict(list)
for w in fc_wrongs:
    pattern = f"{w['expected']} -> {w['router_top1']}"
    by_pattern[pattern].append(w)

print("\n=== Top false-confident patterns ===\n")
for pattern, items in sorted(by_pattern.items(), key=lambda x: -len(x[1]))[:20]:
    print(f"  {pattern}: {len(items)}")
    for w in items[:3]:
        print(f"    \"{w['utterance']}\"")
        print(f"    margin={w['margin']:.3f} cos={w['cosine']:.3f} sch={w['schema']:.3f}")
        print(f"    eff={w['effects']} res={w['resources']} bk={w['backends']}")
        # Check boundary
        exp_b = ALL_BOUNDARIES.get(w['expected'])
        top_b = ALL_BOUNDARIES.get(w['router_top1'])
        if exp_b:
            print(f"    expected owns: {exp_b.owns_resources[:5]}  NOT: {exp_b.does_not_own_resources[:3]}")
        if top_b:
            print(f"    router   owns: {top_b.owns_resources[:5]}  NOT: {top_b.does_not_own_resources[:3]}")
    print()
