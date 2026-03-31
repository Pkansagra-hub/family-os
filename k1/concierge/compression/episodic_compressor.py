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
    )

    def __init__(self, config: CompressionConfig | None = None) -> None:
        self._config = config or CompressionConfig()
        self._episodes: list[CompressedEpisode] = []
        self._compression_count: int = 0
        logger.info(
            "EpisodicCompressor initialised  recent_window=%d episode_size=%d",
            self._config.recent_window,
            self._config.episode_size,
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

        return CompressedEpisode(
            episode_id=episode_id,
            turn_range=turn_range,
            summary=summary,
            key_facts=key_facts[:5],
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
