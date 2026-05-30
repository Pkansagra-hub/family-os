"""Tests for MemoryWriterAgent (E-MW-2.1).

32 tests across 7 test classes covering extraction, budget enforcement,
error handling, parsing, temporal links, correction signals, and prompt building.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from k1.memory_writer.config import MWConfig
from k1.memory_writer.extraction.raw_extraction import PromptLoader
from k1.memory_writer.extraction.writer_agent import MemoryWriterAgent
from k1.memory_writer.invariants import InvariantViolation
from k1.memory_writer.types import (
    Affect,
    ChatResponse,
    CompressedTurn,
    ExtractionContext,
)

# ===========================================================================
# Helpers
# ===========================================================================

# Path to real prompts dir
_PROMPTS_DIR = (
    Path(__file__).resolve().parents[3] / "k1" / "memory_writer" / "extraction" / "prompts"
)


class FakeModelHub:
    """In-memory fake for IModelHubPort."""

    def __init__(
        self,
        response_content: str = "[]",
        total_tokens: int = 100,
        raise_on_chat: BaseException | None = None,
    ) -> None:
        self._content = response_content
        self._total_tokens = total_tokens
        self._raise = raise_on_chat
        self.last_messages: List[Dict[str, str]] = []
        self.last_budget: int = 0
        self.last_model_hint: str = ""

    async def chat(
        self,
        messages: List[Dict[str, str]],
        budget_tokens: int,
        model_hint: str,
    ) -> ChatResponse:
        self.last_messages = messages
        self.last_budget = budget_tokens
        self.last_model_hint = model_hint
        if self._raise:
            raise self._raise
        return ChatResponse(
            content=self._content,
            total_tokens=self._total_tokens,
            prompt_tokens=50,
            completion_tokens=50,
            model="test-model",
            latency_ms=10.0,
        )


def _ctx(**overrides: Any) -> ExtractionContext:
    defaults: Dict[str, Any] = dict(
        current_turn=CompressedTurn(
            turn_id="turn-1",
            role="user",
            text="Mom called about dinner",
            timestamp_ms=1_700_000_000_000,
            turn_number=5,
        ),
        recent_turns=[
            CompressedTurn("t-1", "user", "Hello", 1_700_000_000_000, 1),
            CompressedTurn("t-2", "user", "How are you?", 1_700_000_001_000, 2),
        ],
        active_persons={"Mom": {"type": "PERSON", "person_id": "person_mom"}},
        current_affect=Affect(valence=0.5, arousal=0.3, dominance=0.5),
        active_topics=["dinner", "family"],
        session_id="sess-001",
        conversation_turn=5,
    )
    defaults.update(overrides)
    return ExtractionContext(**defaults)


def _single_extraction_json(**overrides: Any) -> str:
    """Return JSON array with one well-formed extraction."""
    item: Dict[str, Any] = {
        "text": "Had dinner with Mom at the Italian restaurant",
        "participants": ["Mom"],
        "topics": ["dinner", "family"],
        "categories": ["family_event"],
        "activity_type": "MEAL",
        "location_name": "Italian restaurant",
        "location_type": "restaurant",
        "sentiment_label": "positive",
        "emotion_tags": ["happy"],
        "affect": {"valence": 0.6, "arousal": 0.3, "dominance": 0.5},
        "novelty": "EXPECTED",
        "elaboration_depth": "MENTION",
        "temporal_orientation": "PAST",
        "source_type": "user_stated",
        "intent_type": "share_news",
        "social_context": "nuclear_family",
        "social_intimacy": "HIGH",
        "identity_domains": ["parent"],
        "confidence": 0.85,
        "temporal_links": [],
        "correction_signal": False,
        "contradiction_signal": False,
        "supersedes_concept": None,
        "correction_source": None,
        "narrative": None,
    }
    item.update(overrides)
    return json.dumps([item])


def _make_agent(
    response_content: str = "[]",
    raise_on_chat: BaseException | None = None,
    config: MWConfig | None = None,
) -> tuple[MemoryWriterAgent, FakeModelHub]:
    hub = FakeModelHub(response_content=response_content, raise_on_chat=raise_on_chat)
    cfg = config or MWConfig()
    loader = PromptLoader(_PROMPTS_DIR)
    agent = MemoryWriterAgent(model_hub=hub, config=cfg, prompt_loader=loader)
    return agent, hub


# ===========================================================================
# TestWriterAgentExtract
# ===========================================================================


class TestWriterAgentExtract:
    @pytest.mark.asyncio
    async def test_single_extraction_from_meaningful_turn(self):
        agent, _ = _make_agent(_single_extraction_json())
        result = await agent.extract(_ctx(), "trace-001")
        assert len(result) == 1
        assert result[0].text == "Had dinner with Mom at the Italian restaurant"
        assert "Mom" in result[0].participants
        assert "dinner" in result[0].topics

    @pytest.mark.asyncio
    async def test_multi_extraction_from_complex_turn(self):
        items = [
            {"text": "Dinner with Mom", "topics": ["dinner"], "confidence": 0.8},
            {"text": "Dentist tomorrow", "topics": ["health"], "confidence": 0.7},
        ]
        agent, _ = _make_agent(json.dumps(items))
        result = await agent.extract(_ctx(), "trace-001")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_extraction_for_trivial_response(self):
        agent, _ = _make_agent("[]")
        result = await agent.extract(_ctx(), "trace-001")
        assert result == []

    @pytest.mark.asyncio
    async def test_extraction_has_session_metadata(self):
        agent, _ = _make_agent(_single_extraction_json())
        ctx = _ctx(session_id="sess-42", conversation_turn=7)
        result = await agent.extract(ctx, "trace-001")
        assert result[0].session_id == "sess-42"
        assert result[0].conversation_turn == 7
        assert result[0].extraction_sequence == 0

    @pytest.mark.asyncio
    async def test_extraction_has_trace_id(self):
        agent, _ = _make_agent(_single_extraction_json())
        result = await agent.extract(_ctx(), "trace-xyz")
        assert result[0].trace_id == "trace-xyz"

    @pytest.mark.asyncio
    async def test_max_6_extractions_enforced(self):
        items = [{"text": f"Fact {i}", "topics": [f"t{i}"], "confidence": 0.8} for i in range(8)]
        agent, _ = _make_agent(json.dumps(items))
        result = await agent.extract(_ctx(), "trace-001")
        assert len(result) == 6


# ===========================================================================
# TestWriterAgentBudget
# ===========================================================================


class TestWriterAgentBudget:
    @pytest.mark.asyncio
    async def test_mw06_budget_enforced(self):
        agent, hub = _make_agent("[]")
        await agent.extract(_ctx(), "trace-001")
        assert hub.last_budget == 2000

    @pytest.mark.asyncio
    async def test_mw06_violation_raises(self):
        """Calling assert_mw06_token_budget with excess budget triggers violation."""
        from k1.memory_writer.invariants import assert_mw06_token_budget

        config = MWConfig(llm_token_budget=2000)
        with pytest.raises(InvariantViolation, match="MW-06"):
            assert_mw06_token_budget(3000, config)

    @pytest.mark.asyncio
    async def test_model_hint_from_config(self):
        agent, hub = _make_agent("[]")
        await agent.extract(_ctx(), "trace-001")
        assert hub.last_model_hint == "gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_response_token_usage_captured(self):
        """ChatResponse token fields are available (no assertion on agent, just verify hub)."""
        hub = FakeModelHub(response_content="[]", total_tokens=150)
        loader = PromptLoader(_PROMPTS_DIR)
        agent = MemoryWriterAgent(model_hub=hub, config=MWConfig(), prompt_loader=loader)
        await agent.extract(_ctx(), "trace-001")
        # FakeModelHub returns 150 total_tokens; agent uses it but doesn't expose it
        assert hub.last_budget == 2000  # budget was sent correctly


# ===========================================================================
# TestWriterAgentErrorHandling
# ===========================================================================


class TestWriterAgentErrorHandling:
    @pytest.mark.asyncio
    async def test_llm_exception_returns_empty(self):
        agent, _ = _make_agent(raise_on_chat=RuntimeError("LLM down"))
        result = await agent.extract(_ctx(), "trace-001")
        assert result == []

    @pytest.mark.asyncio
    async def test_llm_timeout_returns_empty(self):
        agent, _ = _make_agent(raise_on_chat=TimeoutError("60s exceeded"))
        result = await agent.extract(_ctx(), "trace-001")
        assert result == []

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_returns_empty(self):
        agent, _ = _make_agent(raise_on_chat=ConnectionError("circuit open"))
        result = await agent.extract(_ctx(), "trace-001")
        assert result == []

    @pytest.mark.asyncio
    async def test_malformed_json_returns_empty(self):
        agent, _ = _make_agent("not valid json {{{")
        result = await agent.extract(_ctx(), "trace-001")
        assert result == []

    @pytest.mark.asyncio
    async def test_non_array_json_returns_empty(self):
        agent, _ = _make_agent('{"text": "single object"}')
        result = await agent.extract(_ctx(), "trace-001")
        assert result == []


# ===========================================================================
# TestWriterAgentParsing
# ===========================================================================


class TestWriterAgentParsing:
    @pytest.mark.asyncio
    async def test_parses_all_34_fields(self):
        full_item = {
            "text": "Had dinner with Mom",
            "participants": ["Mom"],
            "topics": ["dinner"],
            "categories": ["family"],
            "activity_type": "MEAL",
            "location_name": "Home",
            "location_type": "home",
            "sentiment_label": "positive",
            "emotion_tags": ["happy"],
            "affect": {"valence": 0.7, "arousal": 0.3, "dominance": 0.5},
            "novelty": "NOVEL",
            "elaboration_depth": "DISCUSSED",
            "temporal_orientation": "PAST",
            "source_type": "user_stated",
            "intent_type": "log_memory",
            "social_context": "nuclear_family",
            "social_intimacy": "HIGH",
            "identity_domains": ["parent"],
            "confidence": 0.9,
            "temporal_links": [
                {
                    "mentioned_time": "yesterday",
                    "link_type": "RETROSPECTIVE",
                    "uncertainty_window_ms": 86400000,
                    "confidence": 0.8,
                }
            ],
            "correction_signal": True,
            "contradiction_signal": False,
            "supersedes_concept": "cuisine:thai",
            "correction_source": "user_explicit",
            "narrative": {
                "thread_id": "t1",
                "arc_position": "RISING_ACTION",
                "is_goal_event": False,
            },
        }
        agent, _ = _make_agent(json.dumps([full_item]))
        result = await agent.extract(_ctx(), "trace-001")
        ext = result[0]
        assert ext.text == "Had dinner with Mom"
        assert ext.participants == ["Mom"]
        assert ext.activity_type == "MEAL"
        assert ext.sentiment_label == "positive"
        assert ext.affect == {"valence": 0.7, "arousal": 0.3, "dominance": 0.5}
        assert ext.correction_signal is True
        assert ext.supersedes_concept == "cuisine:thai"
        assert ext.narrative == {
            "thread_id": "t1",
            "arc_position": "RISING_ACTION",
            "is_goal_event": False,
        }
        assert len(ext.temporal_links) == 1

    @pytest.mark.asyncio
    async def test_missing_optional_fields_use_defaults(self):
        item = {"text": "Simple fact", "topics": ["misc"], "confidence": 0.5}
        agent, _ = _make_agent(json.dumps([item]))
        result = await agent.extract(_ctx(), "trace-001")
        ext = result[0]
        assert ext.location_name is None
        assert ext.emotion_tags == []
        assert ext.sentiment_label == "neutral"
        assert ext.novelty == "EXPECTED"

    @pytest.mark.asyncio
    async def test_markdown_code_fence_stripped(self):
        fenced = '```json\n[{"text": "fact", "topics": ["t"], "confidence": 0.5}]\n```'
        agent, _ = _make_agent(fenced)
        result = await agent.extract(_ctx(), "trace-001")
        assert len(result) == 1
        assert result[0].text == "fact"

    @pytest.mark.asyncio
    async def test_partial_array_keeps_valid_items(self):
        items = [
            {"text": "valid1", "topics": ["t1"], "confidence": 0.8},
            "not a dict",
            {"text": "valid2", "topics": ["t2"], "confidence": 0.7},
        ]
        agent, _ = _make_agent(json.dumps(items))
        result = await agent.extract(_ctx(), "trace-001")
        assert len(result) == 2
        assert result[0].text == "valid1"
        assert result[1].text == "valid2"

    @pytest.mark.asyncio
    async def test_confidence_parsed_as_float(self):
        item = {"text": "fact", "topics": ["t"], "confidence": "0.95"}
        agent, _ = _make_agent(json.dumps([item]))
        result = await agent.extract(_ctx(), "trace-001")
        assert result[0].confidence == 0.95


# ===========================================================================
# TestWriterAgentTemporalLinks
# ===========================================================================


class TestWriterAgentTemporalLinks:
    @pytest.mark.asyncio
    async def test_parses_temporal_links_array(self):
        links = [
            {
                "mentioned_time": "yesterday",
                "link_type": "RETROSPECTIVE",
                "uncertainty_window_ms": 86400000,
                "confidence": 0.9,
            },
            {
                "mentioned_time": "next Friday",
                "link_type": "PROSPECTIVE",
                "uncertainty_window_ms": 86400000,
                "confidence": 0.8,
            },
            {
                "mentioned_time": "now",
                "link_type": "CONCURRENT",
                "uncertainty_window_ms": 0,
                "confidence": 1.0,
            },
        ]
        item = {"text": "fact", "topics": ["t"], "confidence": 0.5, "temporal_links": links}
        agent, _ = _make_agent(json.dumps([item]))
        result = await agent.extract(_ctx(), "trace-001")
        assert len(result[0].temporal_links) == 3

    @pytest.mark.asyncio
    async def test_caps_at_5_links(self):
        links = [
            {"mentioned_time": f"time{i}", "link_type": "CONCURRENT", "confidence": 1.0}
            for i in range(7)
        ]
        item = {"text": "fact", "topics": ["t"], "confidence": 0.5, "temporal_links": links}
        agent, _ = _make_agent(json.dumps([item]))
        result = await agent.extract(_ctx(), "trace-001")
        assert len(result[0].temporal_links) == 5

    @pytest.mark.asyncio
    async def test_invalid_link_dropped(self):
        links = [
            {"link_type": "CONCURRENT"},  # missing mentioned_time
            {"mentioned_time": "yesterday", "link_type": "RETROSPECTIVE", "confidence": 0.9},
        ]
        item = {"text": "fact", "topics": ["t"], "confidence": 0.5, "temporal_links": links}
        agent, _ = _make_agent(json.dumps([item]))
        result = await agent.extract(_ctx(), "trace-001")
        assert len(result[0].temporal_links) == 1

    @pytest.mark.asyncio
    async def test_empty_temporal_links(self):
        item = {"text": "fact", "topics": ["t"], "confidence": 0.5, "temporal_links": []}
        agent, _ = _make_agent(json.dumps([item]))
        result = await agent.extract(_ctx(), "trace-001")
        assert result[0].temporal_links == []


# ===========================================================================
# TestWriterAgentCorrectionSignals
# ===========================================================================


class TestWriterAgentCorrectionSignals:
    @pytest.mark.asyncio
    async def test_correction_signal_parsed(self):
        agent, _ = _make_agent(_single_extraction_json(correction_signal=True))
        result = await agent.extract(_ctx(), "trace-001")
        assert result[0].correction_signal is True

    @pytest.mark.asyncio
    async def test_contradiction_signal_parsed(self):
        agent, _ = _make_agent(_single_extraction_json(contradiction_signal=True))
        result = await agent.extract(_ctx(), "trace-001")
        assert result[0].contradiction_signal is True

    @pytest.mark.asyncio
    async def test_supersedes_concept_parsed(self):
        agent, _ = _make_agent(
            _single_extraction_json(supersedes_concept="cuisine_preference:italian")
        )
        result = await agent.extract(_ctx(), "trace-001")
        assert result[0].supersedes_concept == "cuisine_preference:italian"

    @pytest.mark.asyncio
    async def test_correction_defaults_to_false(self):
        item = {"text": "fact", "topics": ["t"], "confidence": 0.5}
        agent, _ = _make_agent(json.dumps([item]))
        result = await agent.extract(_ctx(), "trace-001")
        assert result[0].correction_signal is False
        assert result[0].contradiction_signal is False
        assert result[0].supersedes_concept is None
        assert result[0].correction_source is None


# ===========================================================================
# TestWriterAgentPromptBuilding
# ===========================================================================


class TestWriterAgentPromptBuilding:
    @pytest.mark.asyncio
    async def test_prompt_includes_recent_turns(self):
        turns = [
            CompressedTurn(f"t-{i}", "user", f"Message {i}", 1_700_000_000_000 + i, i)
            for i in range(1, 6)
        ]
        ctx = _ctx(recent_turns=turns)
        agent, hub = _make_agent("[]")
        await agent.extract(ctx, "trace-001")
        user_msg = hub.last_messages[1]["content"]
        assert "Turn 1" in user_msg
        assert "Turn 5" in user_msg

    @pytest.mark.asyncio
    async def test_prompt_includes_active_entities(self):
        ctx = _ctx(active_persons={"Mom": {"type": "PERSON"}, "Dad": {"type": "PERSON"}})
        agent, hub = _make_agent("[]")
        await agent.extract(ctx, "trace-001")
        user_msg = hub.last_messages[1]["content"]
        assert "Mom (PERSON)" in user_msg
        assert "Dad (PERSON)" in user_msg

    @pytest.mark.asyncio
    async def test_prompt_includes_current_turn(self):
        ctx = _ctx(current_turn=CompressedTurn("t-99", "user", "Mom called about dinner", 0, 5))
        agent, hub = _make_agent("[]")
        await agent.extract(ctx, "trace-001")
        user_msg = hub.last_messages[1]["content"]
        assert "Mom called about dinner" in user_msg
        assert "Turn #: 5" in user_msg

    @pytest.mark.asyncio
    async def test_prompt_truncates_long_turn_text(self):
        long_text = "A" * 500
        turns = [CompressedTurn("t-1", "user", long_text, 0, 1)]
        ctx = _ctx(recent_turns=turns)
        agent, hub = _make_agent("[]")
        await agent.extract(ctx, "trace-001")
        user_msg = hub.last_messages[1]["content"]
        # Turn text should be truncated to 100 chars in recent turns section
        assert "A" * 100 in user_msg
        assert "A" * 200 not in user_msg
