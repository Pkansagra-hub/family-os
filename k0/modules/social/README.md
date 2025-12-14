# Social Module | Version: 0.1.0 | ADR: K008
## Purpose: Family relationship graph resolution

## Configuration (`config.yml`)
```yaml
family_graph:
  relationship_types:
    - SPOUSE_OF, PARENT_OF, CHILD_OF, CARETAKER_OF, SIBLING_OF
  intimacy_scores:
    SPOUSE_OF: "HIGH"
    PARENT_OF: "HIGH"
```

## Usage
```python
from k0.modules.social import FamilyGraphResolver

resolver = FamilyGraphResolver()
result = await resolver.resolve(
    actor_id="person_dad",
    participant_ids=["person_dad", "person_mom"],
)
print(result["participant_roles_json"])  # {"person_dad": "OWNER", "person_mom": "SPOUSE"}
print(result["social_context"])          # "nuclear_family"
print(result["social_intimacy"])         # "HIGH"
```

## Performance: P95 ≤10ms | P99 ≤20ms
## Related: P02, st_relationships, ADR K008 Series
