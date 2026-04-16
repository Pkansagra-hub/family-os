"""
tests.k1.concierge.test_episodic_compressor
E-0.5.26 I-0.5.26.2: EpisodicCompressor (OPP-6) tests.

Validates:
    1. should_compress() threshold (min_turns_to_compress=15).
    2. identify_compressible(): recent window preservation, HITL/safety
       turn preservation, segment grouping by episode_size.
    3. compress_segment(): extractive key-facts, entity extraction,
       topic detection, key_facts capping (≤5), empty segment.
    4. compress_all(): end-to-end pipeline (episodes + recent_turns).
    5. build_compressed_context(): prompt block formatting.
    6. CompressedEpisode: to_prompt_block(), token_estimate().
    7. CompressionConfig / CompressionStrategy constants.
"""

from __future__ import annotations

from typing import Any

import pytest

from k1.concierge.compression.episodic_compressor import (
    CompressedEpisode,
    CompressionConfig,
    CompressionStrategy,
    EpisodicCompressor,
)

# =========================================================================
# Helpers
# =========================================================================


def _make_turn(
    turn_number: int,
    user_message: str = "",
    intent: str = "",
    entities: list | None = None,
    has_hitl: bool = False,
    safety_band: str = "GREEN",
    response: str = "",
) -> dict[str, Any]:
    t: dict[str, Any] = {"turn_number": turn_number}
    if user_message:
        t["user_message"] = user_message
    if intent:
        t["intent"] = intent
    if entities is not None:
        t["entities"] = entities
    if has_hitl:
        t["has_hitl"] = True
    if safety_band != "GREEN":
        t["safety_band"] = safety_band
    if response:
        t["response"] = response
    return t


def _make_turns(count: int, start: int = 1) -> list[dict[str, Any]]:
    """Generate N simple turns."""
    return [
        _make_turn(i, user_message=f"message {i}", intent=f"intent_{i}")
        for i in range(start, start + count)
    ]


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def ec() -> EpisodicCompressor:
    return EpisodicCompressor()


@pytest.fixture
def small_config() -> CompressionConfig:
    """Config with small windows for testing."""
    return CompressionConfig(
        recent_window=3,
        episode_size=2,
        min_turns_to_compress=5,
    )


@pytest.fixture
def ec_small(small_config: CompressionConfig) -> EpisodicCompressor:
    return EpisodicCompressor(small_config)


# =========================================================================
# 1. CompressionStrategy + CompressionConfig
# =========================================================================


class TestCompressionConfig:
    def test_strategy_constants(self) -> None:
        assert CompressionStrategy.KEY_FACTS == "key_facts"
        assert CompressionStrategy.EXTRACTIVE == "extractive"
        assert CompressionStrategy.TOPIC_SUMMARY == "topic_summary"

    def test_default_config(self) -> None:
        cfg = CompressionConfig()
        assert cfg.recent_window == 10
        assert cfg.episode_size == 5
        assert cfg.compression_strategy == CompressionStrategy.KEY_FACTS
        assert cfg.preserve_hitl_turns is True
        assert cfg.preserve_safety_turns is True
        assert cfg.min_turns_to_compress == 15

    def test_custom_config(self) -> None:
        cfg = CompressionConfig(recent_window=5, episode_size=3, min_turns_to_compress=8)
        assert cfg.recent_window == 5
        assert cfg.episode_size == 3
        assert cfg.min_turns_to_compress == 8


# =========================================================================
# 2. should_compress()
# =========================================================================


class TestShouldCompress:
    def test_below_threshold(self, ec: EpisodicCompressor) -> None:
        assert ec.should_compress(14) is False

    def test_at_threshold(self, ec: EpisodicCompressor) -> None:
        assert ec.should_compress(15) is True

    def test_above_threshold(self, ec: EpisodicCompressor) -> None:
        assert ec.should_compress(25) is True

    def test_zero_turns(self, ec: EpisodicCompressor) -> None:
        assert ec.should_compress(0) is False

    def test_custom_threshold(self) -> None:
        ec = EpisodicCompressor(CompressionConfig(min_turns_to_compress=5))
        assert ec.should_compress(5) is True
        assert ec.should_compress(4) is False


# =========================================================================
# 3. identify_compressible()
# =========================================================================


class TestIdentifyCompressible:
    def test_empty_list(self, ec: EpisodicCompressor) -> None:
        assert ec.identify_compressible([]) == []

    def test_fewer_than_window(self, ec: EpisodicCompressor) -> None:
        turns = _make_turns(5)
        assert ec.identify_compressible(turns) == []

    def test_segments_from_old_turns(self, ec_small: EpisodicCompressor) -> None:
        """8 turns, recent_window=3 → 5 old turns → 2 segments of size 2 + 1 leftover."""
        turns = _make_turns(8)
        segments = ec_small.identify_compressible(turns)
        assert len(segments) == 3  # 2+2+1
        assert len(segments[0]) == 2
        assert len(segments[1]) == 2
        assert len(segments[2]) == 1

    def test_hitl_turns_preserved(self) -> None:
        ec = EpisodicCompressor(
            CompressionConfig(
                recent_window=2,
                episode_size=2,
                min_turns_to_compress=3,
                preserve_hitl_turns=True,
            )
        )
        turns = [
            _make_turn(1, user_message="normal"),
            _make_turn(2, user_message="hitl", has_hitl=True),
            _make_turn(3, user_message="normal2"),
            _make_turn(4, user_message="recent1"),
            _make_turn(5, user_message="recent2"),
        ]
        segments = ec.identify_compressible(turns)
        # Turn 2 (has_hitl=True) should be filtered out
        all_turns_in_segments = [t for seg in segments for t in seg]
        assert all(not t.get("has_hitl", False) for t in all_turns_in_segments)

    def test_safety_turns_preserved(self) -> None:
        ec = EpisodicCompressor(
            CompressionConfig(
                recent_window=2,
                episode_size=2,
                min_turns_to_compress=3,
                preserve_safety_turns=True,
            )
        )
        turns = [
            _make_turn(1, user_message="normal"),
            _make_turn(2, user_message="red", safety_band="RED"),
            _make_turn(3, user_message="amber", safety_band="AMBER"),
            _make_turn(4, user_message="recent1"),
            _make_turn(5, user_message="recent2"),
        ]
        segments = ec.identify_compressible(turns)
        all_turns_in_segments = [t for seg in segments for t in seg]
        for t in all_turns_in_segments:
            assert t.get("safety_band", "GREEN") not in ("RED", "AMBER")

    def test_recent_window_kept_intact(self, ec_small: EpisodicCompressor) -> None:
        """Recent 3 turns should never appear in compressible segments."""
        turns = _make_turns(10)
        segments = ec_small.identify_compressible(turns)
        all_segment_numbers = {t["turn_number"] for seg in segments for t in seg}
        recent_numbers = {8, 9, 10}
        assert all_segment_numbers.isdisjoint(recent_numbers)


# =========================================================================
# 4. compress_segment()
# =========================================================================


class TestCompressSegment:
    def test_basic_compression(self, ec: EpisodicCompressor) -> None:
        segment = _make_turns(3, start=5)
        episode = ec.compress_segment(segment)
        assert isinstance(episode, CompressedEpisode)
        assert episode.turn_range == (5, 7)
        assert episode.original_count == 3
        assert episode.episode_id == "ep_5_7"

    def test_custom_episode_id(self, ec: EpisodicCompressor) -> None:
        segment = _make_turns(2, start=1)
        episode = ec.compress_segment(segment, episode_id="custom-1")
        assert episode.episode_id == "custom-1"

    def test_empty_segment(self, ec: EpisodicCompressor) -> None:
        episode = ec.compress_segment([])
        assert episode.episode_id == "empty"
        assert episode.original_count == 0
        assert episode.summary == ""

    def test_key_facts_extracted(self, ec: EpisodicCompressor) -> None:
        segment = [
            _make_turn(1, user_message="Book a flight to Paris"),
            _make_turn(2, user_message="Check weather forecast"),
        ]
        episode = ec.compress_segment(segment)
        assert any("Paris" in f for f in episode.key_facts)

    def test_entity_extraction_strings(self, ec: EpisodicCompressor) -> None:
        segment = [_make_turn(1, entities=["Paris", "hotel"])]
        episode = ec.compress_segment(segment)
        assert any("Paris" in f for f in episode.key_facts)

    def test_entity_extraction_dicts(self, ec: EpisodicCompressor) -> None:
        segment = [_make_turn(1, entities=[{"text": "London"}, {"text": "flight"}])]
        episode = ec.compress_segment(segment)
        assert any("London" in f for f in episode.key_facts)

    def test_key_facts_capped_at_five(self, ec: EpisodicCompressor) -> None:
        segment = [
            _make_turn(i, user_message=f"msg {i}", entities=[f"ent_{i}"]) for i in range(1, 10)
        ]
        episode = ec.compress_segment(segment)
        assert len(episode.key_facts) <= 5

    def test_topic_from_intent(self, ec: EpisodicCompressor) -> None:
        segment = [_make_turn(1, intent="travel_booking")]
        episode = ec.compress_segment(segment)
        assert episode.topic == "travel_booking"

    def test_default_topic(self, ec: EpisodicCompressor) -> None:
        segment = [_make_turn(1, user_message="hello")]
        episode = ec.compress_segment(segment)
        assert episode.topic == "general conversation"

    def test_compression_count_increments(self, ec: EpisodicCompressor) -> None:
        assert ec.compression_count == 0
        ec.compress_segment(_make_turns(2))
        assert ec.compression_count == 1
        ec.compress_segment(_make_turns(2, start=3))
        assert ec.compression_count == 2


# =========================================================================
# 5. compress_all() — end-to-end pipeline
# =========================================================================


class TestCompressAll:
    def test_below_threshold_returns_all(self, ec: EpisodicCompressor) -> None:
        turns = _make_turns(10)
        episodes, recent = ec.compress_all(turns)
        assert episodes == []
        assert recent == turns

    def test_above_threshold_returns_episodes_and_recent(self) -> None:
        ec = EpisodicCompressor(
            CompressionConfig(
                recent_window=3,
                episode_size=2,
                min_turns_to_compress=5,
            )
        )
        turns = _make_turns(8)
        episodes, recent = ec.compress_all(turns)
        assert len(episodes) > 0
        assert len(recent) == 3
        # Recent should be last 3 turns
        assert recent[0]["turn_number"] == 6

    def test_episode_count_tracked(self) -> None:
        ec = EpisodicCompressor(
            CompressionConfig(
                recent_window=2,
                episode_size=2,
                min_turns_to_compress=4,
            )
        )
        turns = _make_turns(6)
        episodes, _ = ec.compress_all(turns)
        assert ec.episode_count == len(episodes)

    def test_empty_turns(self, ec: EpisodicCompressor) -> None:
        episodes, recent = ec.compress_all([])
        assert episodes == []
        assert recent == []


# =========================================================================
# 6. CompressedEpisode
# =========================================================================


class TestCompressedEpisode:
    def test_to_prompt_block_structure(self) -> None:
        ep = CompressedEpisode(
            episode_id="ep1",
            turn_range=(1, 5),
            summary="Discussed travel plans.",
            key_facts=["Paris", "June"],
            topic="travel",
            original_count=5,
        )
        block = ep.to_prompt_block()
        assert "[EPISODE: turns 1-5]" in block
        assert "Topic: travel" in block
        assert "Discussed travel plans." in block
        assert "Key facts:" in block
        assert "Paris" in block
        assert "[END EPISODE]" in block

    def test_to_prompt_block_no_topic(self) -> None:
        ep = CompressedEpisode(
            episode_id="ep2",
            turn_range=(1, 3),
            summary="Chat.",
        )
        block = ep.to_prompt_block()
        assert "Topic:" not in block

    def test_to_prompt_block_no_facts(self) -> None:
        ep = CompressedEpisode(
            episode_id="ep3",
            turn_range=(1, 2),
            summary="Short.",
            topic="misc",
        )
        block = ep.to_prompt_block()
        assert "Key facts:" not in block

    def test_token_estimate(self) -> None:
        ep = CompressedEpisode(
            episode_id="ep4",
            turn_range=(1, 5),
            summary="A" * 100,
            topic="test",
            original_count=5,
        )
        estimate = ep.token_estimate()
        assert isinstance(estimate, int)
        assert estimate > 0

    def test_compressed_at_ns_populated(self) -> None:
        ep = CompressedEpisode(episode_id="ep5", turn_range=(1, 1), summary="x")
        assert ep.compressed_at_ns > 0


# =========================================================================
# 7. build_compressed_context()
# =========================================================================


class TestBuildCompressedContext:
    def test_with_episodes_and_recent(self, ec: EpisodicCompressor) -> None:
        episodes = [
            CompressedEpisode(
                episode_id="ep1",
                turn_range=(1, 5),
                summary="Travel plans.",
                topic="travel",
                original_count=5,
            )
        ]
        recent = [_make_turn(6, user_message="Book now", response="Done")]
        ctx = ec.build_compressed_context(episodes, recent)
        assert "COMPRESSED" in ctx
        assert "RECENT" in ctx
        assert "Travel plans." in ctx
        assert "Book now" in ctx

    def test_empty_episodes(self, ec: EpisodicCompressor) -> None:
        recent = [_make_turn(1, user_message="Hello", response="Hi")]
        ctx = ec.build_compressed_context([], recent)
        assert "COMPRESSED" not in ctx
        assert "RECENT" in ctx

    def test_empty_recent(self, ec: EpisodicCompressor) -> None:
        episodes = [
            CompressedEpisode(
                episode_id="ep1",
                turn_range=(1, 3),
                summary="Chat.",
            )
        ]
        ctx = ec.build_compressed_context(episodes, [])
        assert "COMPRESSED" in ctx
        assert "RECENT" not in ctx

    def test_both_empty(self, ec: EpisodicCompressor) -> None:
        ctx = ec.build_compressed_context([], [])
        assert ctx == ""

    def test_user_message_truncated(self, ec: EpisodicCompressor) -> None:
        long_msg = "x" * 500
        recent = [_make_turn(1, user_message=long_msg)]
        ctx = ec.build_compressed_context([], recent)
        # User message capped at 200 chars
        assert len(ctx) < len(long_msg)
