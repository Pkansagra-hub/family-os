"""
probe_fabric.py — Boot the coordinator and dump everything the LLM can see.
Run: python scripts/probe_fabric.py
"""

import asyncio
import logging
import os
import sys

# Suppress noise
logging.basicConfig(level=logging.ERROR)

os.environ.setdefault("GOOGLE_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))


async def main() -> None:
    from ui.web.coordinator import UiCoordinator

    print("Booting coordinator (test_mode=True)...")
    coord = UiCoordinator(test_mode=True)
    ok = await coord.initialize_system()
    print(f"Coordinator init: {'OK' if ok else 'FAILED'}\n")

    runtime = getattr(coord, "_runtime", None)
    service = getattr(runtime, "_service", None) if runtime else None

    # ------------------------------------------------------------------
    # 1. Family tools bundle
    # ------------------------------------------------------------------
    bundle = getattr(service, "family_tools", None) if service else None

    print("=" * 60)
    print("FAMILY TOOLS BUNDLE")
    print("=" * 60)
    if bundle is None:
        print("  [NONE] — bootstrap failed or enable_family_tools=False")
        cfg = getattr(service, "_config", None)
        if cfg:
            print("  config.enable_family_tools:", getattr(cfg, "enable_family_tools", "N/A"))
            print(
                "  config.family_tool_service_paths:",
                getattr(cfg, "family_tool_service_paths", "N/A"),
            )
    else:
        reg = bundle.tool_registry
        try:
            adapter_ids = list(reg.adapter_ids())
        except Exception:
            adapter_ids = list(getattr(reg, "_services", {}).keys())
        print(f"  Adapters ({len(adapter_ids)}): {adapter_ids}")
        print(f"  Capability names ({len(bundle.capability_names)}):")
        for n in sorted(bundle.capability_names):
            print(f"    {n}")

    # ------------------------------------------------------------------
    # 2. Fabric registry — all contracts via KernelService._shared_fabric
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("FABRIC REGISTRY — ALL CONTRACTS")
    print("=" * 60)

    # The family tool contracts live in KernelService._shared_fabric
    shared_fabric = None
    if service:
        for attr in ("_shared_fabric", "_fabric", "shared_fabric"):
            shared_fabric = getattr(service, attr, None)
            if shared_fabric is not None:
                break

    if shared_fabric is None:
        print("  [_shared_fabric NOT FOUND on service]")
        svc_attrs = (
            [a for a in dir(service) if "fabric" in a.lower() or "registry" in a.lower()]
            if service
            else []
        )
        print("  service fabric/registry attrs:", svc_attrs)
    else:
        print(f"  shared_fabric type: {type(shared_fabric).__name__}")
        cap_reg_raw = getattr(shared_fabric, "capability_registry", None)
        print(
            f"  shared_fabric.capability_registry: {type(cap_reg_raw).__name__ if cap_reg_raw else 'None'}"
        )
        # register_class() writes to fabric.capability_registry (public property)
        reg = cap_reg_raw
        if reg is None:
            # fallback
            for attr in ("_registry", "registry", "_core"):
                reg = getattr(shared_fabric, attr, None)
                if reg is not None:
                    break
        if reg is None:
            print("  [capability_registry not found on shared_fabric]")
            print(
                "  shared_fabric attrs:",
                [a for a in dir(shared_fabric) if not a.startswith("_")][:25],
            )
        else:
            try:
                all_names = list(reg.list_names())
            except Exception:
                all_names = []
            family_names = [n for n in all_names if "tool." in n]
            other_names = [n for n in all_names if "tool." not in n]
            print(f"  Total contracts in _shared_fabric: {len(all_names)}")
            print(f"  Family tool contracts: {len(family_names)}")
            for name in sorted(family_names):
                try:
                    c = reg.lookup(name)
                    desc = getattr(c, "description", "")[:65] if c else ""
                    band = getattr(c, "safety_band_min", "?") if c else "?"
                    ptype = getattr(c, "provider_type", "?") if c else "?"
                    print(f"    {name}")
                    print(f"      {desc!r}  band={band}  provider={ptype}")
                except Exception:
                    print(f"    {name}")
            if other_names:
                print(f"\n  Other contracts ({len(other_names)}):")
                for n in sorted(other_names)[:15]:
                    print(f"    {n}")

    # ------------------------------------------------------------------
    # 3. What the LLM tool declarations look like
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("LLM TOOL DECLARATIONS (what Gemini sees per request)")
    print("=" * 60)

    # The tools are built per-request in the orchestrator from the Fabric registry.
    # Check orchestrator and front/back context.
    orch = getattr(runtime, "orchestrator", None) if runtime else None
    front_ctx = getattr(runtime, "front_ctx", None) if runtime else None
    back_ctx = getattr(runtime, "back_ctx", None) if runtime else None

    print(f"  orchestrator: {type(orch).__name__ if orch else 'None'}")
    print(f"  front_ctx: {type(front_ctx).__name__ if front_ctx else 'None'}")
    print(f"  back_ctx: {type(back_ctx).__name__ if back_ctx else 'None'}")

    # Check what tools the orchestrator knows about
    if orch:
        orch_tools = None
        for attr in ("_tools", "tools", "_capability_tools", "tool_declarations"):
            orch_tools = getattr(orch, attr, None)
            if orch_tools:
                break
        if orch_tools:
            print(f"  orchestrator tools ({len(orch_tools)}):")
            for t in orch_tools:
                name = getattr(t, "name", str(t))
                print(f"    {name}")
        else:
            orch_attrs = [a for a in dir(orch) if not a.startswith("_")]
            print(f"  orchestrator attrs: {orch_attrs[:20]}")

    # Check front_ctx capability_cache or tools
    if front_ctx:
        cap_cache = getattr(front_ctx, "capability_cache", None)
        print(f"  front_ctx.capability_cache: {type(cap_cache).__name__ if cap_cache else 'None'}")
        dispatch = getattr(front_ctx, "dispatch", None)
        if dispatch:
            dtypes = [a for a in dir(dispatch) if not a.startswith("_")]
            print(f"  front_ctx.dispatch attrs: {dtypes[:15]}")

    # The real path: Fabric's discover_capabilities → builds tool decls per request
    # Check if NativeToolProvider is reachable
    if front_ctx and hasattr(front_ctx, "dispatch") and front_ctx.dispatch:
        dispatch = front_ctx.dispatch
        print("\n  === CALLING dispatch.discover_capabilities() ===")
        try:
            caps = await dispatch.discover_capabilities()
            if caps:
                print(f"  Capabilities visible to LLM: {len(caps)}")
                for c in caps:
                    name = getattr(c, "name", str(c))
                    desc = getattr(c, "description", "")[:60]
                    print(f"    {name}: {desc!r}")
            else:
                print("  discover_capabilities() returned empty/None")
        except Exception as e:
            print(f"  discover_capabilities() error: {e}")
    else:
        print("\n  [no dispatch available]")

    # ------------------------------------------------------------------
    # 4. Session state — what the front/back LLM sessions have access to
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("SESSION TOOL ACCESS")
    print("=" * 60)

    session_state = getattr(coord, "session_state", None)
    if session_state:
        tools = getattr(session_state, "available_tools", None) or getattr(
            session_state, "tools", None
        )
        print(f"  session_state.available_tools: {tools!r}")
    else:
        print("  [NO SESSION STATE]")

    # ------------------------------------------------------------------
    # 5. K1 tool REST routes mounted
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("K1 TOOL REST ROUTES MOUNTED")
    print("=" * 60)
    try:
        from ui.web.app import app

        tool_routes = [r.path for r in app.routes if hasattr(r, "path") and "/k1/tools/" in r.path]
        if tool_routes:
            for r in sorted(set(tool_routes)):
                print(f"  {r}")
        else:
            print("  [NONE — /k1/tools/* routes not mounted]")
    except Exception as e:
        print(f"  [ERROR: {e}]")

    # ------------------------------------------------------------------
    # Done
    # ------------------------------------------------------------------
    print()
    await coord.shutdown_system()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
