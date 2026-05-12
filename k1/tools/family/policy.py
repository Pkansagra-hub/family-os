"""
k1.tools.family.policy -- ``VisibilityPolicy`` and default safety-band rules.

The policy module exposes a frozen dataclass (``VisibilityPolicy``) that
captures the per-adapter visibility + band-gating rules and a
``default_policy()`` factory that returns the conservative defaults
every family tool should start from.

Policy evaluation lives in two places:

* ``VisibilityPolicy.check_band/check_role(action, ctx)`` -- gates
  invoked before a side-effecting action is dispatched.

* ``VisibilityPolicy.apply(entity, role) -> Visibility`` -- a rule chain
  that derives the effective visibility for a row based on its source,
  source_label, tags, and metadata.  Falls back to the entity's stored
  ``visibility`` when no rule fires.

* ``k1.tools.family.acl.filter_rows`` -- per-row read filter that
  consumes the same ``VisibilityPolicy`` to decide which records a
  caller may see.

Keeping both gates rooted in one struct guarantees that "you can write
to it but cannot see it" mismatches are detectable in unit tests.

References
----------
* docs/plans/KERNEL_BOOTUP_PLAN.md §E15.0.3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, FrozenSet, List, Optional, Tuple

from k1.tools.family.base import BaseEntity, Role, Visibility, WriteContext
from k1.tools.family.definition import ActionSpec, Band

# ---------------------------------------------------------------------------
# Band ordering
# ---------------------------------------------------------------------------

_BAND_ORDER: tuple[Band, ...] = ("GREEN", "AMBER", "RED", "CRISIS")
_BAND_INDEX: dict[Band, int] = {b: i for i, b in enumerate(_BAND_ORDER)}


def _band_at_or_below(actual: Band, minimum: Band) -> bool:
    """Return True iff ``actual`` is at-or-below ``minimum`` on the band ladder.

    The ``SafetyBand`` ordering runs GREEN (0, calmest) -> CRISIS
    (3, most restrictive).  An action with ``min_band=AMBER`` may run
    when the session band is GREEN or AMBER, but is blocked when the
    session has escalated to RED or CRISIS.
    """

    return _BAND_INDEX[actual] <= _BAND_INDEX[minimum]


# ---------------------------------------------------------------------------
# Default visibility rules
# ---------------------------------------------------------------------------

# A rule receives ``(entity, caller_role)`` and returns either:
#   * an explicit ``Visibility`` band to use for this row, or
#   * ``None`` to defer to the next rule in the chain.
#
# The chain is consulted in order; the first non-None result wins.  When
# every rule defers, ``VisibilityPolicy.apply`` falls back to the
# entity's stored ``visibility`` field.

VisibilityRule = Callable[[BaseEntity, Role], Optional[Visibility]]


_SENSITIVE_KEYWORDS: frozenset[str] = frozenset(
    {
        "doctor",
        "therapy",
        "appointment",
        "medication",
        "prescription",
        "diagnosis",
        "salary",
    }
)


def _native_default(entity: BaseEntity, role: Role) -> Optional[Visibility]:
    """Native records default to whatever the row stored; defer to next rule."""

    if entity.source != "native":
        return None
    # Defer; the fallback in ``apply`` will use ``entity.visibility``.
    return None


def _google_work(entity: BaseEntity, role: Role) -> Optional[Visibility]:
    """Imports from Google with a ``work`` label default to ``adults``."""

    if entity.source == "google" and entity.source_label == "work":
        return "adults"
    return None


def _google_personal(entity: BaseEntity, role: Role) -> Optional[Visibility]:
    """Imports from Google with a ``personal`` label default to the stored band."""

    if entity.source == "google" and entity.source_label == "personal":
        return None
    return None


def _outlook_default(entity: BaseEntity, role: Role) -> Optional[Visibility]:
    """Outlook imports default to ``adults`` unless explicitly tagged ``family``."""

    if entity.source == "outlook":
        if "family" in entity.tags:
            return "family"
        return "adults"
    return None


def _classroom_default(entity: BaseEntity, role: Role) -> Optional[Visibility]:
    """Classroom imports default to ``family`` so kids can see their assignments."""

    if entity.source == "classroom":
        return "family"
    return None


def make_sensitive_keywords_rule(keywords: frozenset) -> VisibilityRule:
    """Factory: return a keyword-tighten rule bound to ``keywords``.

    :func:`FamilySettingsService.update_visibility_policy` calls this
    to hot-swap ``rules[0]`` when the family's keyword list changes.
    """

    def _rule(entity: BaseEntity, role: Role) -> Optional[Visibility]:
        text_blob = " ".join(entity.tags).lower()
        if any(kw in text_blob for kw in keywords):
            return "adults"
        for value in entity.metadata.values():
            if isinstance(value, str) and any(kw in value.lower() for kw in keywords):
                return "adults"
        return None

    return _rule


# Sentinel index so FamilySettingsService can locate the keyword rule by name.
SENSITIVE_KEYWORDS_RULE_INDEX: int = 0

# Default sensitive-keywords rule — created from the module-level keyword set.
_sensitive_keywords: VisibilityRule = make_sensitive_keywords_rule(_SENSITIVE_KEYWORDS)


DEFAULT_RULES: Tuple[VisibilityRule, ...] = (
    _sensitive_keywords,  # Always-on safety floor first (index 0).
    _classroom_default,
    _outlook_default,
    _google_work,
    _google_personal,
    _native_default,
)


# ---------------------------------------------------------------------------
# Role / visibility default tables
# ---------------------------------------------------------------------------

# Which visibility bands each role may read.
_DEFAULT_READ_VISIBILITY: dict[Role, FrozenSet[Visibility]] = {
    "system": frozenset({"family", "adults", "named", "private"}),
    "parent": frozenset({"family", "adults", "named", "private"}),
    "guardian": frozenset({"family", "adults", "named", "private"}),
    "elder": frozenset({"family", "adults", "named"}),
    "child": frozenset({"family", "named"}),
    "guest": frozenset({"family"}),
}


# Roles that may read rows whose ``actor`` field is a different ``member_id``.
_DEFAULT_CROSS_USER: FrozenSet[Role] = frozenset({"system", "parent", "guardian", "elder"})


# ---------------------------------------------------------------------------
# VisibilityPolicy
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class VisibilityPolicy:
    """Per-adapter visibility + band-gating rules.

    The policy is a mutable slotted dataclass (not a Pydantic model)
    because it is constructed once per ``ToolRegistry`` and intentionally
    mutated in-place by ``FamilySettingsService.update_visibility_policy``
    so that every service instance that holds a reference sees the update
    immediately without a restart.  It is never hashed or serialised.
    """

    read_visibility_for_role: dict[Role, FrozenSet[Visibility]] = field(
        default_factory=lambda: dict(_DEFAULT_READ_VISIBILITY)
    )
    cross_user_read_roles: FrozenSet[Role] = field(default_factory=lambda: _DEFAULT_CROSS_USER)
    enforce_band_gates: bool = True
    # Mutable list so FamilySettingsService can splice in new rules at index 0
    # without reconstructing the policy object.  Each VisibilityPolicy gets its
    # own copy via the lambda so mutations are isolated between instances.
    rules: List[VisibilityRule] = field(default_factory=lambda: list(DEFAULT_RULES))
    # Mirrors the keyword set currently active in rules[SENSITIVE_KEYWORDS_RULE_INDEX]
    # for persistence / display purposes.
    sensitive_keywords: frozenset = field(default_factory=lambda: _SENSITIVE_KEYWORDS)

    # ------------------------------------------------------------------ #
    # Read-side decisions
    # ------------------------------------------------------------------ #

    def visible_bands_for(self, role: Role) -> FrozenSet[Visibility]:
        """Return the visibility bands the given role may read."""

        return self.read_visibility_for_role.get(role, frozenset())

    def can_read_cross_user(self, role: Role) -> bool:
        """Return True iff the role may read rows owned by other users."""

        return role in self.cross_user_read_roles

    def apply(self, entity: BaseEntity, role: Role) -> Visibility:
        """Resolve the effective visibility band for ``entity``.

        The configured rule chain is consulted in order; the first
        non-None result wins.  When every rule defers, the entity's
        stored ``visibility`` field is returned unchanged.
        """

        for rule in self.rules:
            verdict = rule(entity, role)
            if verdict is not None:
                return verdict
        return entity.visibility

    # ------------------------------------------------------------------ #
    # Write-side gates
    # ------------------------------------------------------------------ #

    def check_band(self, action: ActionSpec, ctx: WriteContext) -> bool:
        """Return True iff the live caller band is permitted for ``action``.

        When ``enforce_band_gates`` is False the gate is short-circuited
        to True (used in unit fixtures).
        """

        if not self.enforce_band_gates:
            return True
        return _band_at_or_below(ctx.band, action.min_band)

    def check_role(self, action: ActionSpec, ctx: WriteContext) -> bool:
        """Return True iff the caller role is in ``action.allowed_roles``."""

        return ctx.role in action.allowed_roles


# ---------------------------------------------------------------------------
# Default factory
# ---------------------------------------------------------------------------


def default_policy() -> VisibilityPolicy:
    """Return the conservative default policy used by family adapters.

    The returned instance is intentionally mutable so
    ``FamilySettingsService`` can splice rule updates into
    ``policy.rules`` in-place and update ``policy.sensitive_keywords``
    without requiring a kernel restart.
    """

    return VisibilityPolicy()
