"""K1 Kernel Probe — Phase 8 (Model Hub providers).

By default runs in STUB mode (zero API calls): inventories the hub's
services (registry, router, dispatcher, audit logger), confirms the
StubProviderPlugin is wired, and exercises one synthetic ``execute()``
against the stub to verify the full HubRequest -> NormalizationLayer ->
dispatcher -> plugin -> ResponseMetadata roundtrip.

With ``--hub gemini`` (requires GOOGLE_API_KEY) it boots the kernel in
``model_mode="hub"``, asserts the google plugin loaded via the
declarative ProviderConfig path, and sends ONE tiny CHAT request to
``gemini-2.5-flash`` (capped at 50 output tokens) to verify:
  - real network call succeeds
  - AuditLogger captured the call

``--hub all`` registers probes for every known provider but skips any
without configured credentials (INFO, not FAIL).

Usage:
  python -m scripts.kernel_probe_phase8_modelhub --json data/kernel_probe_phase8_stub.json
  python -m scripts.kernel_probe_phase8_modelhub --hub gemini --json data/kernel_probe_phase8_gemini.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── repo path ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from k1.concierge.config.kernel import KernelConfig  # noqa: E402
from k1.kernel.bootstrap import start_kernel, stop_kernel  # noqa: E402
from k1.model_hub.types import (  # noqa: E402
    CapabilityType,
    ChatPayload,
    HubRequest,
    Message,
    ModelPreference,
    RequestConstraints,
)
from scripts._probe_common import ProbeReport, _attr  # noqa: E402

# ── env loader (for --hub gemini) ────────────────────────────────────────

_ENV_FILE = ROOT / "poc" / "chat_experience_poc" / ".env"


def _load_dotenv_for_keys(keys: List[str]) -> None:
    """Pull selected keys from the local .env if not already set."""
    if not _ENV_FILE.exists():
        return
    try:
        text = _ENV_FILE.read_text(encoding="utf-8")
    except Exception:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k in keys and not os.environ.get(k):
            os.environ[k] = v


# ── Hub introspection ────────────────────────────────────────────────────

KNOWN_PROVIDERS = ("openai", "anthropic", "google", "ollama", "vllm")
PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "ollama": None,  # no creds
    "vllm": None,
}


def probe_hub_wiring(svc: Any, report: ProbeReport) -> Optional[Any]:
    layer = "Hub wiring"
    hub = _attr(svc, "_model_hub")
    if hub is None:
        report.add(layer, "svc._model_hub", "FAIL", None, "kernel did not construct a hub")
        return None
    report.add(layer, "svc._model_hub", "OK", type(hub).__name__)

    router = _attr(hub, "_router")
    registry = _attr(hub, "_registry")
    health = _attr(hub, "_health")
    report.add(
        layer, "router", "OK" if router else "FAIL", type(router).__name__ if router else None
    )
    report.add(
        layer,
        "registry",
        "OK" if registry else "FAIL",
        type(registry).__name__ if registry else None,
    )
    report.add(
        layer,
        "health adapter",
        "OK" if health else "WARN",
        type(health).__name__ if health else None,
    )

    # RequestRouter sub-services
    dispatcher = _attr(router, "_dispatcher") if router else None
    audit = _attr(router, "_audit_logger") if router else None
    cache = _attr(router, "_response_cache") if router else None
    norm = _attr(router, "_normalization") if router else None
    sel = _attr(router, "_model_selector") if router else None
    cap_router = _attr(router, "_capability_router") if router else None
    metrics = _attr(router, "_metrics") if router else None

    for name, obj in [
        ("dispatcher", dispatcher),
        ("audit_logger", audit),
        ("response_cache", cache),
        ("normalization", norm),
        ("capability_router", cap_router),
        ("model_selector", sel),
        ("metrics_port", metrics),
    ]:
        report.add(
            layer,
            f"router.{name}",
            "OK" if obj is not None else "WARN",
            type(obj).__name__ if obj is not None else None,
        )
    return hub


def probe_provider_inventory(hub: Any, report: ProbeReport, *, expected: List[str]) -> List[str]:
    layer = "Providers"
    registry = _attr(hub, "_registry")
    if registry is None:
        report.add(layer, "registry", "FAIL", None)
        return []
    count = registry.provider_count if hasattr(registry, "provider_count") else -1
    report.add(layer, "provider_count", "OK" if count >= 1 else "FAIL", count)
    providers = registry.list_providers() if hasattr(registry, "list_providers") else []
    pids = sorted({_attr(p, "provider_id", "?") for p in providers})
    report.add(layer, "registered provider_ids", "OK" if pids else "FAIL", pids)

    # Capability index
    if hasattr(registry, "get_capability_index"):
        idx = registry.get_capability_index()
        cap_summary = {
            cap.value if hasattr(cap, "value") else str(cap): [
                _attr(p, "provider_id", "?") for p in plist
            ]
            for cap, plist in idx.items()
        }
        report.add(layer, "capability_index", "INFO", cap_summary)

    for pid in expected:
        if pid in pids:
            report.add(layer, f"expected:{pid}", "OK", "registered")
        elif PROVIDER_ENV.get(pid) and not os.environ.get(PROVIDER_ENV[pid]):
            report.add(
                layer,
                f"expected:{pid}",
                "INFO",
                "skipped (no creds)",
                f"set {PROVIDER_ENV[pid]} to enable",
            )
        else:
            report.add(layer, f"expected:{pid}", "WARN", "not registered")
    return pids


def _make_chat_request(
    model_id: str, *, max_tokens: int = 50, provider_id: str | None = None
) -> HubRequest:
    payload = ChatPayload(
        messages=[Message(role="user", content="Reply with the single word: pong")]
    )
    return HubRequest(
        capability=CapabilityType.CHAT,
        payload=payload,
        constraints=RequestConstraints(
            max_tokens=max_tokens,
            temperature=0.0,
            timeout_ms=30000,
            provider_preference=provider_id,
            model_preference=ModelPreference(
                preferred_model=model_id, preferred_provider=provider_id
            ),
            consumer_id="probe-phase8",
        ),
        trace_id=f"probe-phase8-{uuid.uuid4().hex[:8]}",
    )


async def probe_stub_execute(hub: Any, report: ProbeReport) -> None:
    layer = "Stub execute"
    router = _attr(hub, "_router")
    audit = _attr(router, "_audit_logger")

    audit_before = audit.count if audit else -1

    req = _make_chat_request("stub-canned-v1", max_tokens=20, provider_id="stub")
    t0 = time.perf_counter()
    try:
        resp = await hub.execute(req)
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "hub.execute(stub)", "FAIL", None, f"{type(exc).__name__}: {exc}")
        return
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    report.add(layer, "hub.execute(stub)", "OK", f"{elapsed_ms}ms")

    md = _attr(resp, "metadata")
    report.add(
        layer, "response.metadata", "OK" if md else "FAIL", type(md).__name__ if md else None
    )
    report.add(layer, "metadata.provider_id", "OK", _attr(md, "provider_id"))
    report.add(layer, "metadata.model_id", "OK", _attr(md, "model_id"))
    usage = _attr(md, "usage")
    report.add(
        layer,
        "metadata.usage",
        "INFO",
        {"prompt": _attr(usage, "prompt_tokens"), "completion": _attr(usage, "completion_tokens")},
    )
    report.add(layer, "metadata.cost_usd", "OK", _attr(md, "cost_usd"))
    report.add(layer, "metadata.latency_ms", "OK", _attr(md, "latency_ms"))
    report.add(layer, "metadata.cache_hit", "INFO", _attr(md, "cache_hit"))
    report.add(
        layer, "metadata.trace_id", "OK" if _attr(md, "trace_id") else "FAIL", _attr(md, "trace_id")
    )

    if audit:
        report.add(
            layer,
            "audit_logger delta records",
            "OK" if audit.count - audit_before >= 1 else "WARN",
            audit.count - audit_before,
        )


async def probe_real_provider(
    hub: Any, report: ProbeReport, *, provider_id: str, model_id: str
) -> None:
    """Send ONE tiny real request and assert cost/audit accounting."""
    layer = f"Real {provider_id}"
    registry = _attr(hub, "_registry")
    if not registry or not registry.is_registered(provider_id):
        report.add(layer, f"{provider_id} registered", "FAIL", False, "provider not loaded by hub")
        return
    report.add(layer, f"{provider_id} registered", "OK", True)

    router = _attr(hub, "_router")
    audit = _attr(router, "_audit_logger")

    audit_before = audit.count if audit else 0

    req = _make_chat_request(model_id, max_tokens=20, provider_id=provider_id)
    report.add(layer, "request model_id", "INFO", model_id)
    report.add(layer, "request max_tokens", "INFO", 20)

    t0 = time.perf_counter()
    try:
        resp = await hub.execute(req)
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "hub.execute(real)", "FAIL", None, f"{type(exc).__name__}: {exc}")
        return
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    report.add(layer, "hub.execute(real)", "OK", f"{elapsed_ms}ms")

    md = _attr(resp, "metadata")
    result = _attr(resp, "result")
    text_preview = ""
    if result is not None:
        text_preview = (_attr(result, "text", "") or str(result))[:80]
    report.add(layer, "response.text preview", "OK" if text_preview else "WARN", text_preview)
    report.add(
        layer,
        "metadata.provider_id",
        "OK" if _attr(md, "provider_id") == provider_id else "WARN",
        _attr(md, "provider_id"),
    )
    report.add(layer, "metadata.model_id", "INFO", _attr(md, "model_id"))
    usage = _attr(md, "usage")
    pt = _attr(usage, "prompt_tokens", 0) or 0
    ct = _attr(usage, "completion_tokens", 0) or 0
    report.add(layer, "usage.prompt_tokens", "OK" if pt > 0 else "WARN", pt)
    report.add(layer, "usage.completion_tokens", "OK" if ct > 0 else "WARN", ct)
    cost = _attr(md, "cost_usd", 0.0) or 0.0
    report.add(
        layer,
        "metadata.cost_usd",
        "OK" if cost > 0 else "WARN",
        cost,
        "real call should have non-zero cost",
    )
    report.add(
        layer,
        "metadata.latency_ms",
        "OK" if _attr(md, "latency_ms", 0) > 0 else "WARN",
        _attr(md, "latency_ms"),
    )
    report.add(layer, "metadata.cache_hit", "INFO", _attr(md, "cache_hit"))

    if audit:
        a_delta = audit.count - audit_before
        report.add(layer, "audit delta records", "OK" if a_delta >= 1 else "WARN", a_delta)


# ── Driver ───────────────────────────────────────────────────────────────


async def _run(args: argparse.Namespace) -> int:
    report = ProbeReport()

    real_targets: List[tuple[str, str]] = []
    if args.hub == "gemini":
        _load_dotenv_for_keys(["GOOGLE_API_KEY"])
        if not os.environ.get("GOOGLE_API_KEY"):
            print(
                "ERROR: --hub gemini requires GOOGLE_API_KEY (env or poc/chat_experience_poc/.env)"
            )
            return 2
        real_targets = [("google", "gemini-2.5-flash")]
    elif args.hub == "all":
        _load_dotenv_for_keys(["GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"])
        if os.environ.get("GOOGLE_API_KEY"):
            real_targets.append(("google", "gemini-2.5-flash"))
        if os.environ.get("OPENAI_API_KEY"):
            real_targets.append(("openai", "gpt-4o-mini"))
        if os.environ.get("ANTHROPIC_API_KEY"):
            real_targets.append(("anthropic", "claude-3-5-haiku-20241022"))

    model_mode = "hub" if real_targets else "test"
    cfg = KernelConfig(model_mode=model_mode)
    print(
        f"Boot mode: model_mode={model_mode!r}; real probes: {[p for p, _ in real_targets] or 'none (stub)'}"
    )

    t_boot = time.perf_counter()
    runtime = await start_kernel(cfg)
    boot_s = time.perf_counter() - t_boot
    title = f"K1 Kernel Probe — Phase 8 (Model Hub) [{model_mode}]"
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)
    print(f"  Boot: {boot_s:.2f}s\n")

    try:
        svc = runtime._service
        hub = probe_hub_wiring(svc, report)
        if hub is None:
            return _finalize(report, args, title)

        # Provider inventory
        if real_targets:
            expected_pids = [pid for pid, _ in real_targets]
            probe_provider_inventory(hub, report, expected=expected_pids)
        else:
            probe_provider_inventory(hub, report, expected=["stub"])

        # Stub execute always — cheap structural check.
        if hub._registry.is_registered("stub"):
            await probe_stub_execute(hub, report)
        else:
            report.add(
                "Stub execute",
                "stub plugin",
                "INFO",
                "not registered (hub mode)",
                "stub-execute path skipped",
            )

        # Real provider probes
        for pid, mid in real_targets:
            await probe_real_provider(hub, report, provider_id=pid, model_id=mid)
    finally:
        print("  Tearing down...")
        await stop_kernel(runtime)

    return _finalize(report, args, title)


def _finalize(report: ProbeReport, args: argparse.Namespace, title: str) -> int:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)
    layers: Dict[str, List] = {}
    for p in report.probes:
        layers.setdefault(p.layer, []).append(p)
    for layer, probes in layers.items():
        print(f"\n[ {layer} ]")
        for p in probes:
            print(p.render())
    counts = report.counts()
    print("\n" + "=" * 72)
    print(
        f"  Summary: OK {counts['OK']}  WARN {counts['WARN']}  "
        f"FAIL {counts['FAIL']}  INFO {counts['INFO']}  "
        f"(total {sum(counts.values())})"
    )
    if args.json:
        out = {
            "title": title,
            "counts": counts,
            "probes": [
                {
                    "layer": p.layer,
                    "name": p.name,
                    "status": p.status,
                    "value": _safe(p.value),
                    "note": p.note,
                }
                for p in report.probes
            ],
        }
        Path(args.json).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(f"  JSON written: {args.json}")
    return 1 if counts["FAIL"] > 0 else 0


def _safe(v: Any) -> Any:
    try:
        json.dumps(v)
        return v
    except Exception:
        return repr(v)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="Write probe results to this JSON path")
    ap.add_argument(
        "--hub",
        choices=["none", "gemini", "all"],
        default="none",
        help="Real provider probes. 'none' = stub-only (free). 'gemini' = one Gemini Flash call (~$0.0001). 'all' = one call per provider with creds.",
    )
    args = ap.parse_args()
    rc = asyncio.run(_run(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
