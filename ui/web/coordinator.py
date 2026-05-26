"""ui.web.coordinator — `UiCoordinator`: web adapter for the K1 kernel.

Thin adapter on top of the production kernel bootstrap API. Owns only
the web-layer concerns (output channel, web-specific bus hooks, family
profile data); the kernel runtime owns its own consumer task.

Phases::

    1. _phase1_web_data       — load family profile + device registry
    2. _phase2_kernel_startup — start_kernel() and copy runtime refs
    3. _phase3_web_wiring     — OutputChannel(WebSocketRenderer) + bus hooks
    4. _phase4_health_check   — sanity-check critical runtime slots

Notes:
    * Production `start_kernel()` calls `KernelService.startup()` and
      `KernelService.create_session()` in one shot. `auto_start_consumer=True`
      makes the production `ConciergeRuntime` own the mailbox consumer; the
      UI layer does NOT spin up a parallel consumer.
    * The family profile is currently loaded from `poc.k1_poc.demo.smith_family`
      as raw dict data. M13 introduces a proper `FamilyProfile` dataclass and
      `SpaceContext` protocol — see `docs/plans/KERNEL_BOOTUP_PLAN.md` §M13.
    * `OutputChannel` lives in `poc.k1_poc.demo.output_channel` for now; it is
      a pure bus subscriber with zero POC kernel coupling, so it is safe to
      import from a production module. M14 will migrate it under `ui.web`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ui.web.renderer import WebSocketRenderer

logger = logging.getLogger(__name__)


def _env_flag(name: str, *, default: bool = False) -> bool:
    """Parse a boolean environment flag using shell-friendly truthy strings."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Timeline entry (lightweight, for /api/session/timeline diagnostics)
# ---------------------------------------------------------------------------


@dataclass
class TimelineEntry:
    """A single boot/runtime timeline event."""

    elapsed_ms: float
    phase: str
    component: str
    event: str
    summary: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "elapsed_ms": round(self.elapsed_ms, 2),
            "phase": self.phase,
            "component": self.component,
            "event": self.event,
            "summary": self.summary,
            "payload": dict(self.payload),
        }


# ---------------------------------------------------------------------------
# UiCoordinator
# ---------------------------------------------------------------------------


class UiCoordinator:
    """Web-layer adapter on the production K1 kernel.

    Lifecycle::

        coord = UiCoordinator(test_mode=False)
        ok = await coord.initialize_system()
        # ... serve websockets ...
        await coord.shutdown_system()
    """

    # -----------------------------------------------------------------
    # Construction
    # -----------------------------------------------------------------

    def __init__(self, *, test_mode: bool = False, model_mode: str | None = None) -> None:
        self._test_mode = test_mode
        # When not in test mode, default to "hub" (live Gemini via ModelHubFactory).
        # Pass model_mode="test" explicitly only when test_mode=True.
        if model_mode is not None:
            self._model_mode = model_mode
        elif test_mode:
            self._model_mode = "test"
        else:
            self._model_mode = "hub"
        self._boot_ns = time.monotonic_ns()
        self.system_ready: bool = False

        # Phase bookkeeping
        self.phases_completed: List[str] = []
        self.startup_times: Dict[str, float] = {}
        self._timeline: List[TimelineEntry] = []

        # Web data (phase 1)
        self.family_profile: Dict[str, Any] = {}
        self.family_profile_obj: Any = None  # verticals.family.FamilyProfile (M13)
        self.device_registry: Dict[str, Any] = {}
        self.session_config: Dict[str, Any] = {}
        self._current_device: str = "alex_phone"

        # Kernel runtime (phase 2)
        self._runtime: Any = None  # k1.kernel.bootstrap.KernelRuntime

        # Runtime slots copied for direct access by app.py
        self.bus: Any = None
        self.router: Any = None
        self.model: Any = None
        self.fsm: Any = None
        self.session_state: Any = None
        self.front_mailbox: Any = None
        self.back_mailbox: Any = None
        self.front_dispatcher: Any = None
        self.back_dispatcher: Any = None
        self.experience_layer: Any = None
        self.delta_aggregator: Any = None
        self.delta_applicator: Any = None
        self.hil_port: Any = None
        self.orchestrator: Any = None
        self.weave_batcher: Any = None
        self.weave_policy: Any = None
        self.activity_tracker: Any = None
        self.ledger: Any = None
        self.ledger_store: Any = None
        self.dead_letter_consumer: Any = None
        self.front_ctx: Any = None
        self.back_ctx: Any = None

        # Web wiring (phase 3)
        self.renderer: WebSocketRenderer = WebSocketRenderer()
        self.output_channel: Any = None  # poc.k1_poc.demo.output_channel.OutputChannel
        self._web_subscriptions: List[Any] = []

    # -----------------------------------------------------------------
    # Timeline helpers
    # -----------------------------------------------------------------

    @property
    def timeline(self) -> List[TimelineEntry]:
        """Merged coordinator + output-channel timeline."""
        merged: List[TimelineEntry] = list(self._timeline)
        if self.output_channel is not None:
            for entry in getattr(self.output_channel, "timeline", []) or []:
                # poc TimelineEntry exposes `elapsed_ms`, `to_dict()` — adapt
                merged.append(
                    TimelineEntry(
                        elapsed_ms=float(getattr(entry, "elapsed_ms", 0.0) or 0.0),
                        phase=str(getattr(entry, "phase", "runtime")),
                        component=str(getattr(entry, "component", "output")),
                        event=str(getattr(entry, "event", "")),
                        summary=str(getattr(entry, "summary", "")),
                        payload=dict(getattr(entry, "payload_excerpt", {}) or {}),
                    )
                )
        merged.sort(key=lambda e: e.elapsed_ms)
        return merged

    @property
    def timeline_dicts(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.timeline]

    def _record(
        self,
        phase: str,
        component: str,
        event: str,
        summary: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        elapsed_ms = (time.monotonic_ns() - self._boot_ns) / 1_000_000
        self._timeline.append(
            TimelineEntry(
                elapsed_ms=elapsed_ms,
                phase=phase,
                component=component,
                event=event,
                summary=summary,
                payload=dict(payload or {}),
            )
        )
        logger.info(
            "[%8.1fms] %-10s %-15s %-30s %s",
            elapsed_ms,
            phase,
            component,
            event,
            summary,
        )

    # -----------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------

    async def initialize_system(self) -> bool:
        """Run all 4 phases. Returns True on success."""
        logger.info("=" * 70)
        logger.info("INIT: UiCoordinator starting (test_mode=%s)", self._test_mode)
        logger.info("=" * 70)
        self._record("boot", "ui", "system.init.start", "UiCoordinator initializing")
        try:
            await self._phase1_web_data()
            await self._phase2_kernel_startup()
            await self._phase3_web_wiring()
            await self._phase4_health_check()
            self.system_ready = True
            self._record(
                "boot",
                "ui",
                "system.init.complete",
                f"4 phases complete in {sum(self.startup_times.values()):.3f}s",
            )
            logger.info("INIT: UiCoordinator READY")
            return True
        except Exception as exc:
            self._record("boot", "ui", "system.init.failed", f"Init failed: {exc}")
            logger.error("INIT: UiCoordinator FAILED: %s", exc, exc_info=True)
            return False

    async def shutdown_system(self) -> None:
        """Graceful teardown (reverse order)."""
        self._record("shutdown", "ui", "system.shutdown.start", "Graceful shutdown")
        shutdown_start = time.time()

        # 1. Unsubscribe web hooks
        for handle in self._web_subscriptions:
            try:
                if hasattr(handle, "unsubscribe"):
                    handle.unsubscribe()
            except Exception:
                logger.debug("Web subscription unsubscribe failed", exc_info=True)
        self._web_subscriptions.clear()

        # 2. Teardown output channel (unsubscribes its own bus handles)
        if self.output_channel is not None:
            try:
                self.output_channel.teardown()
            except Exception:
                logger.debug("OutputChannel teardown failed", exc_info=True)

        # 3. Stop the kernel runtime (cancels consumer, flushes delta, closes
        #    session state, closes model — see k1.concierge.session.stop()).
        if self._runtime is not None:
            try:
                from k1.kernel.bootstrap import stop_kernel

                await stop_kernel(self._runtime)
            except Exception:
                logger.error("stop_kernel failed", exc_info=True)

        self.system_ready = False
        duration = time.time() - shutdown_start
        self._record(
            "shutdown",
            "ui",
            "system.shutdown.complete",
            f"Shutdown complete in {duration:.3f}s",
        )

    # =================================================================
    # PHASE 1 — Web data (family profile, device registry, session config)
    # =================================================================

    async def _phase1_web_data(self) -> None:
        phase_start = time.time()
        self._record("phase1", "ui", "phase1.start", "Loading web data")

        # M13: production FamilyProfile sourced from `verticals.family.smith`
        # (replaces POC `smith_family` dict imports). The legacy `family_profile`
        # dict slot is kept for backwards-compat with /api/family until the
        # web surface is migrated to read from `family_profile_obj` directly.
        from verticals.family.smith import SMITH_PROFILE

        self.family_profile_obj = SMITH_PROFILE
        self.family_profile = self._profile_to_web_dict(SMITH_PROFILE)
        self.device_registry = {
            dev_id: dict(meta) for dev_id, meta in SMITH_PROFILE.devices.items()
        }
        self.session_config = dict(SMITH_PROFILE.session_config)

        self._record(
            "phase1",
            "config",
            "config.family_loaded",
            f"Loaded {self.family_profile.get('family_name', '?')} family "
            f"({len(self.family_profile.get('members', []))} members)",
            payload={
                "family": self.family_profile.get("family_name"),
                "members": len(self.family_profile.get("members", [])),
                "devices": len(self.device_registry),
            },
        )

        duration = time.time() - phase_start
        self.startup_times["phase1"] = duration
        self.phases_completed.append("phase1")
        self._record(
            "phase1",
            "ui",
            "phase1.complete",
            f"Phase 1 complete in {duration:.3f}s",
            payload={"duration_s": round(duration, 3)},
        )

    # =================================================================
    # PHASE 2 — Kernel startup
    # =================================================================

    @staticmethod
    def _profile_to_web_dict(profile: Any) -> Dict[str, Any]:
        """Project a ``FamilyProfile`` to the legacy dict shape expected by /api/family.

        Mirrors ``SMITH_FAMILY_PROFILE`` from the old POC import: ``family_name``,
        ``location``, ``timezone``, ``preferred_language``, ``members`` (rich dicts),
        ``dietary_restrictions``, ``accessibility_needs``.
        """
        return {
            "family_name": profile.family_name,
            "location": profile.location,
            "timezone": profile.timezone,
            "preferred_language": profile.preferred_language,
            "dietary_restrictions": list(profile.dietary_restrictions),
            "accessibility_needs": list(profile.accessibility_needs),
            "members": [
                {
                    "actor_id": m.actor_id,
                    "name": m.name,
                    "relation": m.relation,
                    "age": m.age,
                    "occupation": m.occupation,
                    "grade": m.grade,
                    "access_level": m.access_level,
                    "preferences": dict(m.preferences),
                }
                for m in profile.members
            ],
        }

    @staticmethod
    async def _seed_k0_long_term_memories(live_client: Any, profile: Any) -> int:
        """Seed the family profile's long-term memories into K0 so the
        concierge ``recall_memory`` tool returns real hits.

        Builds one ``memory.write.v1`` envelope per
        :class:`verticals.family.FamilyMemoryEntry` and POSTs them via
        :meth:`k1.kernel.adapters.live_bridge_adapter.LiveBridgeClient.submit_command_batch`.
        Returns the number of envelopes submitted (0 when offline / no
        memories / no submit surface).
        """
        if live_client is None or not getattr(profile, "memories", None):
            return 0
        submit = getattr(live_client, "submit_command_batch", None)
        if submit is None:
            logger.warning("_seed_k0_long_term_memories: live_client has no submit_command_batch")
            return 0

        envelopes: List[Dict[str, Any]] = []
        # ``RecallSelector.type`` only allows {episodic, semantic, session,
        # device, belief, graph}. Map "procedural" → "semantic" so the
        # default LLM recall (episodic+semantic+procedural) still surfaces
        # procedural know-how via the semantic selector.
        _MEMORY_TYPE_MAP = {
            "episodic": "episodic",
            "semantic": "semantic",
            "procedural": "semantic",
        }
        space_id = getattr(profile, "space_id", "") or "family:default"
        for entry in profile.memories:
            mem_type = _MEMORY_TYPE_MAP.get((entry.memory_type or "").lower(), "semantic")
            body = {
                "memory_type": mem_type,
                "content": entry.content,
                "tags": list(entry.tags or []),
                "source": entry.source or "family_profile_seed",
            }
            envelopes.append(
                {
                    "topic": "memory.write.v1",
                    "schema_uri": "schema://memory.write.v1",
                    "body": body,
                    "headers": {
                        "space_id": space_id,
                        "actor": entry.actor_id or "",
                        "band": "GREEN",
                    },
                }
            )

        await submit(envelopes)
        logger.info(
            "_seed_k0_long_term_memories: submitted %d envelopes to space=%s",
            len(envelopes),
            space_id,
        )
        return len(envelopes)

    async def _phase2_kernel_startup(self) -> None:
        phase_start = time.time()
        self._record(
            "phase2",
            "ui",
            "phase2.start",
            "Starting K1 kernel via start_kernel()",
        )

        from k1.concierge.config.kernel import KernelConfig
        from k1.kernel.bootstrap import start_kernel
        from verticals.family.seeder import SpaceDataSeeder

        # M13: build L0 seed_memories BEFORE KernelConfig (Concierge consumes them).
        seeder = SpaceDataSeeder()
        seed_mems: List[Dict[str, Any]] = []
        if self.family_profile_obj is not None:
            seed_mems = seeder.build_seed_memories(
                self.family_profile_obj,
                device_id=self._current_device,
            )
            self._record(
                "phase2",
                "config",
                "seed_memories.built",
                f"Built {len(seed_mems)} seed_memories for KernelConfig",
                payload={"count": len(seed_mems), "device": self._current_device},
            )

        active_member = (
            self.family_profile_obj.member_by_device(self._current_device)
            if self.family_profile_obj is not None
            else None
        )
        active_member_id = active_member.actor_id if active_member is not None else ""

        # M14: live bridge support — if K0_ENDPOINT is set in the environment,
        # K1 S4 will use LiveBridgeAdapter (HttpBridgeClient) instead of the
        # default SinkBridgeAdapter (offline outbox).
        k0_endpoint = os.environ.get("K0_ENDPOINT", "")

        config = KernelConfig(
            ordered_bus=True,
            capture_bus=False,
            test_mode=self._test_mode,
            model_mode=self._model_mode,
            session_mode="standalone",
            session_id=f"web-{uuid.uuid4().hex[:8]}",
            active_member_id=active_member_id,
            enable_experience=True,
            enable_delta=True,
            enable_hitl=True,
            enable_orchestrator=True,
            enable_ledger=True,
            enable_dead_letter_consumer=True,
            auto_start_consumer=True,
            seed_memories=seed_mems,
            k0_endpoint=k0_endpoint,
            enable_temporal=_env_flag("K1_ENABLE_TEMPORAL", default=True),
            enable_grounding=_env_flag("K1_ENABLE_GROUNDING", default=True),
            enable_spatial=_env_flag("K1_ENABLE_SPATIAL"),
            # M13: self-model seeding is MANDATORY per product spec — the L1/L2
            # space-graph projection must be populated so downstream services
            # (composer, capsule builder, policy evaluator) see the family.
            enable_self_model=True,
            selfmodel_space_id=(
                self.family_profile_obj.space_id
                if self.family_profile_obj is not None
                else "family:smith"
            ),
            # M15: K1-native family apps — always enabled in the web shell.
            # bootstrap_family_tools(fabric=self._shared_fabric, ...) runs at
            # S8 of _startup_tier1; register_definition is called per-action,
            # placing each CapabilityContract into the shared Fabric so the
            # Concierge planner can dispatch calendar/tasks/reminders/chores/
            # family_settings natively (no K0 round-trip needed).
            enable_family_tools=True,
            family_tool_service_paths=(
                "k1.tools.family.calendar.service:CalendarToolService",
                "k1.tools.family.tasks.service:TasksToolService",
                "k1.tools.family.reminders.service:RemindersToolService",
                "k1.tools.family.chores.service:ChoresToolService",
                "k1.tools.family.shopping.service:ShoppingToolService",
                "k1.tools.family.family_settings.service:FamilySettingsService",
            ),
        )

        self._runtime = await start_kernel(config)
        if k0_endpoint:
            logger.info("Phase 2: kernel connected to K0 at %s", k0_endpoint)
        else:
            logger.info("Phase 2: kernel in offline bridge mode (outbox)")

        # M15: record Fabric auto-registration outcome in the boot timeline.
        _service = getattr(self._runtime, "_service", None)
        _bundle = getattr(_service, "family_tools", None) if _service is not None else None
        if _bundle is not None:
            _adapter_ids = list(_bundle.tool_registry.adapter_ids())
            self._record(
                "phase2",
                "fabric",
                "family_tools.fabric_registered",
                f"M15: {len(_adapter_ids)} family-tool adapters registered in Fabric "
                f"({', '.join(_adapter_ids)})",
                payload={"adapters": _adapter_ids},
            )
        else:
            self._record(
                "phase2",
                "fabric",
                "family_tools.skipped",
                "M15: family_tools bundle is None — enable_family_tools may have failed",
            )

        # Copy runtime references for direct attribute access by app.py
        rt = self._runtime
        self.bus = rt.bus
        self.router = rt.router
        self.model = rt.model
        self.fsm = rt.fsm
        self.session_state = rt.session_state
        self.front_mailbox = rt.front_mailbox
        self.back_mailbox = rt.back_mailbox
        self.front_dispatcher = rt.front_dispatcher
        self.back_dispatcher = rt.back_dispatcher
        self.experience_layer = rt.experience_layer
        self.delta_aggregator = rt.delta_aggregator
        self.delta_applicator = rt.delta_applicator
        self.hil_port = rt.hil_port
        self.orchestrator = rt.orchestrator
        self.weave_batcher = rt.weave_batcher
        self.weave_policy = rt.weave_policy
        self.activity_tracker = rt.activity_tracker
        self.ledger = rt.ledger
        self.ledger_store = rt.ledger_store
        self.dead_letter_consumer = rt.dead_letter_consumer
        self.front_ctx = rt.front_ctx
        self.back_ctx = rt.back_ctx

        await self._record_device_context(device=self._current_device, device_context={})

        self._record(
            "phase2",
            "kernel",
            "kernel.started",
            f"Kernel started (adapter={type(self.model).__name__}, "
            f"session_id={config.session_id}, test_mode={config.test_mode})",
            payload={
                "adapter": type(self.model).__name__,
                "session_id": config.session_id,
                "test_mode": config.test_mode,
            },
        )

        # M13: write L1/L2 self-model space-graph projection AFTER kernel start.
        # Mandatory by product spec; failures are logged loudly but non-fatal so
        # the UI can still come up with L0 session beliefs.
        bundle = getattr(getattr(rt, "_service", None), "self_model_bundle", None)
        if config.enable_self_model and bundle is not None and self.family_profile_obj is not None:
            try:
                wrote = seeder.seed_space_projection(bundle, self.family_profile_obj)
                self._record(
                    "phase2",
                    "selfmodel",
                    "space_graph.seeded" if wrote else "space_graph.already_seeded",
                    f"seed_space_projection wrote={wrote} space='{config.selfmodel_space_id}'",
                    payload={"wrote": wrote, "space_id": config.selfmodel_space_id},
                )
            except Exception as exc:
                logger.error(
                    "M13 seed_space_projection FAILED — self-model will be empty: %s",
                    exc,
                    exc_info=True,
                )
                self._record(
                    "phase2",
                    "selfmodel",
                    "space_graph.seed_failed",
                    f"seed_space_projection failed (non-fatal): {exc}",
                    payload={"error": str(exc)},
                )
            try:
                n_seeded = seeder.seed_self_projections(
                    bundle,
                    self.family_profile_obj,
                )
                self._record(
                    "phase2",
                    "selfmodel",
                    "self_projections.seeded",
                    f"seed_self_projections wrote={n_seeded} actors",
                    payload={"wrote": n_seeded},
                )
            except Exception as exc:
                logger.error(
                    "M13 seed_self_projections FAILED — policy gate will block tools: %s",
                    exc,
                    exc_info=True,
                )
                self._record(
                    "phase2",
                    "selfmodel",
                    "self_projections.seed_failed",
                    f"seed_self_projections failed (non-fatal): {exc}",
                    payload={"error": str(exc)},
                )
        elif config.enable_self_model and bundle is None:
            logger.error(
                "M13 self-model seeding skipped: enable_self_model=True but bundle is None"
            )
            self._record(
                "phase2",
                "selfmodel",
                "space_graph.bundle_missing",
                "enable_self_model=True but self_model_bundle is None",
            )

        # M14: seed long-term episodic/semantic memories into K0 (pseudo or real)
        # so the concierge ``recall_memory`` tool returns real hits. Offline
        # mode (no k0_endpoint) skips this — there is no durable store there.
        if k0_endpoint and self.family_profile_obj is not None:
            try:
                bridge_client = getattr(getattr(rt, "_service", None), "_bridge", None)
                live_client = bridge_client.get_client() if bridge_client is not None else None
                n_mem = await self._seed_k0_long_term_memories(live_client, self.family_profile_obj)
                self._record(
                    "phase2",
                    "memory",
                    "k0_memories.seeded",
                    f"Seeded {n_mem} long-term memories into K0",
                    payload={"count": n_mem, "endpoint": k0_endpoint},
                )
            except Exception as exc:
                logger.error(
                    "M14 seed_k0_memories FAILED — recall_memory will return empty: %s",
                    exc,
                    exc_info=True,
                )
                self._record(
                    "phase2",
                    "memory",
                    "k0_memories.seed_failed",
                    f"seed_k0_memories failed (non-fatal): {exc}",
                    payload={"error": str(exc)},
                )

        duration = time.time() - phase_start
        self.startup_times["phase2"] = duration
        self.phases_completed.append("phase2")
        self._record(
            "phase2",
            "ui",
            "phase2.complete",
            f"Phase 2 complete in {duration:.3f}s",
            payload={"duration_s": round(duration, 3)},
        )

    # =================================================================
    # PHASE 3 — Web wiring (OutputChannel + bus hooks)
    # =================================================================

    async def _phase3_web_wiring(self) -> None:
        phase_start = time.time()
        self._record("phase3", "ui", "phase3.start", "Wiring web output channel + hooks")

        # OutputChannel is currently sourced from POC; it has zero POC kernel
        # coupling (only depends on the bus interface) so is safe in production.
        # M14 will move it under `ui.web`.
        from poc.k1_poc.demo.output_channel import OutputChannel

        self.output_channel = OutputChannel(
            bus=self.bus,
            renderer=self.renderer,
            current_member="Alex",
            enable_spinner=False,  # no terminal in web mode
        )
        self.output_channel.subscribe_all()
        self._record(
            "phase3",
            "output",
            "output_channel.subscribed",
            "OutputChannel subscribed to bus topics",
        )

        # Wire real-time web hooks for FSM, affect, and tool events
        self._wire_web_timeline_hooks()
        self._record(
            "phase3",
            "bus",
            "web_hooks.subscribed",
            f"Wired {len(self._web_subscriptions)} web-only bus subscriptions",
        )

        duration = time.time() - phase_start
        self.startup_times["phase3"] = duration
        self.phases_completed.append("phase3")
        self._record(
            "phase3",
            "ui",
            "phase3.complete",
            f"Phase 3 complete in {duration:.3f}s",
            payload={"duration_s": round(duration, 3)},
        )

    def _wire_web_timeline_hooks(self) -> None:
        """Subscribe FSM/affect/tool topics; forward to the WebSocketRenderer."""
        from k1.bus import Envelope
        from k1.concierge.bus.topics import (
            TOPIC_AFFECT_UPDATE,
            TOPIC_STATE_UPDATED,
            TOPIC_TASK_FAILED,
            TOPIC_TOOL_COMPLETED,
            TOPIC_TOOL_STARTED,
            TOPIC_TOOL_STATE_CHANGED,  # E15.10
        )
        from k1.hil.topics import TOPIC_HIL_REQUEST as _TOPIC_HIL_REQUEST

        renderer = self.renderer

        def _safe_payload(envelope: Envelope) -> Dict[str, Any]:
            try:
                if not envelope.payload:
                    return {}
                return json.loads(envelope.payload)
            except Exception:
                return {}

        def _on_fsm(envelope: Envelope) -> None:
            p = _safe_payload(envelope)
            try:
                renderer.send_fsm_state(
                    p.get("from_state", "?"),
                    p.get("to_state", "?"),
                    p.get("trigger", "?"),
                )
            except Exception:
                logger.debug("FSM web hook failed", exc_info=True)

        def _on_affect(envelope: Envelope) -> None:
            p = _safe_payload(envelope)
            try:
                renderer.send_affect_update(
                    p.get("emotion", "neutral"),
                    float(p.get("valence", 0.0) or 0.0),
                )
            except Exception:
                logger.debug("Affect web hook failed", exc_info=True)

        def _on_tool(envelope: Envelope) -> None:
            p = _safe_payload(envelope)
            phase = "started" if "started" in envelope.topic else "completed"
            try:
                renderer.send_tool_event(
                    tool_name=p.get("tool_name", "?"),
                    actor=p.get("actor", "?"),
                    phase=phase,
                    duration_ms=p.get("duration_ms", 0),
                    success=p.get("success", True),
                    args_summary=p.get("args_summary", ""),
                    result_summary=p.get("result_summary", ""),
                )
            except Exception:
                logger.debug("Tool web hook failed", exc_info=True)

        bus = self.bus
        self._web_subscriptions.append(bus.subscribe(TOPIC_STATE_UPDATED, _on_fsm))
        self._web_subscriptions.append(bus.subscribe(TOPIC_AFFECT_UPDATE, _on_affect))
        self._web_subscriptions.append(bus.subscribe(TOPIC_TOOL_STARTED, _on_tool))
        self._web_subscriptions.append(bus.subscribe(TOPIC_TOOL_COMPLETED, _on_tool))

        # E15.10: refresh browser adapter views when a tool's state changes
        def _on_tool_state(envelope: Envelope) -> None:
            p = _safe_payload(envelope)
            try:
                renderer.send_tool_refresh(
                    adapter_id=p.get("tool", p.get("adapter_id", "")),
                    space_id=p.get("space_id", ""),
                )
            except Exception:
                logger.debug("Tool state web hook failed", exc_info=True)

        self._web_subscriptions.append(bus.subscribe(TOPIC_TOOL_STATE_CHANGED, _on_tool_state))

        # HIL gate: forward requests to browser so user can approve/deny
        def _on_hil_request(envelope: Envelope) -> None:
            p = _safe_payload(envelope)
            try:
                logger.info(
                    "WEB: hil_request forwarded hil_request_id=%s kind=%s caller_key=%s",
                    p.get("hil_request_id", ""),
                    p.get("kind", ""),
                    p.get("caller_key", ""),
                )
                renderer.send_hil_request(p)
            except Exception:
                logger.debug("HIL request web hook failed", exc_info=True)

        self._web_subscriptions.append(bus.subscribe(_TOPIC_HIL_REQUEST, _on_hil_request))

        # Task failure: clear browser spinner so the user isn't stuck waiting
        # when Back fails and Front never publishes a response.final.
        def _on_task_failed(envelope: Envelope) -> None:
            p = _safe_payload(envelope)
            try:
                logger.info(
                    "WEB: task_failed forwarded task_id=%s reason=%s",
                    p.get("task_id", ""),
                    p.get("reason", ""),
                )
                renderer.send_task_failed(
                    task_id=str(p.get("task_id", "")),
                    reason=str(p.get("reason", "error")),
                    error_message=str(p.get("error_message", "") or p.get("error", "")),
                    error_code=str(p.get("error_code", "")),
                )
            except Exception:
                logger.debug("Task failed web hook failed", exc_info=True)

        self._web_subscriptions.append(bus.subscribe(TOPIC_TASK_FAILED, _on_task_failed))

    # =================================================================
    # PHASE 4 — Health check
    # =================================================================

    async def _phase4_health_check(self) -> None:
        phase_start = time.time()
        self._record("phase4", "ui", "phase4.start", "Running health check")

        checks: Dict[str, bool] = {
            "bus_alive": self.bus is not None,
            "fsm_alive": self.fsm is not None,
            "model_alive": self.model is not None,
            "session_state_alive": self.session_state is not None,
            "output_channel_wired": self.output_channel is not None,
            "consumer_running": (
                self._runtime is not None
                and self._runtime.consumer_task is not None
                and not self._runtime.consumer_task.done()
            ),
            "front_ctx_alive": self.front_ctx is not None,
            "back_ctx_alive": self.back_ctx is not None,
        }

        for name, ok in checks.items():
            self._record(
                "phase4",
                "health",
                f"check.{name}",
                f"{name}: {'OK' if ok else 'FAIL'}",
            )

        all_ok = all(checks.values())
        duration = time.time() - phase_start
        self.startup_times["phase4"] = duration
        self.phases_completed.append("phase4")
        self._record(
            "phase4",
            "ui",
            "phase4.complete",
            f"Phase 4 complete in {duration:.3f}s ({'OK' if all_ok else 'DEGRADED'})",
            payload={
                "checks": checks,
                "all_ok": all_ok,
                "duration_s": round(duration, 3),
            },
        )

        if not all_ok:
            failed = [k for k, v in checks.items() if not v]
            logger.warning("Health check failures: %s", failed)

    # -----------------------------------------------------------------
    # Public surface used by app.py
    # -----------------------------------------------------------------

    def get_bus(self) -> Any:
        if self.bus is None:
            raise RuntimeError("Bus not initialized (kernel not started)")
        return self.bus

    def get_output_channel(self) -> Any:
        if self.output_channel is None:
            raise RuntimeError("Output channel not wired (phase 3 not complete)")
        return self.output_channel

    async def _record_device_context(
        self,
        *,
        device: str,
        device_context: Dict[str, Any] | None,
    ) -> None:
        """Record the latest browser/device timezone snapshot into the kernel port."""
        context = self._device_context_with_defaults(device_context)
        runtime = self._runtime
        service = getattr(runtime, "_service", None) if runtime is not None else None
        port = getattr(service, "device_context_port", None) if service is not None else None
        if port is None:
            return

        from k1.grounding.types import DeviceContextSnapshot

        session_id = str(getattr(runtime, "_session_id", "") or "")
        if not session_id:
            session_id = str(getattr(getattr(runtime, "config", None), "session_id", "") or "web")
        device_id = str(device or context.get("device_id") or "").strip()
        if not device_id:
            return
        installation_id = str(context.get("installation_id") or device_id)
        metadata = dict(context.get("metadata") or {})
        known_keys = {
            "timezone",
            "locale",
            "observed_at_utc",
            "surface",
            "clock_skew_ms",
            "location_permission",
            "location_fix",
            "semantic_place_hint",
            "installation_id",
            "metadata",
        }
        for key, value in context.items():
            if key not in known_keys and value is not None:
                metadata[key] = value

        observed_at = str(context.get("observed_at_utc") or datetime.now(timezone.utc).isoformat())
        snapshot = DeviceContextSnapshot(
            session_id=session_id,
            device_id=device_id,
            installation_id=installation_id,
            observed_at_utc=observed_at,
            surface=str(context.get("surface") or "web"),
            timezone=(
                (str(context.get("timezone")).strip() or None)
                if context.get("timezone") is not None
                else None
            ),
            locale=(
                (str(context.get("locale")).strip() or None)
                if context.get("locale") is not None
                else None
            ),
            clock_skew_ms=context.get("clock_skew_ms"),
            location_permission=str(context.get("location_permission") or "unknown"),
            location_fix=context.get("location_fix"),
            semantic_place_hint=context.get("semantic_place_hint"),
            metadata=metadata,
        )
        await port.update_snapshot(snapshot)

        try:
            meta = (
                self.session_state.get_section("meta") if self.session_state is not None else None
            )
            if meta is not None and hasattr(meta, "set_active_device"):
                meta.set_active_device(device_id)
        except Exception:
            logger.debug("Device context active-device update failed", exc_info=True)

    def _device_context_with_defaults(
        self, device_context: Dict[str, Any] | None
    ) -> Dict[str, Any]:
        context = dict(device_context or {}) if isinstance(device_context, dict) else {}
        family_timezone = self._family_timezone()
        timezone_name = str(context.get("timezone") or "").strip()
        if not timezone_name:
            timezone_name = (
                str(context.get("profile_timezone") or "").strip()
                or family_timezone
                or str(context.get("browser_timezone") or "").strip()
            )
        if timezone_name:
            context["timezone"] = timezone_name
        if family_timezone and not context.get("profile_timezone"):
            context["profile_timezone"] = family_timezone
        context.setdefault("surface", "web")
        context.setdefault("observed_at_utc", datetime.now(timezone.utc).isoformat())
        return context

    def _family_timezone(self) -> str | None:
        candidate = getattr(self.family_profile_obj, "timezone", None) or self.family_profile.get(
            "timezone"
        )
        if isinstance(candidate, str):
            candidate = candidate.strip()
            return candidate or None
        return None

    async def send_message(
        self,
        *,
        text: str,
        member: str,
        device: str,
        turn: int,
        timeout_s: float = 180.0,
    ) -> None:
        """Publish a user input envelope and await the response.

        The output channel's `wait_for_response()` blocks until the
        production front_handler emits `response.final`. The result is
        rendered to the WebSocketRenderer (already wired in phase 3).
        """
        from k1.concierge.bus.builders import build_user_input

        output = self.get_output_channel()
        output.set_member(member)
        output.start_turn(turn)

        # Reset dispatchers (per-turn tool budget bookkeeping)
        try:
            if self.front_dispatcher is not None:
                self.front_dispatcher.reset()
            if self.back_dispatcher is not None:
                self.back_dispatcher.reset()
        except Exception:
            logger.debug("Dispatcher reset failed (non-fatal)", exc_info=True)

        payload: Dict[str, Any] = {
            "text": text,
            "member": member,
            "device": device,
            "device_id": device,
            "turn": turn,
        }
        envelope = build_user_input(payload=payload)
        self.get_bus().publish(envelope)

        await output.wait_for_response(timeout=timeout_s)

    def get_status_report(self) -> Dict[str, Any]:
        """Status snapshot for `/api/status` and `/status` command."""
        report: Dict[str, Any] = {
            "system_ready": self.system_ready,
            "test_mode": self._test_mode,
            "phases_completed": list(self.phases_completed),
            "startup_times": dict(self.startup_times),
            "total_startup_s": round(sum(self.startup_times.values()), 3),
            "timeline_count": len(self._timeline),
            "components": {},
        }
        comp = report["components"]
        if self.family_profile:
            comp["family"] = self.family_profile.get("family_name", "?")
        if self.model is not None:
            comp["llm_adapter"] = type(self.model).__name__
        if self.bus is not None:
            comp["bus"] = type(self.bus).__name__
        if self.fsm is not None:
            comp["fsm_state"] = self.fsm.state.name
        if self.session_state is not None:
            comp["session"] = "active"
        if self.experience_layer is not None:
            comp["experience"] = "active"
        if self.delta_aggregator is not None:
            comp["delta_aggregator"] = "active"
        if self.hil_port is not None:
            comp["hil"] = "active"
        if self.orchestrator is not None:
            comp["orchestrator"] = "active"
        if self.ledger_store is not None:
            try:
                comp["ledger_count"] = self.ledger_store.count()
            except Exception:
                comp["ledger_count"] = -1
        if self.dead_letter_consumer is not None:
            comp["dead_letter_count"] = getattr(self.dead_letter_consumer, "total_dead_letters", 0)
        return report


# ---------------------------------------------------------------------------
# Singleton accessor (used by FastAPI app + tests)
# ---------------------------------------------------------------------------


_coordinator_lock = asyncio.Lock()
_coordinator_instance: Optional[UiCoordinator] = None


def get_web_coordinator(*, test_mode: bool = False, model_mode: str | None = None) -> UiCoordinator:
    """Get-or-create the process-wide UiCoordinator singleton."""
    global _coordinator_instance
    if _coordinator_instance is None:
        _coordinator_instance = UiCoordinator(test_mode=test_mode, model_mode=model_mode)
    return _coordinator_instance


def reset_coordinator() -> None:
    """Drop the singleton (tests + dev reload). Caller must shut down first."""
    global _coordinator_instance
    _coordinator_instance = None
