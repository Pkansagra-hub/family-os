"""
MemoryWriterAgent -- LLM extraction agent (Stage 3).

The only LLM-consuming component in the MW pipeline.
Session-bound: spawned once per session, reused across turns.

Invariants:
  MW-06: budget_tokens always <= config.llm_token_budget (2000)
  MW-10: trace_id propagated to every Model Hub call
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from k1.memory_writer.config import MWConfig
from k1.memory_writer.extraction.raw_extraction import PromptLoader, RawExtraction
from k1.memory_writer.invariants import assert_mw06_token_budget
from k1.memory_writer.ports.model_hub_port import IModelHubPort
from k1.memory_writer.types import ChatResponse, ExtractionContext

log = logging.getLogger(__name__)


class MemoryWriterAgent:
    """LLM extraction agent -- the only LLM-consuming component in MW.

    Session-bound: spawned once per session, reused across turns.
    Pool-reused: goes IDLE between turns, reactivated from AgentPool.

    Invariants:
      MW-06: budget_tokens always <= config.llm_token_budget (2000)
      MW-10: trace_id propagated to every Model Hub call
    """

    __slots__ = ("_model_hub", "_config", "_system_prompt")

    def __init__(
        self,
        model_hub: IModelHubPort,
        config: MWConfig,
        prompt_loader: PromptLoader,
    ) -> None:
        self._model_hub = model_hub
        self._config = config
        self._system_prompt: str = prompt_loader.load("memory_writer_persona")

    async def extract(
        self,
        context: ExtractionContext,
        trace_id: str,
    ) -> List[RawExtraction]:
        """Extract 0-6 memory atoms from ExtractionContext via LLM.

        Args:
            context: Full SS snapshot assembled by ContextBuilder.
            trace_id: cognitive_trace_id from TurnCompletePayload (MW-10).

        Returns:
            List of RawExtraction objects (not yet validated).
            Empty list if LLM returns no extractions or errors.

        Raises:
            Nothing -- errors are caught, logged, and return empty list.
            Pipeline continues (best-effort extraction per Architecture §24).
        """
        # MW-06: enforce budget before call
        assert_mw06_token_budget(self._config.llm_token_budget, self._config)

        # Serialize ExtractionContext -> user prompt
        user_prompt = self._build_user_prompt(context)

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response: ChatResponse = await self._model_hub.chat(
                messages=messages,
                budget_tokens=self._config.llm_token_budget,
                model_hint=self._config.model_hint,
            )
        except Exception as exc:
            log.warning(
                "MW: LLM extraction failed",
                extra={
                    "trace_id": trace_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            return []

        return self._parse_response(response, context, trace_id)

    def _build_user_prompt(self, context: ExtractionContext) -> str:
        """Serialize ExtractionContext into the user prompt template.

        Token budget: ~350 tokens for context, ~200 for turn payload.
        Compresses recent_turns to (role, text[:100], turn_number) tuples.
        Includes active_topics, current_affect, privacy band hint.
        """
        # Recent turns -- compressed to fit budget
        turns_text = ""
        for t in context.recent_turns[-5:]:
            turns_text += f"  Turn {t.turn_number} ({t.role}): {t.text[:100]}\n"

        # Active entities from beliefs_active
        entities_text = (
            ", ".join(
                f"{name} ({info.get('type', 'UNKNOWN')})"
                for name, info in context.active_persons.items()
            )
            if context.active_persons
            else "none"
        )

        # Current emotion
        emotion_text = "unknown"
        if context.current_affect:
            emotion_text = (
                f"valence={context.current_affect.valence:.1f}, "
                f"arousal={context.current_affect.arousal:.1f}"
            )

        # Active topics
        topics_text = ", ".join(context.active_topics[:5]) if context.active_topics else "none"

        # Privacy band from control context
        band = (
            context.control_context.get("safety_band", "GREEN")
            if context.control_context
            else "GREEN"
        )

        current = context.current_turn

        return (
            f"CONTEXT:\n"
            f"  Recent turns:\n{turns_text}"
            f"  Known entities: {entities_text}\n"
            f"  Current emotion: {emotion_text}\n"
            f"  Active topics: {topics_text}\n"
            f"  Privacy band: {band}\n\n"
            f"CURRENT TURN:\n"
            f"  User: {current.text}\n"
            f"  Turn #: {current.turn_number}\n\n"
            f"Extract all memorable content from this turn — facts, opinions, feelings, third-party news. Return as JSON array."
        )

    def _parse_response(
        self,
        response: ChatResponse,
        context: ExtractionContext,
        trace_id: str,
    ) -> List[RawExtraction]:
        """Parse LLM JSON output into RawExtraction list.

        Handles:
          - Valid JSON array -> list of RawExtraction
          - Empty array [] -> empty list
          - Malformed JSON -> log warning, return empty list
          - Individual item parse failure -> skip item, keep valid ones
        """
        content = response.content.strip()
        if not content:
            return []

        # Strip markdown code fences if LLM wraps in ```json ... ```
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(
                line for line in lines if not line.strip().startswith("```")
            ).strip()

        try:
            raw_list = json.loads(content)
        except json.JSONDecodeError as exc:
            log.warning(
                "MW: LLM returned malformed JSON",
                extra={
                    "trace_id": trace_id,
                    "content_preview": content[:200],
                    "error": str(exc),
                },
            )
            return []

        if not isinstance(raw_list, list):
            log.warning(
                "MW: LLM returned non-array JSON",
                extra={
                    "trace_id": trace_id,
                    "json_type": type(raw_list).__name__,
                },
            )
            return []

        extractions: List[RawExtraction] = []
        for i, item in enumerate(raw_list[:6]):  # hard cap at 6 (MW-05)
            if not isinstance(item, dict):
                continue
            try:
                ext = RawExtraction(
                    text=str(item.get("text", "")),
                    participants=list(item.get("participants", [])),
                    location_name=item.get("location_name"),
                    location_type=item.get("location_type"),
                    activity_type=item.get("activity_type"),
                    topics=list(item.get("topics", [])),
                    sentiment_label=item.get("sentiment_label", "neutral"),
                    emotion_tags=list(item.get("emotion_tags", [])),
                    categories=list(item.get("categories", [])),
                    confidence=float(item.get("confidence", 0.0)),
                    temporal_links=self._parse_temporal_links(item.get("temporal_links", [])),
                    correction_signal=bool(item.get("correction_signal", False)),
                    contradiction_signal=bool(item.get("contradiction_signal", False)),
                    supersedes_concept=item.get("supersedes_concept"),
                    correction_source=item.get("correction_source"),
                    narrative=item.get("narrative"),
                    social_context=item.get("social_context"),
                    social_intimacy=item.get("social_intimacy"),
                    intent_type=item.get("intent_type"),
                    identity_domains=list(item.get("identity_domains", [])),
                    source_type=item.get("source_type", "user_stated"),
                    novelty=item.get("novelty", "EXPECTED"),
                    elaboration_depth=item.get("elaboration_depth", "MENTION"),
                    temporal_orientation=item.get("temporal_orientation", "PAST"),
                    affect=item.get("affect"),
                    session_id=context.session_id,
                    conversation_turn=context.conversation_turn,
                    extraction_sequence=i,
                    trace_id=trace_id,
                )
                extractions.append(ext)
            except (ValueError, TypeError, KeyError) as exc:
                log.warning(
                    "MW: Failed to parse extraction item",
                    extra={
                        "trace_id": trace_id,
                        "item_index": i,
                        "error": str(exc),
                    },
                )
                continue

        return extractions

    @staticmethod
    def _parse_temporal_links(raw_links: Any) -> List[Dict[str, Any]]:
        """Parse temporal_links from LLM output.

        Each link: {mentioned_time, link_type, uncertainty_window_ms, confidence}
        Max 5 per atom (MW-12). Invalid entries silently dropped.
        """
        if not isinstance(raw_links, list):
            return []
        links: List[Dict[str, Any]] = []
        for link in raw_links[:5]:  # MW-12 cap
            if isinstance(link, dict) and link.get("mentioned_time"):
                links.append(
                    {
                        "mentioned_time": str(link.get("mentioned_time", "")),
                        "link_type": str(link.get("link_type", "CONCURRENT")),
                        "uncertainty_window_ms": int(link.get("uncertainty_window_ms", 0)),
                        "confidence": float(link.get("confidence", 1.0)),
                    }
                )
        return links
