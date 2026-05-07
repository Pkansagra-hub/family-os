"""kernel_probe_phase3_fabric.py — Phase 3 Fabric capability invocation probe.

Drives a real `fabric.execute(CapabilityRequest)` end-to-end against the
booted kernel, after injecting a `TestMCPTransport` into ProviderFactory's
port_deps so MCP-typed contracts resolve without a real MCP server.

What it verifies:
  - fabric.facade._provider_factory._port_deps['mcp_transport'] is truly
    None at boot (audit F101–F103) — corrects Phase 1's incorrect attr
    walk that looked for `_mcp_transport` slot.
  - Capability registry actually has contracts loaded by ModuleLoader.
  - End-to-end execute path: emit_invoked → resolve → provider build →
    circuit breaker → emit_completed.
  - LocalEventAdapter captures k1.capability.invoked.v1 +
    k1.capability.completed.v1 (audit F132 publish-into-the-void).
  - Resolution failure path: invoke a non-existent capability and
    confirm CapabilityResult.success=False (no exception escape).

Run:
    $env:PYTHONPATH="D:\\familyos"; $env:PYTHONIOENCODING="utf-8"
    python -m scripts.kernel_probe_phase3_fabric
    python -m scripts.kernel_probe_phase3_fabric --json data/kernel_probe_fabric.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from typing import Any

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.bootstrap import start_kernel, stop_kernel
from scripts._probe_common import _C_DIM, ProbeReport, _attr, _c

# ── transport injection ────────────────────────────────────────────────


def _inject_test_mcp_transport(fabric: Any, report: ProbeReport) -> Any:
    """Patch provider_factory._port_deps['mcp_transport'] with TestMCPTransport.

    Returns the transport (so probe can inspect captured calls) or None.
    """
    layer = "Fabric Wiring"
    facade = _attr(fabric, "facade")
    pf = _attr(facade, "_provider_factory") if facade else None
    if pf is None:
        report.add(layer, "provider_factory", "FAIL", None, "facade._provider_factory missing")
        return None

    # E7.M1.1: facade should hold the kernel-owned HumanInTheLoopService.
    fab_hil = _attr(facade, "_hil_port")
    if fab_hil is None:
        report.add(
            layer,
            "facade._hil_port",
            "FAIL",
            None,
            "fabric facade has no _hil_port — E7 wiring broken",
        )
    else:
        report.add(layer, "facade._hil_port", "OK", type(fab_hil).__name__)

    port_deps = _attr(pf, "_port_deps", {}) or {}
    existing = port_deps.get("mcp_transport")
    if existing is None:
        report.add(
            layer,
            "_port_deps[mcp_transport].pre_inject",
            "FAIL",
            None,
            "audit F101–F103 confirmed: mcp_transport is None at boot",
        )
    else:
        report.add(
            layer,
            "_port_deps[mcp_transport].pre_inject",
            "OK",
            type(existing).__name__,
            "transport wired by FabricFactory (F3 fix)",
        )
        # Skip TestMCPTransport injection: production transport is in
        # place. Overwriting it would unwire the BuildAgentHandler
        # registered by FabricFactory STEP 19b (F4 fix).
        return existing

    try:
        from k1.fabric.adapters.test_mcp_transport import TestMCPTransport
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "TestMCPTransport_import", "FAIL", None, f"{type(exc).__name__}: {exc}")
        return None

    transport = TestMCPTransport(connected=True)
    port_deps["mcp_transport"] = transport
    pf._port_deps = port_deps  # ensure write back
    report.add(layer, "_port_deps[mcp_transport].post_inject", "OK", type(transport).__name__)
    return transport


# ── registry inspection ───────────────────────────────────────────────


def _inspect_registry(fabric: Any, report: ProbeReport) -> list[Any]:
    layer = "Capability Registry"
    facade = _attr(fabric, "facade")
    registry = _attr(fabric, "registry") or (_attr(facade, "_registry") if facade else None)
    if registry is None:
        report.add(layer, "registry", "FAIL", None, "no registry")
        return []
    contracts: list[Any] = []
    try:
        contracts = list(registry.list_all())
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "list_all", "FAIL", None, f"{type(exc).__name__}: {exc}")
        return []

    report.add(layer, "registered_contracts", "INFO", len(contracts))

    # Group by capability_name prefix
    by_prefix: dict[str, int] = {}
    for c in contracts:
        name = _attr(c, "capability_name") or _attr(c, "name") or ""
        prefix = name.split(".")[0] if "." in name else name
        by_prefix[prefix] = by_prefix.get(prefix, 0) + 1
    if by_prefix:
        report.add(layer, "by_prefix", "INFO", by_prefix)

    if not contracts:
        report.add(
            layer,
            "empty_registry",
            "WARN",
            None,
            "ModuleLoader scanned 0 contracts — invoke probe will skip",
        )
    return contracts


# ── pick a capability to invoke ───────────────────────────────────────


def _pick_invokable(contracts: list[Any]) -> Any | None:
    """Return a contract preferring tool.* (lowest blast radius)."""
    pref = ["tool.", "agent.", "workflow.", "concierge."]
    for prefix in pref:
        for c in contracts:
            name = _attr(c, "capability_name") or _attr(c, "name") or ""
            if name.startswith(prefix):
                return c
    return contracts[0] if contracts else None


# ── execute probe ──────────────────────────────────────────────────────


async def probe_execute(
    fabric: Any, transport: Any, contracts: list[Any], report: ProbeReport
) -> None:
    layer = "Fabric Execute"
    facade = _attr(fabric, "facade")
    if facade is None:
        report.add(layer, "facade", "FAIL", None, "missing")
        return

    contract = _pick_invokable(contracts)
    if contract is None:
        report.add(layer, "pick", "WARN", None, "no contract available, skipping execute")
        return
    cap_name = _attr(contract, "capability_name") or _attr(contract, "name") or "?"
    report.add(layer, "selected_capability", "INFO", cap_name)

    # Subscribe to capability events on event_port to verify emission
    event_port = _attr(fabric, "event_port") or _attr(facade, "_event_port")
    captured_topics: list[str] = []
    sub_handles: list[Any] = []
    if event_port is not None and hasattr(event_port, "subscribe"):
        for topic in (
            "k1.capability.invoked.v1",
            "k1.capability.completed.v1",
            "k1.capability.failed.v1",
        ):
            try:

                def _mk(t: str):
                    def _h(*args: Any, **kwargs: Any) -> None:
                        captured_topics.append(t)

                    return _h

                h = event_port.subscribe(topic, _mk(topic))
                sub_handles.append(h)
            except Exception:  # noqa: BLE001
                pass

    # Build minimal CapabilityRequest
    try:
        from k1.fabric.types import CapabilityRequest, SafetyBand
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "import_CapabilityRequest", "FAIL", None, f"{type(exc).__name__}: {exc}")
        return

    # Use AMBER band so write/execute capabilities pass the
    # PolicyEngine band check (most write tools require >=AMBER).
    req = CapabilityRequest(
        capability_name=cap_name,
        params={"probe": True},
        caller="kernel_probe_phase3",
        session_id="probe-session",
        safety_band=SafetyBand.AMBER.value,
    )

    try:
        t0 = time.perf_counter()
        result = await asyncio.wait_for(facade.execute(req), timeout=10.0)
        elapsed_ms = (time.perf_counter() - t0) * 1000
    except asyncio.TimeoutError:
        report.add(layer, "execute", "FAIL", None, "timed out after 10s")
        return
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "execute", "FAIL", None, f"raised {type(exc).__name__}: {exc}")
        return

    success = _attr(result, "success", False)
    err = _attr(result, "error", None)
    pid = _attr(result, "provider_id", "?")
    report.add(
        layer,
        "execute",
        "OK" if success else "WARN",
        f"success={success} provider={pid} ({elapsed_ms:.0f}ms)",
        f"error={err!r}" if err else "",
    )

    # Event emission verification
    await asyncio.sleep(0.05)  # let subscribers drain
    report.add(
        layer,
        "events.invoked_captured",
        "OK" if "k1.capability.invoked.v1" in captured_topics else "FAIL",
        captured_topics.count("k1.capability.invoked.v1"),
    )
    if success:
        report.add(
            layer,
            "events.completed_captured",
            "OK" if "k1.capability.completed.v1" in captured_topics else "FAIL",
            captured_topics.count("k1.capability.completed.v1"),
        )
    else:
        report.add(
            layer,
            "events.failed_captured",
            "OK" if "k1.capability.failed.v1" in captured_topics else "INFO",
            captured_topics.count("k1.capability.failed.v1"),
        )

    # MCP transport call inspection (only relevant if MCP-typed)
    if transport is not None and hasattr(transport, "call_count"):
        report.add(layer, "mcp_transport.call_count", "INFO", transport.call_count)


# ── failure path probe ────────────────────────────────────────────────


async def probe_resolution_failure(fabric: Any, report: ProbeReport) -> None:
    layer = "Fabric Failure Path"
    facade = _attr(fabric, "facade")
    if facade is None:
        return
    try:
        from k1.fabric.types import CapabilityRequest
    except Exception:  # noqa: BLE001
        return

    req = CapabilityRequest(
        capability_name=f"tool.nonexistent.{uuid.uuid4().hex[:6]}",
        caller="kernel_probe_phase3",
    )
    try:
        result = await asyncio.wait_for(facade.execute(req), timeout=5.0)
    except Exception as exc:  # noqa: BLE001
        report.add(
            layer,
            "execute_unknown_cap",
            "FAIL",
            None,
            f"raised {type(exc).__name__}: {exc} (should return failure_result, not raise)",
        )
        return
    success = _attr(result, "success", True)
    err = _attr(result, "error", None)
    if not success:
        report.add(
            layer,
            "execute_unknown_cap",
            "OK",
            f"success=False error={err!r}",
            "graceful failure (audit-correct)",
        )
    else:
        report.add(
            layer,
            "execute_unknown_cap",
            "FAIL",
            None,
            "unknown capability returned success=True ?!",
        )


# ── policy engine cognitive_load fix-up probe ────────────────────────


def probe_policy_cognitive(fabric: Any, report: ProbeReport) -> None:
    layer = "Policy Engine"
    facade = _attr(fabric, "facade")
    resolver = _attr(facade, "_resolver") if facade else None
    policy = _attr(resolver, "_policy_engine") if resolver else None
    if policy is None:
        report.add(layer, "policy_engine", "FAIL", None, "missing")
        return
    # The audit said cognitive_load was missing; map of __slots__:
    cog = _attr(policy, "_cognitive") or _attr(policy, "cognitive")
    if cog is None:
        report.add(
            layer,
            "_cognitive",
            "FAIL",
            None,
            "PolicyEngine has no _cognitive attribute (audit F98 bug)",
        )
    else:
        report.add(layer, "_cognitive", "OK", type(cog).__name__)


# ── runner ─────────────────────────────────────────────────────────────


async def run_probe(json_path: str | None) -> int:
    print("=" * 72)
    print(_c("  K1 Kernel Probe — Phase 3 (Fabric capability invocation)", "\x1b[1m"))
    print("=" * 72)

    cfg = KernelConfig(model_mode="test")
    t0 = time.perf_counter()
    runtime = await start_kernel(cfg)
    boot_s = time.perf_counter() - t0
    print(f"  Boot: {boot_s:.2f}s\n")

    report = ProbeReport()
    svc = runtime._service
    sessions = _attr(svc, "_sessions", {})
    session = next(iter(sessions.values())) if sessions else None

    if session is None:
        report.add("Boot", "session", "FAIL", None, "no session created")
    else:
        fabric = _attr(session, "fabric")
        if fabric is None:
            report.add("Boot", "fabric", "FAIL", None, "session.fabric is None")
        else:
            transport = _inject_test_mcp_transport(fabric, report)
            probe_policy_cognitive(fabric, report)
            contracts = _inspect_registry(fabric, report)
            await probe_execute(fabric, transport, contracts, report)
            await probe_resolution_failure(fabric, report)

    report.render("K1 Kernel Probe — Phase 3 (Fabric capability invocation)")

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
