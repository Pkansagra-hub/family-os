#!/usr/bin/env python3
"""Test UltraBERT 12 capabilities with robust family context examples."""

from familyos_ultrabert import Client

c = Client(backend="pytorch", warmup=True)

tests = [
    # Family relationships
    "My daughter Sarah and I went to the park",
    "Grandma is coming for Thanksgiving dinner next week",
    "My husband picked up the kids from soccer practice",
    # Family events
    "We celebrated Emma birthday party with cake and balloons",
    "Family reunion at Uncle Bob house this Saturday",
    "Mom and Dad anniversary is coming up soon",
    # Emotional family moments
    "So proud of my son graduating from college today",
    "Missing grandpa a lot today, it has been a year since he passed",
    "First day of school for the little one, feeling emotional",
    # Daily family life
    "Made pancakes for the whole family this morning",
    "Bedtime story with the kids, reading their favorite book",
    "Family movie night with popcorn and blankets",
    # Safety edge cases
    "The baby has been crying all night, I am exhausted",
    "Worried about mom health, she has a doctor appointment tomorrow",
    "Kids are fighting again over the remote control",
]

print("=" * 100)
print("UltraBERT Family Context Test - 12 Capabilities")
print("=" * 100)
print()

for i, text in enumerate(tests, 1):
    r = c.analyze(text)
    fam = [e["text"] + ":" + e["label"] for e in r.entities]
    gen = [e["text"] + ":" + e["label"] for e in r.general_entities]
    temp = [t["text"] + ":" + t["label"] for t in r.temporal]

    print(f"[{i:02d}] {text}")
    print(f"     1. sentiment:   {r.sentiment} (conf: {r.sentiment_confidence:.2f})")
    print(f"     2. emotions:    {r.emotions[:4]}")
    print(f"     3. safety:      {r.safety}")
    print(f"     4. is_safe:     {r.is_safe}")
    print(f"     5. ner_family:  {fam}")
    print(f"     6. ner_general: {gen}")
    print(f"     7. temporal:    {temp}")
    print(f"     8. intent:      {r.intent} (conf: {r.intent_confidence:.2f})")
    print(f"     9. ingress:     {r.ingress}")
    print(f"    10. relations:   {r.relations}")
    print(f"    11. nli:         {r.nli}")
    print(f"    12. embedding:   dim={r.embedding_dim}")
    print()
