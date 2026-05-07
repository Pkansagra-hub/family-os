"""SemVer + breaking-change classification for manifest revisions.

Lifted (slim) from ``k0/automation/contract_compatibility_checker.py``.
The MS-2.5 surface is intentionally narrow: classify a *manifest-vs-manifest*
diff as ``BREAKING``, ``COMPATIBLE``, or ``PATCH`` and verify the SemVer
bump matches per ADR-0013.

Full schema-level breakage detection (field removal, type change, enum
contraction in payload schemas) lands in MS-3a alongside the first migrated
contract. This module ships now so the framework is in place.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ChangeType(str, Enum):
    BREAKING = "breaking"
    COMPATIBLE = "compatible"
    PATCH = "patch"


@dataclass(frozen=True)
class SchemaChange:
    change_type: ChangeType
    path: str
    old_value: Any
    new_value: Any
    description: str


@dataclass(frozen=True)
class CompatibilityCheckResult:
    topic: str
    old_version: str
    new_version: str
    changes: tuple[SchemaChange, ...]
    is_breaking: bool
    semver_valid: bool
    issues: tuple[str, ...]


def parse_semver(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"invalid semver: {version!r}")
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError as exc:
        raise ValueError(f"invalid semver: {version!r}") from exc


# ---------------------------------------------------------------------------
# Manifest-level diff (intentional MVP scope for MS-2.5).
# ---------------------------------------------------------------------------

# Top-level keys whose change is BREAKING regardless of value.
_BREAKING_KEYS = ("topic", "direction", "schema")


def classify_manifest_change(old: dict[str, Any], new: dict[str, Any]) -> list[SchemaChange]:
    """Diff two parsed manifests and emit a list of changes."""
    changes: list[SchemaChange] = []
    for key in _BREAKING_KEYS:
        if old.get(key) != new.get(key):
            changes.append(
                SchemaChange(
                    change_type=ChangeType.BREAKING,
                    path=key,
                    old_value=old.get(key),
                    new_value=new.get(key),
                    description=f"top-level {key} changed",
                )
            )

    # delivery.transport / ordering / online_required swaps are breaking.
    old_delivery = old.get("delivery", {}) or {}
    new_delivery = new.get("delivery", {}) or {}
    for k in ("transport", "ordering", "online_required", "endpoint_class"):
        if old_delivery.get(k) != new_delivery.get(k):
            changes.append(
                SchemaChange(
                    change_type=ChangeType.BREAKING,
                    path=f"delivery.{k}",
                    old_value=old_delivery.get(k),
                    new_value=new_delivery.get(k),
                    description=f"delivery.{k} changed",
                )
            )

    # status: active -> deprecated is COMPATIBLE; active -> deferred is BREAKING.
    if old.get("status") != new.get("status"):
        ct = ChangeType.COMPATIBLE
        if new.get("status") in {"deferred"}:
            ct = ChangeType.BREAKING
        changes.append(
            SchemaChange(
                change_type=ct,
                path="status",
                old_value=old.get("status"),
                new_value=new.get("status"),
                description="status changed",
            )
        )

    # SLA tightening (lower latency budget) is BREAKING for producers.
    old_sla = old.get("sla", {}) or {}
    new_sla = new.get("sla", {}) or {}
    if (
        "latency_p99_ms" in old_sla
        and "latency_p99_ms" in new_sla
        and new_sla["latency_p99_ms"] < old_sla["latency_p99_ms"]
    ):
        changes.append(
            SchemaChange(
                change_type=ChangeType.BREAKING,
                path="sla.latency_p99_ms",
                old_value=old_sla["latency_p99_ms"],
                new_value=new_sla["latency_p99_ms"],
                description="latency budget tightened",
            )
        )

    if not changes:
        # Pure metadata/cosmetic edits — patch.
        if old != new:
            changes.append(
                SchemaChange(
                    change_type=ChangeType.PATCH,
                    path="<metadata>",
                    old_value=None,
                    new_value=None,
                    description="cosmetic / non-structural change",
                )
            )
    return changes


def check_compatibility(old: dict[str, Any], new: dict[str, Any]) -> CompatibilityCheckResult:
    """Compare two parsed manifests and classify per ADR-0013."""
    issues: list[str] = []
    changes = classify_manifest_change(old, new)
    is_breaking = any(c.change_type == ChangeType.BREAKING for c in changes)

    old_v = old.get("versioning", {}).get("semver", "0.0.0")
    new_v = new.get("versioning", {}).get("semver", "0.0.0")
    try:
        old_major, old_minor, old_patch = parse_semver(old_v)
        new_major, new_minor, new_patch = parse_semver(new_v)
    except ValueError as exc:
        issues.append(str(exc))
        return CompatibilityCheckResult(
            topic=new.get("topic", "<unknown>"),
            old_version=old_v,
            new_version=new_v,
            changes=tuple(changes),
            is_breaking=is_breaking,
            semver_valid=False,
            issues=tuple(issues),
        )

    semver_valid = True
    if is_breaking:
        if new_major <= old_major:
            issues.append(f"breaking change requires major bump: {old_v} -> {new_v}")
            semver_valid = False
    elif any(c.change_type == ChangeType.COMPATIBLE for c in changes):
        if (new_major, new_minor) <= (old_major, old_minor):
            issues.append(f"compatible change requires minor bump: {old_v} -> {new_v}")
            semver_valid = False
    else:
        if (new_major, new_minor, new_patch) <= (old_major, old_minor, old_patch):
            issues.append(f"patch change requires patch bump: {old_v} -> {new_v}")
            semver_valid = False

    return CompatibilityCheckResult(
        topic=new.get("topic", "<unknown>"),
        old_version=old_v,
        new_version=new_v,
        changes=tuple(changes),
        is_breaking=is_breaking,
        semver_valid=semver_valid,
        issues=tuple(issues),
    )
