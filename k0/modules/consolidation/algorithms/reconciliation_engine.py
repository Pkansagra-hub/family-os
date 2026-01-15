"""
ReconciliationEngine — Core reconciliation decision engine for P03.

Determines the reconciliation action (REINFORCE, EXTEND, CREATE, EVOLVE,
CONTRADICT, PRUNE, SKIP) for each incoming event by comparing it against
existing truth records using embedding similarity.

Scientific Basis:
- Cosine similarity for semantic relatedness (Mikolov et al., 2013)
- Bayesian confidence updating (Dossier Appendix C.1.2)

Spec Reference:
    - Dossier §4.3.2: Decision Engine specification
    - Dossier Appendix C.1: Core Reconciliation Algorithms
    - P03_RECONCILIATION_ENGINE_IMPLEMENTATION_PLAN.md
    - P03_envelope_fields_discovery.md Section 2.6

Thresholds (from Dossier Appendix C.1):
    ≥0.85: REINFORCE (strengthen existing truth)
    0.60-0.84: EXTEND (add detail to existing)
    0.40-0.59: EVOLVE (related but distinct)
    <0.40: CONTRADICT or CREATE (based on context)
    Override: is_duplicate=True → SKIP
    Override: prune_decision=TOMBSTONE → PRUNE

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import numpy as np

from k0.pipelines.p03.event_state import P03EventState, PruneDecision, ReconciliationAction

if TYPE_CHECKING:
    from k0.modules.consolidation.staging.truth_query_service import (
        TruthCandidate,
        TruthQueryService,
    )

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Default thresholds from Dossier Appendix C.1
DEFAULT_REINFORCE_THRESHOLD = 0.85
DEFAULT_EXTEND_THRESHOLD = 0.60
DEFAULT_EVOLVE_THRESHOLD = 0.40

# Query parameters
DEFAULT_CANDIDATE_TOP_K = 10
DEFAULT_MIN_SIMILARITY = 0.35

# Bayesian confidence parameters
DEFAULT_PRIOR_CONFIDENCE = 0.5
DEFAULT_EVIDENCE_WEIGHT = 0.3

# Timeout for truth queries (seconds)
DEFAULT_QUERY_TIMEOUT_SECONDS = 5.0

# Truth layers to query in priority order
DEFAULT_TRUTH_LAYERS: Tuple[str, ...] = (
    "st_epi",
    "st_sem",
    "st_procedural",
    "st_social",
    "st_prospective",
)


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class ReconciliationConfig:
    """
    Configuration for ReconciliationEngine.

    Attributes:
        reinforce_threshold: Minimum similarity for REINFORCE action (default 0.85)
        extend_threshold: Minimum similarity for EXTEND action (default 0.60)
        evolve_threshold: Minimum similarity for EVOLVE action (default 0.40)
        candidate_top_k: Number of candidates to retrieve per layer (default 10)
        min_candidate_similarity: Minimum similarity to consider (default 0.35)
        prior_confidence: Bayesian prior for confidence (default 0.5)
        evidence_weight: Weight of evidence in confidence update (default 0.3)
        truth_layers: Tuple of truth layers to query in priority order
        enable_batch_mode: Whether to use batch queries (default True)
    """

    reinforce_threshold: float = DEFAULT_REINFORCE_THRESHOLD
    extend_threshold: float = DEFAULT_EXTEND_THRESHOLD
    evolve_threshold: float = DEFAULT_EVOLVE_THRESHOLD
    candidate_top_k: int = DEFAULT_CANDIDATE_TOP_K
    min_candidate_similarity: float = DEFAULT_MIN_SIMILARITY
    prior_confidence: float = DEFAULT_PRIOR_CONFIDENCE
    evidence_weight: float = DEFAULT_EVIDENCE_WEIGHT
    truth_layers: Tuple[str, ...] = DEFAULT_TRUTH_LAYERS
    enable_batch_mode: bool = True
    query_timeout_seconds: float = DEFAULT_QUERY_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        """Validate configuration."""
        # Validate thresholds are in descending order
        if not (self.reinforce_threshold > self.extend_threshold > self.evolve_threshold):
            raise ValueError(
                f"Thresholds must be in descending order: "
                f"reinforce ({self.reinforce_threshold}) > "
                f"extend ({self.extend_threshold}) > "
                f"evolve ({self.evolve_threshold})"
            )

        # Validate all thresholds in [0, 1]
        for name, val in [
            ("reinforce_threshold", self.reinforce_threshold),
            ("extend_threshold", self.extend_threshold),
            ("evolve_threshold", self.evolve_threshold),
            ("min_candidate_similarity", self.min_candidate_similarity),
            ("prior_confidence", self.prior_confidence),
            ("evidence_weight", self.evidence_weight),
        ]:
            if not 0.0 <= val <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {val}")

        # Validate candidate_top_k
        if self.candidate_top_k < 1:
            raise ValueError(f"candidate_top_k must be >= 1, got {self.candidate_top_k}")

        # Validate timeout
        if self.query_timeout_seconds <= 0:
            raise ValueError(f"query_timeout_seconds must be > 0, got {self.query_timeout_seconds}")


# =============================================================================
# Decision Result
# =============================================================================


@dataclass
class ReconciliationDecision:
    """
    Result of reconciliation for a single event.

    Attributes:
        action: The reconciliation action to take
        best_match_id: ID of the best matching truth record (if any)
        best_match_layer: Truth layer of the best match (st_epi, st_sem, etc.)
        similarity_score: Cosine similarity to best match [0, 1]
        confidence: Confidence in the decision [0, 1]
        reason: Human-readable explanation of the decision
        candidates_evaluated: Number of candidates evaluated
        decision_time_ms: Time taken to make decision in milliseconds
    """

    action: ReconciliationAction
    best_match_id: Optional[str]
    best_match_layer: Optional[str]
    similarity_score: float
    confidence: float
    reason: str
    candidates_evaluated: int
    decision_time_ms: float = 0.0

    def __post_init__(self) -> None:
        """Validate and clamp scores."""
        self.similarity_score = max(0.0, min(1.0, self.similarity_score))
        self.confidence = max(0.0, min(1.0, self.confidence))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "action": self.action.value,
            "best_match_id": self.best_match_id,
            "best_match_layer": self.best_match_layer,
            "similarity_score": round(self.similarity_score, 4),
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "candidates_evaluated": self.candidates_evaluated,
            "decision_time_ms": round(self.decision_time_ms, 2),
        }


# =============================================================================
# Reconciliation Engine
# =============================================================================


class ReconciliationEngine:
    """
    Core reconciliation decision engine for P03 consolidation.

    Queries truth layers for candidates, computes similarity, and applies
    threshold logic to determine the appropriate action for each event.

    Usage:
        from k0.modules.consolidation.algorithms.reconciliation_engine import (
            ReconciliationEngine,
            ReconciliationConfig,
        )
        from k0.modules.consolidation.staging.truth_query_service import TruthQueryService

        config = ReconciliationConfig()
        truth_service = TruthQueryService(conn_factory)
        engine = ReconciliationEngine(config, truth_service)

        # Single event decision
        decision = await engine.decide(
            event=event_state,
            space_id="space_123",
            tenant_id="tenant_abc",
        )

        # Apply to event state
        event.set_reconciliation(
            action=decision.action,
            match_id=decision.best_match_id,
            match_layer=decision.best_match_layer,
            similarity=decision.similarity_score,
            confidence=decision.confidence,
            reason=decision.reason,
        )

    Spec Reference:
        - Dossier §4.3.2 (Decision Engine)
        - Dossier Appendix C.1 (Thresholds)
    """

    def __init__(
        self,
        config: ReconciliationConfig,
        truth_query_service: Optional["TruthQueryService"] = None,
    ) -> None:
        """
        Initialize ReconciliationEngine.

        Args:
            config: Engine configuration with thresholds and parameters
            truth_query_service: Service for querying truth layers (optional for testing)
        """
        self._config = config
        self._truth_service = truth_query_service

        # Metrics tracking
        self._total_decisions = 0
        self._action_counts: Dict[str, int] = {a.value: 0 for a in ReconciliationAction}
        self._similarity_histogram: Dict[str, int] = {
            "0.0-0.2": 0,
            "0.2-0.4": 0,
            "0.4-0.6": 0,
            "0.6-0.8": 0,
            "0.8-1.0": 0,
        }
        self._query_errors = 0
        self._query_timeouts = 0

    @property
    def config(self) -> ReconciliationConfig:
        """Get engine configuration."""
        return self._config

    def set_truth_service(self, service: "TruthQueryService") -> None:
        """
        Set or replace the truth query service.

        Useful for deferred initialization or testing.
        """
        self._truth_service = service

    # =========================================================================
    # Main Decision Methods
    # =========================================================================

    async def decide(
        self,
        event: P03EventState,
        space_id: str,
        tenant_id: str,
    ) -> ReconciliationDecision:
        """
        Make reconciliation decision for a single event.

        Algorithm:
            1. Check override conditions (duplicate, tombstone)
            2. Extract event embedding
            3. Query truth layers for candidates
            4. Find best match by similarity
            5. Apply threshold logic
            6. Compute confidence
            7. Return decision

        Args:
            event: The event to reconcile
            space_id: Space context for truth queries
            tenant_id: Tenant context for truth queries

        Returns:
            ReconciliationDecision with action and metadata
        """
        start_time = time.perf_counter()

        # Check override conditions first (no DB query needed)
        override = self._check_overrides(event)
        if override is not None:
            override.decision_time_ms = (time.perf_counter() - start_time) * 1000
            self._record_decision(override)
            return override

        # Get event embedding
        embedding = self._get_event_embedding(event)
        if embedding is None:
            # No embedding → default to CREATE
            decision = ReconciliationDecision(
                action=ReconciliationAction.CREATE,
                best_match_id=None,
                best_match_layer=None,
                similarity_score=0.0,
                confidence=0.5,
                reason="No embedding available for similarity search",
                candidates_evaluated=0,
            )
            decision.decision_time_ms = (time.perf_counter() - start_time) * 1000
            self._record_decision(decision)
            return decision

        # Query truth layers for candidates
        candidates = await self._find_candidates(
            embedding=embedding,
            space_id=space_id,
            tenant_id=tenant_id,
        )

        # Find best match
        best_match, similarity = self._find_best_match(embedding, candidates)

        # Determine action based on similarity
        action = self._determine_action(
            similarity=similarity,
            has_match=best_match is not None,
            is_duplicate=event.is_duplicate,
            prune_decision=event.prune_decision,
        )

        # Compute confidence
        confidence = self._compute_confidence(
            similarity=similarity,
            action=action,
            candidates_count=len(candidates),
        )

        # Build reason string
        reason = self._build_reason(
            action=action,
            similarity=similarity,
            best_match=best_match,
            candidates_count=len(candidates),
        )

        decision = ReconciliationDecision(
            action=action,
            best_match_id=best_match.record_id if best_match else None,
            best_match_layer=best_match.layer if best_match else None,
            similarity_score=similarity,
            confidence=confidence,
            reason=reason,
            candidates_evaluated=len(candidates),
        )

        decision.decision_time_ms = (time.perf_counter() - start_time) * 1000
        self._record_decision(decision)
        return decision

    async def decide_batch(
        self,
        events: List[P03EventState],
        space_id: str,
        tenant_id: str,
    ) -> Dict[str, ReconciliationDecision]:
        """
        Make reconciliation decisions for a batch of events.

        More efficient than calling decide() for each event when
        batch_mode is enabled in config.

        Args:
            events: List of events to reconcile
            space_id: Space context for truth queries
            tenant_id: Tenant context for truth queries

        Returns:
            Dict mapping event_id to ReconciliationDecision
        """
        results: Dict[str, ReconciliationDecision] = {}

        for event in events:
            decision = await self.decide(
                event=event,
                space_id=space_id,
                tenant_id=tenant_id,
            )
            results[event.event_id] = decision

        return results

    # =========================================================================
    # Override Checks
    # =========================================================================

    def _check_overrides(self, event: P03EventState) -> Optional[ReconciliationDecision]:
        """
        Check for override conditions that bypass similarity search.

        Override conditions (from Dossier Appendix C.1):
            1. is_duplicate=True → SKIP
            2. prune_decision=TOMBSTONE → PRUNE

        Returns:
            ReconciliationDecision if override applies, None otherwise
        """
        # Check duplicate override
        if event.is_duplicate:
            return ReconciliationDecision(
                action=ReconciliationAction.SKIP,
                best_match_id=event.canonical_event_id,  # The event this duplicates
                best_match_layer=None,
                similarity_score=1.0,  # Duplicate implies high similarity
                confidence=0.95,
                reason=f"Duplicate of event {event.canonical_event_id}",
                candidates_evaluated=0,
            )

        # Check tombstone override
        if event.prune_decision == PruneDecision.TOMBSTONE:
            return ReconciliationDecision(
                action=ReconciliationAction.PRUNE,
                best_match_id=None,
                best_match_layer=None,
                similarity_score=0.0,
                confidence=0.9,
                reason=f"Marked for tombstone by decay engine (decay_score={event.decay_score:.3f})",
                candidates_evaluated=0,
            )

        return None

    # =========================================================================
    # Embedding Handling
    # =========================================================================

    def _get_event_embedding(self, event: P03EventState) -> Optional[np.ndarray]:
        """
        Extract embedding from event state.

        The embedding may be in:
            - event.embedding_768 (768-dim UltraBERT vector)
            - event.embedding (legacy field)

        Returns:
            numpy array of embedding, or None if not available
        """
        # Try embedding_768 first (preferred)
        if hasattr(event, "embedding_768") and event.embedding_768 is not None:
            if isinstance(event.embedding_768, (list, tuple)) and len(event.embedding_768) > 0:
                return np.asarray(event.embedding_768, dtype=np.float64)
            if isinstance(event.embedding_768, np.ndarray) and event.embedding_768.size > 0:
                return event.embedding_768.astype(np.float64)

        # Fall back to embedding field
        if hasattr(event, "embedding") and event.embedding is not None:
            if isinstance(event.embedding, (list, tuple)) and len(event.embedding) > 0:
                return np.asarray(event.embedding, dtype=np.float64)
            if isinstance(event.embedding, np.ndarray) and event.embedding.size > 0:
                return event.embedding.astype(np.float64)

        return None

    # =========================================================================
    # Candidate Search
    # =========================================================================

    async def _find_candidates(
        self,
        embedding: np.ndarray,
        space_id: str,
        tenant_id: str,
    ) -> List["TruthCandidate"]:
        """
        Find candidate matches from truth layers.

        Queries configured truth layers via TruthQueryService and returns
        all candidates meeting minimum similarity threshold.

        Args:
            embedding: Event embedding vector
            space_id: Space context
            tenant_id: Tenant context

        Returns:
            List of TruthCandidate sorted by similarity descending
        """
        if self._truth_service is None:
            # No truth service configured → no candidates
            logger.warning(
                "ReconciliationEngine._find_candidates called without truth_service; "
                "all events will become CREATE actions"
            )
            return []

        try:
            candidates = await asyncio.wait_for(
                self._truth_service.find_candidates(
                    embedding=embedding,
                    space_id=space_id,
                    tenant_id=tenant_id,
                    top_k=self._config.candidate_top_k,
                    min_similarity=self._config.min_candidate_similarity,
                    layers=self._config.truth_layers,
                ),
                timeout=self._config.query_timeout_seconds,
            )
            return candidates
        except asyncio.TimeoutError:
            self._query_timeouts += 1
            logger.error(
                "Truth query timeout after %.1fs for space=%s tenant=%s",
                self._config.query_timeout_seconds,
                space_id,
                tenant_id,
            )
            return []
        except Exception as exc:
            self._query_errors += 1
            logger.exception(
                "Truth query failed for space=%s tenant=%s: %s",
                space_id,
                tenant_id,
                exc,
            )
            return []

    def _find_best_match(
        self,
        embedding: np.ndarray,
        candidates: List["TruthCandidate"],
    ) -> Tuple[Optional["TruthCandidate"], float]:
        """
        Find the best matching candidate by similarity.

        Args:
            embedding: Event embedding vector
            candidates: List of candidates from truth layers

        Returns:
            Tuple of (best_candidate, similarity_score)
            If no candidates, returns (None, 0.0)
        """
        if not candidates:
            return None, 0.0

        best_candidate = None
        best_similarity = 0.0

        for candidate in candidates:
            # Use pre-computed similarity if available
            if candidate.similarity > 0:
                similarity = candidate.similarity
            elif candidate.embedding is not None:
                # Compute similarity if not pre-computed but embedding exists
                similarity = self._cosine_similarity(embedding, candidate.embedding)
            else:
                # No embedding available for this candidate, skip
                logger.debug(
                    "Candidate %s has no embedding, skipping similarity computation",
                    candidate.record_id,
                )
                continue

            if similarity > best_similarity:
                best_similarity = similarity
                best_candidate = candidate

        return best_candidate, best_similarity

    # =========================================================================
    # Similarity Computation
    # =========================================================================

    def _cosine_similarity(
        self,
        vec1: np.ndarray,
        vec2: np.ndarray,
    ) -> float:
        """
        Compute cosine similarity between two vectors.

        Replicates logic from EntityDisambiguator._cosine_similarity for
        consistency across algorithms.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity in [0, 1] (clamped from [-1, 1])
        """
        v1 = np.asarray(vec1, dtype=np.float64)
        v2 = np.asarray(vec2, dtype=np.float64)

        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        cos_sim = np.dot(v1, v2) / (norm1 * norm2)

        # Clamp to [0, 1] for scoring purposes
        return float(max(0.0, min(1.0, cos_sim)))

    # =========================================================================
    # Action Determination
    # =========================================================================

    def _determine_action(
        self,
        similarity: float,
        has_match: bool,
        is_duplicate: bool,
        prune_decision: Optional[PruneDecision],
    ) -> ReconciliationAction:
        """
        Apply threshold logic from Dossier Appendix C.1.

        Thresholds:
            ≥0.85: REINFORCE (strengthen existing)
            0.60-0.84: EXTEND (add to existing with link)
            0.40-0.59: EVOLVE (related but distinct)
            <0.40 + has_match: CONTRADICT
            <0.40 + no match: CREATE

        Override conditions (checked first):
            is_duplicate=True: SKIP
            prune_decision=TOMBSTONE: PRUNE

        Args:
            similarity: Best match similarity score
            has_match: Whether a candidate was found
            is_duplicate: Whether event is duplicate
            prune_decision: Decay engine prune decision

        Returns:
            Appropriate ReconciliationAction
        """
        # Override checks (should already be caught, but defensive)
        if is_duplicate:
            return ReconciliationAction.SKIP
        if prune_decision == PruneDecision.TOMBSTONE:
            return ReconciliationAction.PRUNE

        # No match found → CREATE new truth record
        if not has_match:
            return ReconciliationAction.CREATE

        # Apply similarity thresholds
        if similarity >= self._config.reinforce_threshold:
            return ReconciliationAction.REINFORCE
        elif similarity >= self._config.extend_threshold:
            return ReconciliationAction.EXTEND
        elif similarity >= self._config.evolve_threshold:
            return ReconciliationAction.EVOLVE
        else:
            # Low similarity to best match → contradiction
            return ReconciliationAction.CONTRADICT

    # =========================================================================
    # Confidence Computation
    # =========================================================================

    def _compute_confidence(
        self,
        similarity: float,
        action: ReconciliationAction,
        candidates_count: int,
    ) -> float:
        """
        Compute confidence score for the decision.

        Uses Bayesian-style update from Dossier Appendix C.1.2:
            confidence = prior + (evidence_weight * evidence_factor)

        Evidence factors:
            - Similarity distance from threshold boundary
            - Number of candidates (more = more reliable search)
            - Action clarity (REINFORCE/SKIP more confident than EVOLVE)

        Args:
            similarity: Best match similarity
            action: Determined action
            candidates_count: Number of candidates evaluated

        Returns:
            Confidence in [0, 1]
        """
        base_confidence = self._config.prior_confidence

        # Evidence from similarity clarity
        if action == ReconciliationAction.REINFORCE:
            # High similarity = high confidence
            evidence = (similarity - self._config.reinforce_threshold) / (
                1.0 - self._config.reinforce_threshold
            )
            evidence = max(0.0, evidence) * 0.3
        elif action == ReconciliationAction.EXTEND:
            # Distance from boundaries
            mid = (self._config.reinforce_threshold + self._config.extend_threshold) / 2
            distance = 1.0 - abs(similarity - mid) / (
                self._config.reinforce_threshold - self._config.extend_threshold
            )
            evidence = distance * 0.2
        elif action == ReconciliationAction.EVOLVE:
            # Lower confidence for EVOLVE
            evidence = 0.1
        elif action == ReconciliationAction.CONTRADICT:
            # Low similarity = clearer contradiction
            evidence = (self._config.evolve_threshold - similarity) / self._config.evolve_threshold
            evidence = max(0.0, evidence) * 0.2
        elif action == ReconciliationAction.CREATE:
            # No match = moderate confidence
            evidence = 0.25 if candidates_count > 0 else 0.15
        elif action == ReconciliationAction.SKIP:
            # Duplicate = high confidence
            evidence = 0.4
        elif action == ReconciliationAction.PRUNE:
            # Tombstone = moderate-high confidence
            evidence = 0.35
        else:
            evidence = 0.0

        # Boost for more candidates evaluated (better search coverage)
        if candidates_count >= 5:
            evidence += 0.05
        elif candidates_count >= 3:
            evidence += 0.02

        confidence = base_confidence + (self._config.evidence_weight * evidence)
        return max(0.0, min(1.0, confidence))

    # =========================================================================
    # Reason Building
    # =========================================================================

    def _build_reason(
        self,
        action: ReconciliationAction,
        similarity: float,
        best_match: Optional["TruthCandidate"],
        candidates_count: int,
    ) -> str:
        """
        Build human-readable reason string for the decision.

        Args:
            action: The action taken
            similarity: Similarity to best match
            best_match: Best matching candidate (if any)
            candidates_count: Number of candidates evaluated

        Returns:
            Human-readable explanation
        """
        if action == ReconciliationAction.REINFORCE:
            assert best_match is not None  # Invariant: REINFORCE requires match
            return (
                f"High similarity ({similarity:.3f} >= {self._config.reinforce_threshold}) "
                f"to {best_match.layer}:{best_match.record_id}"
            )
        elif action == ReconciliationAction.EXTEND:
            assert best_match is not None  # Invariant: EXTEND requires match
            return (
                f"Moderate similarity ({similarity:.3f}) to {best_match.layer}:{best_match.record_id}; "
                f"adding as extension"
            )
        elif action == ReconciliationAction.EVOLVE:
            assert best_match is not None  # Invariant: EVOLVE requires match
            return (
                f"Related but distinct ({similarity:.3f}) from {best_match.layer}:{best_match.record_id}; "
                f"may evolve existing truth"
            )
        elif action == ReconciliationAction.CONTRADICT:
            assert best_match is not None  # Invariant: CONTRADICT requires match
            return (
                f"Low similarity ({similarity:.3f} < {self._config.evolve_threshold}) "
                f"to {best_match.layer}:{best_match.record_id}; potential contradiction"
            )
        elif action == ReconciliationAction.CREATE:
            if candidates_count == 0:
                return "No candidates found in truth layers; creating new record"
            else:
                return (
                    f"No match above threshold ({similarity:.3f} < {self._config.evolve_threshold}) "
                    f"after evaluating {candidates_count} candidates; creating new record"
                )
        elif action == ReconciliationAction.SKIP:
            return "Event marked as duplicate; skipping"
        elif action == ReconciliationAction.PRUNE:
            return "Event marked for tombstone by decay engine; pruning"
        else:
            return f"Action {action.value} determined"

    # =========================================================================
    # Metrics
    # =========================================================================

    def _record_decision(self, decision: ReconciliationDecision) -> None:
        """Record decision for metrics tracking."""
        self._total_decisions += 1
        self._action_counts[decision.action.value] += 1

        # Record similarity in histogram
        sim = decision.similarity_score
        if sim < 0.2:
            self._similarity_histogram["0.0-0.2"] += 1
        elif sim < 0.4:
            self._similarity_histogram["0.2-0.4"] += 1
        elif sim < 0.6:
            self._similarity_histogram["0.4-0.6"] += 1
        elif sim < 0.8:
            self._similarity_histogram["0.6-0.8"] += 1
        else:
            self._similarity_histogram["0.8-1.0"] += 1

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get accumulated metrics.

        Returns:
            Dict with total_decisions, action_counts, etc.
        """
        return {
            "total_decisions": self._total_decisions,
            "action_counts": dict(self._action_counts),
            "similarity_histogram": dict(self._similarity_histogram),
            "query_errors": self._query_errors,
            "query_timeouts": self._query_timeouts,
            "config": {
                "reinforce_threshold": self._config.reinforce_threshold,
                "extend_threshold": self._config.extend_threshold,
                "evolve_threshold": self._config.evolve_threshold,
                "query_timeout_seconds": self._config.query_timeout_seconds,
            },
        }

    def reset_metrics(self) -> None:
        """Reset metrics counters."""
        self._total_decisions = 0
        self._action_counts = {a.value: 0 for a in ReconciliationAction}
        self._similarity_histogram = {
            "0.0-0.2": 0,
            "0.2-0.4": 0,
            "0.4-0.6": 0,
            "0.6-0.8": 0,
            "0.8-1.0": 0,
        }
        self._query_errors = 0
        self._query_timeouts = 0
