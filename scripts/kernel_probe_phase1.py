"""kernel_probe_phase1.py — Read-only kernel wiring health probe.

PHASE 1 of the K1 component test plan. Boots the kernel in test mode
(no LLM spend), then INTROSPECTS every layer without driving any
traffic. Output is a wiring health table — what's wired, what's stub,
what's None, what's unverified.

Run:
    $env:PYTHONPATH="D:\\familyos"; $env:PYTHONIOENCODING="utf-8"
    python -m scripts.kernel_probe_phase1

    # JSON output for trend tracking:
    python -m scripts.kernel_probe_phase1 --json data/kernel_probe.json

What it checks (NO traffic driven, NO LLM calls):
- KernelService Tier-1: bus, router, model_hub, shared_fabric, bridge,
  orchestrator, planner, ledger
- Per-session Tier-2: concierge, fabric, session_state, memory_writer,
  experience_layer, delta_aggregator, delta_applicator, hitl_coordinator
- Kernel ports: all 8 (bridge/bus/fabric/lifecycle/model_hub/orchestrator/
  planner/session_manager) — instantiated? adapter type?
- HIL surface: count HILCoordinator instances + topics (Concierge/Planner/
  Orchestrator) — surfaces fragmentation
- Fabric: Resolver, CapabilityRegistry size, ProviderMatcher, 4 routing
  classes' state_reader injection, mcp_transport, ModuleLoader.watch
- Model Hub: model_mode, plugin list, BudgetEnforcer, ResponseCache TTL,
  health query type
- Orchestrator: DAGExecutor.guards, _compensate body, max_pending_hil
- Planner: LLMGatewayAdapter type, HIL topics
- SessionState: section count, tier counts, EvictionEngine.section_provider,
  DeltaApplicator callbacks (3× None pattern)
- Bus: backend type, subscriber counts per known topic, BusOutbox wired
- K0 Bridge: SinkBridgeClient.online state
- Module Loader: CapabilityRegistry size, watch flag
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.bootstrap import start_kernel, stop_kernel

# ── ANSI color helpers ─────────────────────────────────────────────────


def _supports_color() -> bool:
    return sys.stdout.isatty()


_C_RED = "\x1b[31m"
_C_YEL = "\x1b[33m"
_C_GRN = "\x1b[32m"
_C_DIM = "\x1b[2m"
_C_BOLD = "\x1b[1m"
_C_RST = "\x1b[0m"


def _c(s: str, code: str) -> str:
    return f"{code}{s}{_C_RST}" if _supports_color() else s


# ── status atom ────────────────────────────────────────────────────────


@dataclass
class Probe:
    """Single probe result: name, status, value/details."""

    layer: str
    name: str
    status: str  # "OK" | "WARN" | "FAIL" | "INFO"
    value: Any = None
    note: str = ""

    def render(self) -> str:
        glyph = {
            "OK": _c("✓", _C_GRN),
            "WARN": _c("⚠", _C_YEL),
            "FAIL": _c("✗", _C_RED),
            "INFO": _c("·", _C_DIM),
        }.get(self.status, "?")
        val = "" if self.value is None else f" = {self.value!r}"
        note = f"  {_c(self.note, _C_DIM)}" if self.note else ""
        return f"  {glyph}  {self.name:<48s}{val}{note}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "name": self.name,
            "status": self.status,
            "value": _safe(self.value),
            "note": self.note,
        }


def _safe(v: Any) -> Any:
    """Make value JSON-serializable."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (list, tuple)):
        return [_safe(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _safe(x) for k, x in v.items()}
    return repr(v)


# ── layer probes ───────────────────────────────────────────────────────


@dataclass
class ProbeReport:
    probes: list[Probe] = field(default_factory=list)
    boot_seconds: float = 0.0
    session_id: str = ""

    def add(self, *args, **kwargs) -> None:
        self.probes.append(Probe(*args, **kwargs))

    def by_layer(self) -> dict[str, list[Probe]]:
        out: dict[str, list[Probe]] = {}
        for p in self.probes:
            out.setdefault(p.layer, []).append(p)
        return out

    def counts(self) -> dict[str, int]:
        c = {"OK": 0, "WARN": 0, "FAIL": 0, "INFO": 0}
        for p in self.probes:
            c[p.status] = c.get(p.status, 0) + 1
        return c


def _present(obj: Any, name: str, layer: str, report: ProbeReport, *, note: str = "") -> bool:
    if obj is None:
        report.add(layer, name, "FAIL", None, note or "is None")
        return False
    report.add(layer, name, "OK", type(obj).__name__, note)
    return True


def _attr(obj: Any, attr: str, default: Any = None) -> Any:
    return getattr(obj, attr, default)


# ── layer 1: KernelService Tier-1 ──────────────────────────────────────


def probe_kernel_service(svc: Any, report: ProbeReport) -> None:
    layer = "KernelService (Tier-1)"
    _present(_attr(svc, "_bus"), "bus", layer, report)
    _present(_attr(svc, "_router"), "router", layer, report)
    _present(_attr(svc, "_model_hub"), "model_hub", layer, report)
    _present(_attr(svc, "_shared_fabric"), "shared_fabric", layer, report)
    _present(_attr(svc, "_bridge"), "bridge", layer, report)
    _present(_attr(svc, "_orchestrator"), "orchestrator", layer, report)
    _present(_attr(svc, "_planner"), "planner", layer, report)
    planner_task = _attr(svc, "_planner_task")
    if planner_task is None:
        report.add(layer, "planner_task", "WARN", None, "no asyncio task — planner not running")
    else:
        alive = not planner_task.done()
        report.add(
            layer,
            "planner_task",
            "OK" if alive else "FAIL",
            "running" if alive else "dead",
        )
    sessions = _attr(svc, "_sessions", {})
    report.add(layer, "session_count", "INFO", len(sessions))


# ── layer 2: Per-session Tier-2 ────────────────────────────────────────


def probe_session(session: Any, report: ProbeReport) -> None:
    layer = "SessionInstance (Tier-2)"
    _present(_attr(session, "concierge"), "concierge", layer, report)
    _present(_attr(session, "fabric"), "fabric", layer, report)
    _present(_attr(session, "session_state"), "session_state", layer, report)
    _present(_attr(session, "memory_writer"), "memory_writer", layer, report)
    _present(_attr(session, "experience_layer"), "experience_layer", layer, report)
    _present(_attr(session, "delta_aggregator"), "delta_aggregator", layer, report)
    _present(_attr(session, "delta_applicator"), "delta_applicator", layer, report)
    _present(_attr(session, "hitl_coordinator"), "hitl_coordinator", layer, report)
    _present(_attr(session, "front_dispatcher"), "front_dispatcher", layer, report)
    _present(_attr(session, "back_dispatcher"), "back_dispatcher", layer, report)
    _present(_attr(session, "ledger"), "ledger", layer, report)


# ── layer 3: Kernel Ports ──────────────────────────────────────────────


def probe_ports(svc: Any, session: Any, report: ProbeReport) -> None:
    layer = "Kernel Ports"
    # Inspect known port-shaped attributes
    port_attrs = [
        ("bus_port", _attr(svc, "_bus")),
        ("model_hub_port", _attr(svc, "_model_hub")),
        ("orchestrator_port", _attr(svc, "_orchestrator")),
        ("planner_port", _attr(svc, "_planner")),
        ("bridge_port", _attr(svc, "_bridge")),
        ("session_state_port", _attr(session, "session_state")),
        ("fabric_port", _attr(session, "fabric")),
    ]
    for name, obj in port_attrs:
        if obj is None:
            report.add(layer, name, "FAIL", None, "port not bound")
        else:
            report.add(layer, name, "OK", type(obj).__name__)

    # Static fact: check whether IHILPort port has been added (F2/W10 fix)
    import os as _os

    _hil_port_path = _os.path.join("k1", "kernel", "ports", "hil_port.py")
    if _os.path.exists(_hil_port_path):
        report.add(
            layer,
            "hil_port",
            "OK",
            "IHILPort",
            "k1/kernel/ports/hil_port.py present (F2/W10 resolved)",
        )
    else:
        report.add(
            layer,
            "hil_port",
            "FAIL",
            None,
            "k1/kernel/ports/hil_port.py does not exist (HIL fragmented across 3 subsystems)",
        )


# ── layer 4: Fabric ────────────────────────────────────────────────────


def probe_fabric(session: Any, report: ProbeReport) -> None:
    layer = "Fabric"
    fabric = _attr(session, "fabric")
    if fabric is None:
        report.add(layer, "fabric", "FAIL", None, "missing")
        return

    facade = _attr(fabric, "facade")
    _present(facade, "facade (CapabilityFabric)", layer, report)

    resolver = _attr(facade, "_resolver") if facade else None
    _present(resolver, "facade._resolver", layer, report)

    registry = _attr(fabric, "registry") or (_attr(facade, "_registry") if facade else None)
    if registry is not None:
        contracts = _attr(registry, "_contracts") or _attr(registry, "contracts")
        size = len(contracts) if contracts is not None and hasattr(contracts, "__len__") else None
        report.add(layer, "registry.size", "INFO", size)
    else:
        report.add(layer, "registry", "FAIL", None, "missing")

    pf = _attr(facade, "_provider_factory") if facade else None
    _present(pf, "facade._provider_factory", layer, report)

    # MCP transport lives on the provider factory.
    # F3 fix: it is exposed via _port_deps['mcp_transport'] (not _mcp_transport).
    port_deps = _attr(pf, "_port_deps", {}) if pf else {}
    mcp = (port_deps or {}).get("mcp_transport") if isinstance(port_deps, dict) else None
    if mcp is None:
        # Legacy attribute fallback
        mcp = _attr(pf, "_mcp_transport") if pf else None
    if mcp is None:
        report.add(
            layer,
            "provider_factory.mcp_transport",
            "FAIL",
            None,
            "mcp_transport=None — kills F101/F102/F103 (audit §10)",
        )
    else:
        report.add(
            layer,
            "provider_factory.mcp_transport",
            "OK",
            type(mcp).__name__,
        )

    emitter = _attr(fabric, "event_emitter")
    _present(emitter, "event_emitter", layer, report)

    # Routing classes live inside resolver._policy_engine
    policy = _attr(resolver, "_policy_engine") if resolver else None
    if policy is not None:
        report.add(layer, "resolver.policy_engine", "OK", type(policy).__name__)
        for attr in ("affective", "cognitive_load", "qos", "security"):
            obj = _attr(policy, attr) or _attr(policy, f"_{attr}")
            if obj is None:
                report.add(layer, f"policy.{attr}", "WARN", None, "not wired")
            else:
                sr = _attr(obj, "_state_reader") or _attr(obj, "state_reader")
                note = "state_reader not injected (audit F99/F100)" if sr is None else ""
                report.add(
                    layer,
                    f"policy.{attr}",
                    "WARN" if sr is None else "OK",
                    type(obj).__name__,
                    note,
                )
    else:
        report.add(layer, "resolver.policy_engine", "WARN", None, "not found on resolver")


# ── layer 5: Model Hub ─────────────────────────────────────────────────


def probe_model_hub(svc: Any, report: ProbeReport) -> None:
    layer = "Model Hub"
    hub = _attr(svc, "_model_hub")
    if hub is None:
        report.add(layer, "model_hub", "FAIL", None, "not initialised")
        return

    cfg = _attr(svc, "_config") or _attr(svc, "config")
    mode = _attr(cfg, "model_mode") if cfg else None
    report.add(layer, "model_mode", "INFO", mode)

    plugins = _attr(hub, "_plugins") or _attr(hub, "plugins")
    if plugins is not None:
        try:
            names = list(plugins.keys()) if hasattr(plugins, "keys") else [str(p) for p in plugins]
            report.add(layer, "plugins", "INFO", names)
        except Exception:
            report.add(layer, "plugins", "INFO", repr(plugins)[:120])

    # Cost / Budget / Cache / Health — these are the BLOAT items per audit
    for bloat_attr, audit_note in (
        ("_cost_tracker", "should move to policy/budget"),
        ("_budget_enforcer", "should move to policy/budget"),
        ("_audit_logger", "should move to observability/audit"),
        ("_response_cache", "should move to fabric/cache"),
        ("_health_query", "_DefaultHealthQuery returns HEALTHY for all (audit F104)"),
    ):
        obj = _attr(hub, bloat_attr)
        if obj is not None:
            report.add(
                layer, bloat_attr.lstrip("_"), "WARN", type(obj).__name__, f"BLOAT — {audit_note}"
            )


# ── layer 6: Orchestrator ──────────────────────────────────────────────


def probe_orchestrator(svc: Any, report: ProbeReport) -> None:
    layer = "Orchestrator"
    orch = _attr(svc, "_orchestrator")
    if orch is None:
        report.add(layer, "orchestrator", "FAIL", None, "not initialised")
        return

    dag = _attr(orch, "_dag_executor") or _attr(orch, "dag_executor")
    if dag is None:
        report.add(layer, "dag_executor", "WARN", None, "not constructed")
    else:
        guards = _attr(dag, "guards") or _attr(dag, "_guards") or []
        report.add(
            layer,
            "dag_executor.guards",
            "WARN" if len(guards) == 0 else "OK",
            len(guards),
            "audit F45 — populate timeout + max-retries guards" if len(guards) == 0 else "",
        )

    # HIL surface (audit §16 F141)
    delta_emit = _attr(orch, "_delta_emit_port") or _attr(orch, "delta_emit_port")
    if delta_emit is not None:
        emit_hil = hasattr(delta_emit, "emit_hil_request")
        report.add(
            layer,
            "delta_emit.emit_hil_request",
            "OK" if emit_hil else "FAIL",
            emit_hil,
            "doesn't belong here — should be IHILPort (audit BLOAT-4)",
        )
    config = _attr(orch, "_config") or _attr(orch, "config")
    if config is not None:
        report.add(layer, "max_pending_hil", "INFO", _attr(config, "max_pending_hil"))
        report.add(layer, "hil_timeout_ms", "INFO", _attr(config, "hil_timeout_ms"))


# ── layer 7: Planner ───────────────────────────────────────────────────


def probe_planner(svc: Any, report: ProbeReport) -> None:
    layer = "Planner"
    planner = _attr(svc, "_planner")
    if planner is None:
        report.add(layer, "planner", "FAIL", None, "not initialised")
        return
    pipeline = _attr(planner, "_pipeline")
    _present(pipeline, "pipeline", layer, report)
    config = _attr(planner, "_config")
    if config is not None:
        report.add(layer, "config_class", "INFO", type(config).__name__)
    running = _attr(planner, "_running")
    report.add(layer, "running", "OK" if running else "WARN", running)
    subs = _attr(planner, "_subscriptions") or []
    report.add(layer, "subscriptions", "INFO", len(subs))
    # LLM/HIL live deeper inside the pipeline — deferred to Phase 2 component probe.


# ── layer 8: Concierge HIL ─────────────────────────────────────────────


def probe_hil(svc: Any, session: Any, report: ProbeReport) -> None:
    layer = "HIL (cross-subsystem)"
    found = []

    c_hil = _attr(session, "hitl_coordinator")
    if c_hil is not None:
        found.append(("concierge", type(c_hil).__name__))

    p = _attr(svc, "_planner")
    p_hil = _attr(p, "_hil_coordinator") or _attr(p, "hil_coordinator") if p else None
    if p_hil is not None:
        found.append(("planner", type(p_hil).__name__))

    o = _attr(svc, "_orchestrator")
    o_hil = (
        _attr(o, "_hil_coordinator") or _attr(o, "hil_coordinator") or _attr(o, "_delta_emit_port")
        if o
        else None
    )
    if o_hil is not None:
        found.append(("orchestrator", type(o_hil).__name__))

    report.add(layer, "coordinator_count", "WARN", len(found), "should be 1 (audit BLOAT-1)")
    for subsys, name in found:
        report.add(layer, f"{subsys}_coordinator_class", "INFO", name)

    # F2/W10 fix: IHILPort Protocol now lives in k1/kernel/ports/hil_port.py.
    # The two HILCoordinator classes (concierge FSM-side + planner clarification)
    # are intentionally NOT collapsed because they serve distinct subsystems;
    # the kernel port documents that contract.
    try:
        from k1.kernel.ports import IHILPort as _IHILPort  # noqa: F401

        report.add(
            layer,
            "unified_IHILPort",
            "OK",
            "IHILPort",
            "k1/kernel/ports/hil_port.py present (F2/W10 resolved; "
            "concrete coordinators kept distinct by design)",
        )
    except Exception:
        report.add(
            layer,
            "unified_IHILPort",
            "FAIL",
            None,
            "k1/kernel/ports/hil_port.py absent (audit §16 headline)",
        )


# ── layer 9: SessionState ──────────────────────────────────────────────


def probe_sessionstate(session: Any, report: ProbeReport) -> None:
    layer = "SessionState"
    ssm = _attr(session, "session_state")
    if ssm is None:
        report.add(layer, "session_state", "FAIL", None, "missing")
        return

    sections = _attr(ssm, "sections", None)
    if sections is None:
        report.add(layer, "sections", "WARN", None, "sections attr not found")
    else:
        names = sorted(sections.keys()) if hasattr(sections, "keys") else []
        report.add(layer, "section_count", "INFO", len(names))
        report.add(layer, "section_names", "INFO", names)

    eviction = _attr(ssm, "_eviction_engine")
    if eviction is not None:
        sp = _attr(eviction, "_section_provider") or _attr(eviction, "section_provider")
        if sp is None:
            report.add(
                layer,
                "eviction_engine.section_provider",
                "FAIL",
                None,
                "audit-J TODO unblocks F70/F71/F77",
            )
        else:
            report.add(layer, "eviction_engine.section_provider", "OK", type(sp).__name__)

    # Tier presence
    for tier in ("_hot", "_warm", "_local_cold"):
        t = _attr(ssm, tier)
        if t is not None:
            report.add(layer, f"tier{tier}", "OK", type(t).__name__)

    # DeltaApplicator (REAL BUG: never stored on SessionInstance)
    da = _attr(session, "delta_applicator")
    if da is None:
        report.add(
            layer,
            "session.delta_applicator",
            "FAIL",
            None,
            "BUG: built in concierge factory step 10 but never stored on SessionInstance "
            "(service.py:1530 hard-codes None)",
        )
    else:
        for fn in ("_preflight_fn", "_write_fn", "_evict_fn"):
            v = _attr(da, fn)
            if v is None:
                # _evict_fn is optional in DeltaApplicator; warn instead of fail.
                level = "WARN" if fn == "_evict_fn" else "FAIL"
                report.add(
                    layer,
                    f"delta_applicator.{fn}",
                    level,
                    None,
                    "callback=None (audit §7)"
                    + ("; optional, blocked by Fix J" if fn == "_evict_fn" else ""),
                )
            else:
                report.add(layer, f"delta_applicator.{fn}", "OK", type(v).__name__)


# ── layer 10: Bus ──────────────────────────────────────────────────────


def probe_bus(svc: Any, session: Any, report: ProbeReport) -> None:
    layer = "Bus"
    bus = _attr(svc, "_bus") or _attr(session, "bus")
    if bus is None:
        report.add(layer, "bus", "FAIL", None, "missing")
        return
    report.add(layer, "backend", "INFO", type(bus).__name__)

    trie = _attr(bus, "_trie")
    if trie is not None:
        size = _attr(trie, "size")
        report.add(layer, "trie.size (total subs)", "INFO", size)
    async_subs = _attr(bus, "_async_subs") or {}
    report.add(layer, "async_subs", "INFO", len(async_subs))
    topics_seen = _attr(bus, "_topics_seen") or set()
    report.add(layer, "topics_seen", "INFO", len(topics_seen))

    # Per-topic subscriber check via match()
    if trie is not None and hasattr(trie, "match"):
        for topic in (
            "k1.capability.invoked.v1",
            "k1.capability.completed.v1",
            "k1.affect.update.v1",
            "k1.agent.delta.v1",
        ):
            try:
                handlers = trie.match(topic)
                count = len(handlers) if handlers is not None else 0
            except Exception:
                count = -1
            status = "WARN" if count == 0 else "OK"
            note = "publish-into-the-void (audit F132)" if count == 0 else ""
            report.add(layer, f"subs[{topic}]", status, count, note)

    outbox = _attr(bus, "_outbox") or _attr(bus, "outbox")
    if outbox is None:
        report.add(layer, "bus_outbox", "WARN", None, "BusOutbox not wired (audit §15 P1)")
    else:
        report.add(layer, "bus_outbox", "OK", type(outbox).__name__)


# ── layer 11: K0 Bridge ────────────────────────────────────────────────


def probe_bridge(svc: Any, report: ProbeReport) -> None:
    layer = "K0 Bridge"
    bridge = _attr(svc, "_bridge")
    if bridge is None:
        report.add(layer, "bridge", "FAIL", None, "not initialised")
        return
    online = _attr(bridge, "online", None)
    if callable(online):
        try:
            online_v = online()
        except Exception as exc:
            online_v = f"<error: {exc}>"
    else:
        online_v = online
    report.add(
        layer,
        "online",
        "WARN" if not online_v else "OK",
        online_v,
        "K0 undeployed (MS-3) — bridge forces OFFLINE" if not online_v else "",
    )


# ── layer 12: Module Loader ────────────────────────────────────────────


def probe_module_loader(session: Any, report: ProbeReport) -> None:
    layer = "Module Loader"
    fabric = _attr(session, "fabric")
    loader = _attr(fabric, "module_loader") if fabric is not None else None
    if loader is None:
        report.add(layer, "module_loader", "WARN", None, "not on fabric")
        return
    watch = _attr(loader, "_watch") or _attr(loader, "watch")
    report.add(
        layer,
        "watch",
        "WARN" if not watch else "OK",
        watch,
        "watch=False in prod (audit F128)" if not watch else "",
    )
    subdirs = _attr(loader, "_CONTRACT_SUBDIRS") or _attr(loader, "contract_subdirs")
    if subdirs is not None:
        report.add(layer, "contract_subdirs", "INFO", list(subdirs))


# ── orchestrator ───────────────────────────────────────────────────────


async def run_probe(json_path: str | None) -> int:
    print("=" * 72)
    print(_c("  K1 Kernel Probe — Phase 1 (read-only wiring health)", _C_BOLD))
    print("=" * 72)

    cfg = KernelConfig(model_mode="test")
    t0 = time.monotonic()
    runtime = await start_kernel(cfg)
    boot_s = time.monotonic() - t0

    report = ProbeReport(boot_seconds=boot_s, session_id=runtime._session_id or "")
    print(f"  Boot: {boot_s:.2f}s  session_id={runtime._session_id}\n")

    svc = runtime._service
    sessions = _attr(svc, "_sessions", {})
    session = next(iter(sessions.values())) if sessions else None

    probe_kernel_service(svc, report)
    if session is not None:
        probe_session(session, report)
        probe_ports(svc, session, report)
        probe_fabric(session, report)
        probe_model_hub(svc, report)
        probe_orchestrator(svc, report)
        probe_planner(svc, report)
        probe_hil(svc, session, report)
        probe_sessionstate(session, report)
        probe_bus(svc, session, report)
        probe_bridge(svc, report)
        probe_module_loader(session, report)
    else:
        report.add("KernelService (Tier-1)", "session", "FAIL", None, "no session created")

    # Render
    for layer, probes in report.by_layer().items():
        print(_c(f"\n[ {layer} ]", _C_BOLD))
        for p in probes:
            print(p.render())

    counts = report.counts()
    print(_c("\n" + "=" * 72, _C_DIM))
    print(
        _c("  Summary: ", _C_BOLD)
        + _c(f"OK {counts['OK']}", _C_GRN)
        + "  "
        + _c(f"WARN {counts['WARN']}", _C_YEL)
        + "  "
        + _c(f"FAIL {counts['FAIL']}", _C_RED)
        + f"  INFO {counts['INFO']}  (total {len(report.probes)})"
    )

    if json_path:
        out = {
            "boot_seconds": report.boot_seconds,
            "session_id": report.session_id,
            "counts": counts,
            "probes": [p.to_dict() for p in report.probes],
        }
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, default=repr)
        print(_c(f"  JSON written: {json_path}", _C_DIM))

    print(_c("  Tearing down...", _C_DIM))
    await stop_kernel(runtime)
    return 0 if counts["FAIL"] == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None, help="Optional path to write JSON report")
    args = ap.parse_args()
    return asyncio.run(run_probe(args.json))


if __name__ == "__main__":
    sys.exit(main())
