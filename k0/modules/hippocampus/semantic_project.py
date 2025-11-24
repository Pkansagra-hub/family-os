"""
M02: hippocampus.semantic_project (CA1 Semantic Projection)

Phase 2 Declarative Module - Entity extraction, KG triple generation, embedding queueing

Architecture:
- Bridges episodic memory (DG) to semantic knowledge structures (CA1)
- Uses spaCy NER for lightweight entity extraction (80% accuracy, 10ms latency)
- Template-based KG triple generation (subject-predicate-object)
- Allocates embedding_id for P08 vector generation (deferred to async pipeline)

Performance:
- Target: ≤20ms P95, ≤35ms P99
- spaCy model: en_core_web_sm (50MB, loaded once at startup)
- No external API calls (local-first, privacy-preserving)

Contract: k0/contracts/modules/hippocampus.semantic_project.v1.yaml
ADR: docs/architecture/decisions-K0/modules/k003.2-ca1-semantic-bridge.md

Related Modules:
- M01 (pattern_separate): Upstream module (DG fingerprinting)
- M04 (affect.analyze): Parallel module
- M14 (outbox.enqueue_embedding): Downstream module (queue write)

Input: cognitive.memory.write.committed.v1 event
Output: p02.hippocampus.semantic_projected.v1 event
Side Effects: Prepares payload for st_embedding_queue (via M14)

Author: K0 Architecture Team
Date: 2025-11-17
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# spaCy will be loaded lazily on first use (not at module import time)
_SPACY_AVAILABLE = None  # Will be set on first call to _ensure_spacy_loaded()
_nlp = None
_SPACY_LOAD_ERROR = None

logger = logging.getLogger(__name__)


def _ensure_spacy_loaded(preloaded_models: dict[str, Any] | None = None):
    """Lazy-load spaCy model on first use, or use preloaded model from app.state."""
    global _SPACY_AVAILABLE, _nlp, _SPACY_LOAD_ERROR

    if _SPACY_AVAILABLE is not None:
        return _SPACY_AVAILABLE  # Already tried loading

    # Check for preloaded model first (from kernel startup)
    if preloaded_models and "spacy_nlp" in preloaded_models:
        preloaded_nlp = preloaded_models["spacy_nlp"]
        if preloaded_nlp is not None:
            _nlp = preloaded_nlp
            _SPACY_AVAILABLE = True
            logger.debug("Using preloaded spaCy model from kernel startup")
            return _SPACY_AVAILABLE

    try:
        import spacy

        _nlp = spacy.load("en_core_web_sm")
        _SPACY_AVAILABLE = True
        logger.info("spaCy model loaded successfully")
    except ImportError as e:
        _SPACY_LOAD_ERROR = f"ImportError: {e}"
        _SPACY_AVAILABLE = False
        logger.warning(
            f"spaCy initialization failed: {_SPACY_LOAD_ERROR}. "
            "Entity extraction will return empty lists."
        )
    except OSError as e:
        # Model not installed: python -m spacy download en_core_web_sm
        _SPACY_LOAD_ERROR = f"OSError (model not found): {e}"
        _SPACY_AVAILABLE = False
        logger.warning(
            f"spaCy model not found: {_SPACY_LOAD_ERROR}. "
            "Run: python -m spacy download en_core_web_sm"
        )
    except Exception as e:
        _SPACY_LOAD_ERROR = f"Unexpected error: {type(e).__name__}: {e}"
        _SPACY_AVAILABLE = False
        logger.error(f"spaCy loading failed unexpectedly: {_SPACY_LOAD_ERROR}")

    return _SPACY_AVAILABLE


# ============================================================================
# Entity Extraction (spaCy NER)
# ============================================================================


@dataclass
class Entity:
    """Extracted named entity with metadata."""

    text: str  # Original text ("mom", "Olive Garden")
    label: str  # spaCy label (PERSON, ORG, GPE, DATE, TIME)
    confidence: float  # NER confidence score (0.0-1.0)
    canonical_id: str | None = None  # Resolved ID ("person_mom", "Olive_Garden_Market_St")


def _extract_entities(
    text: str,
    confidence_threshold: float = 0.6,
    preloaded_models: dict[str, Any] | None = None,
) -> list[Entity]:
    """
    Extract named entities using spaCy NER.

    Args:
        text: Input text to analyze
        confidence_threshold: Minimum confidence for entity inclusion (default 0.6)
        preloaded_models: Optional dict with preloaded spaCy model

    Returns:
        List of Entity objects with text, label, confidence

    Performance: ~10ms for 500-word text

    Supported entity types:
    - PERSON: People, including fictional
    - ORG: Companies, agencies, institutions
    - GPE: Countries, cities, states (geopolitical entities)
    - DATE: Absolute or relative dates
    - TIME: Times smaller than a day

    Example:
        >>> entities = _extract_entities("Dinner with mom at Olive Garden")
        >>> [(e.text, e.label) for e in entities]
        [("mom", "PERSON"), ("Olive Garden", "ORG")]
    """
    if not _ensure_spacy_loaded(preloaded_models):
        logger.warning("spaCy not available, returning empty entity list")
        return []

    if not text or not text.strip():
        return []

    # Run NER tagging (main computation: 10ms for 500 words)
    doc = _nlp(text)  # Type: spacy.tokens.Doc

    # Extract entities with confidence filtering
    entities: list[Entity] = []
    for ent in doc.ents:
        # spaCy doesn't provide confidence scores by default, estimate from context
        confidence = _estimate_entity_confidence(ent, doc)

        if confidence < confidence_threshold:
            continue

        # Filter to relevant entity types
        if ent.label_ in {"PERSON", "ORG", "GPE", "DATE", "TIME"}:
            entities.append(
                Entity(
                    text=ent.text,
                    label=ent.label_,
                    confidence=confidence,
                )
            )

    return entities


def _estimate_entity_confidence(ent, doc) -> float:
    """
    Estimate entity confidence based on context signals.

    spaCy en_core_web_sm doesn't provide direct confidence scores.
    Use heuristics:
    - Entity length (longer = more confident)
    - Capitalization consistency
    - Position in sentence (mid-sentence PERSON = higher confidence)

    Returns: Float 0.0-1.0 (approximate confidence)
    """
    confidence = 0.7  # Base confidence for spaCy small model

    # Boost for multi-token entities (more context)
    token_count = len(ent.text.split())
    if token_count > 1:
        confidence += 0.1

    # Boost for consistent capitalization
    if ent.text[0].isupper():
        confidence += 0.05

    # Penalize very short entities (likely false positives)
    if len(ent.text) <= 2:
        confidence -= 0.15

    return min(1.0, max(0.0, confidence))


def _resolve_entities(
    entities: list[Entity],
    participants: list[str] | None,
    place: str | None,
) -> list[str]:
    """
    Resolve entities to canonical IDs using context.

    Args:
        entities: Extracted entities from spaCy
        participants: List of participant IDs from envelope (e.g., ["person_mom"])
        place: Place ID from envelope (e.g., "Olive_Garden_Market_St")

    Returns:
        List of canonical entity IDs

    Resolution rules:
    - PERSON: Match against participants (fuzzy match)
    - GPE: Match against place if available
    - ORG: Store as-is with "org_" prefix
    - DATE/TIME: Parse to ISO format

    Example:
        >>> entities = [Entity("mom", "PERSON", 0.8)]
        >>> participants = ["person_mom"]
        >>> _resolve_entities(entities, participants, None)
        ["person_mom"]
    """
    resolved: list[str] = []

    for entity in entities:
        canonical_id = None

        if entity.label == "PERSON":
            canonical_id = _resolve_person(entity.text, participants)
        elif entity.label == "GPE":
            canonical_id = _resolve_place(entity.text, place)
        elif entity.label == "ORG":
            canonical_id = f"org_{_normalize_text(entity.text)}"
        elif entity.label in {"DATE", "TIME"}:
            canonical_id = _resolve_temporal(entity.text, entity.label)

        if canonical_id:
            resolved.append(canonical_id)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for entity_id in resolved:
        if entity_id not in seen:
            seen.add(entity_id)
            deduped.append(entity_id)

    return deduped


def _resolve_person(text: str, participants: list[str] | None) -> str | None:
    """
    Resolve person name to canonical ID.

    Matches against participants list using fuzzy matching.
    Handles variants: "mom", "Mom", "mother", "my mom"

    Returns: person_<canonical> or None
    """
    if not participants:
        # No context, use normalized form
        return f"person_{_normalize_text(text)}"

    text_lower = text.lower().strip()

    # Direct match against participant IDs
    for participant in participants:
        if participant.startswith("person_"):
            name = participant.replace("person_", "")
            if name.lower() in text_lower or text_lower in name.lower():
                return participant

    # No match, create new ID
    return f"person_{_normalize_text(text)}"


def _resolve_place(text: str, place: str | None) -> str | None:
    """
    Resolve place name to canonical ID.

    Matches against envelope.place if available.

    Returns: place_<canonical> or GPE text from envelope
    """
    if place and place.strip():
        # Use envelope place if it contains the entity text
        place_lower = place.lower()
        text_lower = text.lower()
        if text_lower in place_lower or place_lower in text_lower:
            return place  # Return envelope place ID

    # No context, use normalized form
    return f"place_{_normalize_text(text)}"


def _resolve_temporal(text: str, label: str) -> str | None:
    """
    Resolve date/time to ISO format.

    For now, store as-is with prefix.
    Future: Parse using dateutil for structured temporal IDs.

    Returns: date_<text> or time_<text>
    """
    prefix = "date" if label == "DATE" else "time"
    return f"{prefix}_{_normalize_text(text)}"


def _normalize_text(text: str) -> str:
    """
    Normalize text for use in canonical IDs.

    Rules:
    - Lowercase
    - Replace spaces with underscores
    - Remove special characters
    - Trim to 50 chars

    Example: "Olive Garden" → "olive_garden"
    """
    normalized = text.lower().strip()
    normalized = "".join(c if c.isalnum() or c.isspace() else "" for c in normalized)
    normalized = "_".join(normalized.split())
    return normalized[:50]


# ============================================================================
# Knowledge Graph Triple Generation (Template-Based)
# ============================================================================


@dataclass
class KGTriple:
    """Knowledge graph triple (subject, predicate, object)."""

    subject: str
    predicate: str
    object: str
    confidence: float = 1.0


def _generate_kg_triples(
    entities: list[str],
    envelope: dict[str, Any],
    confidence_threshold: float = 0.6,
    max_triples: int = 10,
) -> list[list[str]]:
    """
    Generate knowledge graph triples using template-based rules.

    Args:
        entities: Resolved entity IDs
        envelope: Full envelope with context (participants, place, activity_type)
        confidence_threshold: Minimum confidence for triple inclusion
        max_triples: Maximum number of triples to generate

    Returns:
        List of triples [[subject, predicate, object], ...]

    Performance: ~5ms per event

    Template Rules:
    1. Activity templates: (actor, activity_predicate, place)
    2. Participant templates: (actor, "interacted_with", participant)
    3. Location templates: (event, "occurred_at", place)
    4. Entity mention templates: (event, "mentions", entity)

    Example:
        envelope = {
            "actor_id": "person_dad",
            "participants": ["person_mom"],
            "location_name": "Olive_Garden_Market_St",
            "activity_type": "MEAL"
        }
        entities = ["person_mom", "Olive_Garden_Market_St"]

        Output: [
            ["person_dad", "had_meal_with", "person_mom"],
            ["person_dad", "had_meal_at", "Olive_Garden_Market_St"],
            ["event", "occurred_at", "Olive_Garden_Market_St"]
        ]
    """
    triples: list[KGTriple] = []

    # Extract context
    actor_id = envelope.get("actor_id", "unknown_actor")
    participants = envelope.get("participants", [])
    place = envelope.get("location_name") or envelope.get("place")
    activity_type = envelope.get("activity_type")
    event_id = envelope.get("event_id", "unknown_event")

    # Rule 1: Activity-based triples (actor → activity → place/participant)
    if activity_type and place:
        predicate = _activity_type_to_predicate(activity_type, "place")
        triples.append(KGTriple(actor_id, predicate, place, confidence=0.9))

    # Rule 2: Participant interaction triples
    for participant in participants:
        if participant != actor_id:
            predicate = _activity_type_to_predicate(activity_type, "person")
            triples.append(KGTriple(actor_id, predicate, participant, confidence=0.85))

    # Rule 3: Location triples (event → occurred_at → place)
    if place:
        triples.append(KGTriple(event_id, "occurred_at", place, confidence=0.95))

    # Rule 4: Entity mention triples (event → mentions → entity)
    for entity in entities:
        if entity not in {actor_id, place} and entity not in participants:
            triples.append(KGTriple(event_id, "mentions", entity, confidence=0.7))

    # Filter by confidence and deduplicate
    filtered = [t for t in triples if t.confidence >= confidence_threshold]

    # Deduplicate (same subject-predicate-object)
    seen = set()
    deduped = []
    for triple in filtered:
        key = (triple.subject, triple.predicate, triple.object)
        if key not in seen:
            seen.add(key)
            deduped.append(triple)

    # Limit to max_triples
    deduped = deduped[:max_triples]

    # Convert to list of lists (for JSON serialization)
    return [[t.subject, t.predicate, t.object] for t in deduped]


def _activity_type_to_predicate(activity_type: str | None, object_type: str) -> str:
    """
    Map activity type to KG predicate.

    Args:
        activity_type: Activity from envelope (MEAL, SOCIAL_EVENT, TRANSIT, etc.)
        object_type: "place" or "person"

    Returns:
        Predicate string (e.g., "had_meal_at", "attended_event_with")
    """
    if not activity_type:
        return "interacted_at" if object_type == "place" else "interacted_with"

    # Activity-specific predicates
    activity_map = {
        "MEAL": ("had_meal_at", "had_meal_with"),
        "SOCIAL_EVENT": ("attended_event_at", "attended_event_with"),
        "TRANSIT": ("traveled_to", "traveled_with"),
        "WORK": ("worked_at", "worked_with"),
        "EXERCISE": ("exercised_at", "exercised_with"),
        "ENTERTAINMENT": ("visited", "enjoyed_with"),
        "SHOPPING": ("shopped_at", "shopped_with"),
    }

    predicates = activity_map.get(activity_type, ("interacted_at", "interacted_with"))
    return predicates[0] if object_type == "place" else predicates[1]


# ============================================================================
# Main Entry Point (Phase 2 Declarative Module)
# ============================================================================


async def run(
    message: Any,  # Mock message object with .payload attribute
    context: Any,  # Mock context object with .trace_id attribute
    **config: Any,
) -> dict[str, Any]:
    """
    M02: hippocampus.semantic_project - CA1 Semantic Projection

    Phase 2 declarative module entry point.

    Args:
        message: Bus message with envelope payload
        context: Pipeline execution context (trace_id, correlation_id, etc.)
        **config: Module configuration from contract

    Returns:
        Dict with:
            - embedding_id: UUID for P08 vector generation
            - entities_json: JSON array of resolved entity IDs
            - kg_triples_json: JSON array of KG triples
            - semantic_projected_at_utc: ISO timestamp

    Raises:
        ValueError: If envelope is malformed or missing required fields
        RuntimeError: If entity extraction or KG generation fails

    Performance: ≤20ms P95, ≤35ms P99

    Side Effects:
        - Prepares payload for st_embedding_queue (via M14 outbox.enqueue_embedding)

    Contract: k0/contracts/modules/hippocampus.semantic_project.v1.yaml
    """
    # Get trace_id from message, envelope should be passed as kwarg by pipeline_runner
    trace_id = message.trace_id or "unknown"

    # Try to get envelope from kwargs (passed by pipeline_runner)
    envelope = config.get("envelope")
    if envelope is None:
        logger.warning(f"envelope not in config, config keys: {list(config.keys())}")
        # Fallback: decode from message.payload
        try:
            envelope = json.loads(message.payload.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Failed to decode envelope from message payload: {e}")

    # Extract configuration
    confidence_threshold = config.get("kg_confidence_threshold", 0.6)
    max_triples = config.get("max_triples_per_event", 10)
    entity_confidence = config.get("entity_confidence_threshold", 0.6)

    # Get preloaded models from context (if available from kernel startup)
    preloaded_models = getattr(context, "preloaded_models", None)

    # Validate input message
    if not message.payload:
        raise ValueError("Message payload is empty")

    # envelope should already be set from kwargs (passed by pipeline_runner)
    # If not, it was decoded earlier in this function
    if not isinstance(envelope, dict):
        raise ValueError(f"Envelope must be dict, got {type(envelope)}")

    # Extract required fields (cognitive_trace_id is primary identifier per P02 dossier)
    event_id = envelope.get("cognitive_trace_id") or envelope.get("event_id")
    if not event_id:
        raise ValueError(
            f"Envelope missing cognitive_trace_id or event_id. Keys: {list(envelope.keys())}"
        )

    # Extract text for entity extraction
    text = _extract_text_for_entities(envelope)
    if not text or not text.strip():
        logger.warning(
            "Empty text for entity extraction, returning empty results",
            extra={"trace_id": trace_id, "event_id": event_id},
        )
        # Return enriched envelope with minimal output for empty text
        return {
            **envelope,
            "embedding_id": str(uuid.uuid4()),
            "entities_json": "[]",
            "kg_triples_json": "[]",
            "semantic_projected_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }

    # Phase 1: Entity extraction (spaCy NER) - with preloaded models
    entities = _extract_entities(
        text,
        confidence_threshold=entity_confidence,
        preloaded_models=preloaded_models,
    )

    # Phase 2: Entity resolution (canonical IDs)
    participants = envelope.get("participants", [])
    place = envelope.get("location_name") or envelope.get("place")
    resolved_entities = _resolve_entities(entities, participants, place)

    # Phase 3: KG triple generation (template-based)
    kg_triples = _generate_kg_triples(
        resolved_entities,
        envelope,
        confidence_threshold=confidence_threshold,
        max_triples=max_triples,
    )

    # Phase 4: Allocate embedding_id (UUID for P08 processing)
    embedding_id = str(uuid.uuid4())

    # Serialize outputs
    entities_json = json.dumps(resolved_entities)
    kg_triples_json = json.dumps(kg_triples)

    logger.debug(
        "M02 semantic_project complete",
        extra={
            "trace_id": trace_id,
            "event_id": event_id,
            "embedding_id": embedding_id,
            "entity_count": len(resolved_entities),
            "triple_count": len(kg_triples),
        },
    )

    # Return enriched envelope (preserve all original fields + add semantic projection)
    return {
        **envelope,
        "embedding_id": embedding_id,
        "entities_json": entities_json,
        "kg_triples_json": kg_triples_json,
        "semantic_projected_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def _extract_text_for_entities(envelope: dict[str, Any]) -> str:
    """
    Extract all relevant text from envelope for entity extraction.

    Combines:
    - body.text (primary content)
    - participants (as comma-separated names)
    - location_name (place context)
    - activity_type (activity context)

    Example:
        envelope = {
            "body": {"text": "Dinner with mom"},
            "participants": ["person_mom"],
            "location_name": "Olive_Garden_Market_St",
            "activity_type": "MEAL"
        }

        Output: "Dinner with mom person_mom Olive_Garden_Market_St MEAL"
    """
    parts = []

    # Primary text content
    body = envelope.get("body", {})
    if isinstance(body, dict) and "text" in body:
        text = body["text"]
        if text:
            parts.append(str(text))
    elif "text" in envelope:
        text = envelope["text"]
        if text:
            parts.append(str(text))

    # Participant context
    participants = envelope.get("participants", [])
    if participants:
        parts.extend(str(p) for p in participants)

    # Place context
    place = envelope.get("location_name") or envelope.get("place")
    if place:
        parts.append(str(place))

    # Activity context
    activity = envelope.get("activity_type")
    if activity:
        parts.append(str(activity))

    return " ".join(parts)
