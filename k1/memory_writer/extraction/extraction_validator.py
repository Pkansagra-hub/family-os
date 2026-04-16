"""
ExtractionValidator -- Post-LLM deterministic validation.

Takes raw LLM output (RawExtraction) and produces validated MemoryAtom
objects ready for envelope building. No LLM cost. No I/O.

Validation pipeline (5 checks, in order):
  1. Text length (MW-04): truncate to config.max_text_words
  2. Required fields: drop if text or topics empty
  3. Participant resolution: PersonResolver natural names → person_ids
  4. Confidence threshold: drop below config.confidence_floor
  5. temporal_links (MW-12): cap at 5, drop invalid link_types

After all checks: cap at config.max_atoms_per_turn (MW-05).
"""

from __future__ import annotations

import logging
from typing import List

from k1.memory_writer.config import MWConfig
from k1.memory_writer.context.person_resolver import PersonResolver
from k1.memory_writer.extraction.raw_extraction import RawExtraction
from k1.memory_writer.types import (
    ActivityType,
    Affect,
    ArcPosition,
    ElaborationDepth,
    ExtractionContext,
    IntentType,
    LocationType,
    MemoryAtom,
    Narrative,
    NoveltyLevel,
    SentimentLabel,
    SocialContext,
    SocialIntimacy,
    SourceType,
    TemporalLink,
    TemporalLinkType,
    TemporalOrientation,
)

log = logging.getLogger(__name__)


class ExtractionValidator:
    """Post-LLM deterministic validation. Produces validated MemoryAtom list.

    No LLM cost. No I/O. Pure validation + field normalization.
    PersonResolver called here (not in extraction stage).
    """

    __slots__ = ("_person_resolver", "_config")

    def __init__(
        self,
        person_resolver: PersonResolver,
        config: MWConfig,
    ) -> None:
        self._person_resolver = person_resolver
        self._config = config

    def validate(
        self,
        extractions: List[RawExtraction],
        context: ExtractionContext,
    ) -> List[MemoryAtom]:
        """Validate and convert RawExtractions → MemoryAtom list.

        Args:
            extractions: Mutable RawExtractions from WriterAgent.
            context: ExtractionContext for PersonResolver and metadata.

        Returns:
            List of validated, frozen MemoryAtom objects.
            May be empty if all extractions fail validation.
        """
        validated: List[MemoryAtom] = []

        for ext in extractions:
            # Check 1: Text length (MW-04) — truncate, don't drop
            if len(ext.text.split()) > self._config.max_text_words:
                words = ext.text.split()[: self._config.max_text_words]
                ext.text = " ".join(words)
                log.warning(
                    "MW: truncated extraction to max words",
                    extra={
                        "trace_id": ext.trace_id,
                        "max_words": self._config.max_text_words,
                    },
                )

            # Check 2: Required fields — drop if missing
            if not ext.text or not ext.text.strip():
                log.warning(
                    "MW: dropped extraction, empty text",
                    extra={"trace_id": ext.trace_id},
                )
                continue
            if not ext.topics:
                log.warning(
                    "MW: dropped extraction, no topics",
                    extra={"trace_id": ext.trace_id},
                )
                continue

            # Check 3: Participant resolution (PersonResolver from Phase 1)
            resolved_participants: List[str] = []
            if ext.participants:
                resolutions = self._person_resolver.resolve_all(ext.participants, context)
                resolved_participants = [r.person_id for r in resolutions]

            # Check 4: Confidence threshold
            if ext.confidence < self._config.confidence_floor:
                log.info(
                    "MW: dropped low-confidence extraction",
                    extra={
                        "trace_id": ext.trace_id,
                        "confidence": ext.confidence,
                        "floor": self._config.confidence_floor,
                    },
                )
                continue

            # Check 5: temporal_links validation (MW-12)
            validated_links = self._validate_temporal_links(ext.temporal_links)

            # Convert to frozen MemoryAtom
            atom = self._build_atom(ext, resolved_participants, validated_links, context)
            validated.append(atom)

        # MW-05: cap at max atoms per turn
        if len(validated) > self._config.max_atoms_per_turn:
            log.warning(
                "MW: capping atoms to max per turn",
                extra={
                    "count": len(validated),
                    "max": self._config.max_atoms_per_turn,
                },
            )
            validated = validated[: self._config.max_atoms_per_turn]

        return validated

    def _validate_temporal_links(
        self,
        raw_links: List[dict],
    ) -> tuple:
        """Validate and convert temporal_links. MW-12: max 5, valid types."""
        valid_types = {t.value for t in TemporalLinkType}
        links: List[TemporalLink] = []
        for link in raw_links[: self._config.max_temporal_links_per_atom]:
            link_type = link.get("link_type", "CONCURRENT")
            if link_type not in valid_types:
                continue  # drop invalid link_type
            links.append(
                TemporalLink(
                    mentioned_time=str(link.get("mentioned_time", "")),
                    resolved_epoch_ms=int(link.get("resolved_epoch_ms", 0)),
                    uncertainty_window_ms=int(link.get("uncertainty_window_ms", 0)),
                    link_type=link_type,
                    confidence=float(link.get("confidence", 1.0)),
                )
            )
        return tuple(links)

    def _build_atom(
        self,
        ext: RawExtraction,
        resolved_participants: List[str],
        validated_links: tuple,
        context: ExtractionContext,
    ) -> MemoryAtom:
        """Convert validated RawExtraction → frozen MemoryAtom."""
        # Normalize enums with safe fallbacks
        sentiment = _safe_enum(SentimentLabel, ext.sentiment_label, SentimentLabel.NEUTRAL)
        source_type = _safe_enum(SourceType, ext.source_type, SourceType.USER_STATED)
        novelty = _safe_enum(NoveltyLevel, ext.novelty, NoveltyLevel.EXPECTED)
        elaboration = _safe_enum(ElaborationDepth, ext.elaboration_depth, ElaborationDepth.MENTION)
        temporal_orient = _safe_enum(
            TemporalOrientation, ext.temporal_orientation, TemporalOrientation.PAST
        )
        activity = _safe_enum(ActivityType, ext.activity_type, None) if ext.activity_type else None
        location_type = (
            _safe_enum(LocationType, ext.location_type, None) if ext.location_type else None
        )
        social_ctx = (
            _safe_enum(SocialContext, ext.social_context, None) if ext.social_context else None
        )
        social_int = (
            _safe_enum(SocialIntimacy, ext.social_intimacy, None) if ext.social_intimacy else None
        )
        intent = _safe_enum(IntentType, ext.intent_type, None) if ext.intent_type else None

        # Build Affect from dict
        affect = Affect(0.0, 0.0, 0.5)
        if isinstance(ext.affect, dict):
            affect = Affect(
                valence=float(ext.affect.get("valence", 0.0)),
                arousal=float(ext.affect.get("arousal", 0.0)),
                dominance=float(ext.affect.get("dominance", 0.5)),
            )

        # Build Narrative from dict
        narrative = None
        if isinstance(ext.narrative, dict):
            arc_pos = _safe_enum(
                ArcPosition,
                ext.narrative.get("arc_position"),
                ArcPosition.EXPOSITION,
            )
            narrative = Narrative(
                thread_id=str(ext.narrative.get("thread_id", "")),
                arc_position=arc_pos,
                is_goal_event=bool(ext.narrative.get("is_goal_event", False)),
            )

        return MemoryAtom(
            text=ext.text,
            topics=ext.topics,
            categories=ext.categories,
            activity_type=activity,
            participants=resolved_participants,
            location_name=ext.location_name,
            location_type=location_type,
            sentiment_label=sentiment,
            emotion_tags=ext.emotion_tags,
            affect=affect,
            narrative=narrative,
            temporal_links=validated_links,
            temporal_orientation=temporal_orient,
            source_type=source_type,
            novelty=novelty,
            elaboration_depth=elaboration,
            identity_domains=ext.identity_domains,
            intent_type=intent,
            social_context=social_ctx,
            social_intimacy=social_int,
            confidence=ext.confidence,
            session_id=ext.session_id,
            conversation_turn=ext.conversation_turn,
            extraction_sequence=ext.extraction_sequence,
            language="en",
            conversation_anchor_ms=context.turn_timestamp_ms,
            # v2.2 correction signals — pass through unchanged
            correction_signal=ext.correction_signal,
            contradiction_signal=ext.contradiction_signal,
            supersedes_concept=ext.supersedes_concept,
            correction_source=ext.correction_source,
            session_context_id=ext.session_id,
        )


def _safe_enum(enum_cls, value, default):
    """Safely convert a string to an enum value. Returns default on failure."""
    if value is None:
        return default
    try:
        return enum_cls(value)
    except (ValueError, KeyError):
        return default
