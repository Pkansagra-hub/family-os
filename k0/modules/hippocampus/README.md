# Hippocampus Module - Phase 2 Declarative Modules

**Version**: 1.0.0
**Status**: ✅ M01 Implemented | 📋 M02-M03 ADR Complete
**Architecture**: Phase 2 (Declarative YAML-driven pipelines)
**ADR**: [K003](../../../docs/architecture/decisions-K0/modules/k003-hippocampus-architecture.md)

## Purpose

Episodic memory formation subsystem implementing:
- **DG (Dentate Gyrus)**: Pattern separation via SimHash/MinHash
- **CA1**: Semantic projection and entity extraction
- **CA3**: Episode clustering and consolidation (P03 scope)

## Phase 2 Modules (Implemented)

| Module | ID | File | Status | Performance | Tests | ADR |
|--------|-----|------|--------|-------------|-------|-----|
| **pattern_separate** | M01 | `pattern_separate.py` | ✅ Implemented | 0.88ms P95 | 16/16 ✅ | [K003.1](../../../docs/architecture/decisions-K0/modules/k003.1-dg-pattern-separation.md) |
| **semantic_project** | M02 | `semantic_project.py` | 📋 ADR Complete | <20ms P95 | Pending | [K003.2](../../../docs/architecture/decisions-K0/modules/k003.2-ca1-semantic-bridge.md) |
| **ca3_consolidation** | M03 | *(P03 scope)* | 📋 ADR Complete | Background | N/A | [K003.3](../../../docs/architecture/decisions-K0/modules/k003.3-ca3-clustering-service.md) |

## Usage (Phase 2 Pattern)

Modules are invoked by PipelineRunner, not directly instantiated:

```python
# In pipeline YAML (k0/contracts/pipelines/p02_write.v1.yaml):
- id: stage_10_dg_pattern_separate
  module: hippocampus.pattern_separate:v1
  after: []
  config:
    hash_seed: 42
    minhash_permutations: 32
```

Module signature:
```python
async def run(message: BusMessage, context: PipelineContext, **config) -> dict:
    # Pure function, no shared state
    # Access storage via context.syscalls (capability-gated)
    pass
```

## Configuration

Module-specific config is declared in contracts and overridden per-stage in pipeline YAML.

Contract location: `k0/contracts/modules/hippocampus.pattern_separate.v1.yaml`

**Environment Variables**:
- `CA1_SERVICE_ENDPOINT` - External CA1 service URL
- `HIPPO_LOG_LEVEL` - Logging level (DEBUG/INFO/WARN/ERROR)

## Usage

### DG Pattern Separation

```python
from k0.modules.hippocampus import DGService, HippocampusConfig

# Load config (optional, defaults to config.yml)
config = HippocampusConfig.from_dict({
    "dg_simhash_bits": 64,
    "dg_minhash_permutations": 32,
})

dg = DGService(config)
fingerprint = await dg.compute_fingerprint(
    event_id="evt_123",
    text="We had dinner at Olive Garden",
    participants=["person_dad", "person_mom"],
    place="Olive Garden",
    activity_type="dinner",
)

print(f"SimHash: {fingerprint.simhash_hex}")
print(f"MinHash: {fingerprint.minhash32}")
```

### CA1 Semantic Projection

```python
from k0.modules.hippocampus import CA1Bridge

ca1 = CA1Bridge()
projection = await ca1.project_semantic(
    text="We had dinner at Olive Garden with Mom",
    context={"person_id": "person_dad", "space_id": "personal:dad"},
    embedding_id="emb_abc123",
)

print(f"Entities: {projection.entities}")
print(f"KG Triples: {projection.kg_triples}")
```

### CA3 Clustering (P03 only)

```python
from k0.modules.hippocampus import CA3Service

ca3 = CA3Service()

# Find duplicates
duplicates = await ca3.find_near_duplicates(
    simhash="a1b2c3d4e5f67890",
    minhash=[123, 456, 789, ...],
    time_window_hours=24,
)

# Cluster episodes
clusters = await ca3.cluster_episodes(event_ids=["evt_1", "evt_2", "evt_3"])
for cluster in clusters:
    print(f"Cluster {cluster.episode_cluster_id}: {cluster.member_event_ids}")
```

## Extensibility

### Adding New Fingerprint Algorithms

1. Add config in `config.yml`:
```yaml
dg:
  perceptual_hash:
    enabled: true
    algorithm: "phash"
```

2. Extend `DGFingerprint` type:
```python
@dataclass
class DGFingerprint:
    simhash_hex: str
    minhash32: List[int]
    perceptual_hash: Optional[str] = None  # New field
```

3. Implement in `DGService`:
```python
async def compute_multimodal_fingerprint(self, image_data: bytes) -> DGFingerprint:
    # New method, doesn't break existing code
    pass
```

### Adding New CA1 Extractors

1. Add config in `config.yml`:
```yaml
ca1:
  semantic_roles:
    enabled: true
    model: "srl_v1.0"
```

2. Extend `CA1Projection` type:
```python
@dataclass
class CA1Projection:
    entities: List[Dict[str, Any]]
    kg_triples: List[Dict[str, Any]]
    semantic_roles: Optional[List[Dict[str, Any]]] = None  # New field
```

3. Implement in `CA1Bridge`:
```python
async def extract_semantic_roles(self, text: str) -> List[Dict[str, Any]]:
    # New method, doesn't break existing code
    pass
```

## Testing

```bash
# Unit tests
pytest tests/k0/modules/hippocampus/test_dg_service.py -v

# Integration tests
pytest tests/k0/modules/hippocampus/test_integration.py -v

# Performance tests
pytest tests/k0/modules/hippocampus/test_performance.py -v --benchmark
```

## Performance Budgets

| Module | P95 Latency | P99 Latency | Memory |
|--------|-------------|-------------|--------|
| DGService | ≤15ms | ≤25ms | <10MB |
| CA1Bridge | ≤40ms | ≤60ms | <50MB |
| CA3Service | N/A (background) | N/A | <500MB |

## Dependencies

- None (designed to be dependency-free for core functionality)
- Optional: External CA1 service (HTTP/gRPC)
- Optional: LSH indexing library (for future CA3 optimization)

## Version History

- **0.1.0** (2025-11-16): Initial module structure, config externalized, types defined

## Future Roadmap

- [ ] Adaptive MinHash (adjust permutations based on content)
- [ ] LSH indexing for O(1) neighbor queries
- [ ] Multi-modal fingerprints (images, audio, video)
- [ ] Incremental clustering (update without full recomputation)
- [ ] Hierarchical clustering (sub-episode detection)
- [ ] Novelty scoring (deviation from known patterns)

## Related

- **Pipeline**: P02 (Episodic Write), P03 (Consolidation)
- **Tables**: `st_hipp_events`, `st_embedding_queue`
- **ADR Index**: [docs/architecture/decisions-K0/modules/README.md](../../../docs/architecture/decisions-K0/modules/README.md)
