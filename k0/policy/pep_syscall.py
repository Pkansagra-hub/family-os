"""Policy decision point executed for every kernel syscall."""

from __future__ import annotations

import fnmatch
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, cast

LOGGER = logging.getLogger(__name__)

_DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[1] / "contracts" / "policy" / "pep.schema.json"
)
_POLICY_ENV_VAR = "K0_POLICY_MANIFEST_PATH"
_BAND_ORDER = ("GREEN", "AMBER", "RED")

# Cache for manifest fingerprints
_cached_manifest_fingerprint: dict[str, str] = {}


class PolicyConfigurationError(RuntimeError):
    """Raised when the policy manifest is missing or malformed."""


def _empty_details() -> dict[str, str]:
    return {}


@dataclass(slots=True)
class Obligation:
    """Represents a policy obligation emitted by the PEP."""

    name: str
    details: dict[str, str] = field(default_factory=_empty_details)


@dataclass(slots=True)
class PolicyDecision:
    """Outcome emitted by the policy enforcement point (PEP)."""

    admit: bool
    obligations: Sequence[Obligation] = field(default_factory=tuple)
    deny_reason: str | None = None


def evaluate_envelope(envelope: dict[str, object]) -> PolicyDecision:
    """Evaluate the request envelope against band, caps, and ABAC policies."""

    manifest = _load_policy_manifest()

    band = str(envelope.get("band", "GREEN")).upper()
    band_policy = _lookup_band_policy(manifest, band)

    obligations: list[Obligation] = []
    obligations.extend(_build_obligations(manifest.get("default_obligations", [])))
    obligations.extend(_build_obligations(band_policy.get("obligations", [])))

    policy_ctx = _coerce_mapping(
        envelope.get("policy") or envelope.get("pep") or envelope.get("policy_ctx") or {}
    )
    abac_ctx = _coerce_mapping(policy_ctx.get("abac", {}))
    caps_ctx = _coerce_mapping(policy_ctx.get("caps", {}))

    # Device posture guard rails run before any other evaluation.
    posture_decision = _evaluate_device_posture(manifest, abac_ctx, obligations, envelope, band)
    if posture_decision:
        return posture_decision

    # Bands that are blocked outright short-circuit the evaluation.
    if band_policy.get("deny", False):
        obligations = _deduplicate_obligations(obligations)
        decision = PolicyDecision(False, tuple(obligations), deny_reason="BAND_BLOCKED")
        _log_decision(envelope, decision, band)
        return decision

    cap_decision = _evaluate_caps(band_policy, caps_ctx, obligations, envelope, band)
    if cap_decision:
        return cap_decision

    payload_decision = _evaluate_payload_size(band_policy, envelope, obligations, band)
    if payload_decision:
        return payload_decision

    sunset_decision = _evaluate_schema_sunsets(manifest, envelope, obligations, band)
    if sunset_decision:
        return sunset_decision

    role_decision = _evaluate_roles(manifest, abac_ctx, envelope, obligations, band)
    if role_decision:
        return role_decision

    obligations = _deduplicate_obligations(obligations)
    decision = PolicyDecision(True, tuple(obligations))
    _log_decision(envelope, decision, band)
    return decision


def _resolve_policy_manifest_path() -> Path:
    override = os.getenv(_POLICY_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return _DEFAULT_POLICY_PATH


def _load_policy_manifest() -> dict[str, Any]:
    manifest_path = _resolve_policy_manifest_path()
    try:
        return _cached_manifest(manifest_path)
    except FileNotFoundError as exc:  # pragma: no cover - configuration bug
        raise PolicyConfigurationError(f"Policy manifest not found at {manifest_path}") from exc


def get_manifest_fingerprint() -> str | None:
    """Get the fingerprint (SHA-256 hash) of the current policy manifest.

    Returns None if the manifest cannot be loaded.
    """
    import hashlib

    try:
        manifest_path = _resolve_policy_manifest_path()
        path_str = str(manifest_path)

        # Check cache first
        if path_str in _cached_manifest_fingerprint:
            return _cached_manifest_fingerprint[path_str]

        # Compute and cache
        if not manifest_path.exists():
            return None
        manifest_bytes = manifest_path.read_bytes()
        fingerprint = hashlib.sha256(manifest_bytes).hexdigest()
        _cached_manifest_fingerprint[path_str] = fingerprint
        return fingerprint
    except Exception:  # pragma: no cover
        return None


def _clear_manifest_fingerprint_cache() -> None:
    """Clear the manifest fingerprint cache. Used in tests."""
    _cached_manifest_fingerprint.clear()


@lru_cache(maxsize=4)
def _cached_manifest(path: Path) -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if "bands" not in raw or "roles" not in raw:
        raise PolicyConfigurationError("Policy manifest missing required keys: 'bands' and 'roles'")
    return raw


def _lookup_band_policy(manifest: Mapping[str, Any], band: str) -> Mapping[str, Any]:
    bands = manifest.get("bands", {})
    policy = bands.get(band)
    if policy is None:
        raise PolicyConfigurationError(f"No policy configured for band '{band}'")
    return _coerce_mapping(policy)


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        typed_mapping = cast(Mapping[Any, Any], value)
        return {str(k): v for k, v in typed_mapping.items()}
    return {}


def _stringify_detail(value: Any) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value}"
    return str(value)


def _build_obligations(
    entries: Iterable[Any],
    extra_details: Mapping[str, Any] | None = None,
) -> list[Obligation]:
    obligations: list[Obligation] = []
    if extra_details:
        merged_extra = {str(k): _stringify_detail(v) for k, v in extra_details.items()}
    else:
        merged_extra = {}
    for entry in entries:
        if isinstance(entry, str):
            details = dict(merged_extra)
            obligations.append(Obligation(name=entry, details=details))
        elif isinstance(entry, Mapping):
            mapping_entry = _coerce_mapping(entry)
            name = mapping_entry.get("name")
            if not isinstance(name, str) or not name:
                continue
            # For structured obligations like kernel.redact.field, preserve complex types
            # Otherwise stringify simple scalar values
            detail_map = {}
            for k, v in _coerce_mapping(mapping_entry.get("details", {})).items():
                if name == "kernel.redact.field" and k in ("fields", "target"):
                    # Preserve list/sequence types for redaction directives
                    detail_map[str(k)] = v
                elif name == "kernel.redact.field" and k == "mask":
                    # Keep mask as-is (usually a string)
                    detail_map[str(k)] = v
                else:
                    # Stringify other detail values for backward compatibility
                    detail_map[str(k)] = _stringify_detail(v)
            details = {**detail_map, **merged_extra}
            obligations.append(Obligation(name=name, details=details))
    return obligations


def _evaluate_device_posture(
    manifest: Mapping[str, Any],
    abac_ctx: Mapping[str, Any],
    obligations: list[Obligation],
    envelope: Mapping[str, Any],
    band: str,
) -> PolicyDecision | None:
    posture = abac_ctx.get("device_posture")
    if posture is None:
        return None

    posture_rules = _coerce_mapping(manifest.get("device_postures", {}).get(str(posture)))
    if not posture_rules:
        return None

    obligations.extend(_build_obligations(posture_rules.get("obligations", [])))
    if posture_rules.get("deny", False):
        obligations = _deduplicate_obligations(obligations)
        decision = PolicyDecision(False, tuple(obligations), deny_reason="DEVICE_POSTURE_DENIED")
        _log_decision(envelope, decision, band)
        return decision

    return None


def _evaluate_caps(
    band_policy: Mapping[str, Any],
    caps_ctx: Mapping[str, Any],
    obligations: list[Obligation],
    envelope: Mapping[str, Any],
    band: str,
) -> PolicyDecision | None:
    cap_rules = (
        ("fanout", "max_fanout", "CAP_FANOUT_EXCEEDED"),
        ("throughput_pps", "max_throughput_pps", "CAP_THROUGHPUT_EXCEEDED"),
    )

    for cap_key, limit_key, reason in cap_rules:
        limit = band_policy.get(limit_key)
        if limit is None:
            continue
        requested = _extract_cap_value(caps_ctx.get(cap_key))
        if requested is None:
            continue
        if float(requested) > float(limit):
            violation_obligation = band_policy.get("violation_obligation")
            if violation_obligation:
                obligations.extend(
                    _build_obligations(
                        [violation_obligation],
                        {
                            "cap": cap_key,
                            "limit": limit,
                            "requested": requested,
                        },
                    )
                )
            obligations = _deduplicate_obligations(obligations)
            decision = PolicyDecision(False, tuple(obligations), deny_reason=reason)
            _log_decision(envelope, decision, band)
            return decision

    return None


def _evaluate_payload_size(
    band_policy: Mapping[str, Any],
    envelope: Mapping[str, Any],
    obligations: list[Obligation],
    band: str,
) -> PolicyDecision | None:
    limit = band_policy.get("max_payload_bytes")
    if limit is None:
        return None

    payload_bytes = envelope.get("payload_bytes")
    if payload_bytes is None:
        return None

    try:
        payload_value = float(payload_bytes)
    except (TypeError, ValueError):
        return None

    if payload_value > float(limit):
        violation_obligation = band_policy.get("violation_obligation")
        if violation_obligation:
            obligations.extend(
                _build_obligations(
                    [violation_obligation],
                    {
                        "cap": "payload_bytes",
                        "limit": limit,
                        "requested": payload_value,
                    },
                )
            )
        obligations = _deduplicate_obligations(obligations)
        decision = PolicyDecision(False, tuple(obligations), deny_reason="CAP_PAYLOAD_EXCEEDED")
        _log_decision(envelope, decision, band)
        return decision

    return None


def _evaluate_schema_sunsets(
    manifest: Mapping[str, Any],
    envelope: Mapping[str, Any],
    obligations: list[Obligation],
    band: str,
) -> PolicyDecision | None:
    schema_uri = envelope.get("schema_uri")
    schema_version = envelope.get("schema_version")
    if not schema_uri or not schema_version:
        return None

    key = f"{schema_uri}/{schema_version}"
    window_rules = _coerce_mapping(manifest.get("sunset_windows", {}).get(key))
    if not window_rules:
        return None

    ts_value = envelope.get("ts")
    current_ts = _parse_timestamp(ts_value)
    if current_ts is None:
        return None

    warn_after = _parse_timestamp(window_rules.get("warn_after"))
    deny_after = _parse_timestamp(window_rules.get("deny_after"))
    obligation_entry = window_rules.get("obligation")

    if deny_after and current_ts >= deny_after:
        obligations.extend(
            _build_obligations(
                [obligation_entry] if obligation_entry else [],
                {"schema": key, "phase": "deny"},
            )
        )
        obligations = _deduplicate_obligations(obligations)
        decision = PolicyDecision(False, tuple(obligations), deny_reason="SCHEMA_SUNSET")
        _log_decision(envelope, decision, band)
        return decision

    if warn_after and current_ts >= warn_after and obligation_entry:
        obligations.extend(
            _build_obligations(
                [obligation_entry],
                {"schema": key, "phase": "warn"},
            )
        )

    return None


def _evaluate_roles(
    manifest: Mapping[str, Any],
    abac_ctx: Mapping[str, Any],
    envelope: Mapping[str, Any],
    obligations: list[Obligation],
    band: str,
) -> PolicyDecision | None:
    roles_ctx = abac_ctx.get("roles")
    roles: list[str] = []
    if isinstance(roles_ctx, Sequence) and not isinstance(roles_ctx, (str, bytes)):
        roles_sequence = cast(Sequence[Any], roles_ctx)
        roles = [str(role) for role in roles_sequence if isinstance(role, str)]
    topic = str(envelope.get("topic", ""))

    permissible = False

    for role_entry in manifest.get("roles", []):
        role_policy = _coerce_mapping(role_entry)
        role_name = role_policy.get("name")
        if role_name not in roles:
            continue

        max_band = role_policy.get("max_band", "RED")
        if _band_rank(band) > _band_rank(str(max_band)):
            continue

        patterns = role_policy.get("allow_topics", [])
        if _topic_matches(topic, patterns):
            permissible = True
            obligations.extend(_build_obligations(role_policy.get("obligations", [])))

    if permissible:
        return None

    violation_entry = manifest.get("role_violation_obligation")
    if violation_entry:
        obligations.extend(_build_obligations([violation_entry], {"topic": topic}))

    obligations = _deduplicate_obligations(obligations)
    decision = PolicyDecision(False, tuple(obligations), deny_reason="ROLE_FORBIDDEN")
    _log_decision(envelope, decision, band)
    return decision


def _topic_matches(topic: str, patterns: Iterable[Any]) -> bool:
    for pattern in patterns:
        if isinstance(pattern, str) and fnmatch.fnmatch(topic, pattern):
            return True
    return False


def _extract_cap_value(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Mapping):
        typed_value = _coerce_mapping(value)
        for key in ("requested", "value", "current"):
            requested = typed_value.get(key)
            if isinstance(requested, (int, float)):
                return float(requested)
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _band_rank(band: str) -> int:
    try:
        return _BAND_ORDER.index(band)
    except ValueError:
        return len(_BAND_ORDER)


def _deduplicate_obligations(obligations: Iterable[Obligation]) -> list[Obligation]:
    def _make_hashable(value: Any) -> Any:
        """Convert a value to a hashable type for deduplication keys."""
        if isinstance(value, list):
            return tuple(_make_hashable(v) for v in value)
        elif isinstance(value, dict):
            return tuple(sorted((k, _make_hashable(v)) for k, v in value.items()))
        else:
            return value

    seen: set[tuple[str, Any]] = set()
    deduped: list[Obligation] = []
    for obligation in obligations:
        # Convert details to a hashable form
        hashable_details = tuple(
            sorted((k, _make_hashable(v)) for k, v in obligation.details.items())
        )
        key = (obligation.name, hashable_details)
        if key in seen:
            continue
        deduped.append(obligation)
        seen.add(key)
    return deduped


def _log_decision(envelope: Mapping[str, Any], decision: PolicyDecision, band: str) -> None:
    topic = envelope.get("topic")
    tenant = envelope.get("tenant_id")
    space = envelope.get("space_id")
    raw_ctx = envelope.get("policy") or envelope.get("pep") or envelope.get("policy_ctx") or {}
    role_ctx = _coerce_mapping(raw_ctx)
    abac_mapping = _coerce_mapping(role_ctx.get("abac", {}))
    maybe_roles = abac_mapping.get("roles")
    roles: list[str] = []
    if isinstance(maybe_roles, Sequence) and not isinstance(maybe_roles, (str, bytes)):
        roles_iter = cast(Sequence[Any], maybe_roles)
        roles = [str(role) for role in roles_iter if isinstance(role, str)]

    obligation_names = [obligation.name for obligation in decision.obligations]
    log_kwargs: dict[str, object] = {
        "band": band,
        "topic": topic,
        "tenant": tenant,
        "space": space,
        "roles": roles,
        "obligations": obligation_names,
        "deny_reason": decision.deny_reason,
    }

    if decision.admit:
        LOGGER.info("PEP allow", extra={"pep_decision": log_kwargs})
    else:
        LOGGER.warning("PEP deny", extra={"pep_decision": log_kwargs})
