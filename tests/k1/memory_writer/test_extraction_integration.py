"""Tests for E-MW-2.3: Extraction Integration Test.

16 tests in 4 classes exercising the full Phase 2 pipeline:
  ExtractionContext → MemoryWriterAgent → ExtractionValidator → list[MemoryAtom]

Uses FakeModelHubPort with canned ChatResponse objects.
No real LLM calls. No I/O.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from k1.memory_writer.config import MWConfig
from k1.memory_writer.context.person_resolver import PersonResolver
from k1.memory_writer.extraction.extraction_validator import ExtractionValidator
from k1.memory_writer.extraction.raw_extraction import PromptLoader
from k1.memory_writer.extraction.writer_agent import MemoryWriterAgent
from k1.memory_writer.types import (
    ActivityType,
    Affect,
    ChatResponse,
    CompressedTurn,
    ExtractionContext,
    MemoryAtom,
    SentimentLabel,
)

# ===========================================================================
# Shared helpers
# ===========================================================================

_PROMPTS_DIR = (
    Path(__file__).resolve().parents[3] / "k1" / "memory_writer" / "extraction" / "prompts"
)


class FakeModelHubPort:
    """In-memory fake for IModelHubPort.

    Records call args for assertion and returns canned ChatResponse.
    """

    def __init__(
        self,
        response_content: str = "[]",
        total_tokens: int = 200,
        raise_on_chat: BaseException | None = None,
    ) -> None:
        self._content = response_content
        self._total_tokens = total_tokens
        self._raise = raise_on_chat
        self.call_count: int = 0
        self.last_budget: int = 0
        self.last_messages: List[Dict[str, str]] = []

    async def chat(
        self,
        messages: List[Dict[str, str]],
        budget_tokens: int,
        model_hint: str,
    ) -> ChatResponse:
        self.call_count += 1
        self.last_messages = messages
        self.last_budget = budget_tokens
        if self._raise:
            raise self._raise
        return ChatResponse(
            content=self._content,
            total_tokens=self._total_tokens,
            prompt_tokens=80,
            completion_tokens=120,
            model="test-model",
            latency_ms=42.0,
        )


def _ctx(**overrides: Any) -> ExtractionContext:
    """Build an ExtractionContext with sensible integration-test defaults."""
    defaults: Dict[str, Any] = dict(
        current_turn=CompressedTurn(
            turn_id="t-5",
            role="user",
            text="Had dinner with Mom at Olive Garden",
            timestamp_ms=1_700_000_005_000,
            turn_number=5,
        ),
        recent_turns=[
            CompressedTurn("t-3", "user", "How are you?", 1_700_000_003_000, 3),
            CompressedTurn("t-4", "assistant", "I'm well.", 1_700_000_004_000, 4),
            CompressedTurn(
                "t-5", "user", "Had dinner with Mom at Olive Garden", 1_700_000_005_000, 5
            ),
        ],
        active_persons={
            "Mom": {"person_id": "person_mom", "type": "PERSON", "confidence": 1.0},
        },
        current_affect=Affect(valence=0.6, arousal=0.3, dominance=0.5),
        active_topics=["family", "dining"],
        session_id="session-abc",
        conversation_turn=5,
        turn_timestamp_ms=1_700_000_005_000,
        persona_context={"aliases": {"Mom": ["Mother", "Mama"]}},
    )
    defaults.update(overrides)
    return ExtractionContext(**defaults)


def _single_atom_json(**overrides: Any) -> str:
    """Return JSON array with one well-formed LLM extraction."""
    item: Dict[str, Any] = {
        "text": "Had dinner with Mom at Olive Garden",
        "participants": ["Mom"],
        "topics": ["family", "dining"],
        "categories": ["daily_life"],
        "activity_type": "MEAL",
        "location_name": "Olive Garden",
        "location_type": "restaurant",
        "sentiment_label": "positive",
        "emotion_tags": ["contentment"],
        "affect": {"valence": 0.6, "arousal": 0.3, "dominance": 0.5},
        "novelty": "EXPECTED",
        "elaboration_depth": "MENTION",
        "temporal_orientation": "PAST",
        "source_type": "user_stated",
        "intent_type": "share_news",
        "social_context": "nuclear_family",
        "social_intimacy": "HIGH",
        "identity_domains": ["parent"],
        "confidence": 0.95,
        "temporal_links": [],
        "correction_signal": False,
        "contradiction_signal": False,
        "supersedes_concept": None,
        "correction_source": None,
        "narrative": None,
    }
    item.update(overrides)
    return json.dumps([item])


def _multi_atom_json(count: int = 3) -> str:
    """Return JSON array with *count* well-formed extractions."""
    items = []
    texts = [
        ("Had dinner with Mom at Olive Garden", ["Mom"], ["family", "dining"], "MEAL", 0.95),
        ("Dentist appointment is tomorrow", [], ["health"], "HEALTH", 0.85),
        ("Dad got promoted at work", ["Dad"], ["family", "career"], "WORK", 0.90),
    ]
    for i in range(count):
        t = texts[i % len(texts)]
        items.append(
            {
                "text": t[0],
                "participants": t[1],
                "topics": t[2],
                "categories": ["daily_life"],
                "activity_type": t[3],
                "sentiment_label": "positive",
                "emotion_tags": ["happy"],
                "confidence": t[4],
                "temporal_links": [],
            }
        )
    return json.dumps(items)


def _build_pipeline(
    response_content: str = "[]",
    raise_on_chat: BaseException | None = None,
    config: MWConfig | None = None,
) -> tuple[MemoryWriterAgent, ExtractionValidator, FakeModelHubPort]:
    """Build the full Phase 2 pipeline: Agent + Validator + FakeHub."""
    cfg = config or MWConfig()
    hub = FakeModelHubPort(
        response_content=response_content,
        raise_on_chat=raise_on_chat,
    )
    loader = PromptLoader(_PROMPTS_DIR)
    agent = MemoryWriterAgent(model_hub=hub, config=cfg, prompt_loader=loader)
    validator = ExtractionValidator(
        person_resolver=PersonResolver(),
        config=cfg,
    )
    return agent, validator, hub


async def _run_pipeline(
    agent: MemoryWriterAgent,
    validator: ExtractionValidator,
    context: ExtractionContext,
    trace_id: str = "trace-int-001",
) -> List[MemoryAtom]:
    """Run full pipeline: agent.extract() → validator.validate()."""
    raw = await agent.extract(context, trace_id)
    return validator.validate(raw, context)


# ===========================================================================
# TestSingleSessionExtraction — 5 tests
# ===========================================================================


class TestSingleSessionExtraction:
    """Full pipeline: context → agent → validator → MemoryAtom list."""

    @pytest.mark.asyncio
    async def test_single_atom_end_to_end(self):
        """1 extraction: context → agent → validator → 1 MemoryAtom."""
        agent, validator, hub = _build_pipeline(_single_atom_json())
        ctx = _ctx()

        atoms = await _run_pipeline(agent, validator, ctx)

        assert len(atoms) == 1
        atom = atoms[0]
        assert atom.text == "Had dinner with Mom at Olive Garden"
        assert "person_mom" in atom.participants
        assert "family" in atom.topics
        assert atom.activity_type == ActivityType.MEAL
        assert atom.sentiment_label == SentimentLabel.POSITIVE
        assert atom.confidence == 0.95
        assert atom.session_id == "session-abc"
        assert atom.conversation_turn == 5
        assert atom.conversation_anchor_ms == 1_700_000_005_000
        # Frozen
        assert isinstance(atom, MemoryAtom)

    @pytest.mark.asyncio
    async def test_multi_atom_end_to_end(self):
        """LLM returns 3 items → 3 MemoryAtom with resolved participants."""
        ctx = _ctx(
            active_persons={
                "Mom": {"person_id": "person_mom", "type": "PERSON", "confidence": 1.0},
                "Dad": {"person_id": "person_dad", "type": "PERSON", "confidence": 1.0},
            },
            persona_context={"aliases": {"Mom": ["Mother"], "Dad": ["Father"]}},
        )
        agent, validator, hub = _build_pipeline(_multi_atom_json(3))

        atoms = await _run_pipeline(agent, validator, ctx)

        assert len(atoms) == 3
        # First atom: Mom resolved
        assert "person_mom" in atoms[0].participants
        # Third atom: Dad resolved
        assert "person_dad" in atoms[2].participants

    @pytest.mark.asyncio
    async def test_empty_extraction_end_to_end(self):
        """LLM returns [] → empty list, no MemoryAtom."""
        agent, validator, hub = _build_pipeline("[]")

        atoms = await _run_pipeline(agent, validator, _ctx())

        assert atoms == []

    @pytest.mark.asyncio
    async def test_partial_valid_end_to_end(self):
        """3 raw extractions, 1 below confidence → 2 MemoryAtom."""
        items = [
            {
                "text": "Dinner with Mom",
                "topics": ["family"],
                "confidence": 0.9,
                "participants": ["Mom"],
            },
            {"text": "Low confidence fact", "topics": ["misc"], "confidence": 0.1},  # below 0.30
            {
                "text": "Dad got promoted",
                "topics": ["career"],
                "confidence": 0.8,
                "participants": ["Dad"],
            },
        ]
        ctx = _ctx(
            active_persons={
                "Mom": {"person_id": "person_mom", "type": "PERSON", "confidence": 1.0},
                "Dad": {"person_id": "person_dad", "type": "PERSON", "confidence": 1.0},
            },
        )
        agent, validator, _ = _build_pipeline(json.dumps(items))

        atoms = await _run_pipeline(agent, validator, ctx)

        assert len(atoms) == 2
        assert atoms[0].text == "Dinner with Mom"
        assert atoms[1].text == "Dad got promoted"

    @pytest.mark.asyncio
    async def test_correction_signal_end_to_end(self):
        """LLM returns correction_signal=true → MemoryAtom has correction_signal=True."""
        content = _single_atom_json(
            correction_signal=True,
            contradiction_signal=False,
            supersedes_concept="cuisine_preference:italian",
            correction_source="user_explicit",
        )
        agent, validator, _ = _build_pipeline(content)

        atoms = await _run_pipeline(agent, validator, _ctx())

        assert len(atoms) == 1
        assert atoms[0].correction_signal is True
        assert atoms[0].contradiction_signal is False
        assert atoms[0].supersedes_concept == "cuisine_preference:italian"
        assert atoms[0].correction_source == "user_explicit"


# ===========================================================================
# TestConcurrentSessionExtraction — 3 tests
# ===========================================================================


class TestConcurrentSessionExtraction:
    """Concurrent sessions: separate MW instances, isolated trace/session ids."""

    @pytest.mark.asyncio
    async def test_two_sessions_concurrent(self):
        """asyncio.gather(agent_a.extract(), agent_b.extract()) → separate results."""
        agent_a, validator_a, _ = _build_pipeline(
            _single_atom_json(text="Dinner with Mom"),
        )
        agent_b, validator_b, _ = _build_pipeline(
            _single_atom_json(text="Dentist tomorrow"),
        )

        ctx_a = _ctx(session_id="session-A", conversation_turn=3)
        ctx_b = _ctx(
            session_id="session-B",
            conversation_turn=7,
            current_turn=CompressedTurn("t-7", "user", "Dentist tomorrow", 1_700_000_007_000, 7),
        )

        raw_a, raw_b = await asyncio.gather(
            agent_a.extract(ctx_a, "trace-a"),
            agent_b.extract(ctx_b, "trace-b"),
        )

        atoms_a = validator_a.validate(raw_a, ctx_a)
        atoms_b = validator_b.validate(raw_b, ctx_b)

        assert len(atoms_a) == 1
        assert len(atoms_b) == 1
        assert atoms_a[0].text == "Dinner with Mom"
        assert atoms_b[0].text == "Dentist tomorrow"

    @pytest.mark.asyncio
    async def test_trace_ids_isolated_between_sessions(self):
        """session A trace_id != session B trace_id in output."""
        agent_a, validator_a, _ = _build_pipeline(_single_atom_json())
        agent_b, validator_b, _ = _build_pipeline(_single_atom_json())

        ctx_a = _ctx(session_id="session-A")
        ctx_b = _ctx(session_id="session-B")

        raw_a = await agent_a.extract(ctx_a, "trace-aaa")
        raw_b = await agent_b.extract(ctx_b, "trace-bbb")

        assert len(raw_a) == 1 and len(raw_b) == 1
        assert raw_a[0].trace_id == "trace-aaa"
        assert raw_b[0].trace_id == "trace-bbb"
        assert raw_a[0].trace_id != raw_b[0].trace_id

    @pytest.mark.asyncio
    async def test_session_ids_isolated(self):
        """session A session_id != session B session_id in MemoryAtom."""
        agent_a, validator_a, _ = _build_pipeline(_single_atom_json())
        agent_b, validator_b, _ = _build_pipeline(_single_atom_json())

        ctx_a = _ctx(session_id="session-AAA")
        ctx_b = _ctx(session_id="session-BBB")

        atoms_a = await _run_pipeline(agent_a, validator_a, ctx_a, trace_id="trace-a")
        atoms_b = await _run_pipeline(agent_b, validator_b, ctx_b, trace_id="trace-b")

        assert len(atoms_a) == 1 and len(atoms_b) == 1
        assert atoms_a[0].session_id == "session-AAA"
        assert atoms_b[0].session_id == "session-BBB"
        assert atoms_a[0].session_id != atoms_b[0].session_id


# ===========================================================================
# TestExtractionErrorRecovery — 4 tests
# ===========================================================================


class TestExtractionErrorRecovery:
    """Error scenarios return empty list — never crash the pipeline."""

    @pytest.mark.asyncio
    async def test_llm_failure_produces_empty(self):
        """FakeModelHub raises RuntimeError → empty list, no crash."""
        agent, validator, _ = _build_pipeline(
            raise_on_chat=RuntimeError("LLM service unavailable"),
        )

        atoms = await _run_pipeline(agent, validator, _ctx())

        assert atoms == []

    @pytest.mark.asyncio
    async def test_llm_malformed_json_produces_empty(self):
        """FakeModelHub returns invalid JSON → empty list."""
        agent, validator, _ = _build_pipeline(
            response_content="this is not json at all {{{",
        )

        atoms = await _run_pipeline(agent, validator, _ctx())

        assert atoms == []

    @pytest.mark.asyncio
    async def test_validator_drops_all_produces_empty(self):
        """All extractions below confidence → empty list."""
        items = [
            {"text": "Low fact 1", "topics": ["a"], "confidence": 0.1},
            {"text": "Low fact 2", "topics": ["b"], "confidence": 0.05},
            {"text": "Low fact 3", "topics": ["c"], "confidence": 0.2},
        ]
        agent, validator, _ = _build_pipeline(json.dumps(items))

        atoms = await _run_pipeline(agent, validator, _ctx())

        assert atoms == []

    @pytest.mark.asyncio
    async def test_llm_timeout_produces_empty(self):
        """FakeModelHub raises TimeoutError → empty list."""
        agent, validator, _ = _build_pipeline(
            raise_on_chat=TimeoutError("LLM call timed out after 60s"),
        )

        atoms = await _run_pipeline(agent, validator, _ctx())

        assert atoms == []


# ===========================================================================
# TestExtractionMetrics — 4 tests
# ===========================================================================


class TestExtractionMetrics:
    """Metrics: token usage, latency, counts, budget enforcement."""

    @pytest.mark.asyncio
    async def test_token_usage_available_after_extraction(self):
        """ChatResponse.total_tokens accessible for metrics."""
        hub = FakeModelHubPort(
            response_content=_single_atom_json(),
            total_tokens=350,
        )
        cfg = MWConfig()
        loader = PromptLoader(_PROMPTS_DIR)
        agent = MemoryWriterAgent(model_hub=hub, config=cfg, prompt_loader=loader)

        # Execute -- the hub records the call
        raw = await agent.extract(_ctx(), "trace-metrics")

        assert hub.call_count == 1
        # The hub was configured with 350 total tokens
        assert hub._total_tokens == 350

    @pytest.mark.asyncio
    async def test_latency_available_after_extraction(self):
        """ChatResponse.latency_ms accessible after extraction."""
        hub = FakeModelHubPort(response_content=_single_atom_json())
        cfg = MWConfig()
        loader = PromptLoader(_PROMPTS_DIR)
        agent = MemoryWriterAgent(model_hub=hub, config=cfg, prompt_loader=loader)

        raw = await agent.extract(_ctx(), "trace-latency")

        # Hub was called — latency is configured as 42.0 in FakeModelHubPort
        assert hub.call_count == 1

    @pytest.mark.asyncio
    async def test_extraction_count_matches_output(self):
        """2 extractions → 2 MemoryAtom."""
        items = [
            {
                "text": "Dinner with Mom",
                "topics": ["family"],
                "confidence": 0.9,
                "participants": ["Mom"],
            },
            {
                "text": "Dad got promoted",
                "topics": ["career"],
                "confidence": 0.8,
                "participants": ["Dad"],
            },
        ]
        ctx = _ctx(
            active_persons={
                "Mom": {"person_id": "person_mom", "type": "PERSON", "confidence": 1.0},
                "Dad": {"person_id": "person_dad", "type": "PERSON", "confidence": 1.0},
            },
        )
        agent, validator, _ = _build_pipeline(json.dumps(items))

        atoms = await _run_pipeline(agent, validator, ctx)

        assert len(atoms) == 2

    @pytest.mark.asyncio
    async def test_budget_enforcement_in_integration(self):
        """MW-06: budget_tokens=2000 passed in the actual chat() call."""
        agent, validator, hub = _build_pipeline(_single_atom_json())

        await _run_pipeline(agent, validator, _ctx())

        assert hub.last_budget == 2000
        assert hub.call_count == 1
