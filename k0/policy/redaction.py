"""Redaction obligation helpers.

Implements the redaction flow described in ADR-0089. Callers supply a JSON-like
``body`` mapping plus a series of ``RedactionDirective`` entries derived from
policy obligations. The helpers return a sanitized copy without mutating the
original payload so audit trails can retain the pristine request body.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, MutableMapping, Sequence, cast

try:
    import geohash2
except ImportError:
    geohash2 = None  # type: ignore


class RedactionError(RuntimeError):
    """Raised when a redaction directive cannot be applied."""


def _normalise_path(path: Sequence[str] | str | None) -> tuple[str, ...]:
    if path is None:
        return ()
    if isinstance(path, str):
        segments = [segment.strip() for segment in path.split(".") if segment.strip()]
    else:
        segments = [str(part).strip() for part in path if str(part).strip()]
    if not segments:
        return ()
    return tuple(segments)


def _ensure_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return value if isinstance(value, dict) else dict(value)


def _clone_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _clone_value(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_clone_value(child) for child in value]
    return value


def _mask_path(root: MutableMapping[str, object], path: tuple[str, ...], mask: object) -> bool:
    if not path:
        return False

    current: object = root

    for index, segment in enumerate(path):
        is_last = index == len(path) - 1

        if isinstance(current, MutableMapping):
            mapping = current
            if segment not in mapping:
                return False
            if is_last:
                mapping[segment] = mask
                return True
            current = mapping[segment]
            continue

        if isinstance(current, list):
            try:
                list_index = int(segment)
            except (TypeError, ValueError):
                return False

            if list_index < 0 or list_index >= len(current):
                return False

            if is_last:
                current[list_index] = mask
                return True

            current_value = current[list_index]
            if isinstance(current_value, Mapping):
                normalized = _ensure_mapping(current_value)
                if normalized is not current_value:
                    current[list_index] = normalized
                current = normalized
            elif isinstance(current_value, list):
                cloned = list(current_value)
                current[list_index] = cloned
                current = cloned
            else:
                current = current_value
            continue

        return False

    return False


@dataclass(slots=True)
class RedactionDirective:
    """Instruction telling the PEM which fields to mask."""

    obligation: str
    fields: Sequence[str] | str
    target: str | Sequence[str] | None = None
    mask: object = "***REDACTED***"


def apply_redactions(
    body: Mapping[str, object],
    directives: Iterable[RedactionDirective],
) -> dict[str, object]:
    """Apply redaction directives to the provided body.

    Parameters
    ----------
    body:
        Original payload mapping (JSON-like). The function clones the mapping
        lazily so the caller's object is not mutated.
    directives:
        Iterable of ``RedactionDirective`` entries, typically derived from
        policy obligations (e.g., ``kernel.redact.field``).

    Returns
    -------
    dict
        Sanitized copy of ``body`` with requested fields replaced by ``mask``
        values. If a path cannot be located the directive is ignored and the
        original structure is preserved.
    """

    if not isinstance(body, Mapping):
        raise RedactionError("Redaction body must be a mapping")

    sanitized_value = _clone_value(body)
    if not isinstance(sanitized_value, MutableMapping):
        raise RedactionError("Redaction body must be a mapping")

    sanitized = cast(MutableMapping[str, object], sanitized_value)

    for directive in directives:
        base_path = _normalise_path(directive.target)

        field_iterable: Iterable[str]
        if isinstance(directive.fields, str):
            field_iterable = (directive.fields,)
        else:
            field_iterable = directive.fields

        for field in field_iterable:
            field_path = _normalise_path(field)
            full_path = base_path + field_path
            if not full_path:
                raise RedactionError(f"Directive {directive.obligation} produced empty field path")

            if not _mask_path(sanitized, full_path, directive.mask):
                # Silently ignore missing paths; the PEM will log at higher level if needed.
                continue

    return cast(dict[str, object], sanitized)


def _coerce_details_map(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return {str(key): val for key, val in value.items()}
    raise RedactionError("Obligation details must be a mapping")


def directives_from_obligations(
    obligations: Iterable[Any],
    *,
    default_mask: object = "***REDACTED***",
) -> list[RedactionDirective]:
    directives: list[RedactionDirective] = []

    for obligation in obligations:
        if isinstance(obligation, Mapping):
            name = obligation.get("name")
            details = obligation.get("details")
        else:
            name = getattr(obligation, "name", None)
            details = getattr(obligation, "details", None)

        if not isinstance(name, str) or not name:
            continue

        if name != "kernel.redact.field":
            continue

        details_map = _coerce_details_map(details)

        fields_value = details_map.get("fields")
        if isinstance(fields_value, str):
            fields: Sequence[str] | str = fields_value
        elif isinstance(fields_value, Sequence) and not isinstance(
            fields_value, (str, bytes, bytearray)
        ):
            fields = [str(field) for field in fields_value]
        else:
            raise RedactionError(
                "kernel.redact.field obligation missing 'fields' sequence or string"
            )

        target_value = details_map.get("target")
        if target_value is not None and not isinstance(target_value, (str, Sequence)):
            raise RedactionError("Obligation 'target' must be string or sequence")

        mask_value = details_map.get("mask", default_mask)

        directives.append(
            RedactionDirective(
                obligation=name,
                fields=fields,
                target=target_value,
                mask=mask_value,
            )
        )

    return directives


def mask_location_for_band(
    body: dict[str, Any],
    band: str,
    lat_field: str = "location_lat",
    lon_field: str = "location_lon",
) -> dict[str, Any]:
    """Apply geohash masking based on privacy band (GDPR/CCPA compliance).

    This implements privacy-by-design location masking per GDPR Article 25 and
    CCPA requirements. Exact GPS coordinates are replaced with coarse geohash
    values to prevent individual identification while preserving general location.

    Privacy Band Precision Levels:
    - GREEN: No masking (exact lat/lon preserved, precision=1m)
    - AMBER: Geohash-6 (5km precision, ~0.7 km² box)
    - RED: Geohash-4 (25km precision, ~500 km² box)

    Parameters
    ----------
    body : dict[str, Any]
        The envelope body containing location fields
    band : str
        Privacy band (GREEN, AMBER, RED)
    lat_field : str
        Field name for latitude (default: "location_lat")
    lon_field : str
        Field name for longitude (default: "location_lon")

    Returns
    -------
    dict[str, Any]
        Modified body with:
        - location_geohash: Coarse geohash string
        - location_precision_m: Precision in meters
        - location_lat/lon: NULL for AMBER/RED (exact coords removed)

    Raises
    ------
    RedactionError
        If coordinates are invalid or only one coordinate is provided

    Examples
    --------
    >>> body = {"location_lat": 37.7749, "location_lon": -122.4194}
    >>> masked = mask_location_for_band(body, "AMBER")
    >>> masked
    {
        "location_lat": None,
        "location_lon": None,
        "location_geohash": "9q8yy9",
        "location_precision_m": 5000
    }
    """
    if geohash2 is None:
        raise RedactionError("geohash2 library not installed. Run: pip install geohash2")

    band = band.upper()

    # If no location fields present, return unchanged
    if lat_field not in body and lon_field not in body:
        return body

    # Validate both coordinates are present (partial location is error)
    lat = body.get(lat_field)
    lon = body.get(lon_field)

    if (lat is None) != (lon is None):
        raise RedactionError(
            f"Partial location data: both {lat_field} and {lon_field} must be present or absent"
        )

    if lat is None and lon is None:
        return body

    # Validate coordinates
    try:
        lat_value = float(lat)
        lon_value = float(lon)
    except (TypeError, ValueError) as exc:
        raise RedactionError(f"Invalid location coordinates: {exc}") from exc

    if not (-90 <= lat_value <= 90):
        raise RedactionError(f"Invalid latitude {lat_value}: must be in range [-90, 90]")
    if not (-180 <= lon_value <= 180):
        raise RedactionError(f"Invalid longitude {lon_value}: must be in range [-180, 180]")

    # Create modified body copy
    masked = dict(body)

    # Apply band-specific masking
    if band == "GREEN":
        # GREEN: No masking, exact coordinates preserved
        masked["location_geohash"] = geohash2.encode(lat_value, lon_value, precision=12)
        masked["location_precision_m"] = 1  # ~1 meter precision
        # Keep exact lat/lon

    elif band == "AMBER":
        # AMBER: Geohash-6 (5km precision) per GDPR reasonable accuracy
        geohash = geohash2.encode(lat_value, lon_value, precision=6)
        masked["location_geohash"] = geohash
        masked["location_precision_m"] = 5000  # 5km radius
        # Clear exact coordinates (GDPR compliance)
        masked[lat_field] = None
        masked[lon_field] = None

    elif band == "RED":
        # RED: Geohash-4 (25km precision) for high-sensitivity data
        geohash = geohash2.encode(lat_value, lon_value, precision=4)
        masked["location_geohash"] = geohash
        masked["location_precision_m"] = 25000  # 25km radius
        # Clear exact coordinates (GDPR compliance)
        masked[lat_field] = None
        masked[lon_field] = None

    else:
        # Unknown band: treat as RED (most conservative)
        geohash = geohash2.encode(lat_value, lon_value, precision=4)
        masked["location_geohash"] = geohash
        masked["location_precision_m"] = 25000
        masked[lat_field] = None
        masked[lon_field] = None

    return masked
