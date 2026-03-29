"""
poc.k1_poc.fsm.ultrabert_phase1 -- UltraBERT-backed Phase 1 pipeline.

M10 E10.1: Replaces StubPhase1Pipeline with real UltraBERT classification.
Maps 12-head output to Phase1Result, computes multi-factor complexity tier,
applies confidence thresholding, and handles graceful degradation.

The pipeline depends on the ``UltraBERTAdapter`` protocol (not a concrete
class), enabling ``StubUltraBERTAdapter`` injection for GPU-less tests.
"""

from __future__ import annotations

import logging
from typing import Any

from poc.k1_poc.config.loader import Phase1Config, get_config
from poc.k1_poc.fsm.phase1 import Phase1Result, StubPhase1Pipeline
from poc.k1_poc.fsm.ultrabert_adapter import (
    HIGH_AROUSAL_EMOTIONS,
    LOW_AROUSAL_EMOTIONS,
    SENTIMENT_TO_VALENCE,
    UltraBERTAdapter,
)

logger = logging.getLogger(__name__)


class UltraBERTPhase1Pipeline:
    """Real Phase 1 pipeline using UltraBERT via adapter.

    Implements the ``Phase1Pipeline`` protocol. On each ``classify()``
    call it:
      1. Calls ``adapter.analyze(text)`` (single forward pass, ~20ms).
      2. Maps the 12-head dict to a ``Phase1Result``.
      3. Computes multi-factor complexity tier.
      4. Falls back to ``StubPhase1Pipeline`` if the adapter returns None.

    The last embedding produced is retained for downstream consumers
    (e.g. ``recall_memory`` semantic search).
    """

    def __init__(
        self,
        adapter: UltraBERTAdapter,
        fallback: StubPhase1Pipeline | None = None,
        *,
        config: Phase1Config | None = None,
    ) -> None:
        self._adapter = adapter
        self._fallback = fallback or StubPhase1Pipeline()
        self._cfg = config or get_config().phase1
        self._call_count: int = 0
        self._degraded_count: int = 0
        self._last_embedding: list[float] | None = None
        logger.info(
            "UltraBERTPhase1Pipeline initialized (adapter_available=%s)",
            adapter.is_available(),
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def call_count(self) -> int:
        """Total classify() invocations."""
        return self._call_count

    @property
    def degraded_count(self) -> int:
        """Number of classify() calls that fell back to stub."""
        return self._degraded_count

    @property
    def last_embedding(self) -> list[float] | None:
        """768-dim embedding from the last successful UltraBERT call."""
        return self._last_embedding

    # ------------------------------------------------------------------
    # Phase1Pipeline protocol
    # ------------------------------------------------------------------

    def classify(self, text: str) -> Phase1Result:
        """Classify user input via UltraBERT (12 heads, single pass).

        Falls back to ``StubPhase1Pipeline`` when the adapter is
        unavailable or returns ``None``.
        """
        self._call_count += 1

        try:
            analysis = self._adapter.analyze(text)
        except Exception as exc:
            logger.warning(
                "UltraBERTPhase1Pipeline: adapter.analyze raised %s, degrading",
                exc,
            )
            analysis = None

        if analysis is None:
            self._degraded_count += 1
            result = self._fallback.classify(text)
            # Tag degradation in metadata via a wrapper
            result._degraded = True  # type: ignore[attr-defined]
            logger.warning(
                "UltraBERTPhase1Pipeline: degraded to stub (call #%d)",
                self._call_count,
            )
            return result

        return self._map_to_phase1_result(analysis)

    # ------------------------------------------------------------------
    # Mapping: adapter dict -> Phase1Result
    # ------------------------------------------------------------------

    def _map_to_phase1_result(self, analysis: dict[str, Any]) -> Phase1Result:
        """Convert the 12-head output dict to a ``Phase1Result``."""

        # Intent (primary = argmax, multi-label filtered by threshold)
        primary_intent = analysis.get("intent", "general")
        all_intents = self._filter_intents(analysis)

        # Domain (ingress head)
        primary_domain = analysis.get("ingress", "general")

        # Safety band
        safety_band = analysis.get("safety", "GREEN")

        # Emotion
        emotions: list[str] = analysis.get("emotions", [])
        primary_emotion = emotions[0] if emotions else "neutral"
        emotion_scores: dict[str, float] = analysis.get("emotion_scores", {})
        emotion_confidence = max(emotion_scores.values()) if emotion_scores else 0.5

        # Valence from sentiment
        sentiment = analysis.get("sentiment", "neutral")
        valence = SENTIMENT_TO_VALENCE.get(sentiment, 0.5)

        # Arousal heuristic
        arousal = self._infer_arousal(primary_emotion, emotion_scores)

        # Entities: merge family NER + general NER
        entities = self._merge_entities(
            analysis.get("entities", []),
            analysis.get("general_entities", []),
        )

        # Salience map (entity_id -> score)
        salience_map = {e.get("entity_id", f"ent-{i}"): 0.8 for i, e in enumerate(entities)}

        # Temporal expressions and relations (E10.5)
        temporal_expressions = analysis.get("temporal", [])
        relations = analysis.get("relations", [])

        # Embedding (retained for downstream, not in Phase1Result fields)
        embedding = analysis.get("embedding")
        self._last_embedding = embedding if isinstance(embedding, list) else None

        # Complexity tier (multi-factor)
        complexity_tier = self._compute_complexity(
            all_intents=all_intents,
            active_domains=[primary_domain],
            primary_intent=primary_intent,
            entities=entities,
            safety_band=safety_band,
        )

        return Phase1Result(
            intents=all_intents,
            entities=entities,
            salience_map=salience_map,
            primary_emotion=primary_emotion,
            emotion_confidence=emotion_confidence,
            valence=valence,
            arousal=arousal,
            intent_classification=primary_intent,
            domain_context=primary_domain,
            safety_band=safety_band,
            complexity_tier=complexity_tier,
            temporal_expressions=temporal_expressions,
            relations=relations,
        )

    # ------------------------------------------------------------------
    # Intent thresholding (E10.1.3)
    # ------------------------------------------------------------------

    def _filter_intents(self, analysis: dict[str, Any]) -> list[str]:
        """Return intents above the confidence threshold.

        Primary intent (argmax) is always included. Additional intents
        are included only if their score exceeds the threshold configured
        in ``phase1.intent_confidence_threshold``.
        """
        primary = analysis.get("intent", "general")
        # UltraBERT intent head returns a single primary intent.
        # Multi-label support: if the analysis dict contains an
        # ``intent_scores`` key, filter by threshold.
        intent_scores: dict[str, float] = analysis.get("intent_scores", {})
        if not intent_scores:
            return [primary]

        threshold = self._cfg.intent_confidence_threshold
        above = [k for k, v in intent_scores.items() if v >= threshold]
        # Ensure primary is always present
        if primary not in above:
            above.insert(0, primary)
        return above

    # ------------------------------------------------------------------
    # Arousal heuristic
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_arousal(primary_emotion: str, emotion_scores: dict[str, float]) -> float:
        """Heuristic arousal from emotion label and scores.

        High-arousal emotions (anger, excitement, fear, surprise) -> >= 0.7.
        Low-arousal emotions (sadness, calm, boredom, contentment) -> <= 0.3.
        Otherwise midpoint (0.5).
        """
        if primary_emotion in HIGH_AROUSAL_EMOTIONS:
            # Scale by confidence: 0.7 + 0.3 * score
            score = emotion_scores.get(primary_emotion, 0.5)
            return min(0.7 + 0.3 * score, 1.0)
        if primary_emotion in LOW_AROUSAL_EMOTIONS:
            score = emotion_scores.get(primary_emotion, 0.5)
            return max(0.3 - 0.2 * score, 0.0)
        return 0.5

    # ------------------------------------------------------------------
    # Entity merging
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_entities(
        family_entities: list[dict[str, Any]],
        general_entities: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge family NER and general NER, de-duplicate by span.

        Each entity dict has ``{text, label, start, end}``.
        Family entities take priority on overlap.
        """
        seen_spans: set[tuple[int, int]] = set()
        merged: list[dict[str, Any]] = []

        for entity in family_entities:
            span = (entity.get("start", -1), entity.get("end", -1))
            if span not in seen_spans:
                seen_spans.add(span)
                merged.append(entity)

        for entity in general_entities:
            span = (entity.get("start", -1), entity.get("end", -1))
            if span not in seen_spans:
                seen_spans.add(span)
                merged.append(entity)

        return merged

    # ------------------------------------------------------------------
    # Multi-factor complexity classifier (E10.1.2)
    # ------------------------------------------------------------------

    def _compute_complexity(
        self,
        all_intents: list[str],
        active_domains: list[str],
        primary_intent: str,
        entities: list[dict[str, Any]],
        safety_band: str,
    ) -> str:
        """Multi-factor complexity scoring.

        Factors:
          1. Multi-Intent:  len(intents) > 1  -> +1
          2. Cross-Domain:  len(domains) > 1  -> +1
          3. Temporal ambiguity: primary_intent in temporal set AND
             entities contain DATE_REL / TIME_REL -> +1
          4. Safety override: RED/CRISIS -> force LOW

        Score thresholds come from config ``phase1.complexity_thresholds``:
          low_max   (default 0): score <= low_max  -> LOW
          medium_max(default 2): score <= medium_max -> MEDIUM
          else                                      -> HIGH
        """
        # Safety override first
        if safety_band in ("RED", "CRISIS"):
            return "LOW"

        score = 0

        # Factor 1: Multi-intent
        if len(all_intents) > 1:
            score += 1

        # Factor 2: Cross-domain
        if len(active_domains) > 1:
            score += 1

        # Factor 3: Temporal ambiguity
        temporal_intents = {"set_reminder", "seek_advice", "reflect", "scheduling"}
        temporal_labels = {"DATE_REL", "TIME_REL", "TEMPORAL"}
        has_temporal = any(e.get("label") in temporal_labels for e in entities)
        if primary_intent in temporal_intents and has_temporal:
            score += 1

        thresholds = self._cfg.complexity_thresholds
        low_max = thresholds.get("low_max", 0)
        medium_max = thresholds.get("medium_max", 2)

        if score <= low_max:
            return "LOW"
        if score <= medium_max:
            return "MEDIUM"
        return "HIGH"
