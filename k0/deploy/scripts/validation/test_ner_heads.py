"""Test UltraBERT ner_family vs ner_general head behavior."""

from familyos_ultrabert import Client

c = Client(warmup=False)
print(f"=== UltraBERT v{c.VERSION} NER Heads Test ===")
print()
print("Testing ner_family vs ner_general head separation...")
print()

texts = [
    "Mom made dinner with Dad at grandmas house",
    "My wife Sarah and kids went to the park",
    "Brother Bob works at Microsoft in Seattle",
    "John Smith visited Paris last Friday",
    "Dr. Johnson at Mayo Clinic examined the patient",
    "Grandma baked cookies for the birthday party yesterday",
    "My son works at Google in San Francisco with his Uncle",
]

for text in texts:
    r = c.analyze(text)
    fam = [(e["text"], e["label"]) for e in r.entities]
    gen = [(e["text"], e["label"]) for e in r.general_entities]
    temp = [(e["text"], e["label"]) for e in r.temporal]
    print(f'Text: "{text}"')
    print(f"  ner_family: {fam}")
    print(f"  ner_general: {gen}")
    if temp:
        print(f"  temporal: {temp}")
    print()

print("=" * 60)
print("Summary:")
print("- ner_family: Detects KINSHIP (Mom, Dad, wife, kids, etc.)")
print("- ner_general: Detects PER, ORG, LOC (John Smith, Microsoft, Seattle)")
print("- temporal: Detects DATE_REL, TIME (yesterday, last Friday)")
print()
print("R4 uses BOTH heads with priority-based deduplication:")
print("  - ner_family KINSHIP entities have priority=0.95")
print("  - ner_general PER/ORG/LOC have priority=0.80-0.85")
print("  - When spans overlap, higher priority entity wins")
