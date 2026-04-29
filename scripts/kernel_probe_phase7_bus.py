"""
K1 Kernel Probe — Phase 7 (Bus subscribers + persistence/replay)
=================================================================

Per published 9-phase plan: verify the bus wiring at boot exposes the
expected number of subscribers, that a publish is dispatched to a
test handler, and that the durability/replay machinery (P6.13:
BusOutbox + replay_durable_topics) functions end-to-end.

What this probe does:
  1. Boots a real kernel (test mode) and locates svc._bus.
  2. Reports bus type, capture mode, durable_topics, outbox config.
  3. Snapshots stats() at boot (envelopes_published, subscriptions_active,
     topics_seen) and lists the topic patterns currently registered in
     the trie (walks bus._trie._sub_index keys).
  4. Subscribes a test handler to "k1.>" on the kernel bus, publishes a
     synthetic Envelope, verifies dispatch and stats delta.
  5. Reports the documented gap: BusFactory.create_local_ordered() does
     NOT pass an outbox/durable_topics — kernel runs RAM-only with no
     crash-replay safety. Subscribers that would benefit
     (concierge/orchestrator/planner) currently observe at-most-once.
  6. Builds an ISOLATED LocalBus with a SQLite BusOutbox and one
     durable topic; publishes 3 envelopes, restarts subscribers, calls
     replay_durable_topics(), verifies replay count matches.

Run:
  $env:PYTHONPATH = "D:\\familyos"; $env:PYTHONIOENCODING = "utf-8"
  python -m scripts.kernel_probe_phase7_bus --json data/kernel_probe_phase7.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os as _os
import sys
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from k1.bus.envelope.envelope import Envelope  # noqa: E402
from k1.bus.impl.local_bus import LocalBus  # noqa: E402
from k1.bus.outbox.sqlite_outbox import BusOutbox  # noqa: E402
from k1.concierge.config.kernel import KernelConfig  # noqa: E402
from k1.kernel.bootstrap import start_kernel, stop_kernel  # noqa: E402
from scripts._probe_common import _C_DIM, ProbeReport, _attr, _c  # noqa: E402

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _list_subscription_patterns(bus: Any) -> Dict[str, int]:
    """Walk LocalBus._trie._sub_index and tally patterns by topic prefix.

    Falls back to {} when the trie is the rust-backed builtins.TopicTrie
    which exposes no introspection (only size/insert/match/remove).
    """
    trie = _attr(bus, "_trie")
    if trie is None or not hasattr(trie, "_sub_index"):
        return {}
    sub_index = _attr(trie, "_sub_index")
    patterns: Dict[str, int] = {}
    if not sub_index:
        return patterns
    root = _attr(trie, "_root")
    if root is None:
        return patterns

    def _walk(node: Any, prefix: List[str]) -> None:
        handlers = _attr(node, "handlers", []) or []
        sub_ids = _attr(node, "subscription_ids", []) or []
        active = sum(1 for h, sid in zip(handlers, sub_ids) if h is not None and sid)
        if active and prefix:
            patterns[".".join(prefix)] = patterns.get(".".join(prefix), 0) + active
        for seg, child in (_attr(node, "children", {}) or {}).items():
            _walk(child, prefix + [seg])

    _walk(root, [])
    return patterns


# Well-known kernel topics exercised via trie.match() to discover wired
# subscribers when the trie itself is opaque (rust backend).
KNOWN_TOPICS: List[str] = [
    "k1.session.user.input.v1",
    "k1.session.turn.started.v1",
    "k1.session.turn.completed.v1",
    "k1.session.state.updated.v1",
    "k1.session.artifact.created.v1",
    "k1.session.task.state.v1",
    "k1.response.stream.v1",
    "k1.response.final.v1",
    "k1.response.clarification.v1",
    "k1.orchestration.task.dispatch.v1",
    "k1.orchestration.task.complete.v1",
    "k1.orchestration.task.failed.v1",
    "k1.orchestration.task.cancel.v1",
    "k1.orchestration.task.accepted.v1",
    "k1.orchestration.findings.ready.v1",
    "k1.orchestration.clarification.request.v1",
    "k1.fabric.capability.registered.v1",
    "k1.fabric.capability.completed.v1",
    "k1.planner.plan.committed.v1",
    "k1.planner.plan.failed.v1",
    "k1.modelhub.completion.v1",
]


def _probe_known_topics(bus: Any) -> Dict[str, int]:
    """For each well-known topic, ask the trie how many handlers match."""
    out: Dict[str, int] = {}
    trie = _attr(bus, "_trie")
    if trie is None or not hasattr(trie, "match"):
        return out
    for topic in KNOWN_TOPICS:
        try:
            handlers = trie.match(topic)
            n = len(handlers) if handlers is not None else 0
        except Exception:  # noqa: BLE001
            n = -1
        if n > 0:
            out[topic] = n
    return out


def _make_envelope(topic: str, payload: bytes = b"probe") -> Envelope:
    return Envelope(topic=topic, payload=payload)


# ──────────────────────────────────────────────────────────────────────
# Probes
# ──────────────────────────────────────────────────────────────────────


def probe_bus_wiring(svc: Any, report: ProbeReport) -> Optional[Any]:
    layer = "Bus wiring"
    bus = _attr(svc, "_bus")
    report.add(
        layer,
        "svc._bus",
        "OK" if bus is not None else "FAIL",
        type(bus).__name__ if bus else None,
    )
    if bus is None:
        return None

    report.add(
        layer,
        "is LocalBus",
        "OK" if isinstance(bus, LocalBus) else "WARN",
        isinstance(bus, LocalBus),
    )
    report.add(layer, "capture mode", "INFO", _attr(bus, "_capture", False))
    report.add(layer, "timing chain", "INFO", _attr(bus, "_timing_chain") is not None)
    report.add(layer, "middleware", "INFO", _attr(bus, "_middleware") is not None)

    durable = _attr(bus, "_durable_topics", set()) or set()
    outbox = _attr(bus, "_outbox")
    report.add(
        layer,
        "outbox configured",
        "WARN" if outbox is None else "OK",
        outbox is not None,
        (
            "kernel BusFactory.create_local_ordered() does not pass an outbox; "
            "all topics are RAM-only and crash-lossy"
            if outbox is None
            else ""
        ),
    )
    report.add(
        layer,
        "durable_topics",
        "WARN" if not durable else "OK",
        sorted(durable),
        "no topics opted into at-least-once delivery" if not durable else "",
    )

    # Stats snapshot at boot.
    stats = _attr(bus, "stats")
    if stats is not None:
        snap = stats.snapshot() if hasattr(stats, "snapshot") else {}
        report.add(layer, "stats.envelopes_published", "INFO", snap.get("envelopes_published"))
        report.add(layer, "stats.envelopes_delivered", "INFO", snap.get("envelopes_delivered"))
        report.add(layer, "stats.subscriptions_active", "INFO", snap.get("subscriptions_active"))
        report.add(layer, "stats.subscriptions_total", "INFO", snap.get("subscriptions_total"))
        report.add(layer, "stats.topics_seen", "INFO", snap.get("topics_seen"))
        report.add(layer, "stats.handler_errors", "INFO", snap.get("handler_errors"))

    sub_count = _attr(bus, "subscription_count")
    report.add(
        layer,
        "subscription_count (trie.size)",
        "OK" if (sub_count or 0) > 0 else "WARN",
        sub_count,
        "no subscribers registered at boot" if not sub_count else "",
    )
    return bus


def probe_subscriber_inventory(bus: Any, report: ProbeReport) -> None:
    layer = "Bus subscribers"
    trie = _attr(bus, "_bus") if hasattr(bus, "_bus") else None
    backend = "rust" if type(_attr(bus, "_trie")).__module__ == "builtins" else "python"
    report.add(layer, "trie backend", "INFO", backend)

    patterns = _list_subscription_patterns(bus)
    if patterns:
        # Bucket by top-level segment.
        buckets: Dict[str, int] = {}
        for pat, n in patterns.items():
            seg = pat.split(".", 1)[0] if pat else "<empty>"
            buckets[seg] = buckets.get(seg, 0) + n
        report.add(layer, "patterns_by_top_segment", "INFO", buckets)
        report.add(layer, "total_distinct_patterns", "INFO", len(patterns))
        report.add(layer, "patterns_sample", "INFO", sorted(patterns.items())[:12])
    else:
        report.add(
            layer,
            "trie pattern enumeration",
            "INFO",
            "unsupported",
            "rust-backed trie exposes no introspection; using known-topics probe instead",
        )

    matched = _probe_known_topics(bus)
    report.add(
        layer,
        "known_topics_with_handlers",
        "OK" if matched else "WARN",
        len(matched),
        f"{sum(matched.values())} handlers wired across {len(matched)} known topics",
    )
    if matched:
        report.add(layer, "matched_known_topics", "INFO", matched)


def probe_publish_dispatch(bus: Any, report: ProbeReport) -> None:
    layer = "Publish/Dispatch"
    if bus is None or not hasattr(bus, "subscribe") or not hasattr(bus, "publish"):
        report.add(layer, "bus surface", "FAIL", None, "missing subscribe/publish")
        return

    received: List[Envelope] = []

    def _h(env: Envelope) -> None:
        received.append(env)

    test_topic = f"k1.probe.phase7.{uuid.uuid4().hex[:8]}.v1"
    handle = bus.subscribe(test_topic, _h)
    report.add(
        layer, "subscribe", "OK" if handle is not None else "FAIL", _attr(handle, "subscription_id")
    )

    stats0 = bus.stats.snapshot() if hasattr(bus.stats, "snapshot") else {}
    env = _make_envelope(test_topic, b"phase7-probe-payload")
    try:
        bus.publish(env)
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "publish", "FAIL", None, f"{type(exc).__name__}: {exc}")
        return

    # Allow async dispatch / timing chain to drain.
    time.sleep(0.05)

    stats1 = bus.stats.snapshot() if hasattr(bus.stats, "snapshot") else {}
    delta_pub = stats1.get("envelopes_published", 0) - stats0.get("envelopes_published", 0)
    delta_del = stats1.get("envelopes_delivered", 0) - stats0.get("envelopes_delivered", 0)
    report.add(layer, "envelopes_published delta", "OK" if delta_pub >= 1 else "FAIL", delta_pub)
    report.add(layer, "envelopes_delivered delta", "OK" if delta_del >= 1 else "WARN", delta_del)
    report.add(layer, "handler invoked", "OK" if received else "FAIL", len(received))
    if received:
        env_received = received[0]
        report.add(
            layer,
            "envelope_id stamped",
            "OK" if env_received.envelope_id > 0 else "FAIL",
            env_received.envelope_id,
        )
        report.add(
            layer,
            "sequence stamped",
            "OK" if env_received.sequence > 0 else "FAIL",
            env_received.sequence,
        )
        report.add(
            layer,
            "payload roundtrip",
            "OK" if env_received.payload == b"phase7-probe-payload" else "FAIL",
            len(env_received.payload),
        )

    # Cleanup
    try:
        bus.unsubscribe(handle)
    except Exception:  # noqa: BLE001
        pass


def probe_durability_replay(report: ProbeReport) -> None:
    """End-to-end test of P6.13 outbox + replay using an isolated bus.

    The kernel's bus has no outbox today; this probe verifies the
    replay infrastructure itself is intact and would work the moment
    a future change wires an outbox into BusFactory.create_local_ordered.
    """
    layer = "Durability + Replay (isolated bus)"
    tmpdir = tempfile.mkdtemp(prefix="k1_probe_phase7_")
    db_path = _os.path.join(tmpdir, "outbox.sqlite")
    durable_topic = "k1.probe.phase7.durable.v1"

    try:
        outbox = BusOutbox(db_path)
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "BusOutbox()", "FAIL", None, f"{type(exc).__name__}: {exc}")
        return
    report.add(layer, "BusOutbox()", "OK", db_path)

    bus = LocalBus(outbox=outbox, durable_topics={durable_topic})
    report.add(layer, "LocalBus(outbox=...,durable_topics=...)", "OK", durable_topic)

    consumer_id = "probe-consumer"
    received: List[Envelope] = []

    def _h(env: Envelope) -> None:
        received.append(env)

    # Publish 3 envelopes BEFORE any subscriber exists. Outbox stores
    # them as unacked (no consumer = no ack watermark).
    for i in range(3):
        bus.publish(_make_envelope(durable_topic, f"msg-{i}".encode()))
    report.add(
        layer,
        "outbox.count after publish",
        "OK" if outbox.count(durable_topic) == 3 else "FAIL",
        outbox.count(durable_topic),
    )
    report.add(
        layer,
        "live dispatch (no subscriber)",
        "OK" if len(received) == 0 else "FAIL",
        len(received),
        "no subscriber installed yet",
    )

    # Now subscribe with consumer_id and replay.
    handle = bus.subscribe(durable_topic, _h, consumer_id=consumer_id)
    report.add(
        layer,
        "subscribe(consumer_id=...)",
        "OK" if handle else "FAIL",
        _attr(handle, "subscription_id"),
    )

    try:
        n = bus.replay_durable_topics(consumer_id=consumer_id)
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "replay_durable_topics", "FAIL", None, f"{type(exc).__name__}: {exc}")
        return
    report.add(
        layer,
        "replay returned",
        "OK" if n == 3 else "FAIL",
        n,
        "expected 3 unacked envelopes",
    )
    report.add(
        layer,
        "replay handler invocations",
        "OK" if len(received) == 3 else "FAIL",
        len(received),
    )

    # Second replay should drain to 0 because handler acked each one.
    received.clear()
    n2 = bus.replay_durable_topics(consumer_id=consumer_id)
    report.add(
        layer,
        "second replay (after ack)",
        "OK" if n2 == 0 else "WARN",
        n2,
        "expected 0 — acked envelopes should not replay",
    )

    # Cleanup
    try:
        bus.unsubscribe(handle)
        bus.close()
    except Exception:  # noqa: BLE001
        pass


# ──────────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────────


async def run_probe(json_path: Optional[str]) -> int:
    print("=" * 72)
    print(_c("  K1 Kernel Probe — Phase 7 (Bus subscribers + persistence/replay)", "\x1b[1m"))
    print("=" * 72)

    cfg = KernelConfig(model_mode="test")
    t0 = time.perf_counter()
    runtime = await start_kernel(cfg)
    boot_s = time.perf_counter() - t0
    print(f"  Boot: {boot_s:.2f}s\n")

    report = ProbeReport()
    svc = runtime._service

    bus = probe_bus_wiring(svc, report)
    if bus is not None:
        probe_subscriber_inventory(bus, report)
        probe_publish_dispatch(bus, report)
    probe_durability_replay(report)

    report.render("K1 Kernel Probe — Phase 7 (Bus subscribers + persistence/replay)")

    if json_path:
        out = {
            "boot_seconds": boot_s,
            "counts": report.counts(),
            "probes": [
                {
                    "layer": p.layer,
                    "name": p.name,
                    "status": p.status,
                    "value": repr(p.value),
                    "note": p.note,
                }
                for p in report.probes
            ],
        }
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, default=repr)
        print(_c(f"  JSON written: {json_path}", _C_DIM))

    print(_c("  Tearing down...", _C_DIM))
    await stop_kernel(runtime)
    return report.exit_code()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    return asyncio.run(run_probe(args.json))


if __name__ == "__main__":
    sys.exit(main())
