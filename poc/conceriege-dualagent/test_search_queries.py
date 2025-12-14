from l3_execution.specialist_search import SpecialistSearchEngine

queries = [
    "i've been feeling stressed and anxious lately",
    "I want to lose weight and improve my fitness",
    "I'm having trouble sleeping and feel exhausted",
]

engine = SpecialistSearchEngine()

for q in queries:
    print(f"\nQuery: {q}")
    results = engine.search(q, limit=3)
    if not results:
        print("  NO RESULTS")
    else:
        for r in results:
            print(f"  {r['id']:20} {r['match_score']:5.2f}")
