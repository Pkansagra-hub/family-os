"""Per-session Temporal handle exposed to kernel consumers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from k1.temporal.adapters import PersonaTimezoneAdapter, TemporalStateAdapter
from k1.temporal.kernel.bootstrap import TemporalServiceBundle
from k1.temporal.kernel.session_binding import TemporalSessionBinding
from k1.temporal.types import (
    CandidateSpan,
    ResolvedTemporalExpression,
    TemporalAnchor,
    TemporalProjection,
    TemporalTurnSnapshot,
    TemporalWindow,
)


@dataclass
class TemporalHandle:
    """Session-scoped facade that structurally satisfies ITemporalPort."""

    bundle: TemporalServiceBundle
    binding: TemporalSessionBinding
    state_adapter: Any
    service: Any
    installed: bool = False

    @property
    def session_id(self) -> str:
        return self.binding.session_id

    @property
    def principal_id(self) -> str | None:
        return self.binding.principal_id

    @property
    def device_id(self) -> str | None:
        return self.binding.device_id

    @property
    def installation_id(self) -> str | None:
        return self.binding.installation_id

    def install_into_session(self) -> None:
        """Mark the handle installed; safe to call repeatedly."""
        self.installed = True

    def uninstall_from_session(self) -> None:
        """Mark the handle uninstalled; safe to call repeatedly."""
        self.installed = False

    async def get_anchor(self, session_id: str | None = None) -> TemporalAnchor:
        return await self.service.get_anchor(self._session(session_id))

    async def get_windows(self, session_id: str | None = None) -> dict[str, TemporalWindow]:
        return await self.service.get_windows(self._session(session_id))

    async def resolve_expression(
        self,
        session_id: str | None,
        text: str,
        *,
        intent: str | None = None,
        subject_ref: str | None = None,
    ) -> ResolvedTemporalExpression:
        return await self.service.resolve_expression(
            self._session(session_id), text, intent=intent, subject_ref=subject_ref
        )

    async def build_projection(
        self,
        session_id: str | None = None,
        consumer: str = "front",
    ) -> TemporalProjection:
        return await self.service.build_projection(self._session(session_id), consumer)

    async def get_projection(self, consumer: str = "front") -> TemporalProjection:
        """Convenience wrapper for callers already bound to this session."""
        return await self.build_projection(self.session_id, consumer)

    async def refresh_turn(
        self,
        session_id: str | None = None,
        *,
        turn_id: str | None = None,
        trace_id: str | None = None,
        candidates: Iterable[str | CandidateSpan] = (),
        user_text_candidates: Iterable[str | CandidateSpan] | None = None,
        device_id: str | None = None,
        installation_id: str | None = None,
    ) -> TemporalTurnSnapshot:
        effective_candidates = (
            tuple(user_text_candidates) if user_text_candidates is not None else candidates
        )
        return await self.service.refresh_turn(
            self._session(session_id),
            turn_id=turn_id,
            trace_id=trace_id,
            candidates=effective_candidates,
            principal_id=self.principal_id,
            device_id=device_id or self.device_id,
            installation_id=installation_id or device_id or self.installation_id,
        )

    async def shutdown(self) -> None:
        await self.service.shutdown()

    def _session(self, session_id: str | None) -> str:
        if not session_id:
            return self.session_id
        if session_id != self.session_id:
            raise ValueError(
                f"TemporalHandle bound to session {self.session_id!r}, got {session_id!r}"
            )
        return session_id


def build_temporal_handle(
    bundle: TemporalServiceBundle,
    *,
    session_id: str,
    principal_id: str | None = None,
    device_id: str | None = None,
    installation_id: str | None = None,
    state_manager: Any | None = None,
    state_adapter: Any | None = None,
    persona_reader: Any | None = None,
) -> TemporalHandle:
    """Build a per-session temporal handle from a Tier-1 bundle."""
    adapter = state_adapter
    if adapter is None:
        adapter = TemporalStateAdapter(
            state_manager,
            allow_memory_fallback=state_manager is None,
        )

    persona_source = persona_reader
    if persona_source is None and state_manager is not None:
        try:
            persona_source = state_manager.get_section("persona")
        except Exception:
            persona_source = None
    persona_tz = PersonaTimezoneAdapter(persona_source) if persona_source is not None else None
    service = bundle.build_service(state_port=adapter, persona_timezone_port=persona_tz)
    binding = TemporalSessionBinding(
        session_id=session_id,
        principal_id=principal_id,
        device_id=device_id,
        installation_id=installation_id,
    )
    return TemporalHandle(bundle=bundle, binding=binding, state_adapter=adapter, service=service)


__all__ = ["TemporalHandle", "build_temporal_handle"]
