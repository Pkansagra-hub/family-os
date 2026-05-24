"""Top-level temporal service facade."""

from __future__ import annotations

from typing import Any, Iterable

from k1.temporal.config import TemporalConfig
from k1.temporal.events import (
    AnchorCreatedPayload,
    AnchorRefreshedPayload,
    AnchorStalePayload,
    ExpressionAmbiguousPayload,
    ExpressionResolvedPayload,
)
from k1.temporal.ports import (
    IClockPort,
    IRoutinePort,
    ITemporalDeviceContextPort,
    ITemporalEventPort,
    ITemporalIdPort,
    ITemporalMetricsPort,
    ITemporalStatePort,
    ITimezonePort,
)
from k1.temporal.serialization import (
    anchor_to_dict,
    dict_to_anchor,
    dict_to_window,
    turn_snapshot_to_dict,
    window_to_dict,
)
from k1.temporal.service.anchor_builder import build_anchor
from k1.temporal.service.event_emitter import TemporalEventEmitter
from k1.temporal.service.expression_resolver import resolve_expression_candidate
from k1.temporal.service.freshness_evaluator import evaluate_freshness
from k1.temporal.service.health import TemporalHealthStatus
from k1.temporal.service.projection_builder import (
    build_projection as build_projection_from_state,
)
from k1.temporal.service.window_builder import build_standard_windows
from k1.temporal.types import (
    CandidateSpan,
    ResolvedTemporalExpression,
    TemporalAnchor,
    TemporalProjection,
    TemporalTurnSnapshot,
    TemporalWindow,
)


class TemporalService:
    """Authoritative per-session temporal service implementation."""

    def __init__(
        self,
        *,
        clock: IClockPort,
        id_port: ITemporalIdPort,
        state_port: ITemporalStatePort,
        event_port: ITemporalEventPort | None = None,
        device_context_port: ITemporalDeviceContextPort | None = None,
        spatial_timezone_port: ITimezonePort | None = None,
        persona_timezone_port: ITimezonePort | None = None,
        routine_port: IRoutinePort | None = None,
        metrics_port: ITemporalMetricsPort | None = None,
        config: TemporalConfig | None = None,
    ) -> None:
        self._clock = clock
        self._id_port = id_port
        self._state_port = state_port
        self._event_port = event_port
        self._event_emitter = TemporalEventEmitter(event_port)
        self._device_context_port = device_context_port
        self._spatial_timezone_port = spatial_timezone_port
        self._persona_timezone_port = persona_timezone_port
        self._routine_port = routine_port
        self._metrics_port = metrics_port
        self._config = config or TemporalConfig()
        self._closed = False

    async def get_anchor(self, session_id: str) -> TemporalAnchor:
        payload = await self._state_port.read_section(session_id)
        if payload and payload.get("anchor"):
            return dict_to_anchor(payload["anchor"])
        snapshot = await self.refresh_turn(session_id)
        return snapshot.anchor

    async def get_windows(self, session_id: str) -> dict[str, TemporalWindow]:
        payload = await self._state_port.read_section(session_id)
        if payload and payload.get("windows"):
            return {key: dict_to_window(value) for key, value in payload["windows"].items()}
        snapshot = await self.refresh_turn(session_id)
        return dict(snapshot.windows)

    async def resolve_expression(
        self,
        session_id: str,
        text: str,
        *,
        intent: str | None = None,
        subject_ref: str | None = None,
    ) -> ResolvedTemporalExpression:
        anchor = await self.get_anchor(session_id)
        resolution = await resolve_expression_candidate(
            CandidateSpan(text=text, metadata={"intent": intent, "subject_ref": subject_ref}),
            anchor,
            routine_port=self._routine_port,
        )
        await self._emit_resolution(session_id, resolution)
        return resolution

    async def build_projection(self, session_id: str, consumer: str) -> TemporalProjection:
        payload = await self._state_port.read_section(session_id)
        if payload is None or "anchor" not in payload:
            snapshot = await self.refresh_turn(session_id)
            payload = turn_snapshot_to_dict(snapshot)
        return build_projection_from_state(
            payload, consumer=consumer, now_utc=self._clock.now_utc(), config=self._config
        )

    async def refresh_turn(
        self,
        session_id: str,
        *,
        turn_id: str | None = None,
        trace_id: str | None = None,
        candidates: Iterable[str | CandidateSpan] = (),
        principal_id: str | None = None,
        device_id: str | None = None,
        installation_id: str | None = None,
    ) -> TemporalTurnSnapshot:
        previous = await self._state_port.read_section(session_id)
        previous_anchor_id = None
        if previous and previous.get("anchor"):
            previous_anchor_id = str(previous["anchor"].get("anchor_id"))
        device_context = await self._read_device_context(session_id, device_id, installation_id)
        anchor = await build_anchor(
            session_id=session_id,
            clock=self._clock,
            id_port=self._id_port,
            config=self._config,
            device_context=device_context,
            spatial_timezone_port=self._spatial_timezone_port,
            persona_timezone_port=self._persona_timezone_port,
            principal_id=principal_id,
        )
        windows = build_standard_windows(anchor)
        resolutions: list[ResolvedTemporalExpression] = []
        for candidate in candidates:
            resolution = await resolve_expression_candidate(
                candidate, anchor, routine_port=self._routine_port
            )
            resolutions.append(resolution)
            await self._emit_resolution(session_id, resolution)
        snapshot = TemporalTurnSnapshot(
            session_id=session_id,
            turn_id=turn_id,
            anchor=anchor,
            windows=windows,
            resolved_expressions=tuple(resolutions),
            refreshed_at_utc=self._clock.now_utc(),
            source="k1.temporal.temporal_service",
        )
        payload = turn_snapshot_to_dict(snapshot)
        payload["last_trace_id"] = trace_id
        await self._state_port.write_section(session_id, payload)
        await self._emit_anchor_event(session_id, anchor, previous_anchor_id)
        freshness = evaluate_freshness(anchor, self._clock.now_utc(), config=self._config)
        if freshness != "live":
            await self._event_emitter.publish_anchor_stale(
                AnchorStalePayload(anchor.anchor_id, session_id, self._clock.now_utc(), freshness)
            )
        if self._metrics_port is not None:
            self._metrics_port.incr("temporal.refresh_turn")
        return snapshot

    async def shutdown(self) -> None:
        self._closed = True

    def health(self) -> TemporalHealthStatus:
        return TemporalHealthStatus(
            ready=not self._closed,
            state_connected=self._state_port is not None,
            device_context_connected=self._device_context_port is not None,
            event_connected=self._event_port is not None,
        )

    async def _read_device_context(
        self,
        session_id: str,
        device_id: str | None,
        installation_id: str | None,
    ) -> dict[str, Any]:
        if self._device_context_port is None or not device_id or not installation_id:
            return {}
        snapshot = await self._device_context_port.get_device_snapshot(
            session_id, device_id, installation_id
        )
        return dict(snapshot)

    async def _emit_anchor_event(
        self, session_id: str, anchor: TemporalAnchor, previous_anchor_id: str | None
    ) -> None:
        if previous_anchor_id is None:
            await self._event_emitter.publish_anchor_created(
                AnchorCreatedPayload(
                    anchor.anchor_id, session_id, anchor_to_dict(anchor), anchor.captured_at_utc
                )
            )
            return
        await self._event_emitter.publish_anchor_refreshed(
            AnchorRefreshedPayload(
                anchor.anchor_id,
                previous_anchor_id,
                session_id,
                anchor_to_dict(anchor),
                anchor.captured_at_utc,
                {"timezone_source": anchor.timezone_source},
            )
        )

    async def _emit_resolution(
        self, session_id: str, resolution: ResolvedTemporalExpression
    ) -> None:
        if resolution.needs_clarification:
            await self._event_emitter.publish_expression_ambiguous(
                ExpressionAmbiguousPayload(
                    session_id,
                    resolution.raw_text,
                    resolution.clarification_reason or "ambiguous",
                    self._clock.now_utc(),
                )
            )
            return
        await self._event_emitter.publish_expression_resolved(
            ExpressionResolvedPayload(
                session_id=session_id,
                raw_text=resolution.raw_text,
                normalized_label=resolution.normalized_label,
                resolution_kind=resolution.resolution_kind,
                confidence=resolution.confidence,
                resolved_at_utc=self._clock.now_utc(),
                window=window_to_dict(resolution.window) if resolution.window else None,
                instant_local=resolution.instant_local,
            )
        )


__all__ = ["TemporalService"]
