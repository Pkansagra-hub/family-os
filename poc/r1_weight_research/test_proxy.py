"""Quick test of proxy_labels on shard_0000."""

import json
from collections import Counter

from poc.r1_weight_research.proxy_labels import assign_proxy_tier

SHARD = r"D:\Modeling_studio\data\familyos\unified\output_healed_merged\shard_0000.jsonl"

tiers = Counter()
samples: dict = {}

with open(SHARD, encoding="utf-8") as f:
    for line in f:
        event = json.loads(line)
        tier = assign_proxy_tier(event)
        tiers[tier] += 1
        if tier not in samples:
            samples[tier] = event

total = sum(tiers.values())
print(f"Total: {total}")
print("\n=== Proxy Tier Distribution ===")
order = ["CRITICAL", "HIGH", "MEDIUM_HIGH", "MEDIUM", "LOW_MEDIUM", "LOW"]
for tier in order:
    count = tiers.get(tier, 0)
    pct = count * 100 / total
    print(f"  {tier:13s}: {count:5d} ({pct:5.1f}%)")

# Show sample event for each tier
for tier in order:
    e = samples.get(tier)
    if not e:
        continue
    t = e["tasks"]
    r = e["hub_routing"]
    eid = e["id"]
    txt = e["text"][:100]
    safety = t["safety_familyos"]
    sent = t["sentiment"]
    emos = t["emotions"][:3]
    print(f"\n--- {tier} sample ({eid}) ---")
    print(f"  text: {txt}")
    print(f"  safety={safety}, sentiment={sent}, emotions={emos}...")
    print(f"  routing: EMO={r['EMO']}, REL={r['REL']}, MEM={r['MEM']}, TASK={r['TASK']}")
    print(f"  routing: EMO={r['EMO']}, REL={r['REL']}, MEM={r['MEM']}, TASK={r['TASK']}")
