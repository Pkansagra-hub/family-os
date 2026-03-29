"""Analyze the 565K event dataset for R1 POC scoring matrix feasibility."""

import json
from collections import Counter
from pathlib import Path

SHARD = Path(r"D:\Modeling_studio\data\familyos\unified\output_healed_merged\shard_0000.jsonl")

# --- Diverse sample extraction ---
samples = {}

with open(SHARD, encoding="utf-8") as f:
    for line in f:
        j = json.loads(line)
        t = j["tasks"]

        if "keys_done" not in samples:
            print("=== Top-level keys:", list(j.keys()))
            print("=== Tasks keys:", list(t.keys()))
            print("=== Hub routing keys:", list(j.get("hub_routing", {}).keys()))
            samples["keys_done"] = True

        # CRISIS event
        if t.get("safety_familyos") == "CRISIS" and "crisis" not in samples:
            samples["crisis"] = j
        # RED event
        if t.get("safety_familyos") == "RED" and "red" not in samples:
            samples["red"] = j
        # Multi-emotion (5+)
        if len(t.get("emotions", [])) >= 5 and "high_emo" not in samples:
            samples["high_emo"] = j
        # Multi-NER (3+)
        if len(t.get("ner_family", [])) >= 3 and "multi_ner" not in samples:
            samples["multi_ner"] = j
        # Multi-relation (2+)
        if len(t.get("relations", [])) >= 2 and "multi_rel" not in samples:
            samples["multi_rel"] = j
        # Temporal event
        if len(t.get("temporal", [])) >= 2 and "multi_temporal" not in samples:
            samples["multi_temporal"] = j
        # query_memory intent
        if t.get("intent") == "query_memory" and "query" not in samples:
            samples["query"] = j
        # set_reminder
        if t.get("intent") == "set_reminder" and "reminder" not in samples:
            samples["reminder"] = j

for name, s in samples.items():
    if name == "keys_done":
        continue
    eid = s["id"]
    txt = s["text"][:150]
    t = s["tasks"]
    print(f"\n=== {name} ({eid}) ===")
    print(f"  text: {txt}")
    print(f"  emotions: {t['emotions']}")
    print(f"  sentiment: {t['sentiment']}")
    print(f"  intent: {t['intent']}")
    print(f"  ingress: {t['ingress']}")
    print(f"  safety: {t['safety_familyos']}")
    print(f"  ner_family: {t['ner_family']}")
    print(f"  relations: {t['relations']}")
    print(f"  temporal: {t['temporal']}")
    print(f"  hub_routing: {s['hub_routing']}")

# --- NER label distribution ---
print("\n\n=== NER Label Distribution ===")
ner_labels = Counter()
ner_tokens_sample = {}
with open(SHARD, encoding="utf-8") as f:
    for line in f:
        j = json.loads(line)
        for ent in j["tasks"].get("ner_family", []):
            label = ent["label"]
            ner_labels[label] += 1
            if label not in ner_tokens_sample:
                ner_tokens_sample[label] = ent["token"]

for k, v in ner_labels.most_common():
    print(f"  {k}: {v}  (e.g. '{ner_tokens_sample[k]}')")

# --- Temporal label distribution ---
print("\n=== Temporal Label Distribution ===")
temporal_labels = Counter()
with open(SHARD, encoding="utf-8") as f:
    for line in f:
        j = json.loads(line)
        for ent in j["tasks"].get("temporal", []):
            temporal_labels[ent["label"]] += 1
for k, v in temporal_labels.most_common():
    print(f"  {k}: {v}")

# --- Relation predicate distribution ---
print("\n=== Relation Predicate Distribution ===")
rel_preds = Counter()
with open(SHARD, encoding="utf-8") as f:
    for line in f:
        j = json.loads(line)
        for rel in j["tasks"].get("relations", []):
            rel_preds[rel["predicate"]] += 1
for k, v in rel_preds.most_common():
    print(f"  {k}: {v}")

# --- Emotion co-occurrence stats ---
print("\n=== Emotion Count Per Event ===")
emo_counts = Counter()
with open(SHARD, encoding="utf-8") as f:
    for line in f:
        j = json.loads(line)
        emo_counts[len(j["tasks"].get("emotions", []))] += 1
for k in sorted(emo_counts.keys()):
    print(f"  {k} emotions: {emo_counts[k]} events")
