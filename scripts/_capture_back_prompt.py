"""Extract the real Back system prompt using test fixtures."""

import asyncio


async def main():
    from k1.concierge.bus.builders import build_task_dispatch
    from k1.concierge.bus.setup import create_poc_bus
    from k1.concierge.llm.test_model_hub_bridge import TestModelHubBridge
    from k1.concierge.llm.types import ConciergeModelResponse, FinishReason, ToolCallResult
    from k1.concierge.tools.dispatcher import create_back_dispatcher
    from k1.concierge.tools.implementations import ToolContext
    from k1.sessionstate.factory import SessionStateFactory
    import k1.concierge.actors.back as back_mod
    from pathlib import Path

    bus = create_poc_bus(capture=True)
    session_state = SessionStateFactory.create_for_testing()
    session_state.start()

    model = TestModelHubBridge()
    model.set_response_sequence(
        "back",
        "",
        [
            ConciergeModelResponse(
                tool_calls=[
                    ToolCallResult(
                        id="call-1",
                        name="recall_memory",
                        arguments={"query": "test", "memory_types": ["semantic"], "max_results": 1},
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                model_id="test",
            ),
            ConciergeModelResponse(
                tool_calls=[
                    ToolCallResult(
                        id="call-2",
                        name="submit_result",
                        arguments={
                            "result_type": "complete",
                            "final_answer": "done",
                            "results": [],
                            "artifacts_created": [],
                        },
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                model_id="test",
            ),
        ],
    )

    ctx = ToolContext(session_manager=session_state, actor="back")
    dispatcher = create_back_dispatcher(tier="simple", ctx=ctx, bus=bus)
    envelope = build_task_dispatch(
        {
            "task_id": "prompt-capture-1",
            "tier": "LOW",
            "intents": [
                {
                    "action": "schedule dentist for Riley next Monday 3pm",
                    "domain": "calendar",
                    "params": {"start": "2026-06-15T15:00:00"},
                }
            ],
        }
    )

    try:
        await back_mod.back_handler(
            envelope=envelope,
            model=model,
            ss=session_state,
            bus=bus,
            tool_dispatcher=dispatcher,
        )
    finally:
        session_state.stop()

    # Extract system prompt from model request
    request = model.inner.calls_for("back", "")[0]
    prompt = request.system_prompt

    Path("data/_live_back_prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"Captured {len(prompt)} chars to data/_live_back_prompt.txt")

    # Show SESSION CONTEXT section
    idx = prompt.find("== SESSION CONTEXT ==")
    if idx >= 0:
        section = prompt[idx:]
        next_section = section.find("\n==", 30)
        if next_section > 0:
            section = section[:next_section]
        print()
        print("=== LIVE SESSION CONTEXT ===")
        print(section[:1200])


asyncio.run(main())
