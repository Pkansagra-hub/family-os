"""Normalize raw or approximate installed-device location fixes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from k1.spatial.errors import InvalidLocationFixError
from k1.spatial.service.permission_normalizer import normalize_permission_state
from k1.spatial.types import LocationFix


def normalize_location_fix(
    raw: LocationFix | Mapping[str, Any] | None,
    *,
    observed_at_utc: str | None = None,
    permission_state: str = "unknown",
    source: str = "device",
) -> LocationFix:
    """Return a validated fix or an explicit unavailable/hidden fix."""
    permission = normalize_permission_state(permission_state)
    captured_at = observed_at_utc or datetime.now(UTC).isoformat()
    if isinstance(raw, LocationFix):
        return _validate(raw)
    payload = dict(raw or {})
    permission = normalize_permission_state(payload.get("permission_state") or permission)
    captured_at = str(
        payload.get("captured_at_utc") or payload.get("observed_at_utc") or captured_at
    )

    latitude = _optional_float(payload.get("latitude", payload.get("lat")))
    longitude = _optional_float(payload.get("longitude", payload.get("lon", payload.get("lng"))))
    accuracy_m = _optional_float(payload.get("accuracy_m", payload.get("accuracy")))
    if latitude is None or longitude is None or permission != "granted":
        redaction = "permission_denied" if permission == "denied" else "source_unavailable"
        if permission == "hidden":
            redaction = "policy_hidden"
        return LocationFix(
            latitude=None,
            longitude=None,
            accuracy_m=accuracy_m,
            captured_at_utc=captured_at,
            permission_state=permission,
            source=str(payload.get("source") or source),
            confidence=0.0,
            precision="hidden",
            redactions=(redaction,),
            metadata=dict(payload.get("metadata") or {}),
        )
    confidence = _confidence(accuracy_m, payload.get("confidence"))
    return _validate(
        LocationFix(
            latitude=latitude,
            longitude=longitude,
            accuracy_m=accuracy_m,
            captured_at_utc=captured_at,
            permission_state=permission,
            source=str(payload.get("source") or source),
            confidence=confidence,
            altitude_m=_optional_float(payload.get("altitude_m", payload.get("altitude"))),
            heading_deg=_optional_float(payload.get("heading_deg", payload.get("heading"))),
            speed_mps=_optional_float(payload.get("speed_mps", payload.get("speed"))),
            precision="raw",
            metadata=dict(payload.get("metadata") or {}),
        )
    )


def _validate(fix: LocationFix) -> LocationFix:
    if fix.latitude is not None and not -90.0 <= fix.latitude <= 90.0:
        raise InvalidLocationFixError(f"latitude out of range: {fix.latitude}")
    if fix.longitude is not None and not -180.0 <= fix.longitude <= 180.0:
        raise InvalidLocationFixError(f"longitude out of range: {fix.longitude}")
    if fix.accuracy_m is not None and fix.accuracy_m < 0:
        raise InvalidLocationFixError(f"accuracy_m out of range: {fix.accuracy_m}")
    if (fix.latitude is None) != (fix.longitude is None):
        raise InvalidLocationFixError("latitude and longitude must appear together")
    return fix


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _confidence(accuracy_m: float | None, raw_confidence: object) -> float:
    if raw_confidence is not None:
        return max(0.0, min(1.0, float(raw_confidence)))
    if accuracy_m is None:
        return 0.5
    if accuracy_m <= 50:
        return 0.95
    if accuracy_m <= 250:
        return 0.75
    if accuracy_m <= 1_000:
        return 0.45
    return 0.25


__all__ = ["normalize_location_fix"]
