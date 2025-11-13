"""Policy stamp handling for V1.3 (Policy Decision Propagation).

Policy stamps are attached to envelopes after PEP (Policy Enforcement Point)
evaluation and propagate through the entire pipeline to enable:
  1. Auditable proof of which policy version + obligations applied
  2. Complete audit trail in WAL + receipts
  3. Obligation enforcement tracking for compliance
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal


@dataclass
class PolicyStamp:
    """Immutable policy decision stamp (attached post-PEP evaluation)."""

    policy_version: str
    band: Literal["GREEN", "AMBER", "RED"]
    obligations: list[str]
    visible_to: list[str]
    decision: Literal["ALLOW", "DENY", "CONDITIONAL"]
    applied_at: str | None = None

    def __post_init__(self) -> None:
        """Ensure applied_at is set."""
        if self.applied_at is None:
            self.applied_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "policy_version": self.policy_version,
            "band": self.band,
            "obligations": self.obligations,
            "visible_to": self.visible_to,
            "decision": self.decision,
            "applied_at": self.applied_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyStamp:
        """Create from dictionary."""
        return cls(
            policy_version=data["policy_version"],
            band=data["band"],
            obligations=data.get("obligations", []),
            visible_to=data.get("visible_to", []),
            decision=data["decision"],
            applied_at=data.get("applied_at"),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> PolicyStamp:
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


def create_policy_stamp(
    policy_version: str,
    band: Literal["GREEN", "AMBER", "RED"],
    obligations: list[str],
    visible_to: list[str],
    decision: Literal["ALLOW", "DENY", "CONDITIONAL"],
) -> PolicyStamp:
    """Create new policy stamp with current timestamp."""
    return PolicyStamp(
        policy_version=policy_version,
        band=band,
        obligations=obligations,
        visible_to=visible_to,
        decision=decision,
        applied_at=datetime.now(timezone.utc).isoformat(),
    )


def attach_policy_stamp_to_envelope(
    envelope: dict[str, Any],
    policy_stamp: PolicyStamp,
) -> dict[str, Any]:
    """Attach policy stamp to envelope (mutates envelope).

    Returns modified envelope with policy_stamp field set.
    """
    envelope["policy_stamp"] = policy_stamp.to_dict()
    return envelope


def extract_policy_stamp(envelope: dict[str, Any]) -> PolicyStamp | None:
    """Extract policy stamp from envelope if present."""
    policy_stamp_data = envelope.get("policy_stamp")
    if policy_stamp_data is None:
        return None
    return PolicyStamp.from_dict(policy_stamp_data)


__all__ = [
    "PolicyStamp",
    "attach_policy_stamp_to_envelope",
    "create_policy_stamp",
    "extract_policy_stamp",
]
