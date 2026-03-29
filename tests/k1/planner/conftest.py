"""Shared test fixtures for Planner tests (SS30.3, SS30.4).

Provides pytest fixtures that wire all 7 test adapters for use in
integration tests. The composite ``wired_planner`` fixture will use
``PlannerFactory.create_for_testing()`` once Issue 6.3.3 is implemented.

Individual adapter fixtures are immediately usable for unit tests.

File location: tests/k1/planner/conftest.py
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from k1.fabric.types import CapabilityContract, ScoredCapability
from k1.planner.types import HubResponse
from tests.k1.planner.adapters.test_bridge_adapter import TestBridgeAdapter
from tests.k1.planner.adapters.test_delta_adapter import TestDeltaAdapter
from tests.k1.planner.adapters.test_event_adapter import TestEventAdapter
from tests.k1.planner.adapters.test_fabric_retrieval_adapter import (
    TestFabricRetrievalAdapter,
)
from tests.k1.planner.adapters.test_llm_adapter import TestLLMAdapter
from tests.k1.planner.adapters.test_mailbox_adapter import TestMailboxAdapter
from tests.k1.planner.adapters.test_state_read_adapter import TestStateReadAdapter

# =========================================================================
# Constants: preset data for test adapters
# =========================================================================

DEFAULT_STAGE_RESPONSES: Dict[str, HubResponse] = {
    "SKETCH": HubResponse(
        result={
            "content": (
                '{"steps": [{"id": "s1", "capability": "tool.search",'
                ' "description": "Search for information",'
                ' "params": {"query": "test"}}],'
                ' "reasoning": "Single step plan for testing"}'
            ),
        },
        metadata={
            "usage": {"prompt_tokens": 150, "completion_tokens": 80, "total_tokens": 230},
            "latency_ms": 45,
            "model_id": "test-model-v1",
        },
    ),
    "EXPAND": HubResponse(
        result={
            "content": (
                '{"steps": [{"id": "s1", "capability": "tool.search",'
                ' "params": {"query": "test"}, "deps": [],'
                ' "output_schema": {"type": "object"},'
                ' "timeout_ms": 5000}],'
                ' "dependencies": {}}'
            ),
        },
        metadata={
            "usage": {"prompt_tokens": 200, "completion_tokens": 120, "total_tokens": 320},
            "latency_ms": 60,
            "model_id": "test-model-v1",
        },
    ),
    "VALIDATE": HubResponse(
        result={
            "content": ('{"verdict": "approved",' ' "issues": [],' ' "confidence": 0.95}'),
        },
        metadata={
            "usage": {"prompt_tokens": 180, "completion_tokens": 40, "total_tokens": 220},
            "latency_ms": 30,
            "model_id": "test-model-v1",
        },
    ),
}
"""Stage responses with valid JSON matching each stage's OUTPUT_SCHEMA.

SKETCH: SS6.3.1 -- steps array + reasoning
EXPAND: SS7.3.1 -- enriched steps + dependencies
VALIDATE: SS8.3.1 -- verdict + issues + confidence
"""


def _make_sample_capability(
    name: str,
    domain: str = "general",
    score: float = 0.9,
) -> ScoredCapability:
    """Create a sample ScoredCapability for test presets."""
    return ScoredCapability(
        contract=CapabilityContract(
            name=name,
            version="1.0.0",
            domain=[domain],
            description=f"Test capability: {name}",
        ),
        score=score,
    )


SAMPLE_CAPABILITIES: List[ScoredCapability] = [
    _make_sample_capability("tool.search", "information", 0.95),
    _make_sample_capability("tool.calendar", "scheduling", 0.90),
    _make_sample_capability("tool.reminder", "memory", 0.85),
    _make_sample_capability("tool.weather", "information", 0.80),
    _make_sample_capability("tool.calculator", "math", 0.75),
]
"""5 sample capabilities for TestFabricRetrievalAdapter."""


SAMPLE_SECTIONS: Dict[str, Dict[str, Any]] = {
    "beliefs_active": {
        "user_name": "Alice",
        "preferences": {"language": "en", "timezone": "UTC"},
    },
    "control": {
        "safety_band": "GREEN",
        "max_steps": 10,
    },
    "history_recent": {
        "entries": [
            {"role": "user", "content": "Plan a birthday party"},
            {"role": "assistant", "content": "I will create a plan for that."},
        ],
    },
}
"""3 preset sections for TestStateReadAdapter (beliefs_active, control, history_recent)."""


SAMPLE_RECALL: Dict[str, Any] = {
    "facts": [
        {"content": "User prefers outdoor activities", "source": "long_term_memory"},
        {"content": "Last birthday was at a park", "source": "episodic_memory"},
    ],
    "scores": [0.92, 0.87],
}
"""Preset recall data for TestBridgeAdapter."""


# =========================================================================
# Individual adapter fixtures
# =========================================================================


@pytest.fixture
def test_mailbox() -> TestMailboxAdapter:
    """Fresh TestMailboxAdapter with empty queue."""
    return TestMailboxAdapter()


@pytest.fixture
def test_llm() -> TestLLMAdapter:
    """TestLLMAdapter with DEFAULT_STAGE_RESPONSES for SKETCH/EXPAND/VALIDATE."""
    return TestLLMAdapter(stage_responses=dict(DEFAULT_STAGE_RESPONSES))


@pytest.fixture
def test_fabric() -> TestFabricRetrievalAdapter:
    """TestFabricRetrievalAdapter with 5 SAMPLE_CAPABILITIES."""
    return TestFabricRetrievalAdapter(preset_capabilities=list(SAMPLE_CAPABILITIES))


@pytest.fixture
def test_state() -> TestStateReadAdapter:
    """TestStateReadAdapter with SAMPLE_SECTIONS (beliefs, control, history)."""
    return TestStateReadAdapter(preset_sections=dict(SAMPLE_SECTIONS))


@pytest.fixture
def test_bridge() -> TestBridgeAdapter:
    """TestBridgeAdapter with SAMPLE_RECALL, online by default."""
    return TestBridgeAdapter(preset_recall=dict(SAMPLE_RECALL))


@pytest.fixture
def test_delta() -> TestDeltaAdapter:
    """Fresh TestDeltaAdapter with empty capture."""
    return TestDeltaAdapter()


@pytest.fixture
def test_event() -> TestEventAdapter:
    """Fresh TestEventAdapter with empty capture."""
    return TestEventAdapter()


@pytest.fixture
def all_adapters(
    test_mailbox: TestMailboxAdapter,
    test_llm: TestLLMAdapter,
    test_fabric: TestFabricRetrievalAdapter,
    test_state: TestStateReadAdapter,
    test_bridge: TestBridgeAdapter,
    test_delta: TestDeltaAdapter,
    test_event: TestEventAdapter,
) -> Dict[str, Any]:
    """Dict of all 7 test adapters keyed by port name.

    Useful for passing to PlannerFactory.create_for_testing() once
    implemented (Issue 6.3.3).
    """
    return {
        "mailbox": test_mailbox,
        "llm": test_llm,
        "fabric": test_fabric,
        "state": test_state,
        "bridge": test_bridge,
        "delta": test_delta,
        "event": test_event,
    }


# =========================================================================
# Composite wired_planner fixture
# =========================================================================
# PlannerFactory.create_for_testing() is defined in Issue 6.3.3 (Epic 6.3).
# Once PlannerFactory exists, uncomment the wired_planner fixture below.
# Until then, individual adapter fixtures are available for unit tests.
# =========================================================================

# @pytest.fixture
# async def wired_planner(
#     test_mailbox: TestMailboxAdapter,
#     test_llm: TestLLMAdapter,
#     test_fabric: TestFabricRetrievalAdapter,
#     test_state: TestStateReadAdapter,
#     test_bridge: TestBridgeAdapter,
#     test_delta: TestDeltaAdapter,
#     test_event: TestEventAdapter,
# ) -> Tuple[PlannerAgent, Dict[str, Any]]:
#     """Fully wired PlannerAgent with all 7 test adapters.
#
#     Returns (PlannerAgent, adapters_dict) for test access to both
#     the agent and the capture adapters.
#
#     Depends on: PlannerFactory.create_for_testing() (Issue 6.3.3).
#     """
#     from k1.planner.factory import PlannerFactory
#
#     agent = await PlannerFactory.create_for_testing(
#         config=PlannerConfig(),
#         mailbox=test_mailbox,
#         llm=test_llm,
#         fabric=test_fabric,
#         state=test_state,
#         bridge=test_bridge,
#         delta=test_delta,
#         event=test_event,
#     )
#     adapters = {
#         "mailbox": test_mailbox,
#         "llm": test_llm,
#         "fabric": test_fabric,
#         "state": test_state,
#         "bridge": test_bridge,
#         "delta": test_delta,
#         "event": test_event,
#     }
#     return (agent, adapters)
