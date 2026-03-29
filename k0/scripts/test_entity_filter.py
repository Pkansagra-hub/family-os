"""Test entity filtering in entity_extractor."""

from k0.modules.consolidation.algorithms.entity_extractor import UltraBERTEntityExtractor

e = UltraBERTEntityExtractor()

# Check garbage words
garbage_tests = [
    "made",
    "asked",
    "here",
    "afternoon",
    "email",
    "career",
    "motherhood",
    "friends",
    "manager",
]
print("=== Garbage Word Check ===")
for word in garbage_tests:
    is_garbage = word in e.GARBAGE_ENTITY_WORDS
    print(f"  {word:15} -> garbage: {is_garbage}")

# Test normalize_name
print("\n=== Normalize Name (possessives) ===")
emma_norm = e.normalize_name("Emma's")
sofia_norm = e.normalize_name("Sofia's")
smith_norm = e.normalize_name("Smith's")
print(f"  Emma's -> {emma_norm!r}")
print(f"  Sofia's -> {sofia_norm!r}")
print(f"  Smith's -> {smith_norm!r}")

# Test _map_entity with ner_general entities
print("\n=== _map_entity (ner_general PERSON label) ===")
test_entities = [
    {"text": "asked", "label": "PERSON", "start_token": 0, "end_token": 0},
    {"text": "Emma", "label": "PERSON", "start_token": 0, "end_token": 0},
    {"text": "Emma's", "label": "PERSON", "start_token": 0, "end_token": 0},
    {"text": "motherhood", "label": "FAMILY_MEMBER", "start_token": 0, "end_token": 0},
    {"text": "manager", "label": "PERSON", "start_token": 0, "end_token": 0},
    {"text": "CEO", "label": "PERSON", "start_token": 0, "end_token": 0},
    {"text": "afternoon", "label": "ORGANIZATION", "start_token": 0, "end_token": 0},
    {"text": "career", "label": "ORGANIZATION", "start_token": 0, "end_token": 0},
]

for ent in test_entities:
    result = e._map_entity(ent, "ner_general")
    if result:
        print(
            f"  {ent['text']:15} ({ent['label']:12}) -> KEPT: {result.normalized_text!r} ({result.kg_type.value})"
        )
    else:
        print(f"  {ent['text']:15} ({ent['label']:12}) -> FILTERED")
