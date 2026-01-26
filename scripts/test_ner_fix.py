"""
Comprehensive test of NER with confidence threshold fix.
"""

from familyos_ultrabert import Client

c = Client()

# More comprehensive test
tests = [
    # Real entities that should be detected
    "Mom and Dad are coming to visit",
    "Grandma baked cookies for the kids",
    "Sarah got promoted at work today",
    "We adopted a puppy named Max",
    "Jennifer called about lunch tomorrow",
    "Met with Dr. Smith at the hospital",
    "The conference is in San Francisco",
    # No entities - should be empty
    "I need to buy groceries",
    "The weather is nice today",
    "Remember to call later",
    "What time is the meeting",
]

print("Comprehensive NER Test:")
print("=" * 70)
for text in tests:
    result = c.analyze(text, capabilities=["ner_family", "ner_general"])
    family = [(e["text"], e["label"], f"{e['confidence']:.2f}") for e in result.entities]
    general = [(e["text"], e["label"], f"{e['confidence']:.2f}") for e in result.general_entities]
    print(f"\n{text}")
    if family:
        print(f"  Family: {family}")
    if general:
        print(f"  General: {general}")
    if not family and not general:
        print("  (no entities)")
