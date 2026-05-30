"""Spatial privacy policy boundary."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class ISpatialPolicyPort(Protocol):
    """Decide spatial precision by actor, subject, task, and consumer."""

    async def allowed_precision(
        self,
        *,
        session_id: str,
        consumer: str,
        subject_ref: str | None = None,
        task_scope: str | None = None,
        capability: str | None = None,
        requested_precision: str | None = None,
    ) -> str:
        """Return the maximum allowed spatial precision."""
        ...  # pragma: no cover

    async def redaction_reasons(
        self,
        *,
        session_id: str,
        consumer: str,
        precision: str,
        context: Mapping[str, Any] | None = None,
    ) -> tuple[str, ...]:
        """Return policy redaction reasons for an accepted precision."""
        ...  # pragma: no cover


__all__ = ["ISpatialPolicyPort"]
