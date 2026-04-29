"""kernel_smoke_drive.py — End-to-end smoke for Concierge / Orchestrator /
Fabric / Planner / MemoryWriter without spending a cent.

Run:
    $env:PYTHONPATH="D:\\familyos"; $env:PYTHONIOENCODING="utf-8"
    python -m scripts.kernel_smoke_drive

What it does
------------
1. Boots the kernel in canned ("test") mode (TestModelHubBridge).
2. Subscribes to every interesting bus topic and counts events.
3. Drives N scripted user inputs through the bus.
4. Snapshots the SessionState (history_active) to prove Fabric writes.
5. Inspects MemoryWriterService dispatcher buffer + flush log.
6. Tears down and asserts a final session_end flush ran.

Use --turns to control how many inputs (default 22, just past the 20-turn
flush_threshold so we observe a `reason=threshold` flush mid-stream).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from collections import Counter
from typing import Any

from k1.concierge.bus.builders import build_user_input
from k1.concierge.bus.topics import (
    TOPIC_FINAL_RESPONSE,
    TOPIC_RESPONSE_STREAM,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TURN_COMPLETED,
    TOPIC_TURN_STARTED,
    TOPIC_USER_INPUT,
)
from k1.kernel.bootstrap import KernelConfig, start_kernel, stop_kernel

# ── instrumentation log capture ───────────────────────────────────────────


class _RecordCollector(logging.Handler):
    """Captures MW flush log lines so we can assert reasons after the run."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return
        if "MW:" in msg:
            self.records.append(msg)


# ── main driver ───────────────────────────────────────────────────────────


async def drive(turns: int, mode: str = "test") -> int:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    # MW logger to INFO so we can capture flush messages
    mw_log = logging.getLogger("k1.memory_writer.pipeline.session_batch_dispatcher")
    mw_log.setLevel(logging.INFO)
    collector = _RecordCollector()
    mw_log.addHandler(collector)

    print("=" * 64)
    label = "REAL Gemini (model_mode=hub)" if mode == "hub" else "canned stub"
    print(f"  Kernel smoke drive — {turns} mock turns, {label}")
    print("=" * 64)

    cfg = KernelConfig(model_mode=mode)
    t0 = time.monotonic()
    runtime = await start_kernel(cfg)
    boot_s = time.monotonic() - t0
    print(f"  Boot: {boot_s:.2f}s   session_id={runtime._session_id}")

    bus = runtime.bus
    counts: Counter[str] = Counter()
    last_response_text: list[str] = []
    response_q: asyncio.Queue[str] = asyncio.Queue()

    def _mk_handler(topic: str):
        def _h(env) -> None:
            counts[topic] += 1
            if topic == TOPIC_FINAL_RESPONSE:
                try:
                    payload = (
                        json.loads(env.payload)
                        if isinstance(env.payload, (bytes, bytearray))
                        else env.payload
                    )
                except Exception:  # noqa: BLE001
                    payload = {}
                txt = payload.get("text", "") if isinstance(payload, dict) else ""
                last_response_text.append(txt)
                response_q.put_nowait(txt)

        return _h

    subs: list[Any] = []
    for topic in (
        TOPIC_USER_INPUT,
        TOPIC_TURN_STARTED,
        TOPIC_TURN_COMPLETED,
        TOPIC_FINAL_RESPONSE,
        TOPIC_RESPONSE_STREAM,
        TOPIC_TASK_DISPATCH,
        TOPIC_TASK_COMPLETE,
    ):
        subs.append(bus.subscribe(topic, _mk_handler(topic)))

    # Locate MemoryWriterService → dispatcher
    svc = runtime._service
    session = svc._sessions[runtime._session_id]
    mw = session.memory_writer
    dispatcher = getattr(mw, "_dispatcher", None)
    fabric = session.fabric
    planner = svc._planner
    print(
        f"  Wired: concierge={session.concierge is not None} "
        f"fabric={fabric is not None} "
        f"planner={planner is not None} "
        f"orchestrator={svc.orchestrator is not None} "
        f"mw={mw is not None} dispatcher={type(dispatcher).__name__ if dispatcher else None}"
    )

    # ── drive turns ───────────────────────────────────────────────────────
    print(f"\n  Driving {turns} turns...")
    threshold_seen_at: int | None = None
    for i in range(1, turns + 1):
        env = build_user_input({"text": f"smoke turn {i}: ping"})
        bus.publish(env)
        try:
            await asyncio.wait_for(response_q.get(), timeout=15.0)
        except asyncio.TimeoutError:
            print(f"  ! turn {i}: no FINAL_RESPONSE in 15s")

        # detect threshold flush as soon as it shows up
        if threshold_seen_at is None and any("reason=threshold" in r for r in collector.records):
            threshold_seen_at = i
            print(f"    ✓ threshold flush observed after turn {i}")

        if i % 5 == 0:
            buffered = getattr(dispatcher, "buffered_count", "?")
            print(
                f"    turn {i}: final_resp={counts[TOPIC_FINAL_RESPONSE]} "
                f"turn_completed={counts[TOPIC_TURN_COMPLETED]} "
                f"mw_buffered={buffered}"
            )

    # let any pending bus delivery settle
    await asyncio.sleep(0.5)

    # ── inspect SessionState (Fabric write evidence) ──────────────────────
    ssm = session.session_state
    snapshot_dump: dict[str, Any] = {}
    try:
        # Read history_active section directly
        from k1.sessionstate.sections.history_active import HistoryActiveSection  # noqa

        section = ssm._sections.get("history_active") if hasattr(ssm, "_sections") else None
        if section and hasattr(section, "to_dict"):
            snapshot_dump = section.to_dict()
    except Exception as exc:  # noqa: BLE001
        snapshot_dump = {"_error": str(exc)}

    hist_turn_count = snapshot_dump.get("turn_count", "?")
    hist_max = snapshot_dump.get("max_turns", "?")
    print(
        f"\n  HistoryActive: turn_count={hist_turn_count}/{hist_max}  "
        f"current_turn_number={snapshot_dump.get('current_turn_number', '?')}"
    )

    # ── teardown (forces session_end flush) ───────────────────────────────
    print("\n  Tearing down (this triggers MW session_end flush)...")
    for s in subs:
        try:
            bus.unsubscribe(s)
        except Exception:  # noqa: BLE001
            pass
    await stop_kernel(runtime)

    # ── report ────────────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  RESULTS")
    print("=" * 64)
    print(f"  Bus event counts:")
    for topic in (
        TOPIC_USER_INPUT,
        TOPIC_TURN_STARTED,
        TOPIC_TURN_COMPLETED,
        TOPIC_FINAL_RESPONSE,
        TOPIC_RESPONSE_STREAM,
        TOPIC_TASK_DISPATCH,
        TOPIC_TASK_COMPLETE,
    ):
        print(f"    {topic:46s} {counts[topic]:5d}")

    print(f"\n  MW dispatcher records ({len(collector.records)}):")
    for line in collector.records:
        print(f"    {line}")

    # ── assertions ────────────────────────────────────────────────────────
    failures: list[str] = []
    if counts[TOPIC_USER_INPUT] != turns:
        failures.append(f"USER_INPUT count {counts[TOPIC_USER_INPUT]} != driven turns {turns}")
    if counts[TOPIC_FINAL_RESPONSE] < turns:
        failures.append(f"FINAL_RESPONSE count {counts[TOPIC_FINAL_RESPONSE]} < turns {turns}")
    if counts[TOPIC_TURN_COMPLETED] < turns:
        failures.append(
            f"TURN_COMPLETED count {counts[TOPIC_TURN_COMPLETED]} < turns {turns} "
            "(MW will be empty if this is 0)"
        )
    if turns >= 20 and threshold_seen_at is None:
        failures.append("expected reason=threshold flush after 20 turns, none seen")
    if not any("reason=session_end" in r for r in collector.records):
        failures.append("no reason=session_end flush observed at teardown")

    print("\n  Assertions:")
    if not failures:
        print("    ALL GREEN ✓")
        return 0
    for f in failures:
        print(f"    FAIL: {f}")
    return 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--turns", type=int, default=22)
    p.add_argument(
        "--hub",
        action="store_true",
        help="Boot with model_mode=hub (real Gemini, requires GOOGLE_API_KEY).",
    )
    args = p.parse_args()
    mode = "hub" if args.hub else "test"
    if args.hub and not __import__("os").environ.get("GOOGLE_API_KEY"):
        print("ERROR: --hub requires GOOGLE_API_KEY env var.")
        return 2
    return asyncio.run(drive(args.turns, mode=mode))


if __name__ == "__main__":
    sys.exit(main())
