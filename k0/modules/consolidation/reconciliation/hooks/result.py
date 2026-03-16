"""HookResult -- per-record hook execution result (M9.6)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HookResult:
    """Per-record result of hook execution."""

    layer: str
    record_id: str
    summary_regenerated: bool = False
    centroid_recomputed: bool = False
    failed: bool = False
    error_message: str = ""
    time_ms: float = 0.0

    @classmethod
    def success(
        cls,
        layer: str,
        record_id: str,
        *,
        summary: bool = False,
        centroid: bool = False,
        time_ms: float = 0.0,
    ) -> HookResult:
        return cls(
            layer=layer,
            record_id=record_id,
            summary_regenerated=summary,
            centroid_recomputed=centroid,
            time_ms=time_ms,
        )

    @classmethod
    def failure(
        cls,
        layer: str,
        record_id: str,
        error: str,
    ) -> HookResult:
        return cls(
            layer=layer,
            record_id=record_id,
            failed=True,
            error_message=error,
        )
