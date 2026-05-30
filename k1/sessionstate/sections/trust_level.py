"""TrustLevelSection -- HOT conversational trust calibration state."""

from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any


class TrustLevelSection:
    """Canonical HOT SessionState section for Front trust calibration.

    This is a prompt-facing cognitive signal, not an authorization gate. It
    helps Front decide whether to be more explicit, cautious, or concise on
    the next turn while policy and runtime gates continue to own side effects.
    """

    BUDGET_BYTES: int = 2 * 1024
    TIER: str = "hot"
    CAN_EVICT: bool = False
    SECTION_NAME: str = "trust_level"
    MAX_RECENT_SIGNALS: int = 5

    __slots__ = (
        "_session_id",
        "_trust_score",
        "_confidence",
        "_band",
        "_stance",
        "_last_signal",
        "_last_reason",
        "_recent_signals",
        "_last_updated_ms",
        "_extra",
    )

    def __init__(self, session_id: str = "") -> None:
        self._session_id = session_id
        self._trust_score = 0.5
        self._confidence = 0.5
        self._band = self._band_for_score(self._trust_score)
        self._stance = "calibrating"
        self._last_signal = ""
        self._last_reason = ""
        self._recent_signals: list[dict[str, Any]] = []
        self._last_updated_ms = int(time.time() * 1000)
        self._extra: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return self.SECTION_NAME

    @property
    def tier(self) -> str:
        return self.TIER

    @property
    def budget_bytes(self) -> int:
        return self.BUDGET_BYTES

    @property
    def can_evict(self) -> bool:
        return self.CAN_EVICT

    @property
    def trust_score(self) -> float:
        return self._trust_score

    @property
    def confidence(self) -> float:
        return self._confidence

    @property
    def band(self) -> str:
        return self._band

    @property
    def stance(self) -> str:
        return self._stance

    def update(
        self,
        trust_score: float | None = None,
        score: float | None = None,
        delta: float | None = None,
        confidence: float | None = None,
        band: str | None = None,
        stance: str | None = None,
        signal: str | None = None,
        reason: str | None = None,
        source: str | None = None,
        **extra: Any,
    ) -> None:
        """Apply a bounded trust calibration update."""
        base = trust_score if trust_score is not None else score
        if base is not None:
            self._trust_score = self._clamp01(base)
        delta_value: float | None = None
        if delta is not None:
            try:
                delta_value = float(delta)
            except (TypeError, ValueError):
                delta_value = 0.0
            self._trust_score = self._clamp01(self._trust_score + delta_value)
        if confidence is not None:
            self._confidence = self._clamp01(confidence)
        self._band = str(band).strip() if band else self._band_for_score(self._trust_score)
        if stance:
            self._stance = str(stance).strip()
        self._last_signal = str(signal or self._last_signal or "")
        self._last_reason = str(reason or self._last_reason or "")

        if signal or reason or delta is not None:
            self._append_signal(
                {
                    "signal": self._last_signal,
                    "delta": delta_value if delta_value is not None else 0.0,
                    "score": self._trust_score,
                    "confidence": self._confidence,
                    "reason": self._last_reason,
                    "source": str(source or ""),
                    "timestamp_ms": int(time.time() * 1000),
                }
            )
        if extra:
            self._extra.update(deepcopy(extra))
        self._touch()

    def set_data(self, data: dict[str, Any]) -> None:
        payload = dict(data or {})
        self._session_id = str(payload.get("session_id") or self._session_id or "")
        self._trust_score = self._clamp01(
            payload.get("trust_score", payload.get("score", self._trust_score))
        )
        self._confidence = self._clamp01(payload.get("confidence", self._confidence))
        self._band = str(payload.get("band") or self._band_for_score(self._trust_score))
        self._stance = str(payload.get("stance") or self._stance or "calibrating")
        self._last_signal = str(payload.get("last_signal") or payload.get("signal") or "")
        self._last_reason = str(payload.get("last_reason") or payload.get("reason") or "")
        recent = payload.get("recent_signals") or []
        self._recent_signals = [dict(item) for item in recent if isinstance(item, dict)][
            -self.MAX_RECENT_SIGNALS :
        ]
        known = {
            "session_id",
            "trust_score",
            "score",
            "confidence",
            "band",
            "stance",
            "last_signal",
            "signal",
            "last_reason",
            "reason",
            "recent_signals",
        }
        self._extra = deepcopy({key: value for key, value in payload.items() if key not in known})
        self._touch()

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "session_id": self._session_id,
            "trust_score": self._trust_score,
            "confidence": self._confidence,
            "band": self._band,
            "stance": self._stance,
            "last_signal": self._last_signal,
            "last_reason": self._last_reason,
            "recent_signals": deepcopy(self._recent_signals),
            "last_updated_ms": self._last_updated_ms,
        }
        data.update(deepcopy(self._extra))
        return data

    def get_data(self) -> dict[str, Any]:
        return self.to_dict()

    def clear(self) -> None:
        session_id = self._session_id
        self.__init__(session_id=session_id)

    def apply(self, operation: str, data: dict[str, Any]) -> Any:
        if operation == "update":
            self.update(**dict(data or {}))
            return self.to_dict()
        if operation == "clear":
            self.clear()
            return None
        raise ValueError(f"Unknown trust_level operation: {operation}")

    def get_metadata(self) -> dict[str, Any]:
        return {
            "name": self.SECTION_NAME,
            "tier": self.TIER,
            "size_bytes": self.get_size_bytes(),
            "budget_bytes": self.BUDGET_BYTES,
            "last_updated_ms": self._last_updated_ms,
            "trust_score": self._trust_score,
            "band": self._band,
            "signal_count": len(self._recent_signals),
        }

    def get_size_bytes(self) -> int:
        return len(json.dumps(self.to_dict(), separators=(",", ":"), default=str).encode("utf-8"))

    def to_flatbuffer(self) -> bytes:
        return json.dumps(self.to_dict(), separators=(",", ":"), default=str).encode("utf-8")

    def from_flatbuffer(self, data: bytes) -> None:
        if not data:
            self.set_data({})
            return
        payload = json.loads(data.decode("utf-8"))
        self.set_data(payload if isinstance(payload, dict) else {})

    def _append_signal(self, signal: dict[str, Any]) -> None:
        self._recent_signals.append(deepcopy(signal))
        self._recent_signals = self._recent_signals[-self.MAX_RECENT_SIGNALS :]

    def _touch(self) -> None:
        self._last_updated_ms = int(time.time() * 1000)

    @staticmethod
    def _clamp01(value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = 0.5
        return max(0.0, min(1.0, numeric))

    @staticmethod
    def _band_for_score(score: float) -> str:
        if score < 0.3:
            return "low"
        if score < 0.45:
            return "guarded"
        if score < 0.75:
            return "steady"
        return "high"


__all__ = ["TrustLevelSection"]
