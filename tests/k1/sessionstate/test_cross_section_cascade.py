"""
Cross-Section Cascade Integration Tests (Epic 4.5.5)
====================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 4.5 Cross-Section Dependency Tests
ISSUE: 4.5.5

Test full cross-section cascade across HOT, WARM, and LOCAL COLD tiers.

ARCHITECTURE REFERENCES:
- ADR-0017: SessionState 12-Section Tiered Design
- ADR-0017g: Single-Writer Concurrency Pattern
- ADR-0018: 3-Tier Eviction Strategy
- ADR-0020d: LOCAL COLD Tier (K1 SQLite)

HARDCORE INTEGRATION TEST REQUIREMENTS:
    1. ENTRY POINT: SessionStateFactory.create_standalone()
    2. ALL MUTATIONS: manager.mutate(section, operation, data)
    3. ALL READS: manager.get_section() or manager.get_snapshot()
    4. NO MOCKS: Real adapters, real SQLite LOCAL COLD

==============================================================================
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Generator

import pytest

from k1.sessionstate.factory import SessionStateFactory
from k1.sessionstate.manager import SessionStateManager


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """SQLite database path for LOCAL COLD."""
    return tmp_path / "cascade_cross_section.db"


@pytest.fixture
def session_id() -> str:
    """Unique session ID for each test."""
    return f"cascade-cross-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def session(db_path: Path, session_id: str) -> Generator[SessionStateManager, None, None]:
    """Create a standalone session manager with LOCAL COLD."""
    manager = SessionStateFactory.create_standalone(
        session_id=session_id,
        db_path=db_path,
        checkpoint_interval_s=0,
    )
    manager.start(restore_if_exists=False)
    yield manager
    if manager.is_running:
        manager.stop(checkpoint_before_stop=False)


def make_text(seed: str, length: int) -> str:
    """Create deterministic text of the requested length."""
    if not seed:
        seed = "x"
    repeat = (length // len(seed)) + 1
    return (seed * repeat)[:length]


def make_history_turn(turn_num: int) -> dict:
    """Create a large history_active turn payload."""
    return {
        "user_message": make_text(f"user-{turn_num}-", 900),
        "assistant_response": make_text(f"assistant-{turn_num}-", 1200),
    }


def make_belief_fact(index: int) -> dict:
    """Create a belief fact payload."""
    return {
        "subject": f"user-{index}",
        "predicate": "prefers",
        "obj": f"preference-{index}",
        "confidence": 0.9,
        "source": "test",
    }


def make_compressed_turn(turn_num: int) -> dict:
    """Create a compressed turn payload for history_recent."""
    return {
        "turn": {
            "turn_id": f"turn-{turn_num}",
            "turn_number": turn_num,
            "timestamp_ms": 1700000000000 + turn_num,
            "entities": [f"entity-{turn_num}"],
            "intents": ["inform"],
            "key_phrases": [f"phrase-{turn_num}"],
            "emotion": "neutral",
            "user_tokens": 120,
            "response_tokens": 180,
        }
    }


def make_summarized_turn(turn_num: int) -> dict:
    """Create a summarized turn payload for history_recent."""
    return {
        "turn": {
            "turn_id": f"summary-{turn_num}",
            "turn_number": turn_num,
            "timestamp_ms": 1700000100000 + turn_num,
            "summary": make_text(f"summary-{turn_num}-", 160),
            "primary_intent": "inform",
            "primary_entity": f"entity-{turn_num}",
        }
    }


def make_telemetry_turn(turn_num: int) -> dict:
    """Create telemetry turn data."""
    return {
        "turn_number": turn_num,
        "duration_ms": 100 + turn_num,
        "token_count": 500 + turn_num * 5,
        "had_error": False,
        "had_tool_call": turn_num % 2 == 0,
    }


class TestCrossSectionCascade:
    """Full cross-section cascade test across HOT, WARM, and LOCAL COLD."""

    def test_full_cross_section_cascade(self, session: SessionStateManager) -> None:
        """Fill HOT and WARM, trigger eviction to LOCAL COLD, verify integrity."""
        # ------------------------------------------------------------------
        # Step 1: Fill HOT tier via manager.mutate
        # ------------------------------------------------------------------
        for i in range(90):
            result = session.mutate(
                "control",
                "register_agent",
                {
                    "agent_id": f"agent-{i}",
                    "agent_type": "planner",
                    "capabilities": ["plan", "reason"],
                    "priority": i % 5,
                },
                estimated_bytes=100,
            )
            if not result.success:
                break

        for i in range(50):
            result = session.mutate(
                "beliefs_active",
                "add_fact",
                make_belief_fact(i),
                estimated_bytes=160,
            )
            assert result.success

        for i in range(8):
            turn_data = make_history_turn(i)
            result = session.mutate(
                "history_active",
                "append",
                turn_data,
                estimated_bytes=1000,
            )
            if not result.success:
                break

        for i in range(70):
            result = session.mutate(
                "scoreboard",
                "add_referent",
                {
                    "text": f"entity-{i}",
                    "entity_id": f"entity-{i}",
                    "entity_type": "thing",
                },
                estimated_bytes=80,
            )
            if not result.success:
                break

        for i in range(20):
            result = session.mutate(
                "clarifications",
                "request",
                {
                    "agent_id": "planner",
                    "question": make_text(f"clarify-{i}-", 120),
                    "blocking": False,
                },
                estimated_bytes=180,
            )
            if not result.success:
                break

        for i in range(6):
            result = session.mutate(
                "narrative_active",
                "create_thread",
                {
                    "title": make_text(f"thread-{i}-", 180),
                    "goal": make_text(f"goal-{i}-", 240),
                    "turn_number": i + 1,
                },
                estimated_bytes=600,
            )
            assert result.success

        result = session.mutate(
            "affective_now",
            "update",
            {
                "emotion": make_text("optimistic-", 2000),
                "intensity": 0.8,
                "source": make_text("cascade-source-", 2000),
                "turn_number": 1,
            },
            estimated_bytes=3600,
        )
        assert result.success

        result = session.mutate(
            "meta",
            "record_turn",
            {"turn_id": "turn-1"},
            estimated_bytes=64,
        )
        assert result.success

        snapshot = session.get_snapshot()
        assert snapshot.hot_utilization_pct >= 80.0

        # ------------------------------------------------------------------
        # Step 2: Fill WARM tier via manager.mutate
        # ------------------------------------------------------------------
        facts_batch_1 = [make_belief_fact(i) for i in range(50)]
        result = session.mutate(
            "beliefs_history",
            "accept_demoted",
            {"facts": facts_batch_1, "turn": 1},
            estimated_bytes=6000,
        )
        assert result.success

        facts_batch_2 = [make_belief_fact(i + 50) for i in range(50)]
        result = session.mutate(
            "beliefs_history",
            "accept_demoted",
            {"facts": facts_batch_2, "turn": 2},
            estimated_bytes=4000,
        )
        assert result.success

        for i in range(20):
            result = session.mutate(
                "history_recent",
                "add_compressed",
                make_compressed_turn(i),
                estimated_bytes=700,
            )
            assert result.success

        for i in range(10):
            result = session.mutate(
                "history_recent",
                "add_summarized",
                make_summarized_turn(i),
                estimated_bytes=260,
            )
            assert result.success

        long_summary = make_text("session-summary-", 10000)
        result = session.mutate(
            "history_recent",
            "set_session_summary",
            {"summary": long_summary},
            estimated_bytes=1000,
        )
        assert result.success

        for i in range(30):
            result = session.mutate(
                "persona",
                "add_vocabulary",
                {
                    "user_term": f"term-{i}",
                    "system_term": f"meaning-{i}",
                    "context": "cascade",
                },
                estimated_bytes=140,
            )
            assert result.success

        for i in range(20):
            result = session.mutate(
                "telemetry",
                "record_turn",
                make_telemetry_turn(i),
                estimated_bytes=120,
            )
            assert result.success

        snapshot = session.get_snapshot()
        assert snapshot.hot_utilization_pct >= 75.0
        assert snapshot.warm_utilization_pct >= 65.0
        assert snapshot.total_utilization_pct >= 70.0

        # ------------------------------------------------------------------
        # Step 3: Archive WARM sections to LOCAL COLD and clear via manager
        # ------------------------------------------------------------------
        local_cold = session.get_local_cold()
        warm_sections = [
            "beliefs_history",
            "history_recent",
            "persona",
            "telemetry",
        ]
        for section_name in warm_sections:
            section = session.get_section(section_name)
            archive_result = local_cold.archive(
                section_name,
                section.to_flatbuffer(),
                metadata={"reason": "cascade_archive", "section": section_name},
            )
            assert archive_result.success

            clear_result = session.mutate(
                section_name,
                "clear",
                {},
                estimated_bytes=-section.get_size_bytes(),
            )
            assert clear_result.success

        archives = local_cold.list_archives()
        assert len(archives) >= len(warm_sections)

        # ------------------------------------------------------------------
        # Step 4: HOT tier data integrity checks
        # ------------------------------------------------------------------
        control = session.get_section("control")
        assert len(control.list_agents()) > 0

        beliefs_active = session.get_section("beliefs_active")
        assert beliefs_active.get_fact_count() > 0

        history_active = session.get_section("history_active")
        assert history_active.count() > 0

        scoreboard = session.get_section("scoreboard")
        assert len(scoreboard.list_referents()) > 0

        narrative_active = session.get_section("narrative_active")
        assert narrative_active.primary_thread is not None
