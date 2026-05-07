"""``ConstitutionSnapshot.body`` key-schema constants (V0 + V1).

The ``body`` dict shape is locked here so the composer and the policy
evaluator can rely on stable keys without each re-inventing them.

V0 schema (legacy IAM-style — DEPRECATED in M9):

```
body = {
    "visibility_rules": { ... },
    "autonomy_rules": {
        # role -> {can|must_ask|cannot: [tool_ids]}    ← tool names — wrong layer
        "guardian": {
            "can":      ["recall_memory", "set_routine"],
            "must_ask": ["pickup_change"],
            "cannot":   [],
        },
    },
    "authority_rules": { "set_pickup": 2, ... },
    "protection_rules": { ... },
    "consent_rules": { ... },
}
```

V1 schema (M6 — conscience-first; default-allow):

```
body = {
    "schema_version": 1,
    "visibility_rules": { ... unchanged ... },
    "conscience_rules": {
        # role -> { forbidden, must_ask, tier_floor, risk_overrides }
        "guardian": {
            "forbidden":      [],
            "must_ask":       ["set_medication"],
            "tier_floor":     {"set_medication": 3},
            "risk_overrides": {},
        },
    },
    "protection_rules": { ... unchanged ... },
    "consent_rules":    { ... unchanged ... },
}
```

Both schemas are supported during M6–M8. ``get_conscience_bucket()``
auto-detects the schema and returns the unified ``ConscienceBucket``
shape. v0 → derived: ``forbidden = autonomy_rules[role][cannot]``;
``must_ask = autonomy_rules[role][must_ask]``; ``tier_floor`` from
``authority_rules``. v1 → native fields from ``conscience_rules``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final

from k1.selfmodel.contracts.conscience import ConscienceBucket

__all__ = [
    "VISIBILITY_RULES",
    "AUTONOMY_RULES",
    "AUTHORITY_RULES",
    "PROTECTION_RULES",
    "CONSENT_RULES",
    "CONSCIENCE_RULES",
    "AUTONOMY_CAN",
    "AUTONOMY_MUST_ASK",
    "AUTONOMY_CANNOT",
    "CONSCIENCE_FORBIDDEN",
    "CONSCIENCE_MUST_ASK",
    "CONSCIENCE_SOFT_WARN",
    "CONSCIENCE_TIER_FLOOR",
    "CONSCIENCE_RISK_OVERRIDES",
    "CONSENT_AUDIENCE_FAMILY",
    "SCHEMA_VERSION",
    "get_visibility_keys",
    "get_autonomy_bucket",
    "get_authority_tier",
    "get_protection_rules",
    "get_conscience_bucket",
    "is_v1_schema",
]


# ---- Top-level body keys -------------------------------------------------
VISIBILITY_RULES: Final[str] = "visibility_rules"
AUTONOMY_RULES: Final[str] = "autonomy_rules"  # v0 only (deprecated M9)
AUTHORITY_RULES: Final[str] = "authority_rules"  # v0 only (deprecated M9)
PROTECTION_RULES: Final[str] = "protection_rules"
CONSENT_RULES: Final[str] = "consent_rules"
CONSCIENCE_RULES: Final[str] = "conscience_rules"  # v1 only
SCHEMA_VERSION: Final[str] = "schema_version"

# ---- autonomy_rules[role] sub-buckets (v0) ------------------------------
AUTONOMY_CAN: Final[str] = "can"
AUTONOMY_MUST_ASK: Final[str] = "must_ask"
AUTONOMY_CANNOT: Final[str] = "cannot"

# ---- conscience_rules[role] sub-buckets (v1) ----------------------------
CONSCIENCE_FORBIDDEN: Final[str] = "forbidden"
CONSCIENCE_MUST_ASK: Final[str] = "must_ask"
CONSCIENCE_SOFT_WARN: Final[str] = "soft_warn"  # M14.E1.I2
CONSCIENCE_TIER_FLOOR: Final[str] = "tier_floor"
CONSCIENCE_RISK_OVERRIDES: Final[str] = "risk_overrides"

# ---- consent posture audience keys --------------------------------------
CONSENT_AUDIENCE_FAMILY: Final[str] = "family"


def get_visibility_keys(
    body: Mapping[str, Any],
    *,
    viewer_role: str,
    target_role: str,
) -> tuple[str, ...]:
    """Allowed attribute keys for ``viewer_role`` to see on ``target_role``.

    Default-deny: returns ``()`` whenever the key path is missing or the
    stored value is not iterable. NEVER returns a wildcard.
    """
    rules = body.get(VISIBILITY_RULES)
    if not isinstance(rules, Mapping):
        return ()
    by_viewer = rules.get(viewer_role)
    if not isinstance(by_viewer, Mapping):
        return ()
    raw = by_viewer.get(target_role)
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        return ()
    return tuple(str(k) for k in raw)


def get_autonomy_bucket(
    body: Mapping[str, Any],
    *,
    role: str,
    bucket: str,
) -> tuple[str, ...]:
    """Return the autonomy list (``can``/``must_ask``/``cannot``) for a role.

    Default-empty: missing role or missing bucket → ``()``. Caller is
    responsible for treating absence as deny.
    """
    rules = body.get(AUTONOMY_RULES)
    if not isinstance(rules, Mapping):
        return ()
    by_role = rules.get(role)
    if not isinstance(by_role, Mapping):
        return ()
    raw = by_role.get(bucket)
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        return ()
    return tuple(str(t) for t in raw)


def get_authority_tier(body: Mapping[str, Any], *, tool_id: str) -> int:
    """Required identity tier (0..3) for ``tool_id``; default ``0``."""
    rules = body.get(AUTHORITY_RULES)
    if not isinstance(rules, Mapping):
        return 0
    raw = rules.get(tool_id)
    if not isinstance(raw, int) or isinstance(raw, bool):
        return 0
    if raw < 0:
        return 0
    if raw > 3:
        return 3
    return raw


def get_protection_rules(body: Mapping[str, Any], *, situation_kind: str) -> tuple[str, ...]:
    """Protection rule_ids attached to ``situation_kind``; ``()`` if none."""
    rules = body.get(PROTECTION_RULES)
    if not isinstance(rules, Mapping):
        return ()
    raw = rules.get(situation_kind)
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        return ()
    return tuple(str(r) for r in raw)


# ---------------------------------------------------------------------
# v0/v1 schema dispatch + conscience bucket
# ---------------------------------------------------------------------
def is_v1_schema(body: Mapping[str, Any]) -> bool:
    """True if ``body`` uses the v1 (conscience-first) schema."""
    if not isinstance(body, Mapping):
        return False
    if isinstance(body.get(SCHEMA_VERSION), int) and int(body[SCHEMA_VERSION]) >= 1:
        return True
    # Fallback heuristic: presence of conscience_rules implies v1.
    return isinstance(body.get(CONSCIENCE_RULES), Mapping)


def get_conscience_bucket(
    body: Mapping[str, Any],
    *,
    role: str,
    situation_kind: str = "",
) -> ConscienceBucket:
    """Resolve a unified ``ConscienceBucket`` from either schema.

    * **v1**: read directly from ``conscience_rules[role]``.
    * **v0** (legacy): derive from ``autonomy_rules[role]`` —
      ``forbidden = cannot``, ``must_ask = must_ask``;
      ``tier_floor`` from ``authority_rules`` for any tool present in
      either bucket.

    Default-empty: an unknown role returns an empty bucket. Used by
    the composer to populate ``SituationFrame.conscience``.
    """
    if not isinstance(body, Mapping) or not role:
        return ConscienceBucket()

    if is_v1_schema(body):
        return _read_v1_bucket(body, role)
    return _derive_v0_bucket(body, role)


def _read_v1_bucket(body: Mapping[str, Any], role: str) -> ConscienceBucket:
    rules = body.get(CONSCIENCE_RULES)
    if not isinstance(rules, Mapping):
        return ConscienceBucket()
    by_role = rules.get(role)
    if not isinstance(by_role, Mapping):
        return ConscienceBucket()

    forbidden = _coerce_str_tuple(by_role.get(CONSCIENCE_FORBIDDEN))
    must_ask = _coerce_str_tuple(by_role.get(CONSCIENCE_MUST_ASK))
    soft_warn = _coerce_str_tuple(by_role.get(CONSCIENCE_SOFT_WARN))  # M14.E1.I2
    tier_floor = _coerce_int_dict(by_role.get(CONSCIENCE_TIER_FLOOR))
    risk_overrides = _coerce_str_dict(by_role.get(CONSCIENCE_RISK_OVERRIDES))
    return ConscienceBucket(
        forbidden=forbidden,
        must_ask=must_ask,
        soft_warn=soft_warn,
        risk_overrides=risk_overrides,
        tier_floor=tier_floor,
    )


def _derive_v0_bucket(body: Mapping[str, Any], role: str) -> ConscienceBucket:
    forbidden = get_autonomy_bucket(body, role=role, bucket=AUTONOMY_CANNOT)
    must_ask = get_autonomy_bucket(body, role=role, bucket=AUTONOMY_MUST_ASK)
    can = get_autonomy_bucket(body, role=role, bucket=AUTONOMY_CAN)
    tier_floor: dict[str, int] = {}
    for tool_id in (*forbidden, *must_ask, *can):
        tier = get_authority_tier(body, tool_id=tool_id)
        if tier > 0:
            tier_floor[tool_id] = tier
    return ConscienceBucket(
        forbidden=forbidden,
        must_ask=must_ask,
        risk_overrides={},
        tier_floor=tier_floor,
    )


def _coerce_str_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(v) for v in value if v is not None)


def _coerce_int_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, int] = {}
    for k, v in value.items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def _coerce_str_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(k): str(v) for k, v in value.items()}
