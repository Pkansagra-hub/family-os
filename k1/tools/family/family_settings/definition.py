"""k1.tools.family.family_settings.definition -- declarative spec for the Family Settings adapter.

Exposes :data:`FAMILY_SETTINGS_DEFINITION`, the single source of truth consumed by:

* :func:`k1.fabric.manifest_translator.register_definition`
* :func:`k1.tools.family.manifest.ui_manifest`
* :class:`FamilySettingsService`

4 actions
---------
Policy:
  1. ``get_visibility_policy``    read   GREEN  (parent+ only)
    2. ``update_visibility_policy`` write  GREEN  (parent+ only)

Flags:
  3. ``list_feature_flags``       read   GREEN  (parent+ only)
    4. ``set_feature_flag``         write  GREEN  (parent+ only)

All actions are restricted to ``parent`` and ``system`` roles.  Children,
elders, and guests have no face into this adapter.
"""

from __future__ import annotations

import os

from k1.tools.family.definition import (
    ActionSpec,
    FieldSpec,
    LLMHints,
    SSESpec,
    ToolDefinition,
)

_HERE = os.path.dirname(__file__)
with open(os.path.join(_HERE, "tables.sql"), encoding="utf-8") as _f:
    _FAMILY_SETTINGS_DDL: str = _f.read()

# ---------------------------------------------------------------------------
# Shared role lists
# ---------------------------------------------------------------------------

_PARENT_PLUS = ["parent", "system"]

# ---------------------------------------------------------------------------
# FAMILY_SETTINGS_DEFINITION
# ---------------------------------------------------------------------------

FAMILY_SETTINGS_DEFINITION = ToolDefinition(
    adapter_id="family_settings",
    version="1.0.0",
    category="configuration",
    summary=(
        "Parent-only visibility policy editor — control what each role can "
        "see, tune sensitive-keyword detection, and manage feature flags."
    ),
    title="Family Settings",
    icon="tune",
    description=(
        "FamilyOS native settings panel.  Parents configure which visibility "
        "bands each role may access, override per-source defaults "
        "(e.g. mark Outlook imports as adults-only), manage the sensitive-"
        "keyword list that auto-tightens medical and financial content, and "
        "toggle per-space feature flags.  Changes to the visibility policy "
        "take effect immediately across all running family-tool adapters — "
        "no restart required."
    ),
    tables_sql=_FAMILY_SETTINGS_DDL,
    actions=[
        # ── Visibility policy ────────────────────────────────────────────
        ActionSpec(
            name="get_visibility_policy",
            kind="read",
            summary="Return the current space visibility policy document.",
            min_band="GREEN",
            allowed_roles=_PARENT_PLUS,
            params=[],
            llm=LLMHints(
                use_when=[
                    "user asks what content their kids or elders can see",
                    "user wants to review current policy before making changes",
                ],
                avoid_when=["user wants to change the policy — use update_visibility_policy"],
                examples=["what's our current visibility policy?"],
            ),
        ),
        ActionSpec(
            name="update_visibility_policy",
            kind="write",
            summary="Replace the space visibility policy and reload all adapters immediately.",
            min_band="GREEN",
            allowed_roles=_PARENT_PLUS,
            sse=SSESpec(
                emits=["family.family_settings.update_visibility_policy.write.v1"],
                redact_fields=[],
            ),
            params=[
                FieldSpec(
                    name="rules",
                    type="object",
                    required=False,
                    description=(
                        "Source-to-visibility-band overrides.  Keys must be one of: "
                        "``google_work``, ``google_personal``, ``outlook_default``, "
                        "``classroom``, ``native_default``.  Values must be a valid "
                        "visibility band: ``family`` | ``adults`` | ``named`` | ``private``."
                    ),
                ),
                FieldSpec(
                    name="sensitive_keywords",
                    type="array",
                    required=False,
                    description=(
                        "Replacement list of keywords that trigger the ``adults`` "
                        "visibility floor.  Replaces the current list entirely."
                    ),
                ),
                FieldSpec(
                    name="kid_capabilities",
                    type="object",
                    required=False,
                    description=(
                        "Map of capability gate names to booleans, e.g. "
                        '``{\\"can_create_reminders\\": false}``.'
                    ),
                ),
            ],
            llm=LLMHints(
                use_when=[
                    "parent wants to hide work calendar from children",
                    "parent wants to add a sensitive keyword to the detection list",
                    "parent wants to change who can see which content",
                ],
                avoid_when=["user only wants to view the policy — use get_visibility_policy"],
                examples=[
                    "make our Google work calendar adults-only",
                    "add 'insurance' to sensitive keywords",
                ],
            ),
        ),
        # ── Feature flags ────────────────────────────────────────────────
        ActionSpec(
            name="list_feature_flags",
            kind="read",
            summary="Return all feature flags for this space.",
            min_band="GREEN",
            allowed_roles=_PARENT_PLUS,
            params=[],
            llm=LLMHints(
                use_when=["user wants to see which features are on or off"],
                avoid_when=["user wants to change a flag — use set_feature_flag"],
                examples=["list our feature flags"],
            ),
        ),
        ActionSpec(
            name="set_feature_flag",
            kind="write",
            summary="Enable or disable a named feature flag for this space.",
            min_band="GREEN",
            allowed_roles=_PARENT_PLUS,
            sse=SSESpec(
                emits=["family.family_settings.set_feature_flag.write.v1"],
                redact_fields=[],
            ),
            params=[
                FieldSpec(
                    name="flag_name",
                    type="string",
                    required=True,
                    description="Machine-readable flag identifier.",
                ),
                FieldSpec(
                    name="enabled",
                    type="boolean",
                    required=True,
                    description="New state for the flag.",
                ),
                FieldSpec(
                    name="description",
                    type="string",
                    required=False,
                    description="Human-readable label (optional; preserved if omitted).",
                ),
                FieldSpec(
                    name="scope",
                    type="string",
                    required=False,
                    description="``space`` (default) or ``member``.",
                ),
                FieldSpec(
                    name="target_member_id",
                    type="string",
                    required=False,
                    description=(
                        "Family member reference when scope is ``member``, e.g. Riley or riley. "
                        "Do not ask the user for member IDs."
                    ),
                ),
            ],
            llm=LLMHints(
                use_when=["parent wants to enable or disable a specific feature"],
                avoid_when=["user wants to list flags — use list_feature_flags"],
                examples=["disable health.dose_log_visible_to_kids"],
            ),
        ),
    ],
)
