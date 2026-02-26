"""Quick end-to-end smoke test for the K1 POC demo coordinator."""

import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


async def smoke_test() -> None:
    from poc.k1_poc.demo.coordinator import get_k1_demo_coordinator, reset_coordinator

    # Use real LLM if GOOGLE_API_KEY is set, otherwise test adapter
    use_test = not os.getenv("GOOGLE_API_KEY")
    reset_coordinator()
    coord = get_k1_demo_coordinator(test_mode=use_test)

    # Boot
    ok = await coord.initialize_system()
    print(f"\n=== Boot OK: {ok} ===")
    if not ok:
        sys.exit(1)

    # Simulate a turn
    from poc.k1_poc.bus.builders import build_user_input

    env = build_user_input(
        payload={
            "text": "hello",
            "member": "Alex",
            "device": "alex_phone",
            "turn": 1,
        },
    )
    logger.info("SMOKE: publishing user.input...")
    coord.bus.publish(env)
    logger.info("SMOKE: published, waiting for response...")

    oc = coord.get_output_channel()
    timeout = 30.0 if not use_test else 5.0
    try:
        resp = await asyncio.wait_for(
            oc.wait_for_response(timeout=timeout),
            timeout=timeout,
        )
        logger.info("SMOKE: got response: %s", repr(resp[:80]))
    except asyncio.TimeoutError:
        logger.error("SMOKE: TIMEOUT waiting for response")
        resp = ""

    fsm_state = coord.fsm.state.name
    timeline_count = len(coord.timeline)
    logger.info("SMOKE: FSM=%s timeline=%d", fsm_state, timeline_count)

    await coord.shutdown_system()

    # Verdict
    print("\n=== SMOKE TEST RESULT ===")
    print(f"  FSM state after turn:  {fsm_state}")
    print(f"  Response text:         {repr(resp[:80])}")
    print(f"  Timeline entries:      {timeline_count}")

    if fsm_state == "LISTENING" and resp:
        print("  VERDICT: PASS")
    else:
        print("  VERDICT: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(smoke_test())
