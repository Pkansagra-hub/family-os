"""
k1.concierge.session -- ConciergeRuntime + ConciergeSession.

ConciergeRuntime:  Long-lived lifecycle wrapper for the Concierge subsystem.
                   Owns FSM, mailbox consumer, subscriptions, runtime teardown.
                   Created by ConciergeFactory.create_*() methods.

ConciergeSession:  Per-request scope wrapper around ConciergeRuntime.
                   Created by ConciergeFactory.create_request_scope().
                   Lifetime: one user turn (request → response).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from k1.bus.envelope import Envelope
from k1.bus.ports.bus import IBus
from k1.bus.ports.mailbox import IMailbox, IMailboxRouter
from k1.concierge.fsm.controller import ConciergeController
from k1.concierge.protocols.suspension import SuspensionResolutionNotFound

logger = logging.getLogger(__name__)


class ConciergeRuntime:
    """Long-lived lifecycle wrapper for the Concierge subsystem.

    Owns: FSM, mailbox consumer, subscriptions, runtime teardown.
    Created by ConciergeFactory.create_*() methods.

    Lifecycle:
        runtime = factory.create_standalone()    # wired, NOT started
        await runtime.start()                    # begins mailbox consumer
        runtime.inject(envelope)                 # publish user input
        await runtime.stop()                     # teardown
    """

    def __init__(
        self,
        *,
        bus: IBus,
        router: IMailboxRouter,
        front_mailbox: IMailbox,
        back_mailbox: IMailbox,
        fsm: ConciergeController,
        model: Any,
        session_state: Any,
        front_dispatcher: Any,
        back_dispatcher: Any,
        front_subscriptions: list[Any],
        input_port: Any | None = None,
        output_port: Any | None = None,
        dispatch_port: Any | None = None,
        front_ctx: Any | None = None,
        back_ctx: Any | None = None,
        experience_layer: Any | None = None,
        delta_aggregator: Any | None = None,
        delta_applicator: Any | None = None,
        hil_port: Any | None = None,
        orchestrator: Any | None = None,
        ledger: Any | None = None,
        ledger_store: Any | None = None,
        dead_letter_consumer: Any | None = None,
        back_pool: Any | None = None,
        back_topic_router: Any | None = None,
        ready_queue: Any | None = None,
    ) -> None:
        self._bus = bus
        self._router = router
        self._front_mailbox = front_mailbox
        self._back_mailbox = back_mailbox
        self._fsm = fsm
        self._model = model
        self._input_port = input_port
        self._output_port = output_port
        self._llm_port = model
        self._session_state = session_state
        self._state_port = session_state
        self._dispatch_port = dispatch_port
        self._front_dispatcher = front_dispatcher
        self._back_dispatcher = back_dispatcher
        self._front_subscriptions = front_subscriptions
        self._front_ctx = front_ctx
        self._back_ctx = back_ctx
        self._experience_layer = experience_layer
        self._delta_aggregator = delta_aggregator
        self._delta_applicator = delta_applicator
        self._hil_port = hil_port
        self._orchestrator = orchestrator
        self._ledger = ledger
        self._ledger_store = ledger_store
        self._dead_letter_consumer = dead_letter_consumer
        self._back_pool = back_pool
        self._back_topic_router = back_topic_router
        self._ready_queue = ready_queue
        self._consumer_task: asyncio.Task[None] | None = None
        self._back_tasks: dict[str, asyncio.Task[None]] = {}
        self._lease_watcher_task: asyncio.Task | None = None
        self._started = False
        # M5.E4: per-session SelfModelHandle (set by KernelService after
        # P3.5 install). When None, front_handler runs with no grounding
        # capsule (pre-M4 baseline).
        self._self_model: Any = None
        self._temporal: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the mailbox consumer task."""
        if self._started:
            return
        self._consumer_task = asyncio.create_task(self._mailbox_consumer())
        if self._back_pool is not None and hasattr(self._back_pool, "start_lease_watcher"):
            self._lease_watcher_task = await self._back_pool.start_lease_watcher(self._bus)
        self._started = True
        logger.info("ConciergeRuntime.start: consumer task created")

    async def stop(self) -> None:
        """Stop consumer, flush delta, teardown FSM, close session state."""
        if not self._started:
            return

        # 1. Cancel consumer task
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        for task in list(self._back_tasks.values()):
            if not task.done():
                task.cancel()
        if self._back_tasks:
            await asyncio.gather(*self._back_tasks.values(), return_exceptions=True)
        self._back_tasks.clear()

        if self._back_pool is not None and hasattr(self._back_pool, "stop_lease_watcher"):
            await self._back_pool.stop_lease_watcher()
        self._lease_watcher_task = None

        # 2. Flush ledger
        if self._ledger is not None:
            try:
                logger.info(
                    "Ledger shutdown: %d entries",
                    self._ledger_store.count() if self._ledger_store else 0,
                )
            except Exception:
                logger.debug("Ledger flush failed during shutdown", exc_info=True)

        # 3. Log dead-letter summary
        if self._dead_letter_consumer is not None:
            try:
                summary = self._dead_letter_consumer.snapshot()
                total = summary.get("total_dead_letters", 0)
                if total > 0:
                    logger.warning("Session dead-letter summary: %s", summary)
                else:
                    logger.info("Session dead-letter summary: 0 dead-letters")
            except Exception:
                logger.debug("Dead-letter summary failed during shutdown", exc_info=True)

        # 4. Flush delta aggregator
        if self._delta_aggregator is not None:
            try:
                await self._delta_aggregator.flush()
            except Exception:
                logger.debug("Delta flush failed during shutdown", exc_info=True)

        # 5. FSM teardown (unsubscribes all bus handles)
        if self._fsm is not None:
            try:
                self._fsm.teardown()
            except Exception:
                logger.debug("FSM teardown failed", exc_info=True)

        for handle in list(self._front_subscriptions):
            try:
                self._bus.unsubscribe(handle)
            except Exception:
                logger.debug("Front subscription cleanup failed", exc_info=True)
        self._front_subscriptions.clear()

        if self._input_port is not None and hasattr(self._input_port, "close"):
            try:
                self._input_port.close()
            except Exception:
                logger.debug("Input port close failed", exc_info=True)

        # 6. Close session state
        if self._session_state is not None and hasattr(self._session_state, "close"):
            try:
                await self._session_state.close()
            except Exception:
                logger.debug("Session state close failed", exc_info=True)

        # 7. Close model
        if self._model is not None and hasattr(self._model, "close"):
            try:
                await self._model.close()
            except Exception:
                logger.debug("Model close failed", exc_info=True)

        self._started = False
        logger.info("ConciergeRuntime.stop: runtime stopped")

    def inject(self, envelope: Envelope) -> None:
        """Publish an envelope to the session bus (entry point for user input)."""
        self._bus.publish(envelope)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        """Current FSM state name."""
        return self._fsm.state.name

    @property
    def fsm(self) -> ConciergeController:
        return self._fsm

    @property
    def bus(self) -> IBus:
        return self._bus

    @property
    def model(self) -> Any:
        return self._model

    @property
    def session_state(self) -> Any:
        return self._session_state

    @property
    def output_port(self) -> Any | None:
        return self._output_port

    @property
    def dispatch_port(self) -> Any | None:
        return self._dispatch_port

    @property
    def started(self) -> bool:
        return self._started

    @property
    def experience_layer(self) -> Any | None:
        return self._experience_layer

    @property
    def delta_aggregator(self) -> Any | None:
        return self._delta_aggregator

    @property
    def delta_applicator(self) -> Any | None:
        return self._delta_applicator

    @property
    def hil_port(self) -> Any | None:
        return self._hil_port

    @property
    def orchestrator(self) -> Any | None:
        return self._orchestrator

    @property
    def ledger(self) -> Any | None:
        return self._ledger

    @property
    def dead_letter_consumer(self) -> Any | None:
        return self._dead_letter_consumer

    @property
    def back_pool(self) -> Any | None:
        return self._back_pool

    @property
    def back_topic_router(self) -> Any | None:
        return self._back_topic_router

    @property
    def ready_queue(self) -> Any | None:
        return self._ready_queue

    @property
    def active_back_tasks(self) -> dict[str, asyncio.Task[None]]:
        return dict(self._back_tasks)

    @property
    def front_ctx(self) -> Any | None:
        return self._front_ctx

    @property
    def back_ctx(self) -> Any | None:
        return self._back_ctx

    @property
    def self_model(self) -> Any | None:
        """Per-session SelfModelHandle, or None when disabled."""
        return self._self_model

    @property
    def temporal(self) -> Any | None:
        """Per-session TemporalHandle, or None when disabled."""
        return self._temporal

    def set_self_model(self, handle: Any) -> None:
        """Attach a SelfModelHandle for stage 9.5 grounding capsules.

        Must be called before ``start()`` so the runtime cannot race a
        mailbox turn that is already reading the handle.
        """
        if self._started:
            raise RuntimeError("set_self_model() must be called before start()")
        self._self_model = handle

    def set_temporal(self, handle: Any) -> None:
        """Attach a TemporalHandle for turn refresh and prompt projection."""
        if self._started:
            raise RuntimeError("set_temporal() must be called before start()")
        self._temporal = handle

    @property
    def front_subscriptions(self) -> list[Any]:
        return self._front_subscriptions

    @property
    def front_dispatcher(self) -> Any:
        """Front-side tool dispatcher (read-only)."""
        return self._front_dispatcher

    @property
    def back_dispatcher(self) -> Any:
        """Back-side tool dispatcher (read-only)."""
        return self._back_dispatcher

    @property
    def consumer_task(self) -> asyncio.Task[None] | None:
        """Mailbox consumer asyncio.Task, or None before start()."""
        return self._consumer_task

    @property
    def ledger_store(self) -> Any | None:
        """Ledger store, or None if not configured."""
        return self._ledger_store

    # ------------------------------------------------------------------
    # Mailbox consumer (extracted from bootstrap._mailbox_consumer)
    # ------------------------------------------------------------------

    async def _mailbox_consumer(self) -> None:
        """Poll front/back mailboxes and invoke actor handlers."""
        from k1.concierge.actors.front import front_handler
        from k1.concierge.config import get_config
        from k1.concierge.tools.schemas_front import FRONT_TOOL_SCHEMAS

        _kcfg = get_config().kernel
        poll_interval = _kcfg.poll_interval_s
        dedup_limit = _kcfg.dedup_cache_size
        seen_front_ids: set[int] = set()
        seen_back_ids: set[int] = set()

        while True:
            did_work = False

            # --- Front mailbox ---
            front_env = self._front_mailbox.receive(timeout_ms=0)
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
                # M6.E1.I2: route the per-session OppPipeline ONLY to Front.
                # Back never sees OPP -- it builds its own prompt via
                # build_back_prompt and must not receive identity/compression
                # enrichment. getattr() default keeps tests that stub the FSM
                # without ``_opp_pipeline`` working.
                await front_handler(
                    envelope=front_env,
                    model=self._model,
                    ss=self._session_state,
                    bus=self._bus,
                    tool_dispatcher=self._front_dispatcher,
                    all_tool_schemas=FRONT_TOOL_SCHEMAS,
                    fsm_state=self._fsm.state.name,
                    self_model=self._self_model,
                    temporal=self._temporal,
                    opp_pipeline=getattr(self._fsm, "_opp_pipeline", None),
                )
                await self._tick_experience()

            # --- Back mailbox ---
            self._cleanup_back_tasks()
            drained_overflow = self._drain_back_overflow_to_ready_queue()
            if drained_overflow:
                did_work = True

            while True:
                back_env = self._back_mailbox.receive(timeout_ms=0)
                if back_env is None:
                    break
                env_id = int(getattr(back_env, "envelope_id", 0) or 0)
                if env_id and env_id in seen_back_ids:
                    continue
                if env_id:
                    seen_back_ids.add(env_id)
                    if len(seen_back_ids) > dedup_limit:
                        seen_back_ids.clear()
                did_work = True
                await self._enqueue_or_run_back_envelope(back_env)

            scheduled = await self._schedule_ready_back_envelopes()
            if scheduled:
                did_work = True

            if did_work:
                await asyncio.sleep(0)
            else:
                await asyncio.sleep(poll_interval)

    def _parse_back_payload(self, envelope: Envelope) -> dict[str, Any]:
        payload_bytes = getattr(envelope, "payload", None)
        if not payload_bytes:
            return {}
        try:
            if isinstance(payload_bytes, (bytes, bytearray)):
                return json.loads(payload_bytes.decode("utf-8"))
            if isinstance(payload_bytes, str):
                return json.loads(payload_bytes)
        except Exception:
            logger.debug("session: failed to parse back envelope payload", exc_info=True)
        return {}

    def _back_task_id(self, envelope: Envelope) -> str:
        payload = self._parse_back_payload(envelope)
        task_id = str(payload.get("task_id") or "")
        if task_id:
            return task_id
        envelope_id = getattr(envelope, "envelope_id", None)
        return f"envelope-{envelope_id or uuid.uuid4().hex}"

    def _back_depends_on(self, envelope: Envelope) -> str | None:
        payload = self._parse_back_payload(envelope)
        depends_on = payload.get("depends_on")
        if not depends_on:
            depends_on = payload.get("dependsOn")
        if isinstance(depends_on, list):
            depends_on = depends_on[0] if depends_on else None
        if depends_on is None:
            return None
        depends_on_s = str(depends_on).strip()
        return depends_on_s or None

    def _back_session_id(self, envelope: Envelope) -> str | None:
        payload = self._parse_back_payload(envelope)
        session_id = payload.get("session_id") or payload.get("sessionId")
        if session_id:
            return str(session_id)
        return None

    def _back_cancel_token(self, task_id: str) -> Any | None:
        getter = getattr(self._fsm, "get_cancel_token", None)
        if callable(getter):
            token = getter(task_id)
            if token is not None:
                return token

        cancel_handler = getattr(self._fsm, "cancel_handler", None)
        handler_getter = getattr(cancel_handler, "get_token", None)
        if callable(handler_getter):
            return handler_getter(task_id)
        return None

    def _cleanup_back_tasks(self) -> None:
        for task_id, task in list(self._back_tasks.items()):
            if task.done():
                self._back_tasks.pop(task_id, None)

    def _drain_back_overflow_to_ready_queue(self) -> bool:
        if self._back_pool is None or self._ready_queue is None:
            return False
        drained = False
        while True:
            envelope = self._back_pool.dequeue_overflow()
            if envelope is None:
                break
            drained = True
            self._ready_queue.enqueue(envelope)
        return drained

    async def _enqueue_or_run_back_envelope(self, envelope: Envelope) -> None:
        router = self._back_topic_router
        topic = getattr(envelope, "topic", "") or ""
        task_id = self._back_task_id(envelope)

        if router is not None:
            handler = router.route(envelope)
            if handler is None:
                return
            if router.is_cancel_topic(topic):
                cancel_token = router.get_cancel_token_for_task(task_id)
                handler(envelope=envelope, fsm_state=self._fsm, cancel_token=cancel_token)
                return

        if self._ready_queue is None or self._back_pool is None:
            await self._schedule_back_envelope(envelope)
            return

        depends_on = None
        if getattr(self._back_pool.config, "enable_dependency_ordering", True):
            depends_on = self._back_depends_on(envelope)
        status, failed_task_ids = self._ready_queue.enqueue(envelope, depends_on=depends_on)
        if failed_task_ids:
            self._publish_dependency_failures(failed_task_ids, reason=status)

    async def _schedule_ready_back_envelopes(self) -> int:
        if self._ready_queue is None:
            return 0
        scheduled = 0
        for envelope in self._ready_queue.dequeue_ready():
            if await self._schedule_back_envelope(envelope):
                scheduled += 1
        return scheduled

    async def _schedule_back_envelope(self, envelope: Envelope) -> bool:
        task_id = self._back_task_id(envelope)

        if self._back_pool is None:
            task = asyncio.create_task(self._run_back_envelope(envelope))
            self._back_tasks[task_id] = task
            return True

        try:
            slot = self._back_pool.acquire_worker(
                task_id,
                session_id=self._back_session_id(envelope),
                cancellation_token=self._back_cancel_token(task_id),
            )
        except Exception as exc:
            from k1.concierge.actors.back_pool import BackPoolExhausted

            if isinstance(exc, BackPoolExhausted):
                self._back_pool.enqueue_overflow(envelope)
                return False
            raise

        if self._ready_queue is not None:
            self._ready_queue.register_task(task_id)

        task = asyncio.create_task(self._run_back_envelope_with_slot(envelope, slot))
        slot.bind_task(task)
        self._back_tasks[task_id] = task
        return True

    async def _run_back_envelope_with_slot(self, envelope: Envelope, slot: Any) -> None:
        task_id = slot.task_id
        reason = "completed"
        queue_status: str | None = "completed"
        try:
            result = await self._run_back_envelope(
                envelope,
                cancel_token=getattr(getattr(slot, "lease", None), "cancellation_token", None),
                propagate_errors=True,
            )
            status = str(getattr(result, "status", "complete") or "complete")
            if status == "suspended":
                reason = "suspended"
                queue_status = None
            elif status == "cancelled":
                reason = "cancelled"
                queue_status = "cancelled"
            elif status == "complete":
                reason = "completed"
                queue_status = "completed"
            else:
                reason = "error"
                queue_status = "failed"
        except SuspensionResolutionNotFound:
            reason = "error"
            queue_status = "failed"
        except asyncio.CancelledError:
            reason = "cancelled"
            queue_status = "cancelled"
            raise
        except Exception:
            reason = "error"
            queue_status = "failed"
        finally:
            if self._back_pool is not None:
                self._back_pool.release_worker(task_id, reason=reason)
            self._back_tasks.pop(task_id, None)
            if queue_status is not None and self._ready_queue is not None:
                _, failed_task_ids = self._ready_queue.notify_completed(
                    task_id, status=queue_status
                )
                if failed_task_ids:
                    self._publish_dependency_failures(failed_task_ids, reason="dependency_failed")

    def _publish_dependency_failures(self, task_ids: list[str], *, reason: str) -> None:
        from k1.concierge.bus.builders import build_task_failed

        for task_id in task_ids:
            self._bus.publish(
                build_task_failed(
                    payload={
                        "task_id": task_id,
                        "reason": reason,
                        "error": "dependency_failed",
                    }
                )
            )
            if self._ready_queue is not None:
                self._ready_queue.notify_completed(task_id, status="failed")

    async def _run_back_envelope(
        self,
        envelope: Envelope,
        *,
        cancel_token: Any | None = None,
        propagate_errors: bool = False,
    ) -> Any | None:
        """Run one Back actor envelope without blocking Front mailbox polling."""
        from k1.concierge.actors.back import route_back_envelope

        try:
            return await route_back_envelope(
                envelope=envelope,
                model=self._model,
                ss=self._session_state,
                bus=self._bus,
                tool_dispatcher=self._back_dispatcher,
                fsm_state=self._fsm,
                cancel_token=cancel_token,
                hil_port=self._hil_port,
                temporal=self._temporal,
            )
        except SuspensionResolutionNotFound as exc:
            # M6 E6.2 (C08): back_resume_handler raises this when
            # no resume_context is available for the task. The
            # handler has already published `task_failed` on the
            # bus before raising, so observers see the failure.
            # Absorb here to keep the session loop alive.
            logger.warning(
                "session: back resume failed -- SuspensionResolutionNotFound task_id=%s",
                exc.task_id,
            )
            if propagate_errors:
                raise
            return None
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "session: back envelope handling failed topic=%s envelope_id=%s",
                getattr(envelope, "topic", ""),
                getattr(envelope, "envelope_id", "?"),
            )
            if propagate_errors:
                raise
            return None

    # ------------------------------------------------------------------
    # Experience layer tick (extracted from bootstrap._tick_experience)
    # ------------------------------------------------------------------

    async def _tick_experience(self) -> None:
        """Invoke ExperienceLayer tick and emit relevant envelopes."""
        layer = self._experience_layer
        if layer is None:
            return

        from k1.concierge.bus.builders import build_affect_update, build_proactive_fill

        context = self._build_experience_context()
        outputs = await layer.tick(self._fsm.state.name, context)

        emotional = outputs.get("emotional")
        if emotional is not None:
            payload = emotional.__dict__ if hasattr(emotional, "__dict__") else {"value": emotional}
            self._bus.publish(build_affect_update(payload=payload))

        tone = outputs.get("tone")
        if tone is not None:
            try:
                tone_dict = tone.__dict__ if hasattr(tone, "__dict__") else {}
                section = self._session_state.get_section("affective_now")
                if section is not None:
                    section._tone_adjustment = tone_dict
            except Exception:
                pass

        try:
            rc = getattr(layer, "rhythm_controller", None)
            if rc is not None:
                style = getattr(rc, "last_response_style", None)
                if style is not None:
                    section = self._session_state.get_section("affective_now")
                    if section is not None:
                        section._response_style = (
                            style.__dict__ if hasattr(style, "__dict__") else {}
                        )
        except Exception:
            pass

        fill = outputs.get("fill")
        if fill is not None:
            payload = fill.__dict__ if hasattr(fill, "__dict__") else {"text": str(fill)}
            self._bus.publish(build_proactive_fill(payload=payload))

        # M6.E2.I2: write narrative outputs to the ``narrative_active`` SS
        # section so the prompt builder's Stage 8 SS read can render the
        # primary thread (``Thread: <title>`` line). Skip when the FSM is
        # mid-HITL clarification (CLARIFYING_WORKER) -- the user is
        # answering a Back HITL request, so we must NOT create or switch
        # the primary thread mid-clarification. The 0.25 salience-delta
        # gate prevents thrash when two threads have similar frequency.
        try:
            narrative = outputs.get("narrative")
            fsm_state_name = self._fsm.state.name
            if (
                narrative is not None
                and getattr(narrative, "active_threads", None)
                and fsm_state_name != "CLARIFYING_WORKER"
            ):
                section = self._session_state.get_section("narrative_active")
                if section is not None and hasattr(section, "primary_thread"):
                    top = str(narrative.active_threads[0])
                    salience = getattr(narrative, "thread_salience", {}) or {}
                    suggestion = str(getattr(narrative, "weave_suggestion", "") or "")
                    related_intents = list(narrative.active_threads[:5])
                    turn_number = getattr(self._fsm, "turn_number", None)
                    primary = section.primary_thread
                    if primary is None:
                        section.create_thread(
                            title=top,
                            goal=suggestion,
                            turn_number=turn_number,
                            related_intents=related_intents,
                        )
                    elif primary.title == top:
                        if hasattr(section, "update_thread"):
                            section.update_thread(
                                primary.id,
                                goal=suggestion or None,
                                turn_number=turn_number,
                            )
                    else:
                        # Different top thread -- switch only when the new
                        # thread's salience exceeds the primary's by >= 0.25.
                        new_s = float(salience.get(top, 0.0))
                        old_s = float(salience.get(primary.title, 0.0))
                        if new_s - old_s >= 0.25:
                            section.create_thread(
                                title=top,
                                goal=suggestion,
                                turn_number=turn_number,
                                related_intents=related_intents,
                            )
                        elif hasattr(section, "update_thread"):
                            section.update_thread(
                                primary.id,
                                goal=suggestion or None,
                                turn_number=turn_number,
                            )
        except Exception:
            logger.warning("session._tick_experience: narrative write failed", exc_info=True)

    def _build_experience_context(self) -> dict[str, Any]:
        """Build safe context snapshot for ExperienceLayer.tick()."""
        ss = self._session_state

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

        turn_transcript = ""
        try:
            for entry in reversed(self._fsm.history):
                if getattr(entry, "entry_type", None) == "user":
                    turn_transcript = entry.text or ""
                    break
        except Exception:
            pass

        affect_history: list[dict[str, Any]] = []
        affect_confidence = 0.0
        try:
            aff = ss.get_section("affective_now")
            if aff is not None:
                for snap in getattr(aff, "recent_emotions", []):
                    affect_history.append(
                        {
                            "turn_number": snap.turn_number,
                            "emotion": snap.emotion,
                            "intensity": snap.intensity,
                            "valence": snap.valence,
                            "arousal": snap.arousal,
                            "timestamp_ms": snap.timestamp_ms,
                        }
                    )
                src = getattr(aff, "source", "")
                if src in ("front", "ultrabert"):
                    affect_confidence = getattr(aff, "confidence", 0.0) or 0.0
        except Exception:
            pass

        conversation_history: list[dict[str, Any]] = []
        try:
            hist = ss.get_section("history_active")
            if hist is not None and hasattr(hist, "get_typed_entries"):
                for entry in hist.get_typed_entries(10):
                    # M6.E2.I1: project derived signals (intent/topic/thread)
                    # from ``TypedHistoryEntry.metadata`` so the
                    # NarrativeWeaver sees non-empty values. The underlying
                    # dataclass only stores ``task_id`` + ``metadata`` --
                    # all narrative-relevant fields live under metadata
                    # (placed there by the arbiter and the back-channel
                    # writers). Precedence: arbiter.decision -> metadata
                    # ['intent'] -> entry_type fallback.
                    metadata = getattr(entry, "metadata", None) or {}
                    arbiter = metadata.get("arbiter") if isinstance(metadata, dict) else None
                    arbiter_decision = ""
                    if isinstance(arbiter, dict):
                        arbiter_decision = str(arbiter.get("decision", "") or "")
                    intent = (
                        arbiter_decision
                        or str((metadata.get("intent") if isinstance(metadata, dict) else "") or "")
                        or entry.entry_type
                    )
                    topic = ""
                    thread = ""
                    if isinstance(metadata, dict):
                        topic = str(
                            metadata.get("topic")
                            or metadata.get("domain")
                            or metadata.get("current_thread")
                            or ""
                        )
                        thread = str(metadata.get("thread") or "")
                    conversation_history.append(
                        {
                            "turn_number": entry.turn_number,
                            "entry_type": entry.entry_type,
                            "text": entry.text,
                            "timestamp_ms": entry.timestamp_ms,
                            "source": entry.source,
                            "task_id": getattr(entry, "task_id", None),
                            "metadata": metadata if isinstance(metadata, dict) else {},
                            "intent": intent,
                            "topic": topic,
                            "thread": thread,
                        }
                    )
        except Exception:
            pass

        user_cadence: dict[str, Any] = {}
        try:
            user_ts = [
                e["timestamp_ms"]
                for e in conversation_history
                if e.get("source") == "user" and e.get("timestamp_ms")
            ]
            if len(user_ts) >= 2:
                gaps = [user_ts[i] - user_ts[i - 1] for i in range(1, len(user_ts))]
                user_cadence = {
                    "avg_gap_ms": int(sum(gaps) / len(gaps)),
                    "last_gap_ms": gaps[-1],
                    "sample_count": len(gaps),
                }
        except Exception:
            pass
        user_cadence["_conversation_history"] = conversation_history

        return {
            "turn_transcript": turn_transcript,
            "affect_history": affect_history,
            "front_refine_affect_confidence": affect_confidence,
            "conversation_history": conversation_history,
            "memory_recalls": [],
            "task_state": _section_dict("task_state"),
            "user_patterns": {},
            "wait_duration_ms": wait_ms,
            "persona": _section_dict("persona"),
            "user_cadence": user_cadence,
        }


# ---------------------------------------------------------------------------
# ConciergeSession -- per-request scope wrapper around ConciergeRuntime
# ---------------------------------------------------------------------------


@dataclass
class ConciergeSession:
    """Per-request scope wrapper around ConciergeRuntime.

    Created by: ``ConciergeFactory.create_request_scope(runtime, ...)``
    Lifetime:   one user turn (request → response)

    Holds scoped ``ToolContext`` copies that override per-request fields
    (cognitive_trace_id, bundle_idempotency_cache, active_device_id,
    active_task_id, capability_cache) while sharing long-lived references
    (session_manager, actor, writer_port, hil_coordinator, dispatch,
    recall_fn) from the runtime's ToolContext.
    """

    runtime: ConciergeRuntime
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    front_ctx: Any = field(default=None, repr=False)
    back_ctx: Any = field(default=None, repr=False)
    active_device_id: str | None = None
    active_task_id: str | None = None
    _closed: bool = field(default=False, init=False, repr=False)

    def inject(
        self,
        *,
        dispatch: Any | None = None,
        memory: Any | None = None,
    ) -> None:
        """Late-bind optional ports into this session's scoped ToolContexts.

        Maps:
            dispatch -> ToolContext.dispatch
            memory   -> ToolContext.recall_fn

        E4.M1.3: ``hil_coordinator`` parameter removed -- the legacy HIL
        coordinator field on ``ToolContext`` is gone now that the fabric
        capability gate (E3) enforces HIL. ``hil_port=`` injection lands
        in E4.M1.6 once the unified service is wired through the factory.
        """
        if self._closed:
            raise RuntimeError("Cannot inject into a closed ConciergeSession")
        for ctx in (self.front_ctx, self.back_ctx):
            if ctx is None:
                continue
            if dispatch is not None:
                ctx.dispatch = dispatch
            if memory is not None:
                ctx.recall_fn = memory

    async def close(self) -> None:
        """Cleanup per-request state.  Does NOT stop the runtime."""
        if self._closed:
            return
        # Clear per-request caches to help GC
        for ctx in (self.front_ctx, self.back_ctx):
            if ctx is None:
                continue
            ctx.bundle_idempotency_cache = None
            ctx.capability_cache = None
        self._closed = True
        logger.debug("ConciergeSession.close: trace_id=%s closed", self.trace_id)

    @property
    def closed(self) -> bool:
        return self._closed
