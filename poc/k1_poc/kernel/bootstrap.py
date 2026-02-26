"""Independent Concierge kernel bootstrap (Phase A extraction scaffold).

This module intentionally avoids importing from ``poc.k1_poc.demo`` to keep a
clean system <-> demo boundary. It provides a standalone startup path that can
later be consumed by demo as an adapter layer.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Auto-load .env for GOOGLE_API_KEY if not already set
try:
    from dotenv import load_dotenv

    # Search: project-root .env, then chat_experience_poc .env as fallback
    _root = Path(__file__).resolve().parents[3]  # familyos/
    _env_candidates = [
        _root / ".env",
        _root / "poc" / "chat_experience_poc" / ".env",
    ]
    for _env_path in _env_candidates:
        if _env_path.is_file():
            load_dotenv(_env_path, override=False)
            break
except ImportError:
    pass

from poc.k1_poc.actors.back import back_handler  # subscribe_back_events removed: FSM routes all
from poc.k1_poc.actors.front import front_handler, subscribe_front_events
from poc.k1_poc.bus.builders import (
    build_affect_update,
    build_proactive_fill,
    build_task_failed,
    build_task_resume,
    build_task_suspended,
)
from poc.k1_poc.experience.layer import ExperienceLayer
from poc.k1_poc.fsm.controller import ConciergeController
from poc.k1_poc.main import boot
from poc.k1_poc.tools.dispatcher import create_back_dispatcher, create_front_dispatcher
from poc.k1_poc.tools.implementations import ToolContext
from poc.k1_poc.tools.schemas_front import FRONT_TOOL_SCHEMAS

logger = logging.getLogger(__name__)


@dataclass
class KernelConfig:
    """Configuration for independent kernel startup."""

    ordered_bus: bool = True
    capture_bus: bool = False
    test_mode: bool = False
    tool_tier: str = "LOW"
    session_mode: str = "standalone"  # standalone | testing
    session_id: str | None = None
    enable_experience: bool = True
    enable_delta: bool = True
    enable_hitl: bool = True
    enable_orchestrator: bool = True
    auto_start_consumer: bool = True
    seed_memories: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class KernelRuntime:
    """Live kernel runtime object returned by start_kernel()."""

    config: KernelConfig
    bus: Any
    router: Any
    adapter: Any
    front_mailbox: Any
    back_mailbox: Any
    session_state: Any
    capability_registry: Any
    model: Any
    fsm: ConciergeController
    front_dispatcher: Any
    back_dispatcher: Any
    experience_layer: Any = None
    delta_aggregator: Any = None
    delta_applicator: Any = None
    hitl_coordinator: Any = None
    orchestrator: Any = None
    front_subscriptions: list[Any] = field(default_factory=list)
    back_subscriptions: list[Any] = field(default_factory=list)
    consumer_task: asyncio.Task | None = None
    started: bool = False


async def start_kernel(config: KernelConfig | None = None) -> KernelRuntime:
    """Start the Concierge kernel independently from demo modules."""

    from poc.k1_poc.config import get_config

    cfg = config or KernelConfig()

    infra = boot(capture=cfg.capture_bus, ordered=cfg.ordered_bus)
    bus = infra["bus"]
    router = infra["router"]
    adapter = infra["adapter"]
    front_mailbox = infra["front_mailbox"]
    back_mailbox = infra["back_mailbox"]

    model = _create_model(cfg)
    session_state = _create_session_state(cfg)
    capability_registry = _create_capability_registry()

    fsm = ConciergeController(bus=bus, router=router)

    # Wire FSM history to SS history_active so front handler gets context
    try:
        history_section = session_state.get_section("history_active")
        if history_section and hasattr(history_section, "add_turn"):
            fsm.set_history_sink(history_section)
    except Exception:
        pass  # Non-critical, front handler works without history

    # Wire FSM to SessionStateManager for scoreboard/narrative reads
    fsm.set_session_state(session_state)

    recall_fn = _build_recall_fn(cfg)

    front_ctx = ToolContext(
        session_manager=session_state,
        cognitive_trace_id=f"k-front-{uuid.uuid4().hex[:6]}",
        actor="front",
        recall_fn=recall_fn,
        capability_fn=_capability_discover(capability_registry),
        invoke_fn=_capability_invoke(capability_registry),
    )
    back_ctx = ToolContext(
        session_manager=session_state,
        cognitive_trace_id=f"k-back-{uuid.uuid4().hex[:6]}",
        actor="back",
        recall_fn=recall_fn,
        capability_fn=_capability_discover(capability_registry),
        invoke_fn=_capability_invoke(capability_registry),
    )

    front_dispatcher = create_front_dispatcher(tier=cfg.tool_tier, ctx=front_ctx, bus=bus)
    back_dispatcher = create_back_dispatcher(tier=cfg.tool_tier, ctx=back_ctx, bus=bus)

    runtime = KernelRuntime(
        config=cfg,
        bus=bus,
        router=router,
        adapter=adapter,
        front_mailbox=front_mailbox,
        back_mailbox=back_mailbox,
        session_state=session_state,
        capability_registry=capability_registry,
        model=model,
        fsm=fsm,
        front_dispatcher=front_dispatcher,
        back_dispatcher=back_dispatcher,
    )

    if cfg.enable_experience:
        runtime.experience_layer = ExperienceLayer()

    if cfg.enable_delta:
        from poc.k1_poc.delta.aggregator import DeltaAggregator

        applicator = _build_delta_applicator(session_state, bus)
        runtime.delta_applicator = applicator
        runtime.delta_aggregator = DeltaAggregator(
            flush_fn=applicator.apply, batch_window_ms=get_config().delta.batch_window_ms
        )

    if cfg.enable_hitl:
        from poc.k1_poc.protocols.hitl_coordinator import HILCoordinator

        async def _on_suspended(request: Any) -> None:
            env = build_task_suspended(
                payload={
                    "task_id": getattr(request, "task_id", ""),
                    "hil_type": getattr(request, "hil_type", "clarification"),
                    "question": getattr(request, "question", ""),
                    "options": getattr(request, "options", []),
                    "side_effects": getattr(request, "side_effects", []),
                    "timeout_s": int(getattr(request, "timeout_ms", 60_000) / 1000),
                }
            )
            bus.publish(env)

        async def _on_resume(response: Any) -> None:
            env = build_task_resume(
                payload={
                    "task_id": getattr(response, "task_id", ""),
                    "decision": getattr(response, "decision", "answered"),
                    "resolution": getattr(response, "resolution", {}),
                    "answer": getattr(response, "raw_user_text", ""),
                }
            )
            bus.publish(env)

        async def _on_timeout(task_id: str) -> None:
            env = build_task_failed(
                payload={
                    "task_id": task_id,
                    "reason": "timeout",
                    "error_code": "HITL_TIMEOUT",
                }
            )
            bus.publish(env)

        runtime.hitl_coordinator = HILCoordinator(
            on_emit_suspended=_on_suspended,
            on_emit_resume=_on_resume,
            on_timeout=_on_timeout,
        )
        # Wire HILCoordinator into FSM for limit enforcement and safety band
        if hasattr(runtime.fsm, "set_hitl_coordinator"):
            runtime.fsm.set_hitl_coordinator(runtime.hitl_coordinator)

    # Wire WeaveBatcher for Front-busy queue management
    if hasattr(runtime.fsm, "set_weave_batcher"):
        from poc.k1_poc.protocols.weave_batcher import WeaveBatcher

        async def _weave_flush(results: list) -> None:  # type: ignore[type-arg]
            """Callback when WeaveBatcher flushes a batch."""
            logger.info("WeaveBatcher flush: %d results", len(results))

        runtime.weave_batcher = WeaveBatcher(flush_fn=_weave_flush)
        runtime.fsm.set_weave_batcher(runtime.weave_batcher)

    if cfg.enable_orchestrator:
        from poc.k1_poc.orchestrator.stub import OrchestratorStub

        runtime.orchestrator = OrchestratorStub(
            fabric_gateway=_FabricGatewayAdapter(capability_registry),
            state_read=_StateReadAdapter(session_state),
            delta_emit=_DeltaEmitAdapter(aggregator=runtime.delta_aggregator, bus=bus),
        )
        if hasattr(runtime.fsm, "set_orchestrator"):
            runtime.fsm.set_orchestrator(runtime.orchestrator)

    def _route_front_subscription(envelope: Any) -> None:
        try:
            runtime.router.deliver("front_half", envelope)
        except Exception:
            logger.exception("Front subscription routing failed: topic=%s", envelope.topic)

    def _route_back_subscription(envelope: Any) -> None:
        try:
            runtime.router.deliver("back_half", envelope)
        except Exception:
            logger.exception("Back subscription routing failed: topic=%s", envelope.topic)

    runtime.front_subscriptions = subscribe_front_events(bus, _route_front_subscription)
    # NOTE: Do NOT call subscribe_back_events here. The FSM is the sole routing
    # authority for all back-bound topics (task.dispatch, task.cancel,
    # task.resume, clarification.response). It routes them via
    # _route_via_orchestrator -> _deliver_to_back. Subscribing the back
    # handler directly to these bus topics created duplicate deliveries.
    runtime.back_subscriptions = []

    if cfg.auto_start_consumer:
        runtime.consumer_task = asyncio.create_task(_mailbox_consumer(runtime))
    runtime.started = True

    logger.info(
        "Kernel started (ordered=%s, session_mode=%s, tool_tier=%s)",
        cfg.ordered_bus,
        cfg.session_mode,
        cfg.tool_tier,
    )
    return runtime


async def stop_kernel(runtime: KernelRuntime) -> None:
    """Gracefully stop kernel runtime."""

    if runtime.consumer_task and not runtime.consumer_task.done():
        runtime.consumer_task.cancel()
        try:
            await runtime.consumer_task
        except asyncio.CancelledError:
            pass

    if runtime.delta_aggregator is not None:
        try:
            await runtime.delta_aggregator.flush()
        except Exception:
            logger.debug("Delta flush failed during shutdown", exc_info=True)

    if runtime.fsm is not None:
        try:
            runtime.fsm.teardown()
        except Exception:
            logger.debug("FSM teardown failed", exc_info=True)

    if runtime.session_state is not None and hasattr(runtime.session_state, "close"):
        try:
            await runtime.session_state.close()
        except Exception:
            logger.debug("Session state close failed", exc_info=True)

    if runtime.model is not None and hasattr(runtime.model, "close"):
        try:
            await runtime.model.close()
        except Exception:
            logger.debug("Model close failed", exc_info=True)

    runtime.started = False
    logger.info("Kernel stopped")


async def _mailbox_consumer(runtime: KernelRuntime) -> None:
    """Poll front/back mailboxes and invoke actor handlers."""

    from poc.k1_poc.config import get_config

    _kcfg = get_config().kernel
    poll_interval = _kcfg.poll_interval_s
    dedup_limit = _kcfg.dedup_cache_size
    seen_front_ids: set[int] = set()
    seen_back_ids: set[int] = set()

    while True:
        did_work = False

        front_env = runtime.front_mailbox.receive(timeout_ms=0)
        if front_env is not None:
            env_id = int(getattr(front_env, "envelope_id", 0) or 0)
            if env_id and env_id in seen_front_ids:
                front_env = None
            else:
                if env_id:
                    seen_front_ids.add(env_id)
                    if len(seen_front_ids) > dedup_limit:
                        seen_front_ids.clear()

        if front_env is not None:
            did_work = True
            await front_handler(
                envelope=front_env,
                model=runtime.model,
                ss=runtime.session_state,
                bus=runtime.bus,
                tool_dispatcher=runtime.front_dispatcher,
                all_tool_schemas=FRONT_TOOL_SCHEMAS,
                fsm_state=runtime.fsm.state.name,
            )
            await _tick_experience(runtime)

        back_env = runtime.back_mailbox.receive(timeout_ms=0)
        if back_env is not None:
            env_id = int(getattr(back_env, "envelope_id", 0) or 0)
            if env_id and env_id in seen_back_ids:
                back_env = None
            else:
                if env_id:
                    seen_back_ids.add(env_id)
                    if len(seen_back_ids) > dedup_limit:
                        seen_back_ids.clear()

        if back_env is not None:
            did_work = True
            await back_handler(
                envelope=back_env,
                model=runtime.model,
                ss=runtime.session_state,
                bus=runtime.bus,
                tool_dispatcher=runtime.back_dispatcher,
            )

        if did_work:
            await asyncio.sleep(0)
        else:
            await asyncio.sleep(poll_interval)


async def _tick_experience(runtime: KernelRuntime) -> None:
    """Invoke ExperienceLayer tick and emit relevant envelopes."""
    layer = runtime.experience_layer
    if layer is None:
        return

    context = _build_experience_context(runtime)
    outputs = await layer.tick(runtime.fsm.state.name, context)

    emotional = outputs.get("emotional")
    if emotional is not None:
        payload = emotional.__dict__ if hasattr(emotional, "__dict__") else {"value": emotional}
        runtime.bus.publish(build_affect_update(payload=payload))

    fill = outputs.get("fill")
    if fill is not None:
        payload = fill.__dict__ if hasattr(fill, "__dict__") else {"text": str(fill)}
        runtime.bus.publish(build_proactive_fill(payload=payload))


def _build_experience_context(runtime: KernelRuntime) -> dict[str, Any]:
    """Build safe context snapshot for ExperienceLayer.tick()."""
    ss = runtime.session_state

    def _section_dict(name: str) -> dict[str, Any]:
        try:
            section = ss.get_section(name)
            if hasattr(section, "to_dict"):
                return section.to_dict()
            if isinstance(section, dict):
                return section
            return {}
        except Exception:
            return {}

    control = _section_dict("control")
    wait_ms = 0
    if isinstance(control, dict):
        wait_ms = int(control.get("wait_duration_ms", 0) or 0)

    return {
        "turn_transcript": "",
        "affect_history": [],
        "front_refine_affect_confidence": 0.0,
        "conversation_history": [],
        "memory_recalls": [],
        "task_state": _section_dict("task_state"),
        "user_patterns": {},
        "wait_duration_ms": wait_ms,
        "persona": _section_dict("persona"),
        "user_cadence": {},
    }


def _create_model(cfg: KernelConfig) -> Any:
    if cfg.test_mode:
        from poc.k1_poc.llm.test_adapter import TestConciergeAdapter

        return TestConciergeAdapter()

    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        from poc.k1_poc.llm.gemini_adapter import GeminiConciergeAdapter

        return GeminiConciergeAdapter(api_key=api_key)

    from poc.k1_poc.llm.test_adapter import TestConciergeAdapter

    return TestConciergeAdapter()


def _create_session_state(cfg: KernelConfig) -> Any:
    from poc.k1_poc.sessionstate.factory import SessionStateFactory

    session_id = cfg.session_id or f"kernel-{uuid.uuid4().hex[:8]}"

    if cfg.session_mode == "testing":
        return SessionStateFactory.create_for_testing(session_id=session_id)

    return SessionStateFactory.create_standalone(session_id=session_id)


def _create_capability_registry() -> Any:
    from poc.k1_poc.fabric.capability_registry import create_demo_registry

    return create_demo_registry()


def _build_recall_fn(cfg: KernelConfig):
    seed = list(cfg.seed_memories)

    # Stopwords to ignore during scoring
    _STOP = {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "of",
        "in",
        "to",
        "for",
        "on",
        "at",
        "by",
        "with",
        "from",
        "and",
        "or",
        "but",
        "not",
        "so",
        "if",
        "then",
        "than",
        "it",
        "its",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "she",
        "they",
        "them",
        "their",
        "this",
        "that",
        "what",
        "whats",
        "which",
        "who",
        "how",
        "when",
        "where",
    }

    def _tokenize(text: str) -> set[str]:
        # Strip punctuation before splitting so "agenda:" matches "agenda"
        cleaned = re.sub(r"[^\w\s]", " ", text.lower())
        return {w for w in cleaned.split() if len(w) > 1 and w not in _STOP}

    # Synonym sets: if any word in a group appears in the query, add all
    _SYNONYMS = [
        {"agenda", "schedule", "calendar", "plan", "plans", "itinerary"},
        {"todo", "todos", "tasks", "task", "chores", "chore", "errands"},
        {"appointment", "appointments", "meeting", "meetings"},
        {"routine", "routines", "daily", "morning", "evening"},
    ]

    def _expand_query(words: set[str]) -> set[str]:
        """Expand query words with synonyms and day-of-week for 'today'."""
        expanded = set(words)
        # "today" -> current day name (e.g., "monday")
        if "today" in expanded or "todays" in expanded:
            day_name = datetime.now().strftime("%A").lower()
            expanded.add(day_name)
            expanded.discard("today")
            expanded.discard("todays")
            # Also add common schedule words since asking about "today"
            expanded.update({"agenda", "schedule", "todo"})
        # "tomorrow" -> next day name
        if "tomorrow" in expanded or "tomorrows" in expanded:
            from datetime import timedelta

            day_name = (datetime.now() + timedelta(days=1)).strftime("%A").lower()
            expanded.add(day_name)
            expanded.discard("tomorrow")
            expanded.discard("tomorrows")
            expanded.update({"agenda", "schedule", "todo"})
        # Synonym expansion
        for syn_group in _SYNONYMS:
            if expanded & syn_group:
                expanded.update(syn_group)
        return expanded

    async def _recall_memory(
        query: str, memory_types: list | None = None, max_results: int = 5
    ) -> list[dict]:
        q_words = _expand_query(_tokenize(query or ""))
        if not q_words:
            return []

        scored: list[tuple[float, dict]] = []
        for item in seed:
            # Filter by type early if requested
            if memory_types and item.get("type") not in memory_types:
                continue

            tags = {str(t).lower() for t in item.get("tags", [])}
            content_words = _tokenize(item.get("content", ""))
            all_item_words = tags | content_words

            # Score: how many query words appear in this memory's tags + content
            hit_count = len(q_words & all_item_words)
            if hit_count == 0:
                # Also check if any query word is a substring of any tag
                # (e.g. "todo" matches tag "todo", "sched" matches "schedule")
                substring_hits = sum(1 for qw in q_words if any(qw in t or t in qw for t in tags))
                if substring_hits == 0:
                    continue
                hit_count = substring_hits * 0.5  # partial credit

            # Bonus for tag matches (tags are curated, higher signal)
            tag_hits = len(q_words & tags)
            score = hit_count + tag_hits * 1.5

            scored.append((score, item))

        # Sort by score descending, return top N
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:max_results]]

    return _recall_memory


def _capability_discover(registry: Any):
    async def _discover(
        intent: str, domain: str | None = None, constraints: dict | None = None
    ) -> dict:
        if registry is None:
            return {"capabilities": [], "count": 0, "hint": "No capability registry available."}
        return await registry.discover(intent, domain, constraints)

    return _discover


def _capability_invoke(registry: Any):
    async def _invoke(name: str, params: dict, session_id: str | None = None) -> dict:
        if registry is None:
            return {"success": False, "error": "No capability registry"}
        return await registry.invoke(name, params, session_id)

    return _invoke


class _FabricGatewayAdapter:
    """Capability registry adapter for OrchestratorStub fabric port."""

    def __init__(self, registry: Any) -> None:
        self._registry = registry

    async def execute(self, request: Any) -> Any:
        from poc.k1_poc.orchestrator.types import CapabilityResult

        result = await self._registry.invoke(
            request.name,
            request.params or {},
            request.session_id,
        )
        success = bool(result.get("success", result.get("status") == "ok"))
        return CapabilityResult(
            success=success,
            data=result if success else {},
            error="" if success else str(result.get("error", "invoke_failed")),
            capability_name=request.name,
        )

    async def execute_batch(self, requests: list[Any]) -> list[Any]:
        return [await self.execute(req) for req in requests]


class _StateReadAdapter:
    """SessionState adapter for OrchestratorStub state read port."""

    def __init__(self, session_state: Any) -> None:
        self._ss = session_state

    async def snapshot(self, sections: list[str]) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        for section_name in sections:
            try:
                section = self._ss.get_section(section_name)
                snapshot[section_name] = (
                    section.to_dict() if hasattr(section, "to_dict") else section
                )
            except Exception:
                snapshot[section_name] = {}
        return snapshot

    async def read_section(self, session_id: str, section: str) -> dict[str, Any] | None:
        try:
            value = self._ss.get_section(section)
            return value.to_dict() if hasattr(value, "to_dict") else value
        except Exception:
            return None


def _build_delta_applicator(session_state: Any, bus: Any) -> Any:
    """Build a DeltaApplicator wired to session state and bus notification."""
    from poc.k1_poc.delta.applicator import DeltaApplicator
    from poc.k1_poc.delta.topics import STATE_UPDATED

    def _preflight(section: str, operation: str, estimated_size: int) -> Any:
        """MutationGuard preflight check if guard is available."""
        if hasattr(session_state, "guard"):
            return session_state.guard.preflight(section, operation, estimated_size)

        # No guard -- approve unconditionally
        class _Approved:
            approved = True
            reason = "no guard"

        return _Approved()

    async def _write(section: str, key: str, operation: str, data: dict) -> None:
        """Write a delta to a session state section."""
        try:
            sec = session_state.get_section(section)
            if sec is None:
                logger.warning("Delta write: section '%s' not found", section)
                return
            if operation == "set":
                if hasattr(sec, "__setitem__"):
                    sec[key] = data
                elif hasattr(sec, "update"):
                    sec.update({key: data})
            elif operation == "update":
                if hasattr(sec, "update"):
                    sec.update({key: data})
                elif hasattr(sec, "__setitem__"):
                    sec[key] = data
            elif operation == "append":
                if hasattr(sec, "append"):
                    sec.append({key: data})
                elif hasattr(sec, "update"):
                    existing = sec.get(key, []) if hasattr(sec, "get") else []
                    if isinstance(existing, list):
                        existing.append(data)
                        sec.update({key: existing})
                    else:
                        sec.update({key: data})
            elif operation == "delete":
                if hasattr(sec, "__delitem__"):
                    try:
                        del sec[key]
                    except (KeyError, IndexError):
                        pass
            logger.debug("Delta applied: section=%s key=%s op=%s", section, key, operation)
        except Exception as exc:
            logger.warning(
                "Delta write failed: section=%s key=%s op=%s err=%s",
                section,
                key,
                operation,
                exc,
            )

    async def _notify(batch_id: str, applied_count: int) -> None:
        """Emit k1.session.state.updated.v1 after applying a batch."""
        import json

        from k1.bus.envelope import Envelope, PayloadFormat, Priority

        payload = json.dumps(
            {"batch_id": batch_id, "applied": applied_count},
            separators=(",", ":"),
        ).encode("utf-8")
        env = Envelope(
            topic=STATE_UPDATED,
            priority=Priority.BACKGROUND,
            payload=payload,
            payload_format=PayloadFormat.JSON,
        )
        bus.publish(env)
        logger.info(
            "Delta notification: batch=%s applied=%d topic=%s",
            batch_id,
            applied_count,
            STATE_UPDATED,
        )

    return DeltaApplicator(
        preflight_fn=_preflight,
        write_fn=_write,
        notify_fn=_notify,
    )


class _DeltaEmitAdapter:
    """Delta emitter adapter that routes events through the aggregator.

    When a delta_aggregator is available, delta-lane topics are parsed
    into SessionDelta objects and collected into the aggregator's batch
    window.  Non-delta events are published directly to the bus.
    """

    def __init__(
        self,
        aggregator: Any = None,
        bus: Any = None,
    ) -> None:
        self._aggregator = aggregator
        self._bus = bus

    async def emit(self, event_topic: str, payload: Any, trace_id: str = "") -> None:
        """Emit an event -- route deltas to aggregator, others to bus."""
        from poc.k1_poc.delta.topics import ARTIFACT_CREATED, TASK_STATE_CHANGED

        if self._aggregator is not None and event_topic in (
            ARTIFACT_CREATED,
            TASK_STATE_CHANGED,
        ):
            # Parse payload into SessionDelta and collect into batch
            from poc.k1_poc.delta.session_delta import SessionDelta

            if isinstance(payload, SessionDelta):
                await self._aggregator.collect(payload)
            elif isinstance(payload, dict):
                try:
                    delta = SessionDelta.from_dict(payload)
                    await self._aggregator.collect(delta)
                except Exception as exc:
                    logger.warning("Failed to parse delta from payload: %s", exc)
            return

        # Non-delta events: publish directly to bus if available
        if self._bus is not None:
            import json as _json

            from k1.bus.envelope import Envelope, PayloadFormat, Priority

            payload_bytes = (
                _json.dumps(payload, separators=(",", ":")).encode("utf-8")
                if isinstance(payload, dict)
                else str(payload).encode("utf-8")
            )
            env = Envelope(
                topic=event_topic,
                priority=Priority.INTERACTIVE,
                payload=payload_bytes,
                payload_format=PayloadFormat.JSON,
            )
            self._bus.publish(env)
