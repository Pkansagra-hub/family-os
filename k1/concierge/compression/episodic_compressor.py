"""
k1.concierge.compression.episodic_compressor -- Episodic Compression (OPP-6)

Generalized kernel primitive: compresses older conversation turns into
episodic summaries to maintain context without exceeding token budgets.

Architecture:
    HistoryActiveSection (raw turns, MAX_TURNS=25)
        -> EpisodicCompressor (identifies compressible segments)
        -> CompressedEpisode (summary + key facts from N turns)
        -> Dynamic history window (recent turns + compressed episodes)

The kernel provides the compressor interface; verticals configure:
    - Compression threshold (how old before compressing)
    - Summary strategy (extractive, abstractive, key-facts-only)
    - Preservation rules (always keep turns with HITL, safety events, etc.)
    - Episode granularity (how many turns per episode)

Token economics:
    - 25 raw turns * ~200 tokens = ~5000 tokens
    - 5 episodes * ~80 tokens + 10 recent turns * ~200 = ~2400 tokens
    - Net savings: ~50% token reduction with key context preserved
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class CompressionStrategy:
    """Strategy identifiers for episodic compression."""

    KEY_FACTS = "key_facts"
    EXTRACTIVE = "extractive"
    TOPIC_SUMMARY = "topic_summary"
    # M6 E6.1 (C01): LLM-backed abstractive compression strategy.
    # Dispatched in compress_segment() when configured; falls back to
    # extractive heuristics when no LLM port is wired (default).
    LLM = "llm"


@dataclass
class CompressedEpisode:
    """A compressed summary of N conversation turns.

    Replaces the original turns in the prompt context with a
    compact representation preserving key information.

    Attributes:
        episode_id:       Unique identifier for this episode.
        turn_range:       (start_turn, end_turn) inclusive.
        summary:          Compressed text summary.
        key_facts:        Extracted facts that must survive compression.
        topic:            Primary topic of the episode.
        original_count:   Number of turns compressed.
        compressed_at_ns: When compression occurred.
    """

    episode_id: str
    turn_range: tuple[int, int]
    summary: str
    key_facts: list[str] = field(default_factory=list)
    topic: str = ""
    original_count: int = 0
    compressed_at_ns: int = field(default_factory=time.monotonic_ns)

    def to_prompt_block(self) -> str:
        """Format as a prompt injection block."""
        lines = [
            f"[EPISODE: turns {self.turn_range[0]}-{self.turn_range[1]}]",
            f"Topic: {self.topic}" if self.topic else "",
            self.summary,
        ]
        if self.key_facts:
            lines.append("Key facts: " + "; ".join(self.key_facts))
        lines.append("[END EPISODE]")
        return "\n".join(line for line in lines if line)

    def token_estimate(self) -> int:
        """Rough token estimate for this episode."""
        text = self.to_prompt_block()
        return len(text) // 4


@dataclass
class CompressionConfig:
    """Configuration for episodic compression.

    Attributes:
        recent_window:        Number of recent turns to keep uncompressed.
        episode_size:         Number of turns per compressed episode.
        compression_strategy: Which compression strategy to use.
        preserve_hitl_turns:  Always keep HITL turns uncompressed.
        preserve_safety_turns: Always keep safety-flagged turns uncompressed.
        min_turns_to_compress: Minimum total turns before compression activates.
    """

    recent_window: int = 10
    episode_size: int = 5
    compression_strategy: str = CompressionStrategy.KEY_FACTS
    preserve_hitl_turns: bool = True
    preserve_safety_turns: bool = True
    min_turns_to_compress: int = 15


class EpisodicCompressor:
    """Compresses old conversation turns into episodic summaries.

    Generalized kernel primitive. Takes a list of turns, identifies
    compressible segments, and produces CompressedEpisode objects.

    The compressor does NOT call LLMs -- it uses extractive heuristics.
    Production can override with abstractive (LLM-based) compression
    by subclassing and overriding compress_segment().
    """

    __slots__ = (
        "_config",
        "_episodes",
        "_compression_count",
        "_llm_port",
    )

    def __init__(
        self,
        config: CompressionConfig | None = None,
        llm_port: Any | None = None,
    ) -> None:
        self._config = config or CompressionConfig()
        self._episodes: list[CompressedEpisode] = []
        self._compression_count: int = 0
        # M6 E6.1 (C01): Optional LLM port for `CompressionStrategy.LLM`.
        # When None, LLM strategy gracefully falls back to extractive.
        self._llm_port = llm_port
        logger.info(
            "EpisodicCompressor initialised  recent_window=%d episode_size=%d strategy=%s",
            self._config.recent_window,
            self._config.episode_size,
            self._config.compression_strategy,
        )

    def should_compress(self, total_turns: int) -> bool:
        """Check if compression should be triggered.

        Args:
            total_turns: Current total turn count.

        Returns:
            True if turns exceed min_turns_to_compress.
        """
        return total_turns >= self._config.min_turns_to_compress

    def identify_compressible(
        self,
        turns: list[dict[str, Any]],
    ) -> list[list[dict[str, Any]]]:
        """Identify segments of turns that can be compressed.

        Keeps the most recent `recent_window` turns intact.
        Groups older turns into segments of `episode_size`.
        Preserves HITL and safety turns if configured.

        Args:
            turns: All turns ordered by turn number (oldest first).

        Returns:
            List of turn segments, each ready for compression.
        """
        if len(turns) <= self._config.recent_window:
            return []

        compressible_turns = turns[: -self._config.recent_window]

        if self._config.preserve_hitl_turns:
            compressible_turns = [t for t in compressible_turns if not t.get("has_hitl", False)]

        if self._config.preserve_safety_turns:
            compressible_turns = [
                t
                for t in compressible_turns
                if t.get("safety_band", "GREEN") not in ("RED", "AMBER")
            ]

        segments: list[list[dict[str, Any]]] = []
        for i in range(0, len(compressible_turns), self._config.episode_size):
            segment = compressible_turns[i : i + self._config.episode_size]
            if segment:
                segments.append(segment)

        return segments

    def compress_segment(
        self,
        segment: list[dict[str, Any]],
        episode_id: str = "",
    ) -> CompressedEpisode:
        """Compress a segment of turns into a single episode.

        Default implementation: extractive key-facts compression.
        Override for LLM-based abstractive compression.

        Args:
            segment:    List of turn dicts to compress.
            episode_id: Unique ID for the episode.

        Returns:
            CompressedEpisode summarizing the segment.
        """
        if not segment:
            return CompressedEpisode(
                episode_id=episode_id or "empty",
                turn_range=(0, 0),
                summary="",
                original_count=0,
            )

        # M6 E6.1 (C01): Strategy dispatch.  LLM strategy delegates to
        # _compress_with_llm when a port is wired; otherwise transparently
        # falls back to the extractive key-facts path.  TOPIC_SUMMARY uses
        # a topic-only summary without enumerated key_facts.  EXTRACTIVE
        # and KEY_FACTS share the existing implementation.
        strategy = self._config.compression_strategy

        if strategy == CompressionStrategy.LLM and self._llm_port is not None:
            try:
                return self._compress_with_llm(segment, episode_id)
            except Exception:
                logger.warning(
                    "EpisodicCompressor: LLM strategy failed, falling back to extractive",
                    exc_info=True,
                )
                # Fall through to extractive

        turn_numbers = [t.get("turn_number", 0) for t in segment]
        turn_range = (min(turn_numbers), max(turn_numbers))

        key_facts: list[str] = []
        topics: list[str] = []

        for turn in segment:
            user_msg = turn.get("user_message", "")
            if user_msg:
                key_facts.append(f"User: {user_msg[:80]}")

            intent = turn.get("intent", "")
            if intent and intent not in topics:
                topics.append(intent)

            entities = turn.get("entities", [])
            for ent in entities[:2]:
                if isinstance(ent, str):
                    key_facts.append(f"Entity: {ent}")
                elif isinstance(ent, dict):
                    key_facts.append(f"Entity: {ent.get('text', '')}")

        topic = topics[0] if topics else "general conversation"
        summary = f"Discussed {topic} over {len(segment)} turns."

        if not episode_id:
            episode_id = f"ep_{turn_range[0]}_{turn_range[1]}"

        self._compression_count += 1

        # M6 E6.1 (C01): TOPIC_SUMMARY drops enumerated key_facts and keeps
        # only the topic+summary line.  KEY_FACTS / EXTRACTIVE keep the
        # bounded key_facts list (top 5).
        if strategy == CompressionStrategy.TOPIC_SUMMARY:
            episode_key_facts: list[str] = []
        else:
            episode_key_facts = key_facts[:5]

        return CompressedEpisode(
            episode_id=episode_id,
            turn_range=turn_range,
            summary=summary,
            key_facts=episode_key_facts,
            topic=topic,
            original_count=len(segment),
        )

    def _compress_with_llm(
        self,
        segment: list[dict[str, Any]],
        episode_id: str,
    ) -> CompressedEpisode:
        """LLM-backed abstractive compression (M6 E6.1 C01).

        Synchronous wrapper around the configured LLM port.  Falls back
        to the extractive path on any error (handled by caller).

        Expects `self._llm_port` to expose a synchronous `summarize(prompt: str) -> str`
        method.  Async ports should be adapted by the caller.
        """
        turn_numbers = [t.get("turn_number", 0) for t in segment]
        turn_range = (min(turn_numbers), max(turn_numbers))

        # Build a compact prompt
        lines: list[str] = []
        for turn in segment:
            user = (turn.get("user_message") or "").strip()
            resp = (turn.get("response") or "").strip()
            if user:
                lines.append(f"U: {user[:200]}")
            if resp:
                lines.append(f"A: {resp[:200]}")
        prompt = "Summarize the following conversation turns concisely:\n" + "\n".join(lines)

        port = self._llm_port
        summarize = getattr(port, "summarize", None)
        if not callable(summarize):
            raise AttributeError("llm_port has no callable summarize()")
        summary = str(summarize(prompt)).strip() or "Conversation segment."

        if not episode_id:
            episode_id = f"ep_{turn_range[0]}_{turn_range[1]}"

        self._compression_count += 1
        topics = [t.get("intent", "") for t in segment if t.get("intent")]
        topic = topics[0] if topics else "general conversation"

        return CompressedEpisode(
            episode_id=episode_id,
            turn_range=turn_range,
            summary=summary,
            key_facts=[],
            topic=topic,
            original_count=len(segment),
        )

    def compress_all(
        self,
        turns: list[dict[str, Any]],
    ) -> tuple[list[CompressedEpisode], list[dict[str, Any]]]:
        """Compress eligible turns and return episodes + recent turns.

        This is the main entry point. Returns both the compressed
        episodes (for old context) and the recent uncompressed turns.

        Args:
            turns: All turns ordered by turn number.

        Returns:
            Tuple of (compressed_episodes, recent_turns).
        """
        if not self.should_compress(len(turns)):
            return [], turns

        segments = self.identify_compressible(turns)

        episodes: list[CompressedEpisode] = []
        for segment in segments:
            episode = self.compress_segment(segment)
            episodes.append(episode)
            self._episodes.append(episode)

        recent = turns[-self._config.recent_window :]
        return episodes, recent

    def build_compressed_context(
        self,
        episodes: list[CompressedEpisode],
        recent_turns: list[dict[str, Any]],
    ) -> str:
        """Build prompt context from episodes + recent turns.

        Args:
            episodes:     Compressed episodes for older context.
            recent_turns: Recent uncompressed turns.

        Returns:
            Formatted string for prompt injection.
        """
        parts: list[str] = []

        if episodes:
            parts.append("== CONVERSATION HISTORY (COMPRESSED) ==")
            for ep in episodes:
                parts.append(ep.to_prompt_block())
            parts.append("")

        if recent_turns:
            parts.append("== RECENT CONVERSATION ==")
            for turn in recent_turns:
                user = turn.get("user_message", "")
                resp = turn.get("response", "")
                turn_num = turn.get("turn_number", "?")
                if user:
                    parts.append(f"[Turn {turn_num}] User: {user[:200]}")
                if resp:
                    parts.append(f"[Turn {turn_num}] Assistant: {resp[:200]}")

        return "\n".join(parts)

    @property
    def compression_count(self) -> int:
        """Total compressions performed."""
        return self._compression_count

    @property
    def episode_count(self) -> int:
        """Total episodes created."""
        return len(self._episodes)
