"""
K1 Kernel Probe — Phase 6 (SessionState eviction + tiering)
============================================================

Per published 9-phase plan:
  "SessionState eviction + tiering | Force HOT->WARM migration with
   SectionDataAdapter injected; verify emergency mode triggers | No (no LLM)"

What this probe does:
  1. Boots a real kernel (test mode) and locates the SessionStateManager
     attached to the first session.
  2. Verifies the documented production gap (audit Fix J) — both
     EvictionEngine._section_provider and MigrationEngine._section_provider
     are None at boot, so any eviction/migration runs in placeholder mode.
  3. Verifies a second documented gap — SessionStateManager stores an
     event_port but never publishes EmergencyActivatedEvent /
     EmergencyResolvedEvent / EvictionTriggeredEvent. Subscribers will
     never observe these topics today.
  4. Forces WARM tier into EMERGENCY pressure by writing
     SizeTracker.set_section_size() directly, then triggers eviction
     in placeholder mode and confirms behaviour.
  5. Re-runs the eviction with a fake IEvictionSectionProvider injected
     into EvictionEngine._section_provider; confirms real bytes flow
     through the provider (clear_section / get_evictable_data /
     remove_evicted_data are all called) and section sizes shrink to 0.
  6. Forces HOT tier into EMERGENCY pressure, injects a fake
     IMigrationSectionProvider into MigrationEngine, and calls
     demote_on_pressure(); confirms HOT->WARM migration moves bytes.
  7. Subscribes to sessionstate.emergency.activated /
     sessionstate.emergency.resolved on the kernel event bus and
     reports whether anything publishes them (today: nothing).

Run:
  $env:PYTHONPATH = "D:\\familyos"; $env:PYTHONIOENCODING = "utf-8"
  python -m scripts.kernel_probe_phase6_sessionstate --json data/kernel_probe_phase6.json
"""

from __future__ import annotations

import argparse
import asyncio
import json

# Allow running as a script via `python scripts/kernel_probe_phase6_sessionstate.py`
import os as _os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from k1.concierge.config.kernel import KernelConfig  # noqa: E402
from k1.kernel.bootstrap import start_kernel, stop_kernel  # noqa: E402
from k1.sessionstate.events import EventType  # noqa: E402
from k1.sessionstate.eviction import EvictionEngine  # noqa: E402
from k1.sessionstate.migration import MigrationEngine, MigrationItem  # noqa: E402
from k1.sessionstate.sizetracker import (  # noqa: E402
    HOT_SECTIONS,
    HOT_SIZE_LIMIT_BYTES,
    SECTION_BUDGETS,
    WARM_SECTIONS,
    WARM_SIZE_LIMIT_BYTES,
    PressureLevel,
)
from scripts._probe_common import _C_DIM, ProbeReport, _attr, _c  # noqa: E402

# ──────────────────────────────────────────────────────────────────────
# Fake providers — minimal in-memory implementations of the two
# Protocols sessionstate engines depend on. Used only by this probe.
# ──────────────────────────────────────────────────────────────────────


class FakeEvictionSectionProvider:
    """In-memory IEvictionSectionProvider for the probe."""

    def __init__(self) -> None:
        self.data: Dict[str, bytes] = {}
        self.calls: Dict[str, int] = {
            "get_section_data": 0,
            "clear_section": 0,
            "get_evictable_data": 0,
            "remove_evicted_data": 0,
        }

    def seed(self, section: str, blob: bytes) -> None:
        self.data[section] = blob

    def get_section_data(self, section: str) -> Optional[bytes]:
        self.calls["get_section_data"] += 1
        return self.data.get(section)

    def clear_section(self, section: str) -> int:
        self.calls["clear_section"] += 1
        n = len(self.data.get(section, b""))
        self.data[section] = b""
        return n

    def get_evictable_data(self, section: str, target_bytes: int) -> Tuple[bytes, int]:
        self.calls["get_evictable_data"] += 1
        blob = self.data.get(section, b"")
        n = min(target_bytes, len(blob))
        return blob[:n], n

    def remove_evicted_data(self, section: str, bytes_to_remove: int) -> int:
        self.calls["remove_evicted_data"] += 1
        blob = self.data.get(section, b"")
        n = min(bytes_to_remove, len(blob))
        self.data[section] = blob[n:]
        return n


class FakeMigrationSectionProvider:
    """In-memory IMigrationSectionProvider for the probe."""

    def __init__(self) -> None:
        self.sections: Dict[str, List[MigrationItem]] = {}
        self.calls: Dict[str, int] = {
            "get_items": 0,
            "add_items": 0,
            "remove_items": 0,
            "clear_section": 0,
            "get_turn_count": 0,
            "get_oldest_turns": 0,
        }

    def seed(self, section: str, items: List[MigrationItem]) -> None:
        self.sections[section] = list(items)

    def get_items(self, section: str) -> List[MigrationItem]:
        self.calls["get_items"] += 1
        return list(self.sections.get(section, []))

    def add_items(self, section: str, items: List[MigrationItem]) -> int:
        self.calls["add_items"] += 1
        bucket = self.sections.setdefault(section, [])
        total = 0
        for it in items:
            bucket.append(it)
            total += it.size_bytes
        return total

    def remove_items(self, section: str, keys: List[str]) -> int:
        self.calls["remove_items"] += 1
        kset = set(keys)
        bucket = self.sections.get(section, [])
        freed = 0
        keep: List[MigrationItem] = []
        for it in bucket:
            if it.key in kset:
                freed += it.size_bytes
            else:
                keep.append(it)
        self.sections[section] = keep
        return freed

    def clear_section(self, section: str) -> int:
        self.calls["clear_section"] += 1
        bucket = self.sections.get(section, [])
        freed = sum(it.size_bytes for it in bucket)
        self.sections[section] = []
        return freed

    def get_turn_count(self, section: str) -> int:
        self.calls["get_turn_count"] += 1
        return len(self.sections.get(section, []))

    def get_oldest_turns(self, section: str, count: int) -> List[MigrationItem]:
        self.calls["get_oldest_turns"] += 1
        return list(self.sections.get(section, []))[:count]


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _subscribe_topics(bus: Any, topics: List[str]) -> Tuple[List[Tuple[str, Any]], List[Any]]:
    """Subscribe to topics on the kernel event bus.

    Reused pattern from phase 5 — handler accepts *args because the
    EventPortProdAdapter calls handler(topic, payload).
    """
    captured: List[Tuple[str, Any]] = []
    handles: List[Any] = []
    if bus is None or not hasattr(bus, "subscribe"):
        return captured, handles
    for topic in topics:

        def _mk(t: str):
            def _h(*args: Any) -> None:
                payload = args[-1] if args else None
                captured.append((t, payload))

            return _h

        try:
            handles.append(bus.subscribe(topic, _mk(topic)))
        except Exception:  # noqa: BLE001
            pass
    return captured, handles


def _resolve_event_bus(svc: Any) -> Any:
    """Find an event-bus-like object exposing subscribe()."""
    for attr in ("_event_port", "_event_bus", "event_port", "event_bus", "_bus"):
        candidate = _attr(svc, attr)
        if candidate is None:
            continue
        underlying = _attr(candidate, "_event_port") or candidate
        if hasattr(underlying, "subscribe"):
            return underlying
    return None


def _set_warm_full(ssm: Any, target_pct: float = 0.97) -> Dict[str, int]:
    """Force WARM tier into EMERGENCY pressure (>95%) via SizeTracker.

    Distributes bytes across WARM sections proportional to their budget.
    """
    target = int(WARM_SIZE_LIMIT_BYTES * target_pct)
    sizes: Dict[str, int] = {}
    # Skip artifacts_warm: LocalColdArchive.SECTION_TABLE_MAP has no entry
    # for it (production gap). Including it generates noisy archive
    # failures without changing the eviction outcome.
    eligible = [s for s in WARM_SECTIONS if s != "artifacts_warm"]
    warm_total_budget = sum(SECTION_BUDGETS[s].max_bytes for s in eligible)
    for section in eligible:
        budget = SECTION_BUDGETS[section].max_bytes
        share = int(target * budget / warm_total_budget)
        share = min(share, budget)
        ssm.size_tracker.set_section_size(section, share)
        sizes[section] = share
    return sizes


def _set_hot_full(ssm: Any, target_pct: float = 0.97) -> Dict[str, int]:
    """Force HOT tier into EMERGENCY pressure via SizeTracker.

    Inflates ALL HOT sections (including never-evict) to push tier
    pressure above EMERGENCY threshold, then returns only the
    demote-eligible sizes (skipping task_artifacts whose WARM target
    has no LocalColdArchive table mapping).
    """
    target = int(HOT_SIZE_LIMIT_BYTES * target_pct)
    hot_total_budget = sum(SECTION_BUDGETS[s].max_bytes for s in HOT_SECTIONS)
    eligible_for_demote: Dict[str, int] = {}
    for section in HOT_SECTIONS:
        budget = SECTION_BUDGETS[section].max_bytes
        share = int(target * budget / hot_total_budget)
        share = min(share, budget)
        ssm.size_tracker.set_section_size(section, share)
        if SECTION_BUDGETS[section].can_migrate and section != "task_artifacts":
            eligible_for_demote[section] = share
    return eligible_for_demote


def _reset_all_sections(ssm: Any) -> None:
    for s in list(HOT_SECTIONS) + list(WARM_SECTIONS):
        ssm.size_tracker.set_section_size(s, 0)


# ──────────────────────────────────────────────────────────────────────
# Probes
# ──────────────────────────────────────────────────────────────────────


def probe_session_manager(svc: Any, report: ProbeReport) -> Optional[Any]:
    layer = "SessionState wiring"
    sessions = _attr(svc, "_sessions", {}) or {}
    if not sessions:
        report.add(layer, "session", "FAIL", None, "no sessions on svc._sessions")
        return None
    sid, session = next(iter(sessions.items()))
    ssm = _attr(session, "session_state")
    report.add(layer, "session_id", "INFO", sid)
    if ssm is None:
        report.add(layer, "session_state", "FAIL", None, "session.session_state is None")
        return None
    report.add(layer, "session_state", "OK", type(ssm).__name__)

    eviction = _attr(ssm, "_eviction_engine") or _attr(ssm, "eviction_engine")
    migration = _attr(ssm, "_migration_engine") or _attr(ssm, "migration_engine")
    report.add(
        layer,
        "EvictionEngine",
        "OK" if isinstance(eviction, EvictionEngine) else "FAIL",
        type(eviction).__name__ if eviction else None,
    )
    report.add(
        layer,
        "MigrationEngine",
        "OK" if isinstance(migration, MigrationEngine) else "FAIL",
        type(migration).__name__ if migration else None,
    )

    # Audit Fix J — both providers should be None at boot today.
    e_provider = _attr(eviction, "_section_provider")
    m_provider = _attr(migration, "_section_provider")
    report.add(
        layer,
        "EvictionEngine._section_provider",
        "WARN" if e_provider is None else "OK",
        e_provider,
        "audit Fix J: placeholder mode (expected today)" if e_provider is None else "",
    )
    report.add(
        layer,
        "MigrationEngine._section_provider",
        "WARN" if m_provider is None else "OK",
        m_provider,
        "audit Fix J: placeholder mode (expected today)" if m_provider is None else "",
    )

    # Manager stores an event_port but never publishes through it.
    ep = _attr(ssm, "_event_port")
    report.add(
        layer,
        "SessionStateManager._event_port",
        "INFO",
        type(ep).__name__ if ep is not None else None,
    )

    # Separate production gap surfaced while writing this probe:
    # LocalColdArchive.SECTION_TABLE_MAP omits artifacts_warm even though
    # SECTION_BUDGETS classifies it as a WARM (evictable) section. Eviction
    # of artifacts_warm raises ValueError("Unknown section: artifacts_warm")
    # inside LocalColdArchive._get_table_for_section.
    try:
        from k1.sessionstate.local_cold import SECTION_TABLE_MAP

        unmapped = sorted(
            s
            for s in WARM_SECTIONS
            if s not in SECTION_TABLE_MAP and not s.startswith(("beliefs", "history", "narrative"))
        )
        report.add(
            layer,
            "LocalColdArchive unmapped WARM sections",
            "WARN" if unmapped else "OK",
            unmapped,
            "production gap: archive() raises ValueError for these",
        )
    except Exception:  # noqa: BLE001
        pass

    return ssm


def probe_emergency_event_emitter_gap(svc: Any, ssm: Any, report: ProbeReport) -> None:
    """Verify that nothing on the kernel bus publishes the emergency topics."""
    layer = "Emergency event wiring"
    bus = _resolve_event_bus(svc)
    report.add(
        layer,
        "kernel_event_bus",
        "OK" if bus is not None else "FAIL",
        type(bus).__name__ if bus else None,
    )
    if bus is None:
        return

    captured, _h = _subscribe_topics(
        bus,
        [
            EventType.EMERGENCY_ACTIVATED.value,
            EventType.EMERGENCY_RESOLVED.value,
            EventType.EVICTION_TRIGGERED.value,
            EventType.EVICTION_COMPLETED.value,
            EventType.MUTATION_REQUESTED.value,
        ],
    )

    # Force EMERGENCY pressure and trigger eviction. If any code path emits
    # the topics this list will populate; today it should remain empty.
    _reset_all_sections(ssm)
    _set_warm_full(ssm, target_pct=0.97)
    pressure_before = ssm.size_tracker.get_pressure("warm")
    report.add(layer, "warm_pressure_forced", "INFO", pressure_before.value)
    try:
        ssm._trigger_eviction_if_needed()
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "trigger_eviction", "FAIL", None, f"{type(exc).__name__}: {exc}")
        return

    by_topic: Dict[str, int] = {}
    for t, _ in captured:
        by_topic[t] = by_topic.get(t, 0) + 1
    report.add(layer, "events_observed_after_emergency", "INFO", by_topic)
    report.add(
        layer,
        "EMERGENCY_ACTIVATED published",
        "WARN" if by_topic.get(EventType.EMERGENCY_ACTIVATED.value, 0) == 0 else "OK",
        by_topic.get(EventType.EMERGENCY_ACTIVATED.value, 0),
        "production gap: factory exists but no code path publishes it",
    )
    report.add(
        layer,
        "EVICTION_TRIGGERED published",
        "WARN" if by_topic.get(EventType.EVICTION_TRIGGERED.value, 0) == 0 else "OK",
        by_topic.get(EventType.EVICTION_TRIGGERED.value, 0),
        "production gap: SessionStateManager._event_port is never invoked",
    )

    _reset_all_sections(ssm)


def probe_eviction_placeholder_mode(ssm: Any, report: ProbeReport) -> None:
    layer = "Eviction (placeholder)"
    eviction: EvictionEngine = ssm._eviction_engine
    _reset_all_sections(ssm)
    sizes = _set_warm_full(ssm, target_pct=0.97)
    report.add(layer, "warm_sizes", "INFO", sizes)
    report.add(
        layer,
        "warm_pressure",
        "INFO",
        ssm.size_tracker.get_pressure("warm").value,
        f"warm_total={ssm.size_tracker.get_tier_size('warm')}/{WARM_SIZE_LIMIT_BYTES}",
    )

    candidates = eviction.get_eviction_candidates()
    report.add(
        layer,
        "candidates",
        "OK" if candidates else "FAIL",
        [c.section for c in candidates],
    )

    target_bytes = ssm.size_tracker.get_tier_size("warm") - int(WARM_SIZE_LIMIT_BYTES * 0.70)
    result = eviction.evict(target_bytes=target_bytes, reason="probe-placeholder")
    report.add(
        layer,
        "evict.success",
        "OK" if result.success else "WARN",
        result.success,
        result.error or "",
    )
    report.add(layer, "evict.bytes_freed", "INFO", result.bytes_freed)
    report.add(layer, "evict.bytes_archived", "INFO", result.bytes_archived)
    report.add(layer, "evict.sections", "INFO", result.sections_evicted)
    report.add(layer, "evict.new_pressure", "INFO", result.new_pressure.value)
    report.add(
        layer,
        "warm_total_after",
        "OK" if ssm.size_tracker.get_tier_size("warm") < sum(sizes.values()) else "FAIL",
        ssm.size_tracker.get_tier_size("warm"),
    )

    _reset_all_sections(ssm)


def probe_eviction_with_provider(ssm: Any, report: ProbeReport) -> None:
    layer = "Eviction (provider injected)"
    eviction: EvictionEngine = ssm._eviction_engine

    # Inject fake provider with real bytes seeded per WARM section.
    fake = FakeEvictionSectionProvider()
    _reset_all_sections(ssm)
    sizes = _set_warm_full(ssm, target_pct=0.97)
    for section, n in sizes.items():
        fake.seed(section, b"X" * n)
    eviction._section_provider = fake  # type: ignore[attr-defined]

    target_bytes = ssm.size_tracker.get_tier_size("warm") - int(WARM_SIZE_LIMIT_BYTES * 0.70)
    result = eviction.evict(target_bytes=target_bytes, reason="probe-real-provider")

    report.add(
        layer,
        "evict.success",
        "OK" if result.success else "FAIL",
        result.success,
        result.error or "",
    )
    report.add(layer, "evict.bytes_freed", "INFO", result.bytes_freed)
    report.add(layer, "evict.bytes_archived", "INFO", result.bytes_archived)
    report.add(
        layer,
        "evict.bytes_archived>0",
        "OK" if result.bytes_archived > 0 else "FAIL",
        result.bytes_archived,
        "real bytes should flow through provider->LocalColdArchive",
    )
    report.add(layer, "provider.calls", "INFO", dict(fake.calls))
    report.add(
        layer,
        "provider.get_evictable_data called",
        "OK" if fake.calls["get_evictable_data"] > 0 else "FAIL",
        fake.calls["get_evictable_data"],
    )
    report.add(
        layer,
        "provider.remove_evicted_data called",
        "OK" if fake.calls["remove_evicted_data"] > 0 else "FAIL",
        fake.calls["remove_evicted_data"],
    )
    report.add(
        layer,
        "warm_total_after",
        (
            "OK"
            if ssm.size_tracker.get_tier_size("warm") <= int(WARM_SIZE_LIMIT_BYTES * 0.71)
            else "WARN"
        ),
        ssm.size_tracker.get_tier_size("warm"),
        "should drop near 70% target after eviction",
    )

    eviction._section_provider = None  # type: ignore[attr-defined]
    _reset_all_sections(ssm)


def probe_migration_with_provider(ssm: Any, report: ProbeReport) -> None:
    layer = "Migration HOT->WARM (provider injected)"
    migration: MigrationEngine = ssm._migration_engine

    _reset_all_sections(ssm)
    hot_sizes = _set_hot_full(ssm, target_pct=0.97)
    report.add(layer, "hot_sizes_seeded", "INFO", hot_sizes)
    report.add(layer, "hot_pressure", "INFO", ssm.size_tracker.get_pressure("hot").value)

    fake = FakeMigrationSectionProvider()
    # Seed each demotable HOT section with a few items totalling ~its byte size.
    for section, total in hot_sizes.items():
        item_bytes = max(64, total // 4)
        items: List[MigrationItem] = []
        remaining = total
        idx = 0
        while remaining > 0:
            take = min(item_bytes, remaining)
            items.append(
                MigrationItem(
                    section=section,
                    key=f"{section}-k{idx}",
                    data=b"y" * take,
                    size_bytes=take,
                )
            )
            remaining -= take
            idx += 1
        fake.seed(section, items)
    migration._section_provider = fake  # type: ignore[attr-defined]

    warm_before = ssm.size_tracker.get_tier_size("warm")
    hot_before = ssm.size_tracker.get_tier_size("hot")

    try:
        results = migration.demote_on_pressure()
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "demote_on_pressure", "FAIL", None, f"{type(exc).__name__}: {exc}")
        migration._section_provider = None  # type: ignore[attr-defined]
        _reset_all_sections(ssm)
        return

    if not isinstance(results, list):
        results = [results]

    successes = [r for r in results if getattr(r, "success", False)]
    report.add(
        layer,
        "demote_on_pressure.results",
        "OK" if successes else "WARN",
        len(successes),
        f"total={len(results)} success={len(successes)}",
    )
    report.add(layer, "provider.calls", "INFO", dict(fake.calls))
    hot_after = ssm.size_tracker.get_tier_size("hot")
    warm_after = ssm.size_tracker.get_tier_size("warm")
    report.add(
        layer,
        "hot_total_decreased",
        "OK" if hot_after < hot_before else "WARN",
        f"{hot_before}->{hot_after}",
    )
    report.add(
        layer,
        "warm_total_increased_or_same",
        "OK" if warm_after >= warm_before else "WARN",
        f"{warm_before}->{warm_after}",
        "demote moves bytes; some shrink via summarization",
    )

    migration._section_provider = None  # type: ignore[attr-defined]
    _reset_all_sections(ssm)


# ──────────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────────


async def run_probe(json_path: Optional[str]) -> int:
    print("=" * 72)
    print(_c("  K1 Kernel Probe — Phase 6 (SessionState eviction + tiering)", "\x1b[1m"))
    print("=" * 72)

    cfg = KernelConfig(model_mode="test")
    t0 = time.perf_counter()
    runtime = await start_kernel(cfg)
    boot_s = time.perf_counter() - t0
    print(f"  Boot: {boot_s:.2f}s\n")

    report = ProbeReport()
    svc = runtime._service

    ssm = probe_session_manager(svc, report)
    if ssm is not None:
        probe_emergency_event_emitter_gap(svc, ssm, report)
        probe_eviction_placeholder_mode(ssm, report)
        probe_eviction_with_provider(ssm, report)
        probe_migration_with_provider(ssm, report)

    report.render("K1 Kernel Probe — Phase 6 (SessionState eviction + tiering)")

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
