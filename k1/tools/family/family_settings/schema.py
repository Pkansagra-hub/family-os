"""k1.tools.family.family_settings.schema -- Family Settings entity types.

Two entities:

* :class:`VisibilityPolicyDoc` -- singleton per ``space_id``.  Persists
  the declarative rule overrides (source→band mapping), the active
  sensitive-keyword list, and per-kid capability gates.  On write, the
  service rebuilds the live ``VisibilityPolicy`` object shared by every
  family-tool adapter.

* :class:`FamilyFeatureFlag` -- named boolean flag scoped to a space (or
  optionally to a specific member).  Used by the manifest layer to show or
  hide individual actions for particular roles.

Design notes
------------
* ``VisibilityPolicyDoc`` is a true ``BaseEntity`` so it gets the full
  audit trail (actor, version, updated_at, deleted_at).  The service
  enforces the one-per-space singleton invariant at write time, not via
  a DB UNIQUE constraint, to allow soft-deletion round-trips.
* ``rules`` stores a declarative JSON dict whose keys map to known
  visibility rule names (``google_work``, ``outlook_default``, …) and
  whose values are valid ``Visibility`` bands.  Unknown keys are rejected
  by the service before writing.
* Both models are ``extra="forbid"`` and ``frozen=True`` per the M15
  convention.  Mutations go through ``model_copy(update=...)``.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from k1.tools.family.base import BaseEntity

# ---------------------------------------------------------------------------
# VisibilityPolicyDoc
# ---------------------------------------------------------------------------


class VisibilityPolicyDoc(BaseEntity):
    """Persisted representation of the space's custom visibility policy.

    Attributes
    ----------
    rules:
        Declarative source→visibility-band overrides applied **before**
        the hard-coded defaults.  Example::

            {"google_work": "adults", "outlook_default": "adults",
             "classroom": "family"}

        Only keys in ``KNOWN_RULE_KEYS`` are accepted.
    sensitive_keywords:
        Whitespace-free keyword strings that trigger the ``adults``
        visibility floor when found in entity tags or metadata.
        Replaces the module-level default set.
    kid_capabilities:
        Map of capability gate names to booleans.  The manifest layer
        reads this to filter which actions appear in the child-role UI.
        Example::

            {"can_create_reminders": False, "can_see_chores": True}
    """

    rules: dict[str, str] = Field(default_factory=dict)
    sensitive_keywords: list[str] = Field(default_factory=list)
    kid_capabilities: dict[str, bool] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# FamilyFeatureFlag
# ---------------------------------------------------------------------------


class FamilyFeatureFlag(BaseEntity):
    """A named boolean feature flag for a space (or a specific member).

    Attributes
    ----------
    flag_name:
        Machine-readable identifier, e.g. ``"health.dose_log_visible_to_kids"``.
    enabled:
        Current state.
    description:
        Human-readable label shown in the Settings UI.
    scope:
        ``"space"`` means all members; ``"member"`` means only
        ``target_member_id``.
    target_member_id:
        Set when ``scope == "member"``; ignored otherwise.
    """

    flag_name: str = Field(min_length=1, max_length=120)
    enabled: bool = False
    description: str = Field(default="", max_length=255)
    scope: str = Field(default="space", pattern=r"^(space|member)$")
    target_member_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Known rule keys (used by service for validation)
# ---------------------------------------------------------------------------

KNOWN_RULE_KEYS: frozenset[str] = frozenset(
    {
        "google_work",
        "google_personal",
        "outlook_default",
        "classroom",
        "native_default",
        "sensitive_keywords",
    }
)
