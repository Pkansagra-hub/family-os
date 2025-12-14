# Space Module | Version: 0.1.0 | ADR: K005
## Purpose: ACL and ownership resolution for episodic memories

## Configuration (`config.yml`)
```yaml
acl_resolution:
  mode: "intersection"
  cache_ttl_seconds: 300
ownership:
  derive_from_actor: true
  max_co_owners: 10
performance:
  target_p95_ms: 3
```

## Usage
```python
from k0.modules.space import SpaceResolver
resolver = SpaceResolver()
resolution = await resolver.resolve(
    actor_id="person_dad",
    space_id="personal:dad",
    policy_visible_to=["person_dad"],
)
print(resolution.visible_to)  # ["person_dad"]
```

## Performance: P95 ≤3ms | P99 ≤5ms | Memory <5MB
## Related: P02, ADR K005 Series
