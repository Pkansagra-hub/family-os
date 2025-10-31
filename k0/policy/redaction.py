"""Redaction obligation helpers.

Implements the redaction flow described in ADR-0089. Callers supply a JSON-like
``body`` mapping plus a series of ``RedactionDirective`` entries derived from
policy obligations. The helpers return a sanitized copy without mutating the
original payload so audit trails can retain the pristine request body.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, MutableMapping, Sequence, cast


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
                raise RedactionError(
                    f"Directive {directive.obligation} produced empty field path"
                )

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
        if target_value is not None and not isinstance(
            target_value, (str, Sequence)
        ):
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
