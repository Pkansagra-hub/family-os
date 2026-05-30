"""
probe_back_profiles.py -- Direct Back handler probe.

Boots real kernel components (SessionState, Fabric, prompt contracts)
and drives back_handler directly with a calendar + reminder task.
Prints:
  1. Fabric startup — templates loaded (shared + session scope)
  2. Profile selection telemetry (task_id, profile_ids, confidence, evidence)
  3. Full Back SYSTEM PROMPT with == EXECUTION PROFILES == block
  4. Planner EXPAND step bindings (if triggered via a HIGH-tier variant)
  5. react_loop iteration trace

Usage:
    cd d:\\familyos
    python scripts/probe_back_profiles.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
import textwrap

# ---------------------------------------------------------------------------
# Logging — capture everything we care about, silence the dequeue spam
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(name)-55s %(levelname)-7s  %(message)s",
    stream=sys.stdout,
)
logging.getLogger("k1.orchestrator.orchestration.orchestrator_service").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

import k1.concierge.actors.back as back_mod
from k1.concierge.bus.builders import build_task_dispatch
from k1.concierge.bus.setup import create_poc_bus
from k1.concierge.llm.test_model_hub_bridge import TestModelHubBridge
from k1.concierge.llm.types import ConciergeModelResponse, FinishReason, ToolCallResult
from k1.concierge.tools.dispatcher import create_back_dispatcher
from k1.concierge.tools.implementations import ToolContext
from k1.sessionstate.factory import SessionStateFactory

DIVIDER = "=" * 80


def _make_model() -> TestModelHubBridge:
    """
    Deterministic sequence:
      iter 0 → recall_memory   (satisfies no-work guard)
      iter 1 → submit_result(complete)
    """
    model = TestModelHubBridge()
    model.set_response_sequence(
        "back",
        "",
        [
            ConciergeModelResponse(
                tool_calls=[
                    ToolCallResult(
                        id="probe-recall",
                        name="recall_memory",
                        arguments={
                            "query": "calendar soccer",
                            "memory_types": ["semantic"],
                            "max_results": 2,
                        },
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                model_id="probe-model",
            ),
            ConciergeModelResponse(
                tool_calls=[
                    ToolCallResult(
                        id="probe-submit",
                        name="submit_result",
                        arguments={
                            "result_type": "complete",
                            "final_answer": "Calendar event and reminder created.",
                            "results": [],
                            "artifacts_created": [],
                        },
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                model_id="probe-model",
            ),
        ],
    )
    return model


async def run_probe() -> None:
    print(f"\n{DIVIDER}")
    print("  PROBE: back_handler direct invocation — Activity Profile Injection")
    print(DIVIDER)

    # 1. Boot real SessionState
    session_state = SessionStateFactory.create_for_testing()
    session_state.start()
    bus = create_poc_bus(capture=True)
    model = _make_model()

    # 2. Build task — calendar + reminder (dual domain to test profile selection)
    task_payload = {
        "task_id": "probe-task-calendar-001",
        "tier": "LOW",
        "safety_band": "AMBER",
        "intents": [
            {
                "action": "create a calendar event for Riley soccer practice tomorrow at 5pm",
                "domain": "calendar",
                "params": {
                    "title": "Riley Soccer Practice",
                    "start": "2026-05-18T17:00:00",
                    "duration_minutes": 60,
                    "attendees": ["Riley"],
                },
            },
            {
                "action": "add a reminder 1 hour before the event",
                "domain": "reminders",
                "params": {"offset_minutes": -60, "event_ref": "Riley Soccer Practice"},
            },
        ],
    }
    envelope = build_task_dispatch(task_payload)

    # 3. Build dispatcher
    ctx = ToolContext(session_manager=session_state, actor="back")
    dispatcher = create_back_dispatcher(tier="simple", ctx=ctx, bus=bus)

    # 4. Intercept the system_prompt passed to the model so we can print it
    original_call = model.inner.__class__.call if hasattr(model.inner.__class__, "call") else None
    captured_system_prompt: list[str] = []

    _orig_react = back_mod.react_loop  # type: ignore[attr-defined]

    async def _intercepting_react(*, system_prompt: str, **kwargs):
        captured_system_prompt.append(system_prompt)
        return await _orig_react(system_prompt=system_prompt, **kwargs)

    back_mod.react_loop = _intercepting_react  # type: ignore[attr-defined]

    print(f"\n[1] Dispatching task: {task_payload['task_id']}")
    print(f"    intents: {[i['domain'] for i in task_payload['intents']]}")

    try:
        result = await back_mod.back_handler(
            envelope=envelope,
            model=model,
            ss=session_state,
            bus=bus,
            tool_dispatcher=dispatcher,
        )
    finally:
        back_mod.react_loop = _orig_react  # type: ignore[attr-defined]
        session_state.stop()

    # 5. Print result
    print(f"\n[2] back_handler result: status={result.status}")

    # 6. Print full system prompt
    if captured_system_prompt:
        prompt = captured_system_prompt[0]
        print(f"\n{DIVIDER}")
        print(f"[3] FULL BACK SYSTEM PROMPT  ({len(prompt)} chars)")
        print(DIVIDER)
        # Find and highlight the EXECUTION PROFILES block
        ep_start = prompt.find("== EXECUTION PROFILES ==")
        if ep_start != -1:
            ep_end = prompt.find("\n\n", ep_start)
            ep_block = (
                prompt[ep_start:ep_end] if ep_end != -1 else prompt[ep_start : ep_start + 800]
            )
            print("\n>>> EXECUTION PROFILES block injected at char", ep_start, "<<<")
            print(ep_block)
            print("\n>>> Full prompt (truncated to 4000 chars for readability) <<<")
            print(textwrap.shorten(prompt, width=4000, placeholder="\n...[truncated]"))
        else:
            print("WARNING: No '== EXECUTION PROFILES ==' found in system prompt!")
            print(prompt[:2000])
    else:
        print("WARNING: system_prompt was not captured!")


if __name__ == "__main__":
    asyncio.run(run_probe())
