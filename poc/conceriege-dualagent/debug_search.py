from l3_execution.specialist_search import SpecialistSearchEngine

engine = SpecialistSearchEngine()

queries = [
    "lose weight and improve my fitness",
    "weight loss fitness",
    "fitness workout",
]

for q in queries:
    results = engine.search(q, limit=5)
    print(f"\nQuery: {q}")
    for r in results:
        print(f'  {r["id"]:25} {r["match_score"]:5.2f}  {r["domain"]}')
