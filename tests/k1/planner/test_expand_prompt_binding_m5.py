"""M5 tests for EXPAND prompt binding and activity profile enrichment."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from k1.planner.stages.expand_service import ExpandService, validate_prompt_binding


class FakeLLMPort:
    async def execute(self, request: Any) -> Any:
        raise AssertionError("LLM is not used by these tests")


class FakeToolRouter:
    @property
    def tool_call_count(self) -> int:
        return 0

    def reset(self) -> None:
        return None


class FakeCapabilityContract:
    def __init__(
        self,
        name: str,
        *,
        domain: Optional[List[str]] = None,
        activity_profile: Optional[str] = None,
    ) -> None:
        self.name = name
        self.domain = domain or []
        self.activity_profile = activity_profile
        self.has_side_effects = False
        self.avg_latency_ms = 0


class FakePromptContract:
    def __init__(
        self,
        name: str,
        *,
        domain: Optional[List[str]] = None,
        activity_profile: Optional[str] = None,
        compatible_tools: Optional[List[str]] = None,
    ) -> None:
        self.name = name
        self.domain = domain or []
        self.activity_profile = activity_profile
        self.compatible_tools = compatible_tools or []
        self.compatible_agents: List[str] = []


class FakeScoredPrompt:
    def __init__(self, contract: FakePromptContract, score: float) -> None:
        self.contract = contract
        self.score = score


class FakeRetrievalResult:
    def __init__(self, capabilities: List[FakeScoredPrompt]) -> None:
        self.capabilities = capabilities


def _svc(
    prompt_inventory: Optional[Dict[str, Any] | set[str]] = None,
) -> ExpandService:
    return ExpandService(
        llm_port=FakeLLMPort(),
        tool_router=FakeToolRouter(),
        prompt_inventory=prompt_inventory or {},
    )


def test_valid_prompt_template_from_find_prompts_is_preserved() -> None:
    result = validate_prompt_binding(
        requested_template="calendar_activity_v1",
        capability_name="tool.execute.calendar.create_event",
        discovered_prompts=[
            {
                "name": "calendar_activity_v1",
                "domain": ["calendar"],
                "score": 0.95,
            }
        ],
        prompt_inventory=set(),
    )

    assert result.state == "valid"
    assert result.resolved_name == "calendar_activity_v1"


def test_hallucinated_prompt_cleared_even_when_compatible_prompt_is_discovered() -> None:
    result = validate_prompt_binding(
        requested_template="calendar_expert_v99",
        capability_name="tool.execute.calendar.create_event",
        discovered_prompts=[
            {
                "name": "calendar_activity_v1",
                "domain": ["calendar"],
                "compatible_tools": ["tool.execute.calendar.create_event"],
                "score": 0.95,
            }
        ],
        prompt_inventory=set(),
    )

    assert result.state == "cleared"
    assert result.resolved_name is None


def test_hallucinated_prompt_cleared_when_only_domain_matches() -> None:
    result = validate_prompt_binding(
        requested_template="calendar_expert_v99",
        capability_name="tool.execute.calendar.create_event",
        discovered_prompts=[
            {
                "name": "calendar_activity_v1",
                "domain": ["calendar"],
                "score": 0.95,
            }
        ],
        prompt_inventory=set(),
    )

    assert result.state == "cleared"
    assert result.resolved_name is None


def test_inventory_backed_prompt_is_preserved_without_find_prompts() -> None:
    result = validate_prompt_binding(
        requested_template="calendar_activity_v1",
        capability_name="tool.execute.calendar.create_event",
        discovered_prompts=[],
        prompt_inventory={"calendar_activity_v1"},
    )

    assert result.state == "missing_inventory"
    assert result.resolved_name == "calendar_activity_v1"


def test_unverified_prompt_is_cleared_without_find_prompts_or_inventory() -> None:
    result = validate_prompt_binding(
        requested_template="calendar_expert_v99",
        capability_name="tool.execute.calendar.create_event",
        discovered_prompts=[],
        prompt_inventory=set(),
    )

    assert result.state == "cleared"
    assert result.resolved_name is None


def test_no_prompt_template_is_noop_valid() -> None:
    result = validate_prompt_binding(
        requested_template=None,
        capability_name="tool.execute.calendar.create_event",
        discovered_prompts=[],
        prompt_inventory=set(),
    )

    assert result.state == "valid"
    assert result.resolved_name is None


def test_enrich_steps_uses_exact_discovered_prompt_activity_profile() -> None:
    svc = _svc()
    discovered = FakeRetrievalResult(
        [
            FakeScoredPrompt(
                FakePromptContract(
                    "calendar_activity_v1",
                    domain=["calendar"],
                    activity_profile="calendar.v1",
                    compatible_tools=["tool.execute.calendar.create_event"],
                ),
                0.95,
            )
        ]
    )
    llm_steps = [
        {
            "id": "s1",
            "capability": "tool.execute.calendar.create_event",
            "params": {},
            "prompt_template": "calendar_activity_v1",
        }
    ]

    steps = svc._enrich_steps(llm_steps, {"prompts": [discovered]})

    assert steps[0].prompt_template == "calendar_activity_v1"
    assert steps[0].activity_profile == "calendar.v1"


def test_enrich_steps_clears_unverified_prompt(caplog: Any) -> None:
    svc = _svc()
    llm_steps = [
        {
            "id": "s1",
            "capability": "tool.execute.calendar.create_event",
            "params": {},
            "prompt_template": "calendar_expert_v99",
        }
    ]

    with caplog.at_level(logging.WARNING):
        steps = svc._enrich_steps(llm_steps, {"prompts": []})

    assert steps[0].prompt_template is None
    assert "EXPAND prompt binding cleared" in caplog.text


def test_enrich_steps_uses_contract_activity_profile_without_llm_override() -> None:
    svc = _svc()
    contract = FakeCapabilityContract(
        "tool.execute.calendar.create_event",
        activity_profile="calendar.v1",
    )
    llm_steps = [
        {
            "id": "s1",
            "capability": "tool.execute.calendar.create_event",
            "params": {},
        }
    ]

    steps = svc._enrich_steps(llm_steps, {"schema": [contract], "prompts": []})

    assert steps[0].activity_profile == "calendar.v1"


def test_enrich_steps_uses_inventory_activity_profile_for_preserved_prompt() -> None:
    svc = _svc(
        {
            "calendar_activity_v1": {
                "domain": ["calendar"],
                "activity_profile": "calendar.v1",
            }
        }
    )
    llm_steps = [
        {
            "id": "s1",
            "capability": "tool.execute.calendar.create_event",
            "params": {},
            "prompt_template": "calendar_activity_v1",
        }
    ]

    steps = svc._enrich_steps(llm_steps, {"prompts": []})

    assert steps[0].prompt_template == "calendar_activity_v1"
    assert steps[0].activity_profile == "calendar.v1"
