# R2 Episodic Integrator Phase - Wiki Documentation

> **Pipeline**: P03 Consolidation
> **Phase**: R2 (Episodic Integration / DBSCAN Clustering)
> **Version**: 1.0.0
> **Last Updated**: 2026-01-28
> **Source File**: `k0/pipelines/p03/phases/r2_episodic_integrator.py`

---

## Table of Contents

1. [Overview](#overview)
2. [Scientific Basis](#scientific-basis)
3. [File Dependencies](#file-dependencies)
4. [Class Reference](#class-reference)
5. [Algorithms](#algorithms)
6. [API Reference](#api-reference)
7. [Data Structures](#data-structures)
8. [End-to-End Process Flow](#end-to-end-process-flow)
9. [Configuration](#configuration)
10. [Metrics & Observability](#metrics--observability)
11. [Error Handling](#error-handling)
12. [Usage Examples](#usage-examples)

---

## Overview

The **R2 Episodic Integrator Phase** groups related events into coherent episodes using density-based clustering (DBSCAN/HDBSCAN). It transforms individual memory events into meaningful episode structures for long-term storage.

### Responsibilities

1. **Split events into sequences** - By time gap, location, and activity boundaries
2. **Cluster sequences** - Using DBSCAN or HDBSCAN with composite distance
3. **Match to existing episodes** - Query `st_epi` to avoid duplicates (REINFORCE)
4. **Compute centroids** - Weighted episode embeddings for retrieval
5. **Track cluster quality** - Adaptive parameter learning
6. **Canonicalize episodes** - Merge by signature (optional)

### Position in Pipeline

```
R0 (Batch Selection) → R1 (Importance Scoring) → R2 (Episode Clustering) → R3 (Dedup/Decay) → R4 → R5 → R6 → R7 → R8
```

### Key Features

| Feature | Description |
|---------|-------------|
| **HDBSCAN Default** | Hierarchical density clustering with noise rescue |
| **Composite Distance** | 70% semantic + 30% temporal |
| **Episode Matching** | Query existing episodes before clustering |
| **Adaptive Parameters** | Learn eps and min_samples from quality metrics |
| **UltraBERT Activity Types** | 12-type INGRESS classification |

---

## Scientific Basis

### Event Segmentation Theory (Zacks & Swallow, 2007)

People naturally segment continuous experience into discrete events at boundaries where prediction errors spike. The R2 phase implements this by:

- **Time gaps**: Natural breaks in temporal continuity
- **Location changes**: Geohash prefix differences
- **Activity changes**: Context shift detection

### Temporal Binding in Episodic Memory (Tulving, 2002)

Events occurring close together in time are more likely to be part of the same episode. The composite distance metric reflects this by combining:

- **Semantic similarity**: Events about similar topics cluster together
- **Temporal proximity**: Events close in time cluster together

### DBSCAN Density-Based Clustering (Ester et al., 1996)

DBSCAN discovers clusters of arbitrary shape without requiring the number of clusters upfront:

- **Core points**: Events with ≥ min_samples neighbors within eps
- **Border points**: Within eps of a core point
- **Noise points**: Neither core nor border (become micro-episodes)

### HDBSCAN Hierarchical Extension (McInnes et al., 2017)

HDBSCAN improves on DBSCAN with:

- **Multi-resolution clustering**: No fixed eps required
- **Soft membership**: Probability scores per event
- **Outlier scores**: Enable intelligent noise rescue

---

## File Dependencies

### Primary Files

| File Path | Purpose | Key Exports |
|-----------|---------|-------------|
| `k0/pipelines/p03/phases/r2_episodic_integrator.py` | Phase implementation | `R2EpisodicIntegrator`, `R2Config`, `create_r2_phase()` |
| `k0/modules/consolidation/algorithms/episodic_dbscan.py` | DBSCAN clustering | `EpisodicDBSCAN`, `ClusteringResult` |
| `k0/modules/consolidation/algorithms/episodic_hdbscan.py` | HDBSCAN clustering | `EpisodicHDBSCAN`, `HDBSCANParams`, `HDBSCANClusteringResult` |
| `k0/modules/consolidation/algorithms/composite_distance.py` | Distance metric | `CompositeDistance`, `DBSCANParams` |
| `k0/modules/consolidation/algorithms/episode_splitter.py` | Pre-clustering split | `EpisodeSplitter`, `SplitConfig`, `SplitResult` |
| `k0/modules/consolidation/algorithms/centroid_calculator.py` | Centroid computation | `CentroidCalculator`, `CentroidResult`, `WeightingStrategy` |
| `k0/modules/consolidation/algorithms/cluster_quality.py` | Quality tracking | `ClusterQualityTracker`, `ClusterQualityMetrics` |
| `k0/modules/consolidation/algorithms/eps_adjuster.py` | Adaptive eps | `EpsAdjuster`, `EpsAdjustmentConfig` |
| `k0/modules/consolidation/algorithms/min_samples_adjuster.py` | Adaptive min_samples | `MinSamplesAdjuster`, `MinSamplesConfig` |
| `k0/pipelines/p03/phase_outputs.py` | Output containers | `EpisodeCluster` |
| `k0/pipelines/p03/event_state.py` | Event state | `ReconciliationAction` |

### Import Graph

```
r2_episodic_integrator.py
├── k0.modules.consolidation.algorithms
│   ├── CentroidCalculator
│   ├── CentroidResult
│   ├── ClusteringResult
│   ├── ClusterQualityMetrics
│   ├── ClusterQualityTracker
│   ├── DBSCANParams
│   ├── EpisodeCandidate
│   ├── EpisodeSplitter
│   ├── EpisodicDBSCAN
│   ├── EpisodicHDBSCAN (default)
│   ├── EpsAdjuster
│   ├── HDBSCANClusteringResult
│   ├── HDBSCANParams
│   ├── MinSamplesAdjuster
│   ├── SplitConfig
│   └── WeightingStrategy
├── k0.pipelines.p03.event_state
│   └── ReconciliationAction
├── k0.pipelines.p03.observability
│   └── P03Error
├── k0.pipelines.p03.phase_interface
│   └── P03PhaseResult
├── k0.pipelines.p03.phase_outputs
│   └── EpisodeCluster
├── k0.pipelines.p03.runner_contract
│   └── P03PhaseId
└── numpy (np)
```

---

## Class Reference

### R2EpisodicIntegrator

**Location:** `k0/pipelines/p03/phases/r2_episodic_integrator.py`

```python
class R2EpisodicIntegrator:
    """
    R2 Phase: Episodic Integration (DBSCAN Clustering).
    """

    PHASE_ID = P03PhaseId.R2_CLUSTER

    def __init__(self, config: Optional[R2Config] = None) -> None: ...

    @property
    def phase_id(self) -> P03PhaseId: ...

    def should_skip(self, envelope: P03BatchEnvelope) -> bool: ...

    def idempotency_key(self, envelope: P03BatchEnvelope) -> str: ...

    async def run(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
    ) -> P03PhaseResult: ...
```

### R2Config

**Location:** `k0/pipelines/p03/phases/r2_episodic_integrator.py`

```python
@dataclass
class R2Config:
    """R2 phase configuration."""

    # Batch settings
    min_batch_size: int = 2              # Minimum events for clustering

    # DBSCAN parameters
    eps: float = 0.0                      # 0.0 = use adaptive learning
    min_samples: int = 0                  # 0 = use adaptive learning
    semantic_weight: float = 0.7          # Embedding distance weight
    temporal_weight: float = 0.3          # Time distance weight

    # Splitting
    enable_splitting: bool = True         # Split before clustering
    time_gap_minutes: int = 60            # Gap threshold for split

    # Adaptive learning
    enable_adaptive_eps: bool = True
    enable_adaptive_min_samples: bool = True
    enable_quality_tracking: bool = True

    # Centroid weighting
    weighting_strategy: WeightingStrategy = WeightingStrategy.IMPORTANCE

    # HDBSCAN settings (default algorithm)
    use_hdbscan: bool = True              # Use HDBSCAN instead of DBSCAN
    noise_rescue_threshold: float = 0.5   # Rescue noise with outlier_score < this
    cluster_selection_method: str = "leaf"  # 'leaf' preserves small clusters

    # Canonicalization (optional)
    enable_canonicalization: bool = False
    canonicalization_time_bucket_hours: int = 1

    # Episode matching (Issue 2 fix)
    enable_episode_matching: bool = True
    episode_reinforce_threshold: float = 0.85  # Cosine similarity for REINFORCE
    episode_extend_threshold: float = 0.60     # Future use
    episode_query_limit: int = 50
```

### DBSCANParams

**Location:** `k0/modules/consolidation/algorithms/composite_distance.py`

```python
@dataclass(frozen=True)
class DBSCANParams:
    """DBSCAN clustering parameters."""

    eps: float = 0.15                     # Max distance to cluster (UltraBERT optimized)
    min_samples: int = 2                  # Minimum events for core point
    temporal_weight: float = 0.3          # Weight for temporal component
    max_temporal_gap_hours: float = 4.0   # Hard limit (events further apart cannot cluster)

    @property
    def semantic_weight(self) -> float:
        return 1.0 - self.temporal_weight

    @property
    def max_temporal_gap_ms(self) -> int:
        return int(self.max_temporal_gap_hours * 3_600_000)
```

### HDBSCANParams

**Location:** `k0/modules/consolidation/algorithms/episodic_hdbscan.py`

```python
@dataclass(frozen=True)
class HDBSCANParams:
    """HDBSCAN clustering parameters."""

    min_cluster_size: int = 2             # Smallest episode size
    min_samples: int = 1                  # Lower = less noise, more inclusive
    cluster_selection_epsilon: float = 0.0  # 0 = automatic, >0 = flat cut
    cluster_selection_method: str = "leaf"  # 'leaf' preserves small clusters
    noise_rescue_threshold: float = 0.5   # Rescue noise with outlier_score < this
    temporal_weight: float = 0.3
    max_temporal_gap_hours: float = 4.0
    allow_single_cluster: bool = False
```

---

## Algorithms

### 1. Composite Distance Formula

Combines semantic similarity and temporal proximity into a unified distance metric.

```python
distance = (1 - temporal_weight) × cosine_distance(emb_a, emb_b)
         + temporal_weight × normalized_time_distance(ts_a, ts_b)
```

**Where:**

- `cosine_distance = 1 - cosine_similarity` → [0.0, 2.0]
- `normalized_time_distance = min(1.0, |ts_a - ts_b| / max_temporal_gap_ms)` → [0.0, 1.0]
- `max_temporal_gap_ms = 4 hours = 14,400,000 ms`

**Default Weights:**

| Component | Weight | Range |
|-----------|--------|-------|
| Semantic (cosine) | 0.7 | [0.0, 1.4] |
| Temporal | 0.3 | [0.0, 0.3] |
| **Total** | 1.0 | [0.0, ~1.7] |

**Hard Limit:** Events > 4 hours apart return `distance = inf` (cannot cluster)

### 2. Episode Splitting Algorithm

Pre-clustering segmentation prevents cross-activity clusters.

**Split Signals (priority order):**

| Priority | Signal | Threshold | Reason |
|----------|--------|-----------|--------|
| 1 | Location Change | geohash prefix differs by > 4 chars | Physical context shift |
| 2 | Activity Change | activity_type changes | Semantic context shift |
| 3 | Time Gap | gap > 30 minutes (configurable) | Temporal discontinuity |
| 4 | Hard Limit | episode duration > 4 hours | Prevent mega-episodes |

**Geohash Distance Formula:**

```python
def geohash_distance(gh1: str, gh2: str) -> int:
    # Distance = characters from first difference position
    for i in range(min(len(gh1), len(gh2))):
        if gh1[i] != gh2[i]:
            return max(len(gh1), len(gh2)) - i
    return abs(len(gh1) - len(gh2))
```

### 3. HDBSCAN Clustering with Noise Rescue

**Step 1: Build Distance Matrix**

```python
distances = CompositeDistance(params).build_distance_matrix(events)
distances = np.clip(distances, 0.0, 1e10)  # Cap infinities
```

**Step 2: Run HDBSCAN**

```python
clusterer = hdbscan.HDBSCAN(
    min_cluster_size=2,
    min_samples=1,
    metric="precomputed",
    cluster_selection_epsilon=0.0,
    cluster_selection_method="leaf",
)
clusterer.fit(distances)
labels = clusterer.labels_  # -1 = noise
probabilities = clusterer.probabilities_
outlier_scores = clusterer.outlier_scores_
```

**Step 3: Noise Rescue**

Rescues noise points with low outlier scores:

```python
threshold = 0.5  # noise_rescue_threshold

for idx in noise_indices:
    if outlier_scores[idx] < threshold:
        # Find nearest cluster
        best_cluster = argmin(distances[idx, clustered_points])

        if best_distance < 0.3:
            # Rescue: assign to nearest cluster
            labels[idx] = best_cluster
        else:
            # Create weak cluster with nearby noise
            nearby_noise = [j for j in noise_indices
                          if distances[idx, j] < 0.2
                          and outlier_scores[j] < threshold]
            if nearby_noise:
                labels[idx] = new_cluster_id
                for j in nearby_noise:
                    labels[j] = new_cluster_id
```

### 4. Centroid Calculation

**Weighting Strategies:**

| Strategy | Formula | Use Case |
|----------|---------|----------|
| `uniform` | All events weighted equally (1/n) | Baseline |
| `importance` | Weight by importance_score | Key moments matter more |
| `recency` | Weight by timestamp (recent = higher) | Recent events matter more |
| `hybrid` (default) | 0.7 × importance + 0.3 × recency | Balanced approach |

**Centroid Formula:**

```python
centroid = sum(weight_i × embedding_i for i in events)
centroid = L2_normalize(centroid)  # For cosine similarity compatibility
```

**Variance (Cohesion):**

```python
variance = mean((1 - cos_sim(event, centroid))² for all events)
cohesion = 1 / (1 + variance)  # Higher = tighter cluster
```

### 5. Episode Matching (Issue 2 Fix)

Matches incoming events to existing episodes before clustering.

**Query Existing Episodes:**

```sql
SELECT e.episode_id, e.episode_type, e.primary_location,
       e.start_time_utc, v.vector
FROM st_epi e
LEFT JOIN st_vec v ON e.embedding_id = v.embedding_id
WHERE e.tenant_id = $1 AND e.space_id = $2
  AND e.archival_status = 'ACTIVE'
  AND e.start_time_utc >= $3  -- Extended by 7 days
  AND v.vector IS NOT NULL
ORDER BY e.start_time_utc DESC
LIMIT 50
```

**Matching Logic:**

```python
for event in events:
    for episode in existing_episodes:
        similarity = cosine_similarity(event.embedding, episode.embedding)

        if similarity >= 0.85:  # reinforce_threshold
            event.reconciliation_action = REINFORCE
            event.episode_match_id = episode.episode_id
            matched_events.append(event)
            break
    else:
        novel_events.append(event)

# Only cluster novel_events (matched events update existing episodes)
```

### 6. Episode Confidence Score

Multi-factor confidence calculation:

```python
def compute_confidence(
    event_count: int,
    temporal_start: int,
    temporal_end: int,
    participant_count: int,
    cohesion: float,
    location_purity: float,
) -> float:

    # Event count score (saturates at 10)
    event_score = min(1.0, event_count / 10.0)

    # Temporal compactness
    duration_hours = (temporal_end - temporal_start) / 3_600_000
    if duration_hours <= 1:
        temporal_score = 1.0
    elif duration_hours <= 4:
        temporal_score = 1.0 - (duration_hours - 1) * 0.167
    else:
        temporal_score = max(0.25, 0.5 - (duration_hours - 4) * 0.03)

    # Participant score
    participant_score = min(1.0, 0.5 + participant_count * 0.1)

    # Weighted combination
    confidence = (
        0.25 * event_score +
        0.20 * temporal_score +
        0.15 * participant_score +
        0.25 * cohesion +
        0.15 * location_purity
    )

    return clamp(confidence, 0.0, 1.0)
```

### 7. Ambiguity Score (SPC-UQ)

Quantifies uncertainty based on missing critical fields:

```python
def compute_ambiguity_score(
    location_hint,
    participants_json,
    activity_type,
    activity_type_ultrabert,
    entity_ids,
    cluster_events,
) -> float:

    missing_fields = 0
    total_fields = 4  # location, participants, activity, entities

    if not location_hint:
        missing_fields += 1
    if not json.loads(participants_json or "[]"):
        missing_fields += 1
    if not (activity_type_ultrabert or activity_type):
        missing_fields += 1
    if not entity_ids:
        missing_fields += 1

    base_score = missing_fields / total_fields

    # Penalties
    if len(cluster_events) < 3:
        base_score += 0.1
    if not any(has_sentiment_data for e in cluster_events):
        base_score += 0.1

    return min(1.0, base_score)
```

### 8. Cluster Quality Metrics

Closed-loop quality tracking from Dossier §4.3.4.1:

| Signal | Source | Weight | Target | Interpretation |
|--------|--------|--------|--------|----------------|
| Silhouette Score | sklearn | 0.40 | > 0.5 | Cluster cohesion/separation |
| Grounding Rate | K1 feedback | 0.30 | > 0.6 | % clusters used by K1 |
| Correction Rate | User feedback | 0.20 | < 0.05 | User corrections / cluster |
| Singleton Rate | Noise proxy | 0.10 | < 0.20 | Singleton % of total |

**Composite Quality Formula:**

```python
composite = 0.40 × silhouette + 0.30 × grounding +
            0.20 × (1 - correction) + 0.10 × (1 - singleton)
```

### 9. Adaptive Eps Learning

Adjusts eps based on quality metrics:

```python
if silhouette_score < 0.5:
    if singleton_rate > 0.20:
        eps = eps * 1.1  # INCREASE (too much noise)
    else:
        eps = eps * 0.9  # DECREASE (clusters too loose)
```

### 10. Adaptive Min_Samples Learning

Adjusts min_samples based on singleton rate:

```python
if singleton_rate > 0.20:
    min_samples = min_samples - 1  # DECREASE (too strict)
elif singleton_rate < 0.05:
    min_samples = min_samples + 1  # INCREASE (too few noise)
```

---

## API Reference

### Input: P03BatchEnvelope

```python
@dataclass
class P03BatchEnvelope:
    context: P03CycleContext
    events: List[P03EventState]  # Events from R1 (with importance scores)
    phases: P03PhaseOutputs
    current_phase: P03PhaseId
    phase_statuses: Dict[P03PhaseId, P03PhaseStatus]
```

#### Event Input Fields (P03EventState)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_id` | `str` | Yes | ULID |
| `timestamp` | `int` | Yes | Milliseconds since epoch |
| `embedding_768` | `List[float]` | Yes | 768-dim embedding from P02 |
| `importance_score` | `float` | Yes | From R1 |
| `sentiment_score` | `float` | No | Sentiment analysis |
| `location_name` | `str` | No | Location display name |
| `location_type` | `str` | No | Location category |
| `activity_type` | `str` | No | Legacy 7-type |
| `activity_type_ultrabert` | `str` | No | UltraBERT 12-type |
| `participants_json` | `str` | No | JSON array of participants |
| `ner_entities_json` | `str` | No | NER extraction results |
| `emotions_json` | `str` | No | Emotion classifications |

### Output: P03PhaseResult

```python
@dataclass
class P03PhaseResult:
    phase_id: P03PhaseId          # R2_CLUSTER
    status: P03PhaseStatus        # DONE, SKIP, or FAIL
    duration_ms: int
    outputs_summary: Dict[str, Any]
    error_info: Optional[P03Error]
    skip_reason: Optional[str]
    idempotency_key: Optional[str]
```

#### outputs_summary Structure

```python
{
    "clusters_formed": int,          # Episode clusters created
    "matched_to_existing": int,      # Events matched to existing episodes
    "noise_events": int,             # Events not clustered
    "avg_cluster_size": float,       # Average events per cluster
    "eps": float,                    # DBSCAN eps used
    "min_samples": int,              # DBSCAN min_samples used
    "silhouette": Optional[float],   # Quality score
}
```

### Envelope Mutations

After R2 execution, the envelope is enriched:

```python
# Phase outputs populated:
envelope.phases.r2_clusters: List[EpisodeCluster]
envelope.phases.r2_noise_event_ids: List[str]
envelope.phases.r2_cluster_count: int
envelope.phases.r2_avg_cluster_size: float
envelope.phases.r2_clustering_params: Dict[str, Any]

# Each event state updated:
event.cluster_id: Optional[str]           # Episode ID (None if noise)
event.cluster_label: int                  # DBSCAN label (-1 if noise)
event.is_noise: bool                      # True if not clustered

# Matched events (Issue 2 fix):
event.episode_match_id: Optional[str]     # Existing episode ID
event.episode_match_similarity: float     # Similarity score
event.reconciliation_action: ReconciliationAction  # REINFORCE
event.reconciliation_reason: str          # Human-readable reason
```

---

## Data Structures

### EpisodeCluster

```python
@dataclass
class EpisodeCluster:
    """Episode formed by clustering events in R2."""

    cluster_id: str                           # UUID
    member_event_ids: List[str] = []          # Events in this cluster
    member_contexts: List[ObservationContext] = []  # Issue 7.6
    entity_ids: List[str] = []                # NER entities
    ambiguity_score: float = 0.0              # SPC-UQ uncertainty

    # Centroid
    centroid_embedding_id: Optional[str] = None  # Set by R7

    # Aggregated attributes
    dominant_sentiment: float = 0.0
    dominant_emotion: str = ""
    aggregated_sentiment: Optional[float] = None
    aggregated_salience: Optional[float] = None
    dominant_location: Optional[str] = None
    dominant_social_context: Optional[str] = None

    # Temporal bounds (milliseconds)
    temporal_start: int = 0
    temporal_end: int = 0

    # Location
    location_hint: Optional[str] = None
    location_type: Optional[str] = None       # GAP-002

    # Participants and activity
    participants_json: str = "[]"
    activity_type: str = ""                   # Legacy 7-type
    activity_type_ultrabert: str = ""         # Issue 0060

    # Quality
    cohesion_score: float = 0.0               # Intra-cluster similarity

    # Content
    title: str = ""
    summary: str = ""

    @property
    def event_count(self) -> int:
        return len(self.member_event_ids)

    @property
    def duration_ms(self) -> int:
        return self.temporal_end - self.temporal_start
```

### ClusteringResult (DBSCAN)

```python
@dataclass
class ClusteringResult:
    """Complete result from DBSCAN clustering."""

    clusters: List[EpisodeCluster]    # Including noise clusters
    total_events: int
    cluster_count: int                 # Non-noise clusters
    noise_count: int                   # Noise/singleton events
    labels: List[int]                  # DBSCAN labels per event

    @property
    def singleton_rate(self) -> float:
        return self.noise_count / self.total_events if self.total_events > 0 else 0.0
```

### HDBSCANClusteringResult

```python
@dataclass
class HDBSCANClusteringResult:
    """Extended result from HDBSCAN clustering."""

    clusters: List[EpisodeCluster]
    total_events: int
    cluster_count: int
    noise_count: int                   # True noise (not rescued)
    rescued_count: int                 # Rescued into weak episodes
    labels: List[int]
    probabilities: List[float]         # Cluster membership [0, 1]
    outlier_scores: List[float]        # Outlier-ness [0, 1]

    @property
    def rescue_rate(self) -> float:
        original_noise = self.noise_count + self.rescued_count
        return self.rescued_count / original_noise if original_noise > 0 else 0.0
```

### CentroidResult

```python
@dataclass
class CentroidResult:
    """Result from centroid computation."""

    centroid: np.ndarray              # 768-dim L2-normalized
    variance: float                    # Cluster cohesion measure
    weights: np.ndarray               # Weights used per event
    strategy: str                      # Weighting strategy name
    event_count: int                   # Events with valid embeddings

    @property
    def centroid_list(self) -> List[float]:
        return self.centroid.tolist()
```

### ClusterQualityMetrics

```python
@dataclass
class ClusterQualityMetrics:
    """Cluster quality metrics for closed-loop learning."""

    # Core metrics [0, 1]
    silhouette_score: float = 0.0
    grounding_rate: float = 0.0
    correction_rate: float = 0.0
    singleton_rate: float = 0.0

    # Derived
    composite_quality: float = 0.0    # Weighted composite [0, 1]

    # Raw counts
    total_clusters: int = 0
    grounded_clusters: int = 0
    corrected_clusters: int = 0
    singleton_clusters: int = 0

    # Metadata
    space_id: str = ""
    cycle_id: str = ""
    computed_at: int = 0

    @property
    def is_acceptable(self) -> bool:
        return self.composite_quality > 0.5
```

### SplitResult

```python
@dataclass
class SplitResult:
    """Result from episode splitting operation."""

    episodes: List[List[SplittableEvent]]
    split_count: int
    split_reasons: Dict[str, int]     # By reason type
    total_events: int

    @property
    def episode_count(self) -> int:
        return len(self.episodes)
```

---

## End-to-End Process Flow

### Sequence Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      R2 EPISODIC INTEGRATOR PHASE                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: Initialize                                                          │
│   • Create R2EpisodicIntegrator(config)                                     │
│   • Initialize algorithm components:                                        │
│     - EpisodeSplitter (time_gap_minutes=60)                                 │
│     - EpisodicHDBSCAN or EpisodicDBSCAN                                     │
│     - CentroidCalculator (strategy=IMPORTANCE)                              │
│     - ClusterQualityTracker                                                 │
│     - EpsAdjuster, MinSamplesAdjuster                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: Skip Check                                                          │
│   • If len(events) < min_batch_size (2) → SKIP                              │
│   • If no events have embedding_768 → SKIP                                  │
│   • Return P03PhaseResult.skip() with reason                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: Filter Events                                                       │
│   • Separate events with embeddings from those without                      │
│   • Log warning if events excluded                                          │
│   • events_with_embeddings → proceed                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 4: Match to Existing Episodes (Issue 2 Fix)                            │
│   IF enable_episode_matching:                                               │
│     • Query st_epi for episodes in time window (extended 7 days back)       │
│     • For each event:                                                       │
│       - Compute cosine similarity to each episode centroid                  │
│       - IF similarity >= 0.85 (reinforce_threshold):                        │
│           event.reconciliation_action = REINFORCE                           │
│           event.episode_match_id = episode_id                               │
│           matched_events.append(event)                                      │
│       - ELSE: novel_events.append(event)                                    │
│     • Only novel_events proceed to clustering                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 5: Adapt Events                                                        │
│   • Wrap P03EventState in EventAdapter for algorithm compatibility          │
│   • adapted_events = [EventAdapter(e) for e in novel_events]                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 6: Split into Sequences                                                │
│   IF enable_splitting:                                                      │
│     • Sort events by timestamp                                              │
│     • For each consecutive pair:                                            │
│       - Check location change (geohash distance > 4)                        │
│       - Check activity change (activity_type differs)                       │
│       - Check time gap (> 60 minutes)                                       │
│       - Check hard limit (episode > 4 hours)                                │
│       - Split if any condition met                                          │
│     • Result: List[List[EventAdapter]] (sequences)                          │
│   ELSE:                                                                     │
│     • sequences = [adapted_events]                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 7: Cluster Each Sequence                                               │
│   FOR each sequence in sequences:                                           │
│     IF len(sequence) < min_batch_size:                                      │
│       • Mark all as noise → all_noise_ids.extend()                          │
│       • Continue to next sequence                                           │
│                                                                             │
│     • Build distance matrix (CompositeDistance)                             │
│     • Run HDBSCAN/DBSCAN clustering                                         │
│     • Extract labels, probabilities, outlier_scores                         │
│     • Rescue noise (if HDBSCAN, outlier_score < threshold)                  │
│     • all_results.append(clustering_result)                                 │
│     • Extract noise IDs (label == -1) → all_noise_ids                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 8: Compute Centroids & Build Episodes                                  │
│   FOR each cluster in all_results:                                          │
│     • Skip noise clusters (single events)                                   │
│     • Skip single-member clusters                                           │
│     • Get cluster events from event_lookup                                  │
│                                                                             │
│     • Compute centroid:                                                     │
│       centroid = CentroidCalculator.compute(events, strategy=IMPORTANCE)    │
│       cohesion = 1 / (1 + variance)                                         │
│                                                                             │
│     • Build EpisodeCandidate:                                               │
│       - cluster_id, space_id, event_ids                                     │
│       - centroid_embedding                                                  │
│       - temporal_start/end                                                  │
│       - cohesion_score, variance                                            │
│                                                                             │
│     • Build EpisodeCluster:                                                 │
│       - Extract dominant sentiment (average)                                │
│       - Extract dominant emotion (most common)                              │
│       - Extract location_hint, location_type (most common)                  │
│       - Aggregate participants (union)                                      │
│       - Extract entity_ids from NER                                         │
│       - Extract activity_type, activity_type_ultrabert (most common)        │
│       - Compute ambiguity_score                                             │
│       - Generate title (activity + participants + location)                 │
│       - Generate summary (event texts)                                      │
│       - Build member_contexts (ObservationContext for each event)           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 9: Canonicalize (Optional)                                             │
│   IF enable_canonicalization AND len(episodes) > 1:                         │
│     • Group episodes by signature:                                          │
│       (episode_type, location, time_bucket, participant_count,              │
│        event_count_bucket, semantic_hint)                                   │
│     • Merge groups with > 1 episode:                                        │
│       - Union member_event_ids                                              │
│       - Union participants                                                  │
│       - Min/max temporal bounds                                             │
│       - Weighted average sentiment                                          │
│       - Most common emotion                                                 │
│       - Average cohesion                                                    │
│       - Regenerate title/summary                                            │
│     • Recompute confidence for all episodes                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 10: Update Event States                                                │
│   FOR each event in envelope.events:                                        │
│     IF event_id in cluster assignments:                                     │
│       event.cluster_id = cluster_id                                         │
│       event.cluster_label = label                                           │
│       event.is_noise = False                                                │
│     ELIF event_id in all_noise_ids:                                         │
│       event.cluster_id = None                                               │
│       event.cluster_label = -1                                              │
│       event.is_noise = True                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 11: Populate Envelope Outputs                                          │
│   envelope.phases.r2_clusters = episode_clusters                            │
│   envelope.phases.r2_noise_event_ids = all_noise_ids                        │
│   envelope.phases.r2_cluster_count = len(episode_clusters)                  │
│   envelope.phases.r2_avg_cluster_size = avg(event_count per cluster)        │
│   envelope.phases.r2_clustering_params = {                                  │
│     "eps": eps,                                                             │
│     "min_samples": min_samples,                                             │
│     "semantic_weight": 0.7,                                                 │
│     "temporal_weight": 0.3,                                                 │
│     "episode_matching_enabled": True,                                       │
│     "matched_to_existing": len(matched_events),                             │
│   }                                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 12: Track Quality & Adapt                                              │
│   IF enable_quality_tracking:                                               │
│     • Compute batch silhouette (average cohesion)                           │
│     • Track metrics via ClusterQualityTracker                               │
│     • IF enable_adaptive_eps:                                               │
│         eps_result = EpsAdjuster.adjust(...)                                │
│         IF adjusted: persist to st_learned_weights                          │
│     • IF enable_adaptive_min_samples:                                       │
│         min_samples_result = MinSamplesAdjuster.adjust(...)                 │
│         IF adjusted: persist to st_learned_weights                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 13: Return P03PhaseResult                                              │
│   return P03PhaseResult.done(                                               │
│     phase_id=P03PhaseId.R2_CLUSTER,                                         │
│     duration_ms=execution_time,                                             │
│     outputs_summary={                                                       │
│       "clusters_formed": len(episode_clusters),                             │
│       "matched_to_existing": len(matched_events),                           │
│       "noise_events": len(all_noise_ids),                                   │
│       "avg_cluster_size": avg_cluster_size,                                 │
│       "eps": eps,                                                           │
│       "min_samples": min_samples,                                           │
│       "silhouette": silhouette_score,                                       │
│     },                                                                      │
│     idempotency_key="p03:r2:{cycle_id}",                                    │
│   )                                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │   Proceed to R3 (Dedup/Decay)        │
                    └─────────────────────────────────────┘
```

### Data Flow Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                                  INPUT                                      │
├────────────────────────────────────────────────────────────────────────────┤
│  P03BatchEnvelope                                                          │
│  ├── context                                                               │
│  │   ├── cycle_id, batch_id, space_id, tenant_id                           │
│  │                                                                         │
│  ├── events: List[P03EventState] (from R1)                                 │
│  │   ├── event_id: str                                                     │
│  │   ├── timestamp: int (milliseconds)                                     │
│  │   ├── embedding_768: List[float] (768-dim)                              │
│  │   ├── importance_score: float [0, 1]                                    │
│  │   ├── sentiment_score: float [-1, 1]                                    │
│  │   ├── activity_type: str                                                │
│  │   ├── location_name, location_type: str                                 │
│  │   └── participants_json, ner_entities_json: str (JSON)                  │
│  │                                                                         │
│  └── phases: P03PhaseOutputs (R1 populated)                                │
└────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │  R2EpisodicIntegrator.run()
                                      │
                                      ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                                 OUTPUT                                      │
├────────────────────────────────────────────────────────────────────────────┤
│  P03BatchEnvelope (enriched)                                               │
│  ├── context (unchanged)                                                   │
│  │                                                                         │
│  ├── events: List[P03EventState] (cluster fields populated)               │
│  │   ├── cluster_id: Optional[str]                                         │
│  │   ├── cluster_label: int (-1 if noise)                                  │
│  │   ├── is_noise: bool                                                    │
│  │   ├── episode_match_id: Optional[str] (if REINFORCE)                    │
│  │   ├── episode_match_similarity: float                                   │
│  │   └── reconciliation_action: ReconciliationAction                       │
│  │                                                                         │
│  ├── phases: P03PhaseOutputs                                               │
│  │   ├── r2_clusters: List[EpisodeCluster]                                 │
│  │   │   ├── cluster_id, member_event_ids                                  │
│  │   │   ├── temporal_start, temporal_end                                  │
│  │   │   ├── dominant_sentiment, dominant_emotion                          │
│  │   │   ├── location_hint, location_type                                  │
│  │   │   ├── activity_type, activity_type_ultrabert                        │
│  │   │   ├── participants_json                                             │
│  │   │   ├── cohesion_score, ambiguity_score                               │
│  │   │   ├── entity_ids                                                    │
│  │   │   ├── title, summary                                                │
│  │   │   └── member_contexts: List[ObservationContext]                     │
│  │   │                                                                     │
│  │   ├── r2_noise_event_ids: List[str]                                     │
│  │   ├── r2_cluster_count: int                                             │
│  │   ├── r2_avg_cluster_size: float                                        │
│  │   └── r2_clustering_params: Dict                                        │
│  │                                                                         │
│  └── observability: P03ObservabilityContext (metrics updated)              │
│                                                                            │
│  + P03PhaseResult                                                          │
│    ├── phase_id: R2_CLUSTER                                                │
│    ├── status: DONE                                                        │
│    ├── duration_ms: int                                                    │
│    ├── outputs_summary: Dict                                               │
│    └── idempotency_key: "p03:r2:{cycle_id}"                                │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Configuration

### R2Config Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `min_batch_size` | `int` | `2` | Minimum events for clustering |
| `eps` | `float` | `0.0` | DBSCAN eps (0.0 = adaptive) |
| `min_samples` | `int` | `0` | DBSCAN min_samples (0 = adaptive) |
| `semantic_weight` | `float` | `0.7` | Weight for embedding distance |
| `temporal_weight` | `float` | `0.3` | Weight for time distance |
| `enable_splitting` | `bool` | `True` | Pre-cluster splitting |
| `time_gap_minutes` | `int` | `60` | Time gap threshold for splitting |
| `enable_adaptive_eps` | `bool` | `True` | Learn eps from quality |
| `enable_adaptive_min_samples` | `bool` | `True` | Learn min_samples |
| `enable_quality_tracking` | `bool` | `True` | Track cluster quality |
| `weighting_strategy` | `WeightingStrategy` | `IMPORTANCE` | Centroid weighting |
| `use_hdbscan` | `bool` | `True` | Use HDBSCAN (vs DBSCAN) |
| `noise_rescue_threshold` | `float` | `0.5` | HDBSCAN noise rescue |
| `cluster_selection_method` | `str` | `"leaf"` | HDBSCAN cluster selection |
| `enable_episode_matching` | `bool` | `True` | Match to existing episodes |
| `episode_reinforce_threshold` | `float` | `0.85` | Similarity for REINFORCE |
| `episode_query_limit` | `int` | `50` | Max episodes to query |

### Environment Config Keys

```python
ctx.get_config("p03.clustering.eps", default=0.07)
ctx.get_config("p03.clustering.min_samples", default=2)
ctx.get_config("p03.clustering.temporal_weight", default=0.3)
```

---

## Metrics & Observability

### Prometheus Metrics

| Metric Name | Type | Description |
|-------------|------|-------------|
| `p03_r2_clusters_formed` | Counter | Total clusters formed |
| `p03_r2_noise_events` | Counter | Total noise events |
| `p03_r2_silhouette_score` | Gauge | Batch silhouette score |
| `p03_r2_singleton_rate` | Gauge | Noise/total ratio |
| `p03_r2_eps_used` | Gauge | Current eps value |
| `p03_r2_min_samples_used` | Gauge | Current min_samples |
| `p03_r2_duration_ms` | Histogram | Phase execution time |
| `p03_r2_matched_to_existing` | Counter | Events matched to existing episodes |

### Log Fields

```json
{
  "cycle_id": "01HXYZ...",
  "tenant_id": "t_123",
  "space_id": "sp_456",
  "event_count": 50,
  "clusters_formed": 8,
  "matched_to_existing": 5,
  "noise_events": 7,
  "avg_cluster_size": 4.75,
  "eps": 0.07,
  "min_samples": 2,
  "silhouette": 0.65,
  "duration_ms": 345
}
```

---

## Error Handling

### Skip Conditions

| Condition | Result |
|-----------|--------|
| `len(events) < min_batch_size` | `SKIP("Batch size X < min_batch_size 2")` |
| No events with embeddings | `SKIP("No events with embeddings")` |

### Error Recovery

| Error Type | Strategy | Recoverable |
|------------|----------|-------------|
| Clustering failure | Create P03Error, return FAIL | Yes |
| HDBSCAN not installed | Fall back to DBSCAN | Yes |
| Episode query failure | Proceed with clustering all | Yes |

### P03Error Structure

```python
P03Error.create(
    phase="R2",
    stage_id="episodic_integrator",
    error_type="R2_CLUSTERING_ERROR",
    error_message=str(e),
    recoverable=True,
)
```

---

## Usage Examples

### Basic Usage

```python
from k0.pipelines.p03.phases.r2_episodic_integrator import (
    R2EpisodicIntegrator,
    R2Config,
    create_r2_phase,
)

# Create phase with default config (HDBSCAN)
r2_phase = create_r2_phase()

# Or with custom config
config = R2Config(
    use_hdbscan=True,
    noise_rescue_threshold=0.6,
    enable_episode_matching=True,
    episode_reinforce_threshold=0.80,
)
r2_phase = R2EpisodicIntegrator(config=config)

# Run phase
result = await r2_phase.run(envelope, ctx)

if result.is_success:
    print(f"Formed {result.outputs_summary['clusters_formed']} clusters")
    print(f"Matched {result.outputs_summary['matched_to_existing']} to existing")
    print(f"Noise: {result.outputs_summary['noise_events']} events")
elif result.is_skipped:
    print(f"Skipped: {result.skip_reason}")
else:
    print(f"Failed: {result.error_info.error_message}")
```

### Direct Algorithm Usage

```python
from k0.modules.consolidation.algorithms import (
    EpisodicHDBSCAN,
    HDBSCANParams,
    CentroidCalculator,
    WeightingStrategy,
)

# Create HDBSCAN clusterer
params = HDBSCANParams(
    min_cluster_size=2,
    noise_rescue_threshold=0.5,
    cluster_selection_method="leaf",
)
clusterer = EpisodicHDBSCAN(params=params)

# Cluster events
result = clusterer.cluster(events)

print(f"Clusters: {result.cluster_count}")
print(f"Noise: {result.noise_count}")
print(f"Rescued: {result.rescued_count}")

# Compute centroids
calculator = CentroidCalculator(default_strategy="hybrid")

for cluster in result.clusters:
    cluster_events = [e for e in events if e.event_id in cluster.member_event_ids]
    centroid_result = calculator.compute(cluster_events)

    print(f"Cluster {cluster.cluster_id}:")
    print(f"  Events: {len(cluster_events)}")
    print(f"  Variance: {centroid_result.variance:.4f}")
    print(f"  Cohesion: {1/(1+centroid_result.variance):.4f}")
```

### Episode Splitting

```python
from k0.modules.consolidation.algorithms import EpisodeSplitter, SplitConfig

config = SplitConfig(
    max_episode_hours=4.0,
    time_gap_minutes=30.0,
    geohash_distance_threshold=4,
)
splitter = EpisodeSplitter(config=config)

result = splitter.split(events)

print(f"Episodes: {result.episode_count}")
print(f"Splits: {result.split_count}")
print(f"Reasons: {result.split_reasons}")
```

---

## Related Documentation

- **Spec**: `docs/pipelines/P03_consolidation_dossier_v2.md` Appendix C.3
- **Execution**: `docs/TEMP_EXECUTION_DOCS/M4_EXECUTION.md` Epic 4.2
- **R1 Phase**: `docs/pipelines/p03/r1_importance_scorer_phase_wiki.md`
- **Phase Interface**: `k0/pipelines/p03/phase_interface.py`
- **Runner Contract**: `k0/pipelines/p03/runner_contract.py`

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-28 | Initial documentation |
