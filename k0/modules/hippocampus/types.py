"""
Hippocampus Module - Type Definitions

Shared types for DG, CA1, CA3 services.
Extensible dataclasses allow adding fields without breaking existing code.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DGFingerprint:
    """
    DG (Dentate Gyrus) Pattern Separation Output

    Extensible: Add new fingerprint types without breaking existing code.
    """

    simhash_hex: str
    minhash32: List[int]
    input_features: Dict[str, Any]
    computation_ms: float

    # Extensibility fields
    model_version: str = "dg_v0.1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Future fields (examples):
    # lsh_buckets: Optional[List[str]] = None
    # perceptual_hash: Optional[str] = None  # For images
    # audio_fingerprint: Optional[str] = None


@dataclass
class CA1Projection:
    """
    CA1 Semantic Projection Output

    Extensible: Add new semantic extraction features.
    """

    entities: List[Dict[str, Any]]
    kg_triples: List[Dict[str, Any]]
    embedding_id: str
    confidence: float

    # Extensibility fields
    model_version: str = "ca1_v0.1.0"
    extraction_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Future fields (examples):
    # semantic_roles: Optional[List[Dict[str, Any]]] = None
    # event_causality: Optional[List[Dict[str, Any]]] = None
    # temporal_entities: Optional[List[Dict[str, Any]]] = None


@dataclass
class CA3Cluster:
    """
    CA3 Clustering Output

    Extensible: Add new clustering metrics.
    """

    episode_cluster_id: str
    member_event_ids: List[str]
    cluster_confidence: float
    representative_event_id: str

    # Extensibility fields
    algorithm: str = "greedy"
    model_version: str = "ca3_v0.1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Future fields (examples):
    # cluster_centroid: Optional[Dict[str, Any]] = None
    # intra_cluster_similarity: Optional[float] = None
    # temporal_span_hours: Optional[float] = None


@dataclass
class HippocampusConfig:
    """
    Runtime configuration for hippocampus module.

    Loaded from config.yml, can be overridden per-tenant or per-pipeline.
    """

    # DG config
    dg_simhash_bits: int = 64
    dg_minhash_permutations: int = 32
    dg_target_latency_ms: int = 15

    # CA1 config
    ca1_endpoint: Optional[str] = None
    ca1_timeout_ms: int = 40
    ca1_circuit_breaker_enabled: bool = True

    # CA3 config
    ca3_hamming_threshold: int = 4
    ca3_jaccard_threshold: float = 0.8
    ca3_time_window_hours: int = 24

    # Feature flags
    enable_adaptive_minhash: bool = False
    enable_lsh_indexing: bool = False
    enable_multimodal: bool = False

    # Observability
    emit_metrics: bool = True
    emit_traces: bool = True
    log_fingerprints: bool = False

    # Extensibility
    custom_config: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "HippocampusConfig":
        """Create config from dictionary (loaded from YAML)."""
        return cls(**{k: v for k, v in config.items() if k in cls.__annotations__})

    def to_dict(self) -> Dict[str, Any]:
        """Export config as dictionary."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
