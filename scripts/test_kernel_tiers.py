"""Drive the K1 kernel end-to-end for LOW and MED tier paths.

Boots the kernel once per tier, publishes a user_input envelope,
and captures the final response + any dispatch events observed on
the bus so we can see which path (Fabric LOW vs Orchestrator MED)
actually executed.

Usage (from repo root, with .env loaded):

    python scripts/test_kernel_tiers.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# ── Load .env if present ─────────────────────────────────────────────
_ENV = Path("poc/chat_experience_poc/.env")
if _ENV.exists():
    for line in _ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k in {"GOOGLE_API_KEY", "GOOGLE_MODEL", "LLM_PROVIDER"} and v:
            os.environ.setdefault(k, v)

from k1.concierge.bus.builders import build_user_input
from k1.concierge.bus.topics import (
    TOPIC_FINAL_RESPONSE,
    TOPIC_RESPONSE_STREAM,
)
from k1.concierge.config.kernel import KernelConfig
from k1.kernel.bootstrap import start_kernel, stop_kernel

logging.basicConfig(
    level=os.environ.get("K1_LOG_LEVEL", "WARNING"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

# Force DEBUG on model hub + google plugin + concierge react loop so we can
# trace how each request is dispatched and what the provider returns.
for _name in (
    "k1.model_hub",
    "k1.model_hub.services.request_router",
    "k1.model_hub.services.provider_dispatcher",
    "k1.model_hub.plugins.google_plugin",
    "k1.concierge.react.loop",
):
    logging.getLogger(_name).setLevel(logging.DEBUG)

# Topics that signal tier routing so we can observe which path fired.
TIER_TOPICS = [
    "k1.orchestration.task.dispatch.v1",  # LOW or MED/HIGH dispatch record
    "k1.orchestration.task.result.v1",
    "k1.fabric.capability.execute.v1",
    "k1.fabric.capability.result.v1",
    "k1.orchestrator.plan.requested.v1",
    "k1.planner.plan.ready.v1",
]


def _decode(env) -> dict:
    p = env.payload
    if isinstance(p, (bytes, bytearray)):
        try:
            return json.loads(p)
        except Exception:
            return {"_raw": p.decode("utf-8", errors="replace")}
    return p if isinstance(p, dict) else {"_raw": str(p)}


async def run_tier(tier: str, prompt: str, timeout_s: float = 45.0) -> dict:
    """Boot kernel with given tool_tier, send prompt, collect response."""
    print("\n" + "=" * 60)
    print(f"  TIER TEST: tool_tier={tier!r}")
    print(f"  Prompt:   {prompt!r}")
    print("=" * 60)

    cfg = KernelConfig(model_mode="hub", tool_tier=tier)
    t0 = time.monotonic()
    runtime = await start_kernel(cfg)
    boot_s = time.monotonic() - t0
    print(f"  [ok] Booted in {boot_s:.2f}s   session={runtime._session_id}")

    response_q: asyncio.Queue[str] = asyncio.Queue()
    stream_chunks: list[str] = []
    tier_events: list[tuple[str, dict]] = []

    def _on_final(env):
        payload = _decode(env)
        response_q.put_nowait(
            payload.get("text", "") if isinstance(payload, dict) else str(payload)
        )

    def _on_stream(env):
        payload = _decode(env)
        if isinstance(payload, dict):
            txt = payload.get("text", "")
            if txt:
                stream_chunks.append(txt)

    def _mk_tier_observer(topic: str):
        def _h(env):
            tier_events.append((topic, _decode(env)))
        return _h

    bus = runtime.bus
    subs = [
        bus.subscribe(TOPIC_FINAL_RESPONSE, _on_final),
        bus.subscribe(TOPIC_RESPONSE_STREAM, _on_stream),
    ]
    for t in TIER_TOPICS:
        try:
            subs.append(bus.subscribe(t, _mk_tier_observer(t)))
        except Exception as e:  # topic might not be registered
            print(f"  (skip subscribe {t}: {e})")

    # Fire the turn
    print(f"  -> publishing user_input ...")
    turn_t0 = time.monotonic()
    bus.publish(build_user_input({"text": prompt}))

    final_text = ""
    try:
        final_text = await asyncio.wait_for(response_q.get(), timeout=timeout_s)
    except asyncio.TimeoutError:
        final_text = "[TIMEOUT]"
    turn_s = time.monotonic() - turn_t0

    # Summarize
    print(f"  [ok] Turn latency: {turn_s:.2f}s")
    try:
        print(f"    FSM state:    {runtime.fsm.state.name}")
    except Exception:
        pass
    print(f"    Stream chunks: {len(stream_chunks)}")
    print(f"    Tier events observed: {len(tier_events)}")
    for topic, payload in tier_events[:10]:
        short = {k: v for k, v in (payload or {}).items() if k in {"tier", "task_id", "intent", "capability", "status"}}
        print(f"      - {topic}  {short}")

    preview = final_text.strip().replace("\n", " ")
    if len(preview) > 200:
        preview = preview[:200] + "..."
    print(f"    Response:     {preview}")

    # Cleanup
    for s in subs:
        try:
            bus.unsubscribe(s)
        except Exception:
            pass
    await stop_kernel(runtime)
    print("  [ok] Shutdown clean")

    return {
        "tier": tier,
        "boot_s": boot_s,
        "turn_s": turn_s,
        "final": final_text,
        "tier_events": tier_events,
        "fsm_state": getattr(getattr(runtime, "fsm", None), "state", None),
    }


async def main() -> int:
    if not os.environ.get("GOOGLE_API_KEY"):
        print("ERROR: GOOGLE_API_KEY not set (checked .env at poc/chat_experience_poc/.env).")
        return 1

    low = await run_tier("LOW", "In one sentence, what is the capital of France?")
    med = await run_tier(
        "MED",
        "Plan a 3-step outline for writing a short blog post about hexagonal architecture.",
    )

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    for r in (low, med):
        print(
            f"  tier={r['tier']:<4}  boot={r['boot_s']:.2f}s  turn={r['turn_s']:.2f}s  "
            f"events={len(r['tier_events'])}  resp_chars={len(r['final'])}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
