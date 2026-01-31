"""
SPC-UQ — Schematic Pattern Completion with Uncertainty Quantification.

This module implements episodic simulation that recombines episode fragments
to reconstruct plausible narratives with uncertainty signals.

Key Features:
- Gap identification in incomplete episodes
- Schema-based Bayesian reconstruction
- Temporal coherence scoring
- Non-canonical reconstruction outputs (per A.0.6 invariant)

References:
- M8_EXECUTION.md Issue 8.1.8: SPC-UQ Episodic Simulation
- Dossier §4.6.3: Episodic Simulation (SPC-UQ)
- Dossier Appendix C.8.1: SPC-UQ Algorithm Details

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.

CRITICAL INVARIANT (A.0.6):
SPC-UQ reconstructions are NEVER canonical truth. They must be written as
candidates only with is_canonical=False and explicit provenance.
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from logging import getLogger
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

logger = getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Default simulation count
P03_SPC_DEFAULT_SIMULATIONS = 100

# Minimum confidence to include reconstruction
P03_SPC_MIN_CONFIDENCE = 0.3

# Temporal coherence threshold
P03_SPC_COHERENCE_THRESHOLD = 0.4

# Maximum gaps to fill per episode
P03_SPC_MAX_GAPS_PER_EPISODE = 5

# Ambiguity score threshold for gap detection
P03_SPC_AMBIGUITY_THRESHOLD = 0.5


# =============================================================================
# ENUMS
# =============================================================================


class GapType(str, Enum):
    """Types of gaps in episodic memory."""

    LOCATION = "location"
    PARTICIPANTS = "participants"
    ACTIVITY = "activity"
    TEMPORAL = "temporal"
    EMOTIONAL = "emotional"
    CONTENT = "content"


class ReconstructionProvenance(str, Enum):
    """Source of reconstructed value."""

    INFERRED_FROM_SCHEMA = "inferred_from_schema"
    TEMPORAL_INTERPOLATION = "temporal_interpolation"
    PATTERN_COMPLETION = "pattern_completion"
    CONTEXT_PROPAGATION = "context_propagation"
    # Fragment-based provenance types (mapped from fragment.provenance_type)
    CALENDAR = "calendar"
    MESSAGE = "message"
    SENSOR = "sensor"
    ROUTINE_PRIOR = "routine_prior"
    INFERRED_PRIOR = "inferred_prior"


# Fragment provenance type mapping (prefix -> ReconstructionProvenance)
FRAGMENT_PROVENANCE_MAP = {
    "calendar": ReconstructionProvenance.CALENDAR,
    "message": ReconstructionProvenance.MESSAGE,
    "sensory": ReconstructionProvenance.SENSOR,
    "sensor": ReconstructionProvenance.SENSOR,
    "routine": ReconstructionProvenance.ROUTINE_PRIOR,
    "inferred": ReconstructionProvenance.INFERRED_PRIOR,
}

# Fragment ID prefix -> provenance type mapping
FRAGMENT_ID_PREFIX_MAP = {
    "frag_cal_": ReconstructionProvenance.CALENDAR,
    "frag_msg_": ReconstructionProvenance.MESSAGE,
    "frag_sens_": ReconstructionProvenance.SENSOR,
    "frag_rout_": ReconstructionProvenance.ROUTINE_PRIOR,
    "frag_inf_": ReconstructionProvenance.INFERRED_PRIOR,
}


# =============================================================================
# PROTOCOLS
# =============================================================================


@runtime_checkable
class Episode(Protocol):
    """Protocol for episodic memory."""

    episode_id: str
    start_time_ms: int
    end_time_ms: Optional[int]

    @property
    def location_name(self) -> Optional[str]: ...

    @property
    def participants(self) -> Optional[List[str]]: ...

    @property
    def activity_type(self) -> Optional[str]: ...

    @property
    def ambiguity_score(self) -> float: ...


@runtime_checkable
class SemanticPattern(Protocol):
    """Protocol for semantic patterns/schemas."""

    pattern_id: str
    activity_type: str
    confidence: float

    def get_attribute_distribution(
        self,
        attribute_name: str,
    ) -> Dict[str, float]: ...


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class SPCConfig:
    """
    Configuration for SPC-UQ algorithm.

    Attributes:
        simulation_count: Number of Monte Carlo simulations
        min_confidence: Minimum confidence for reconstructions
        coherence_threshold: Minimum temporal coherence score
        max_gaps_per_episode: Maximum gaps to fill per episode
        ambiguity_threshold: Ambiguity score threshold for gap detection
        uncertainty_alpha: Beta distribution alpha for uncertainty
        uncertainty_beta: Beta distribution beta for uncertainty
        seed: RNG seed for determinism
    """

    simulation_count: int = P03_SPC_DEFAULT_SIMULATIONS
    min_confidence: float = P03_SPC_MIN_CONFIDENCE
    coherence_threshold: float = P03_SPC_COHERENCE_THRESHOLD
    max_gaps_per_episode: int = P03_SPC_MAX_GAPS_PER_EPISODE
    ambiguity_threshold: float = P03_SPC_AMBIGUITY_THRESHOLD
    uncertainty_alpha: float = 1.0
    uncertainty_beta: float = 1.0
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.simulation_count < 1:
            raise ValueError("simulation_count must be at least 1")
        if not 0 <= self.min_confidence <= 1:
            raise ValueError("min_confidence must be in [0, 1]")
        if not 0 <= self.coherence_threshold <= 1:
            raise ValueError("coherence_threshold must be in [0, 1]")
        if self.max_gaps_per_episode < 1:
            raise ValueError("max_gaps_per_episode must be at least 1")
        if self.uncertainty_alpha <= 0:
            raise ValueError("uncertainty_alpha must be positive")
        if self.uncertainty_beta <= 0:
            raise ValueError("uncertainty_beta must be positive")


@dataclass
class SemanticPatternData:
    """
    Concrete implementation of SemanticPattern protocol for st_sem schemas.

    M4-E2: Provides schema data for SPC-UQ reconstruction guidance.

    Attributes:
        pattern_id: Unique pattern identifier from st_sem.sem_id
        activity_type: Pattern type (ACTIVITY, LOCATION, ROUTINE, etc.)
        confidence: Pattern confidence score
        attribute_distributions: Attribute name -> value distribution mapping
    """

    pattern_id: str
    activity_type: str
    confidence: float
    attribute_distributions: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def get_attribute_distribution(self, attribute_name: str) -> Dict[str, float]:
        """
        Get probability distribution for an attribute.

        Args:
            attribute_name: Name of the attribute (location_name, participants, etc.)

        Returns:
            Dictionary mapping values to probabilities
        """
        return self.attribute_distributions.get(attribute_name, {})


@dataclass
class AttributeGap:
    """
    Represents a missing or uncertain attribute in an episode.

    Attributes:
        attribute_name: Name of the missing attribute
        gap_type: Classification of the gap
        priority: Priority for filling (0.0 to 1.0)
        current_value: Existing value (if ambiguous)
        ambiguity_score: How uncertain the current value is
    """

    attribute_name: str
    gap_type: GapType
    priority: float = 0.5
    current_value: Optional[Any] = None
    ambiguity_score: float = 0.0

    def __post_init__(self) -> None:
        """Validate priority."""
        if not 0 <= self.priority <= 1:
            raise ValueError("priority must be in [0, 1]")


@dataclass
class ReconstructedValue:
    """
    A reconstructed attribute value with uncertainty.

    Attributes:
        attribute_name: Name of the reconstructed attribute
        value: The reconstructed value
        confidence: Confidence in the reconstruction (0.0 to 1.0)
        uncertainty: Uncertainty quantification (0.0 to 1.0)
        provenance: Source of the reconstruction
        schema_id: Schema used for reconstruction (if any)
        created_at_ms: Timestamp of reconstruction
    """

    attribute_name: str
    value: Any
    confidence: float
    uncertainty: float
    provenance: ReconstructionProvenance
    schema_id: Optional[str] = None
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    @property
    def is_high_confidence(self) -> bool:
        """Return True if confidence >= 0.7."""
        return self.confidence >= 0.7

    @property
    def is_low_uncertainty(self) -> bool:
        """Return True if uncertainty <= 0.3."""
        return self.uncertainty <= 0.3


@dataclass(frozen=True)
class EpisodeFragment:
    """
    A fragment of an episode for reconstruction.

    Attributes:
        fragment_id: Unique identifier
        source_episode_id: Original episode ID
        source_event_id: Source event ID (for provenance)
        start_time_ms: Fragment start time
        end_time_ms: Fragment end time
        content: Fragment content/summary
        attributes: Known attributes of this fragment
    """

    fragment_id: str
    source_episode_id: str
    source_event_id: str
    start_time_ms: int
    end_time_ms: int
    content: str
    attributes: Tuple[Tuple[str, Any], ...] = ()

    def get_attribute(self, name: str) -> Optional[Any]:
        """Get attribute value by name."""
        for attr_name, value in self.attributes:
            if attr_name == name:
                return value
        return None


@dataclass(frozen=True)
class ReconstructedEpisode:
    """
    A reconstructed episode (non-canonical).

    Per A.0.6 invariant: This is NEVER canonical truth.
    is_canonical is always False.

    Attributes:
        episode_id: New unique identifier for reconstruction
        original_episode_id: Original episode being reconstructed
        summary: Reconstructed narrative summary
        reconstructed_fields: List of reconstructed attributes
        confidence_score: Overall reconstruction confidence
        uncertainty_score: Overall uncertainty quantification
        temporal_coherence_score: How temporally coherent the reconstruction is
        provenance: Detailed provenance information
        is_canonical: Always False for reconstructions
        created_at_ms: Creation timestamp
    """

    episode_id: str
    original_episode_id: str
    summary: str
    reconstructed_fields: Tuple[ReconstructedValue, ...]
    confidence_score: float
    uncertainty_score: float
    temporal_coherence_score: float
    provenance: Dict[str, Any]
    is_canonical: bool = False  # CRITICAL: Never True for reconstructions
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def __post_init__(self) -> None:
        """Ensure is_canonical is never True."""
        if self.is_canonical:
            raise ValueError("SPC-UQ reconstructions must NEVER be canonical (A.0.6 invariant)")

    @classmethod
    def create(
        cls,
        episode_id: str,
        original_episode_id: str,
        summary: str,
        reconstructed_fields: List[ReconstructedValue],
        confidence_score: float,
        uncertainty_score: float,
        temporal_coherence_score: float,
        provenance: Dict[str, Any],
    ) -> "ReconstructedEpisode":
        """Factory method with validation."""
        return cls(
            episode_id=episode_id,
            original_episode_id=original_episode_id,
            summary=summary,
            reconstructed_fields=tuple(reconstructed_fields),
            confidence_score=max(0.0, min(1.0, confidence_score)),
            uncertainty_score=max(0.0, min(1.0, uncertainty_score)),
            temporal_coherence_score=max(0.0, min(1.0, temporal_coherence_score)),
            provenance=provenance,
            is_canonical=False,  # Enforced
            created_at_ms=int(time.time() * 1000),
        )


# =============================================================================
# MOCK EPISODE FOR TESTING
# =============================================================================


@dataclass
class SimpleEpisode:
    """Simple episode implementation for testing."""

    episode_id: str
    start_time_ms: int
    end_time_ms: Optional[int] = None
    _location_name: Optional[str] = None
    _participants: Optional[List[str]] = None
    _activity_type: Optional[str] = None
    _ambiguity_score: float = 0.0
    summary: str = ""

    @property
    def location_name(self) -> Optional[str]:
        return self._location_name

    @property
    def participants(self) -> Optional[List[str]]:
        return self._participants

    @property
    def activity_type(self) -> Optional[str]:
        return self._activity_type

    @property
    def ambiguity_score(self) -> float:
        return self._ambiguity_score


# =============================================================================
# SPC-UQ ALGORITHM
# =============================================================================


@dataclass
class FragmentConflict:
    """Detected conflict between fragments."""

    attribute_name: str
    conflicting_values: List[Any]
    fragment_ids: List[str]
    provenance_types: List[ReconstructionProvenance]
    severity: float  # 0.0-1.0, higher = more severe conflict


class EpisodicSimulator:
    """
    SPC-UQ Episodic Simulator.

    Reconstructs incomplete episodes using schema-based Bayesian inference
    with uncertainty quantification.

    This class orchestrates:
    1. Gap identification in episodes
    2. Schema retrieval for reconstruction guidance
    3. Bayesian inference for gap filling
    4. Temporal coherence validation
    5. Uncertainty quantification
    6. Conflict detection and resolution

    CRITICAL: All reconstructions are NON-CANONICAL per A.0.6 invariant.

    Usage:
        config = SPCConfig(simulation_count=100)
        simulator = EpisodicSimulator(config)

        reconstructions = simulator.simulate(
            episodes=incomplete_episodes,
            fragments=episode_fragments,
            schemas=available_schemas,
            rng_seed=42,
        )
    """

    def __init__(
        self,
        config: Optional[SPCConfig] = None,
    ):
        """
        Initialize EpisodicSimulator.

        Args:
            config: SPC-UQ configuration
        """
        self.config = config or SPCConfig()
        self._logger = getLogger(f"{__name__}.{self.__class__.__name__}")

    # -------------------------------------------------------------------------
    # Gap Identification
    # -------------------------------------------------------------------------

    def identify_gaps(self, episode: Any) -> List[AttributeGap]:
        """
        Find missing or uncertain attributes in an episode.

        Checks for:
        - NULL values in key attributes (location, participants)
        - High ambiguity scores
        - Missing activity type

        Args:
            episode: Episode to analyze

        Returns:
            List of identified gaps sorted by priority
        """
        gaps: List[AttributeGap] = []

        # Check location
        location = self._get_attr(episode, "location_name")
        if not location:
            gaps.append(
                AttributeGap(
                    attribute_name="location_name",
                    gap_type=GapType.LOCATION,
                    priority=0.8,
                )
            )

        # Check participants
        participants = self._get_attr(episode, "participants")
        if not participants:
            gaps.append(
                AttributeGap(
                    attribute_name="participants",
                    gap_type=GapType.PARTICIPANTS,
                    priority=0.7,
                )
            )

        # Check activity type
        activity = self._get_attr(episode, "activity_type")
        if not activity:
            gaps.append(
                AttributeGap(
                    attribute_name="activity_type",
                    gap_type=GapType.ACTIVITY,
                    priority=0.6,
                )
            )

        # Check ambiguity
        ambiguity = self._get_attr(episode, "ambiguity_score", 0.0)
        if ambiguity > self.config.ambiguity_threshold:
            gaps.append(
                AttributeGap(
                    attribute_name="ambiguous_content",
                    gap_type=GapType.CONTENT,
                    priority=0.9,
                    ambiguity_score=ambiguity,
                )
            )

        # Sort by priority (highest first)
        gaps.sort(key=lambda g: g.priority, reverse=True)

        # Limit to max gaps
        return gaps[: self.config.max_gaps_per_episode]

    # -------------------------------------------------------------------------
    # Schema Matching
    # -------------------------------------------------------------------------

    def find_matching_schema(
        self,
        episode: Any,
        schemas: List[Any],
    ) -> Optional[Any]:
        """
        Find the best matching schema for an episode.

        Args:
            episode: Episode to match
            schemas: Available semantic patterns

        Returns:
            Best matching schema or None
        """
        if not schemas:
            return None

        activity_type = self._get_attr(episode, "activity_type")
        if not activity_type:
            return None

        # Filter schemas by activity type
        matching = [
            s
            for s in schemas
            if self._get_attr(s, "activity_type") == activity_type
            and self._get_attr(s, "confidence", 0) >= 0.6
        ]

        if not matching:
            return None

        # Return highest confidence match
        return max(matching, key=lambda s: self._get_attr(s, "confidence", 0))

    # -------------------------------------------------------------------------
    # Bayesian Reconstruction
    # -------------------------------------------------------------------------

    def bayesian_reconstruction(
        self,
        gap: AttributeGap,
        schema: Optional[Any],
        context: Dict[str, Any],
        rng: random.Random,
        fragments: Optional[List[Any]] = None,
        conflicts: Optional[List["FragmentConflict"]] = None,
    ) -> Optional[ReconstructedValue]:
        """
        Fill gap using Bayesian inference.

        P(value | schema, context) ∝ P(context | value) × P(value | schema)

        Args:
            gap: Gap to fill
            schema: Schema for prior distribution
            context: Context clues for likelihood
            rng: Random number generator
            fragments: Fragments for provenance attribution
            conflicts: Detected conflicts for uncertainty adjustment

        Returns:
            ReconstructedValue or None if cannot reconstruct
        """
        if schema is None:
            # No schema - use context-based heuristics with fragment provenance
            return self._reconstruct_from_context(
                gap, context, rng, fragments=fragments, conflicts=conflicts
            )

        # Get prior distribution from schema
        prior = self._get_prior_distribution(schema, gap.attribute_name)
        if not prior:
            return self._reconstruct_from_context(
                gap, context, rng, fragments=fragments, conflicts=conflicts
            )

        # Compute likelihoods
        likelihoods: Dict[str, float] = {}
        for value, prior_prob in prior.items():
            likelihood = self._compute_likelihood(value, context, gap.gap_type)
            likelihoods[value] = prior_prob * likelihood

        # Normalize to get posterior
        total = sum(likelihoods.values())
        if total == 0:
            return None

        posteriors = {v: p / total for v, p in likelihoods.items()}

        # Sample or select MAP
        if self.config.simulation_count > 1:
            # Monte Carlo sampling
            values = list(posteriors.keys())
            weights = list(posteriors.values())
            sampled_value = rng.choices(values, weights=weights, k=1)[0]
            confidence = posteriors[sampled_value]
        else:
            # Maximum a posteriori
            sampled_value = max(posteriors, key=lambda k: posteriors[k])
            confidence = posteriors[sampled_value]

        # Compute uncertainty using Beta distribution
        uncertainty = self._compute_uncertainty(confidence, rng)

        schema_id = self._get_attr(schema, "pattern_id")

        return ReconstructedValue(
            attribute_name=gap.attribute_name,
            value=sampled_value,
            confidence=confidence,
            uncertainty=uncertainty,
            provenance=ReconstructionProvenance.INFERRED_FROM_SCHEMA,
            schema_id=schema_id,
        )

    def _reconstruct_from_context(
        self,
        gap: AttributeGap,
        context: Dict[str, Any],
        rng: random.Random,
        fragments: Optional[List[Any]] = None,
        conflicts: Optional[List[FragmentConflict]] = None,
    ) -> Optional[ReconstructedValue]:
        """Reconstruct without schema using context and fragment provenance.

        Uses fragment provenance types when available. Increases uncertainty
        when conflicts are detected.
        """
        fragments = fragments or []
        conflicts = conflicts or []

        # Determine provenance from fragments
        provenance = self._get_dominant_provenance(fragments, gap)

        # Check if there's a conflict for this attribute
        has_conflict = any(c.attribute_name == gap.attribute_name for c in conflicts)
        conflict_penalty = 0.15 if has_conflict else 0.0

        # Try to infer from temporal context
        if gap.gap_type == GapType.LOCATION:
            nearby_locations = context.get("nearby_locations", [])
            if nearby_locations:
                location = rng.choice(nearby_locations)
                base_conf = 0.4 - conflict_penalty
                return ReconstructedValue(
                    attribute_name=gap.attribute_name,
                    value=location,
                    confidence=max(0.2, base_conf),
                    uncertainty=0.6 + conflict_penalty,
                    provenance=provenance,
                )

        elif gap.gap_type == GapType.PARTICIPANTS:
            frequent_contacts = context.get("frequent_contacts", [])
            if frequent_contacts:
                participants = rng.sample(frequent_contacts, min(2, len(frequent_contacts)))
                base_conf = 0.35 - conflict_penalty
                return ReconstructedValue(
                    attribute_name=gap.attribute_name,
                    value=participants,
                    confidence=max(0.2, base_conf),
                    uncertainty=0.65 + conflict_penalty,
                    provenance=provenance,
                )

        return None

    def _get_prior_distribution(
        self,
        schema: Any,
        attribute_name: str,
    ) -> Dict[str, float]:
        """Get prior distribution from schema."""
        if hasattr(schema, "get_attribute_distribution"):
            return schema.get_attribute_distribution(attribute_name)
        return {}

    def _compute_likelihood(
        self,
        value: Any,
        context: Dict[str, Any],
        gap_type: GapType,
    ) -> float:
        """Compute likelihood P(context | value)."""
        # Base likelihood
        likelihood = 0.5

        # Adjust based on context clues
        if gap_type == GapType.LOCATION:
            known_locations = context.get("known_locations", [])
            if value in known_locations:
                likelihood += 0.3
            time_of_day = context.get("time_of_day", "")
            if time_of_day == "evening" and "home" in str(value).lower():
                likelihood += 0.2

        elif gap_type == GapType.PARTICIPANTS:
            frequent_contacts = context.get("frequent_contacts", [])
            if value in frequent_contacts:
                likelihood += 0.3

        return min(1.0, likelihood)

    def _compute_uncertainty(
        self,
        confidence: float,
        rng: random.Random,
    ) -> float:
        """
        Compute uncertainty using Beta distribution.

        Higher alpha/beta = lower uncertainty.
        """
        # Scale confidence to Beta parameters
        alpha = self.config.uncertainty_alpha + confidence * 10
        beta = self.config.uncertainty_beta + (1 - confidence) * 10

        # Sample from Beta
        try:
            sampled = rng.betavariate(alpha, beta)
        except ValueError:
            sampled = 0.5

        # Uncertainty is inverse of sampled value
        return 1.0 - sampled

    # -------------------------------------------------------------------------
    # Temporal Coherence
    # -------------------------------------------------------------------------

    def calculate_temporal_coherence(
        self,
        fragments: List[EpisodeFragment],
    ) -> float:
        """
        Calculate temporal coherence of fragments.

        Measures how well fragments fit together temporally.

        Args:
            fragments: Episode fragments

        Returns:
            Coherence score (0.0 to 1.0)
        """
        if len(fragments) < 2:
            return 1.0  # Single fragment is perfectly coherent

        # Sort by start time
        sorted_fragments = sorted(fragments, key=lambda f: f.start_time_ms)

        # Check for overlaps and gaps
        coherence_penalties = 0.0
        total_checks = len(sorted_fragments) - 1

        for i in range(total_checks):
            current = sorted_fragments[i]
            next_frag = sorted_fragments[i + 1]

            # Check for temporal overlap (bad)
            if current.end_time_ms > next_frag.start_time_ms:
                overlap_ms = current.end_time_ms - next_frag.start_time_ms
                # Penalize based on overlap size
                coherence_penalties += min(0.3, overlap_ms / 3600000)  # Per hour

            # Check for large gap (suspicious)
            gap_ms = next_frag.start_time_ms - current.end_time_ms
            if gap_ms > 24 * 3600 * 1000:  # > 24 hours
                coherence_penalties += 0.2

        # Calculate coherence
        coherence = 1.0 - (coherence_penalties / max(1, total_checks))
        return max(0.0, min(1.0, coherence))

    # -------------------------------------------------------------------------
    # Main Simulation Entry Point
    # -------------------------------------------------------------------------

    def simulate(
        self,
        episodes: List[Any],
        fragments: Optional[List[EpisodeFragment]] = None,
        schemas: Optional[List[Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        rng_seed: Optional[int] = None,
    ) -> List[ReconstructedEpisode]:
        """
        Run episodic simulation to reconstruct incomplete episodes.

        Args:
            episodes: Episodes to potentially reconstruct
            fragments: Episode fragments for reconstruction
            schemas: Semantic patterns for guidance
            context: Contextual information
            rng_seed: Seed for deterministic behavior

        Returns:
            List of reconstructed episodes (all non-canonical)
        """
        start_ms = int(time.time() * 1000)

        # Initialize RNG
        seed = rng_seed if rng_seed is not None else self.config.seed
        rng = random.Random(seed)

        fragments = fragments or []
        schemas = schemas or []
        context = context or {}

        reconstructions: List[ReconstructedEpisode] = []
        all_conflicts: List[FragmentConflict] = []

        for episode in episodes:
            episode_id = self._get_attr(episode, "episode_id", "unknown")

            # Step 0: Get relevant fragments for this episode
            relevant_fragments = [
                f for f in fragments if self._get_attr(f, "source_episode_id") == episode_id
            ]

            # Step 1: Detect conflicts in fragments
            episode_conflicts = self._detect_conflicts(fragments, episode_id)
            all_conflicts.extend(episode_conflicts)

            # Step 2: Identify gaps
            gaps = self.identify_gaps(episode)
            if not gaps:
                continue  # Episode is complete

            # Step 3: Find matching schema
            schema = self.find_matching_schema(episode, schemas)

            # Step 4: Reconstruct each gap (with conflict awareness)
            reconstructed_fields: List[ReconstructedValue] = []
            provenance_types_used: set = set()

            for gap in gaps:
                # Try schema-based reconstruction first (pass fragments for provenance)
                reconstruction = self.bayesian_reconstruction(
                    gap=gap,
                    schema=schema,
                    context=context,
                    rng=rng,
                    fragments=relevant_fragments,
                    conflicts=episode_conflicts,
                )

                # Fall back to context-based with fragment provenance
                if not reconstruction or reconstruction.confidence < self.config.min_confidence:
                    reconstruction = self._reconstruct_from_context(
                        gap=gap,
                        context=context,
                        rng=rng,
                        fragments=relevant_fragments,
                        conflicts=episode_conflicts,
                    )

                if reconstruction and reconstruction.confidence >= self.config.min_confidence:
                    reconstructed_fields.append(reconstruction)
                    provenance_types_used.add(reconstruction.provenance)

            if not reconstructed_fields:
                continue  # No viable reconstructions

            # Collect ALL fragment provenance types that contributed to this episode
            # This gives a fuller picture of provenance diversity
            all_fragment_provenances: set = set()
            for frag in relevant_fragments:
                frag_prov = self._get_fragment_provenance(frag)
                all_fragment_provenances.add(frag_prov)

            # Step 5: Calculate temporal coherence
            temporal_coherence = self.calculate_temporal_coherence(relevant_fragments)

            # Step 6: Filter by coherence threshold
            if temporal_coherence < self.config.coherence_threshold:
                self._logger.debug(
                    f"Skipping reconstruction due to low coherence: {temporal_coherence}"
                )
                continue

            # Step 7: Compute overall scores (penalize for conflicts)
            conflict_penalty = 0.1 * len(episode_conflicts)
            overall_confidence = (
                sum(r.confidence for r in reconstructed_fields) / len(reconstructed_fields)
            ) - conflict_penalty
            overall_confidence = max(0.1, overall_confidence)

            overall_uncertainty = (
                sum(r.uncertainty for r in reconstructed_fields) / len(reconstructed_fields)
            ) + conflict_penalty
            overall_uncertainty = min(0.95, overall_uncertainty)

            # Step 8: Generate new episode ID
            new_episode_id = self._generate_reconstruction_id(episode_id, seed, rng)

            # Step 9: Create reconstructed episode (NON-CANONICAL)
            reconstructed = ReconstructedEpisode.create(
                episode_id=new_episode_id,
                original_episode_id=episode_id,
                summary=self._generate_summary(episode, reconstructed_fields),
                reconstructed_fields=reconstructed_fields,
                confidence_score=overall_confidence,
                uncertainty_score=overall_uncertainty,
                temporal_coherence_score=temporal_coherence,
                provenance={
                    "algorithm": "SPC-UQ",
                    "source_fragments": [
                        self._get_attr(f, "fragment_id") or self._get_attr(f, "id")
                        for f in relevant_fragments
                    ],
                    "schema_id": self._get_attr(schema, "pattern_id") if schema else None,
                    "simulation_count": self.config.simulation_count,
                    "rng_seed": seed,
                    # provenance_types_used = ALL fragment provenance types that contributed
                    "provenance_types_used": [str(p) for p in all_fragment_provenances],
                    # reconstruction_provenance = the dominant provenance used in field reconstructions
                    "reconstruction_provenance": [str(p) for p in provenance_types_used],
                    "conflicts_detected": len(episode_conflicts),
                    "conflict_details": [
                        {
                            "attribute": c.attribute_name,
                            "values": c.conflicting_values,
                            "severity": c.severity,
                        }
                        for c in episode_conflicts
                    ],
                },
            )
            reconstructions.append(reconstructed)

        compute_ms = int(time.time() * 1000) - start_ms

        self._logger.debug(
            "SPC-UQ simulation complete",
            extra={
                "episodes_processed": len(episodes),
                "reconstructions_generated": len(reconstructions),
                "compute_ms": compute_ms,
            },
        )

        return reconstructions

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _get_attr(self, obj: Any, attr: str, default: Any = None) -> Any:
        """Get attribute from object (supports dict and object)."""
        if isinstance(obj, dict):
            return obj.get(attr, default)
        return getattr(obj, attr, default)

    def _get_fragment_provenance(self, fragment: Any) -> ReconstructionProvenance:
        """Determine provenance type from fragment.

        Uses fragment.provenance_type if available, otherwise falls back to
        fragment ID prefix mapping.
        """
        # Try direct provenance_type attribute
        prov_type = self._get_attr(fragment, "provenance_type")
        if prov_type and prov_type in FRAGMENT_PROVENANCE_MAP:
            return FRAGMENT_PROVENANCE_MAP[prov_type]

        # Try attributes tuple (SPCFragment uses this format)
        attributes = self._get_attr(fragment, "attributes")
        if isinstance(attributes, (list, tuple)):
            for attr_tuple in attributes:
                if isinstance(attr_tuple, (list, tuple)) and len(attr_tuple) >= 2:
                    if (
                        attr_tuple[0] == "provenance_type"
                        and attr_tuple[1] in FRAGMENT_PROVENANCE_MAP
                    ):
                        return FRAGMENT_PROVENANCE_MAP[attr_tuple[1]]

        # Try fragment ID prefix
        frag_id = self._get_attr(fragment, "fragment_id", "") or self._get_attr(fragment, "id", "")
        for prefix, provenance in FRAGMENT_ID_PREFIX_MAP.items():
            if frag_id.startswith(prefix):
                return provenance

        # Default fallback
        return ReconstructionProvenance.CONTEXT_PROPAGATION

    def _detect_conflicts(
        self,
        fragments: List[Any],
        episode_id: str,
    ) -> List[FragmentConflict]:
        """Detect conflicts between fragments for an episode.

        Conflicts occur when:
        1. Fragments have explicit conflicting_with declarations
        2. Multiple fragments provide different values for the same attribute
           (time, location, participants, etc.)
        """
        conflicts: List[FragmentConflict] = []

        # Group fragments by episode
        episode_fragments = [
            f for f in fragments if self._get_attr(f, "source_episode_id") == episode_id
        ]

        if len(episode_fragments) < 2:
            return conflicts

        # Build fragment ID map for lookups
        frag_id_map = {}
        for frag in episode_fragments:
            frag_id = self._get_attr(frag, "fragment_id", "") or self._get_attr(frag, "id", "")
            if frag_id:
                frag_id_map[frag_id] = frag

        # Method 1: Check for explicit conflicting_with declarations
        explicit_conflicts_seen: set = set()  # Avoid duplicates
        for frag in episode_fragments:
            frag_id = self._get_attr(frag, "fragment_id", "") or self._get_attr(frag, "id", "")
            conflicting_with = self._get_attr(frag, "conflicting_with", [])
            conflict_type = self._get_attr(frag, "conflict_type", "factual")
            content = self._get_attr(frag, "content", "")

            if conflicting_with:
                for conflicting_id in conflicting_with:
                    # Create sorted tuple to avoid duplicates
                    pair = tuple(sorted([frag_id, conflicting_id]))
                    if pair not in explicit_conflicts_seen:
                        explicit_conflicts_seen.add(pair)
                        conflicting_frag = frag_id_map.get(conflicting_id)
                        if conflicting_frag:
                            other_content = self._get_attr(conflicting_frag, "content", "")
                            conflicts.append(
                                FragmentConflict(
                                    attribute_name=conflict_type or "factual",
                                    conflicting_values=[content[:50], other_content[:50]],
                                    fragment_ids=[frag_id, conflicting_id],
                                    provenance_types=[
                                        self._get_fragment_provenance(frag),
                                        self._get_fragment_provenance(conflicting_frag),
                                    ],
                                    severity=0.7,
                                )
                            )

        # Method 2: Detect implicit conflicts from content/entities
        # Extract values by attribute type based on fragment content/entities
        time_values: Dict[str, List[str]] = {}  # fragment_id -> time values
        location_values: Dict[str, List[str]] = {}
        participant_values: Dict[str, List[str]] = {}

        for frag in episode_fragments:
            frag_id = self._get_attr(frag, "fragment_id", "") or self._get_attr(frag, "id", "")
            content = self._get_attr(frag, "content", "")
            entities = self._get_attr(frag, "entities_mentioned", [])

            # Check for time mentions in content (look for time patterns)
            import re

            time_patterns = re.findall(
                r"\d{1,2}:\d{2}(?:\s*[AP]M)?|\d{1,2}(?::\d{2})?\s*[AP]M", content, re.IGNORECASE
            )
            if time_patterns:
                time_values[frag_id] = time_patterns

            # Check for location entities
            loc_entities = [e for e in entities if "loc_" in str(e) or "location" in str(e).lower()]
            if loc_entities:
                location_values[frag_id] = [str(e) for e in loc_entities]

            # Check for participant entities
            person_entities = [
                e for e in entities if "person_" in str(e) or "person" in str(e).lower()
            ]
            if person_entities:
                participant_values[frag_id] = [str(e) for e in person_entities]

        # Detect time conflicts
        if len(time_values) >= 2:
            all_times = set()
            for times in time_values.values():
                all_times.update(times)
            if len(all_times) >= 2:  # Different times mentioned
                conflicts.append(
                    FragmentConflict(
                        attribute_name="temporal",
                        conflicting_values=list(all_times),
                        fragment_ids=list(time_values.keys()),
                        provenance_types=[
                            self._get_fragment_provenance(
                                next(
                                    (
                                        f
                                        for f in episode_fragments
                                        if (
                                            self._get_attr(f, "fragment_id")
                                            or self._get_attr(f, "id")
                                        )
                                        == fid
                                    ),
                                    None,
                                )
                            )
                            for fid in time_values.keys()
                        ],
                        severity=0.7,
                    )
                )

        # Detect location conflicts
        if len(location_values) >= 2:
            all_locs = set()
            for locs in location_values.values():
                all_locs.update(locs)
            if len(all_locs) >= 2:  # Different locations
                conflicts.append(
                    FragmentConflict(
                        attribute_name="location_name",
                        conflicting_values=list(all_locs),
                        fragment_ids=list(location_values.keys()),
                        provenance_types=[
                            self._get_fragment_provenance(
                                next(
                                    (
                                        f
                                        for f in episode_fragments
                                        if (
                                            self._get_attr(f, "fragment_id")
                                            or self._get_attr(f, "id")
                                        )
                                        == fid
                                    ),
                                    None,
                                )
                            )
                            for fid in location_values.keys()
                        ],
                        severity=0.6,
                    )
                )

        return conflicts

    def _get_dominant_provenance(
        self,
        fragments: List[Any],
        gap: "AttributeGap",
    ) -> ReconstructionProvenance:
        """Get the dominant provenance type from contributing fragments.

        Prioritizes by reliability:
        1. CALENDAR (highest reliability)
        2. MESSAGE
        3. SENSOR
        4. ROUTINE_PRIOR
        5. INFERRED_PRIOR (lowest reliability)
        6. CONTEXT_PROPAGATION (fallback)
        """
        if not fragments:
            return ReconstructionProvenance.CONTEXT_PROPAGATION

        provenance_priority = {
            ReconstructionProvenance.CALENDAR: 6,
            ReconstructionProvenance.MESSAGE: 5,
            ReconstructionProvenance.SENSOR: 4,
            ReconstructionProvenance.ROUTINE_PRIOR: 3,
            ReconstructionProvenance.INFERRED_PRIOR: 2,
            ReconstructionProvenance.CONTEXT_PROPAGATION: 1,
        }

        best_prov = ReconstructionProvenance.CONTEXT_PROPAGATION
        best_priority = 0

        for frag in fragments:
            prov = self._get_fragment_provenance(frag)
            priority = provenance_priority.get(prov, 0)
            if priority > best_priority:
                best_priority = priority
                best_prov = prov

        return best_prov

    def _generate_reconstruction_id(
        self,
        original_id: str,
        seed: Optional[int],
        rng: random.Random,
    ) -> str:
        """Generate unique ID for reconstruction."""
        hash_input = f"{original_id}:{seed}:{rng.random()}"
        hash_bytes = hashlib.sha256(hash_input.encode()).digest()
        return hash_bytes[:13].hex().upper()

    def _generate_summary(
        self,
        episode: Any,
        reconstructed_fields: List[ReconstructedValue],
    ) -> str:
        """Generate summary for reconstructed episode."""
        original_summary = self._get_attr(episode, "summary", "")
        field_list = ", ".join(r.attribute_name for r in reconstructed_fields)
        return f"{original_summary} [Reconstructed: {field_list}]"
