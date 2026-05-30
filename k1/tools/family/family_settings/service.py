"""k1.tools.family.family_settings.service -- ``FamilySettingsService``.

Implements the 4 Family Settings adapter actions:

1. ``get_visibility_policy``    -- return (auto-seeding) the policy doc.
2. ``update_visibility_policy`` -- persist new policy doc AND mutate the
   live ``VisibilityPolicy`` in-place so every adapter sees it immediately.
3. ``list_feature_flags``       -- return all active flags for the space.
4. ``set_feature_flag``         -- upsert a flag, emit SSE.

Live policy reload design
-------------------------
All family-tool service instances are constructed by :class:`ToolRegistry`
which passes them the *same* ``VisibilityPolicy`` object.  Because
``VisibilityPolicy`` is a mutable dataclass (not frozen), mutating its
fields here propagates immediately to every service that holds a reference
— no restart, no message bus round-trip.

``update_visibility_policy`` rewrites:
* ``self._policy.rules``            -- rebuilt from declarative ``rules`` dict.
* ``self._policy.sensitive_keywords`` -- replaced with the new keyword set.

The rule reconstruction order follows the fixed default order in
``DEFAULT_RULES``; custom overrides for individual source keys **replace**
the visibility returned by that rule's closure.  Unmentioned rules are
preserved unchanged.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar, Optional

from k1.tools.family.acl import filter_rows
from k1.tools.family.base import BaseEntity, WriteContext
from k1.tools.family.base_service import BaseToolService
from k1.tools.family.family_settings.definition import FAMILY_SETTINGS_DEFINITION
from k1.tools.family.family_settings.schema import (
    KNOWN_RULE_KEYS,
    FamilyFeatureFlag,
    VisibilityPolicyDoc,
)
from k1.tools.family.policy import (
    SENSITIVE_KEYWORDS_RULE_INDEX,
    VisibilityRule,
    _classroom_default,
    _google_personal,
    _google_work,
    _native_default,
    _outlook_default,
    make_sensitive_keywords_rule,
)

logger = logging.getLogger(__name__)

# JSON-encoded columns that must be round-tripped via json.loads / json.dumps.
_JSON_COLS = ("named_visible", "tags", "metadata")


def _new_id() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ui_interaction_metadata(params: dict[str, Any]) -> dict[str, Any]:
    source = str(params.get("interaction_source") or "").strip()
    if not source:
        return {}
    kind = str(params.get("interaction_kind") or "").strip()
    stamp: dict[str, Any] = {"at": _now_iso(), "source": source}
    if kind:
        stamp["kind"] = kind
    for key in ("target", "preset", "previous", "next"):
        value = params.get(f"interaction_{key}")
        if value is not None:
            stamp[key] = value
    return {"_last_ui_interaction": stamp}


def _metadata_updates(params: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if isinstance(params.get("metadata"), dict):
        updates.update(params["metadata"])
    updates.update(_ui_interaction_metadata(params))
    return updates


def _merged_metadata(existing: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    updates = _metadata_updates(params)
    if not updates:
        return dict(existing)
    merged = dict(existing)
    merged.update(updates)
    return merged


# ---------------------------------------------------------------------------
# Rule key → default callable (order determines evaluation priority)
# ---------------------------------------------------------------------------

# Mapping from the declarative rule key stored in VisibilityPolicyDoc.rules to
# the base callable that produced it.  When a key appears in the doc, we
# override the returned band via a wrapping closure rather than replacing the
# callable entirely, so rule identity (index) stays stable.
_RULE_BASE_CALLABLES: dict[str, VisibilityRule] = {
    "google_work": _google_work,
    "google_personal": _google_personal,
    "outlook_default": _outlook_default,
    "classroom": _classroom_default,
    "native_default": _native_default,
}

# Order to rebuild the rules list (sensitive_keywords is always index 0).
_RULE_ORDER: list[str] = [
    "google_work",
    "google_personal",
    "outlook_default",
    "classroom",
    "native_default",
]

_VALID_BANDS = frozenset({"family", "adults", "named", "private"})


def _make_override_rule(key: str, band: str) -> VisibilityRule:
    """Return a visibility rule that pins ``key``-matched entities to ``band``."""

    def _rule(entity: BaseEntity, role) -> Optional[str]:
        if _matches_rule_key(key, entity):
            return band
        return None

    return _rule


def _matches_rule_key(key: str, entity: BaseEntity) -> bool:
    if key == "google_work":
        return entity.source == "google" and entity.source_label == "work"
    if key == "google_personal":
        return entity.source == "google" and entity.source_label == "personal"
    if key == "outlook_default":
        return entity.source == "outlook"
    if key == "classroom":
        return entity.source == "classroom"
    if key == "native_default":
        return entity.source == "native"
    return False


# ---------------------------------------------------------------------------
# FamilySettingsService
# ---------------------------------------------------------------------------


class FamilySettingsService(BaseToolService):
    """Family Settings adapter — visibility policy editor."""

    DEFINITION: ClassVar = FAMILY_SETTINGS_DEFINITION
    ENTITY_CLASSES: ClassVar[dict[str, type[BaseEntity]]] = {
        "visibility_policy_doc": VisibilityPolicyDoc,
        "family_feature_flag": FamilyFeatureFlag,
    }

    # ------------------------------------------------------------------ #
    # Action handlers
    # ------------------------------------------------------------------ #

    async def get_visibility_policy(
        self, params: dict[str, Any], ctx: WriteContext
    ) -> dict[str, Any]:
        doc = self._load_policy_doc(ctx.space_id)
        if doc is None:
            doc = self._seed_default_doc(ctx)
        rows = filter_rows([doc.model_dump(mode="json")], ctx, self._policy)
        if not rows:
            return {"success": True, "policy": None}
        return {"success": True, "policy": rows[0]}

    async def update_visibility_policy(
        self, params: dict[str, Any], ctx: WriteContext
    ) -> dict[str, Any]:
        action = self._spec("update_visibility_policy")

        rules_override: dict[str, str] = params.get("rules") or {}
        kw_list: Optional[list[str]] = params.get("sensitive_keywords")
        kid_caps: dict[str, bool] = params.get("kid_capabilities") or {}

        # Validate rule keys and band values.
        bad_keys = set(rules_override) - KNOWN_RULE_KEYS - {"sensitive_keywords"}
        if bad_keys:
            raise ValueError(f"unknown rule keys: {sorted(bad_keys)}")
        bad_bands = {k: v for k, v in rules_override.items() if v not in _VALID_BANDS}
        if bad_bands:
            raise ValueError(f"invalid visibility bands: {bad_bands}")

        # Resolve keyword set.
        if kw_list is not None:
            new_keywords: frozenset[str] = frozenset(str(k) for k in kw_list if k)
        else:
            new_keywords = self._policy.sensitive_keywords

        # Load or create the existing policy doc.
        existing = self._load_policy_doc(ctx.space_id)

        if existing is None:
            # First-ever update: create at version 1 directly (no seed→bump round-trip).
            doc = VisibilityPolicyDoc(
                id=_new_id(),
                space_id=ctx.space_id,
                actor=ctx.user_id,
                visibility="private",
                metadata=_metadata_updates(params),
                rules=dict(rules_override),
                sensitive_keywords=list(new_keywords),
                kid_capabilities=dict(kid_caps),
            )
        else:
            # Merge updates into doc (rule overrides replace; kid_caps merge).
            merged_rules = dict(existing.rules)
            merged_rules.update(rules_override)
            merged_caps = dict(existing.kid_capabilities)
            merged_caps.update(kid_caps)
            merged_kws = list(new_keywords)

            doc = existing.model_copy(
                update={
                    "rules": merged_rules,
                    "sensitive_keywords": merged_kws,
                    "kid_capabilities": merged_caps,
                    "metadata": _merged_metadata(existing.metadata, params),
                }
            )
            doc = doc.bump(ctx.user_id)
        self._upsert_policy_doc(doc)

        # ---- mutate the live policy in-place --------------------------
        self._apply_policy_doc_to_live(doc, new_keywords)

        self.emit_entity_write("update", doc, ctx, action=action)
        return {
            "success": True,
            "policy_id": doc.id,
            "version": doc.version,
            "applied_rules": list(doc.rules.keys()),
            "sensitive_keyword_count": len(new_keywords),
            "policy": doc.model_dump(mode="json"),
        }

    async def list_feature_flags(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        rows = self._scan_flags(ctx.space_id)
        visible = filter_rows(rows, ctx, self._policy)
        return {"success": True, "flags": visible}

    async def set_feature_flag(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("set_feature_flag")

        flag_name = params.get("flag_name")
        if not flag_name:
            raise ValueError("set_feature_flag requires flag_name")
        enabled = bool(params["enabled"])
        scope = params.get("scope", "space")
        target = params.get("target_member_id")

        existing = self._load_flag(ctx.space_id, flag_name)
        if existing is None:
            flag = FamilyFeatureFlag(
                id=_new_id(),
                space_id=ctx.space_id,
                actor=ctx.user_id,
                metadata=_metadata_updates(params),
                flag_name=flag_name,
                enabled=enabled,
                description=params.get("description", ""),
                scope=scope,
                target_member_id=target,
            )
        else:
            updates: dict[str, Any] = {"enabled": enabled}
            if "description" in params and params["description"] is not None:
                updates["description"] = params["description"]
            if "scope" in params and params["scope"] is not None:
                updates["scope"] = params["scope"]
            if "target_member_id" in params and params["target_member_id"] is not None:
                updates["target_member_id"] = params["target_member_id"]
            metadata = _merged_metadata(existing.metadata, params)
            if metadata != existing.metadata:
                updates["metadata"] = metadata
            flag = existing.model_copy(update=updates).bump(ctx.user_id)

        self._upsert_flag(flag)
        self.emit_entity_write("upsert", flag, ctx, action=action)
        return {
            "success": True,
            "flag_id": flag.id,
            "flag_name": flag.flag_name,
            "enabled": flag.enabled,
            "flag": flag.model_dump(mode="json"),
        }

    # ------------------------------------------------------------------ #
    # Live policy mutation
    # ------------------------------------------------------------------ #

    def _apply_policy_doc_to_live(self, doc: VisibilityPolicyDoc, new_keywords: frozenset) -> None:
        """Mutate ``self._policy`` in-place from the persisted doc.

        Steps:
        1. Replace rules[SENSITIVE_KEYWORDS_RULE_INDEX] with a fresh
           closure over ``new_keywords``.
        2. For each overridden rule key in ``doc.rules``, replace the
           matching entry in the rules list with an override closure that
           pins the band.
        """
        policy = self._policy

        # Rebuild the mutable rules list preserving length and index.
        # Start from a fresh copy of DEFAULT_RULES so stale overrides
        # from previous calls don't accumulate.
        from k1.tools.family.policy import DEFAULT_RULES

        policy.rules[:] = list(DEFAULT_RULES)

        # Slot 0: sensitive keywords.
        policy.rules[SENSITIVE_KEYWORDS_RULE_INDEX] = make_sensitive_keywords_rule(new_keywords)
        policy.sensitive_keywords = new_keywords

        # Slots 1-N: source overrides from doc.rules.
        for key, band in doc.rules.items():
            if key == "sensitive_keywords":
                continue  # handled above
            if key not in _RULE_ORDER:
                continue  # unknown key (already validated upstream)
            # Find the index in the current rules list that corresponds to
            # this key by comparing identity to the base callable.
            base = _RULE_BASE_CALLABLES[key]
            for idx, rule in enumerate(policy.rules):
                if rule is base:
                    policy.rules[idx] = _make_override_rule(key, band)
                    break

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _spec(self, name: str):
        spec = self.DEFINITION.find_action(name)
        if spec is None:  # pragma: no cover
            raise RuntimeError(f"FamilySettingsService missing ActionSpec {name!r}")
        return spec

    def _seed_default_doc(self, ctx: WriteContext) -> VisibilityPolicyDoc:
        """Create and persist a default policy doc for the space."""
        doc = VisibilityPolicyDoc(
            id=_new_id(),
            space_id=ctx.space_id,
            actor=ctx.user_id,
            visibility="private",
            rules={},
            sensitive_keywords=[],
            kid_capabilities={},
        )
        self._upsert_policy_doc(doc)
        return doc

    # ---- visibility_policy_docs I/O ------------------------------------ #

    def _upsert_policy_doc(self, doc: VisibilityPolicyDoc) -> None:
        data = doc.model_dump(mode="json")
        cols = [
            "id",
            "space_id",
            "actor",
            "source",
            "source_label",
            "visibility",
            "named_visible",
            "version",
            "created_at",
            "updated_at",
            "deleted_at",
            "tags",
            "metadata",
            "rules",
            "sensitive_keywords",
            "kid_capabilities",
        ]
        values = [
            data["id"],
            data["space_id"],
            data["actor"],
            data["source"],
            data["source_label"],
            data["visibility"],
            json.dumps(data["named_visible"]),
            data["version"],
            data["created_at"],
            data["updated_at"],
            data.get("deleted_at"),
            json.dumps(data["tags"]),
            json.dumps(data["metadata"]),
            json.dumps(data["rules"]),
            json.dumps(data["sensitive_keywords"]),
            json.dumps(data["kid_capabilities"]),
        ]
        ph = ",".join("?" for _ in cols)
        sql = f"INSERT OR REPLACE INTO visibility_policy_docs " f"({','.join(cols)}) VALUES ({ph})"
        with self._conn:
            self._conn.execute(sql, values)

    def _load_policy_doc(self, space_id: str) -> Optional[VisibilityPolicyDoc]:
        cur = self._conn.execute(
            "SELECT * FROM visibility_policy_docs "
            "WHERE space_id=? AND deleted_at IS NULL "
            "ORDER BY version DESC LIMIT 1",
            (space_id,),
        )
        raw = cur.fetchone()
        if raw is None:
            return None
        row = _decode_policy_row(dict(raw))
        return VisibilityPolicyDoc(**row)

    # ---- feature_flags I/O -------------------------------------------- #

    def _upsert_flag(self, flag: FamilyFeatureFlag) -> None:
        data = flag.model_dump(mode="json")
        cols = [
            "id",
            "space_id",
            "actor",
            "source",
            "source_label",
            "visibility",
            "named_visible",
            "version",
            "created_at",
            "updated_at",
            "deleted_at",
            "tags",
            "metadata",
            "flag_name",
            "enabled",
            "description",
            "scope",
            "target_member_id",
        ]
        values = [
            data["id"],
            data["space_id"],
            data["actor"],
            data["source"],
            data["source_label"],
            data["visibility"],
            json.dumps(data["named_visible"]),
            data["version"],
            data["created_at"],
            data["updated_at"],
            data.get("deleted_at"),
            json.dumps(data["tags"]),
            json.dumps(data["metadata"]),
            data["flag_name"],
            1 if data["enabled"] else 0,
            data.get("description", ""),
            data.get("scope", "space"),
            data.get("target_member_id"),
        ]
        ph = ",".join("?" for _ in cols)
        sql = f"INSERT OR REPLACE INTO feature_flags " f"({','.join(cols)}) VALUES ({ph})"
        with self._conn:
            self._conn.execute(sql, values)

    def _load_flag(self, space_id: str, flag_name: str) -> Optional[FamilyFeatureFlag]:
        cur = self._conn.execute(
            "SELECT * FROM feature_flags "
            "WHERE space_id=? AND flag_name=? AND deleted_at IS NULL "
            "LIMIT 1",
            (space_id, flag_name),
        )
        raw = cur.fetchone()
        if raw is None:
            return None
        row = _decode_flag_row(dict(raw))
        return FamilyFeatureFlag(**row)

    def _scan_flags(self, space_id: str) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM feature_flags WHERE space_id=? AND deleted_at IS NULL",
            (space_id,),
        )
        return [_decode_flag_row(dict(r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Row decoders
# ---------------------------------------------------------------------------


def _decode_policy_row(row: dict[str, Any]) -> dict[str, Any]:
    for col in ("named_visible", "tags", "metadata"):
        if isinstance(row.get(col), str):
            row[col] = json.loads(row[col])
    for col in ("rules", "sensitive_keywords", "kid_capabilities"):
        if isinstance(row.get(col), str):
            row[col] = json.loads(row[col])
    return row


def _decode_flag_row(row: dict[str, Any]) -> dict[str, Any]:
    for col in ("named_visible", "tags", "metadata"):
        if isinstance(row.get(col), str):
            row[col] = json.loads(row[col])
    row["enabled"] = bool(row.get("enabled", 0))
    return row
