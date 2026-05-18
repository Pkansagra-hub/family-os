"""Tests for FamilySettingsService (§E15.6).

Test structure
--------------
* conftest-level fixture ``svc`` yields ``(service, pub, store)``.
* Tests are split by concern:
  - schema  — VisibilityPolicyDoc / FamilyFeatureFlag construction
  - definition — adapter_id, action names, role lists
  - service crud — happy-path CRUD round-trips
  - service acl — role/band gates on all 4 actions
  - live policy reload — update_visibility_policy mutates the shared
    VisibilityPolicy object in-place and every subsequent filter_rows
    call sees the new rule
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.tools.family.acl import filter_rows
from k1.tools.family.base import WriteContext
from k1.tools.family.events import EventEmitter
from k1.tools.family.family_settings.definition import FAMILY_SETTINGS_DEFINITION
from k1.tools.family.family_settings.schema import (
    KNOWN_RULE_KEYS,
    FamilyFeatureFlag,
    VisibilityPolicyDoc,
)
from k1.tools.family.family_settings.service import FamilySettingsService
from k1.tools.family.idem import IdempotencyStore
from k1.tools.family.policy import default_policy
from k1.tools.family.storage import K1FamilyStore
from tests.k1.tools.family._stubs import RecordingSsePublisher

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def svc(tmp_path: Path):
    store = K1FamilyStore(str(tmp_path / "family_settings.db"))
    pub = RecordingSsePublisher()
    emitter = EventEmitter(pub)
    policy = default_policy()
    idem = IdempotencyStore(store.conn)
    service = FamilySettingsService(store.conn, emitter, policy, idem)
    try:
        yield service, pub, store, policy
    finally:
        store.close()


def _ctx(
    *,
    user_id: str = "u1",
    space_id: str = "h1",
    role: str = "parent",
    band: str = "GREEN",
) -> WriteContext:
    return WriteContext(
        user_id=user_id,
        space_id=space_id,
        trace_id=f"trace-{user_id}",
        role=role,  # type: ignore[arg-type]
        band=band,  # type: ignore[arg-type]
    )


# ===========================================================================
# Schema tests
# ===========================================================================


class TestVisibilityPolicyDocSchema:
    def test_default_construction(self):
        doc = VisibilityPolicyDoc(
            id="d1",
            space_id="h1",
            actor="u1",
            rules={},
            sensitive_keywords=[],
            kid_capabilities={},
        )
        assert doc.rules == {}
        assert doc.sensitive_keywords == []
        assert doc.kid_capabilities == {}

    def test_with_rules(self):
        doc = VisibilityPolicyDoc(
            id="d2",
            space_id="h1",
            actor="u1",
            rules={"google_work": "adults"},
            sensitive_keywords=["salary"],
            kid_capabilities={"can_create_reminders": False},
        )
        assert doc.rules["google_work"] == "adults"
        assert "salary" in doc.sensitive_keywords
        assert doc.kid_capabilities["can_create_reminders"] is False


class TestFamilyFeatureFlagSchema:
    def test_default_enabled_is_false(self):
        flag = FamilyFeatureFlag(
            id="f1",
            space_id="h1",
            actor="u1",
            flag_name="health.dose_log_visible_to_kids",
        )
        assert flag.enabled is False
        assert flag.scope == "space"
        assert flag.target_member_id is None

    def test_member_scoped_flag(self):
        flag = FamilyFeatureFlag(
            id="f2",
            space_id="h1",
            actor="u1",
            flag_name="reminders.beta",
            enabled=True,
            scope="member",
            target_member_id="riley",
        )
        assert flag.scope == "member"
        assert flag.target_member_id == "riley"

    def test_known_rule_keys_non_empty(self):
        assert len(KNOWN_RULE_KEYS) >= 5
        assert "google_work" in KNOWN_RULE_KEYS
        assert "outlook_default" in KNOWN_RULE_KEYS


# ===========================================================================
# Definition tests
# ===========================================================================


class TestFamilySettingsDefinition:
    def test_adapter_id(self):
        assert FAMILY_SETTINGS_DEFINITION.adapter_id == "family_settings"

    def test_action_names(self):
        names = {a.name for a in FAMILY_SETTINGS_DEFINITION.actions}
        assert names == {
            "get_visibility_policy",
            "update_visibility_policy",
            "list_feature_flags",
            "set_feature_flag",
        }

    def test_all_actions_parent_only(self):
        for action in FAMILY_SETTINGS_DEFINITION.actions:
            for role in ("child", "elder", "guest", "guardian"):
                assert (
                    role not in action.allowed_roles
                ), f"action {action.name!r} should not allow role {role!r}"

    def test_write_actions_amber(self):
        write_actions = {a.name for a in FAMILY_SETTINGS_DEFINITION.actions if a.kind == "write"}
        assert write_actions == {"update_visibility_policy", "set_feature_flag"}
        for action in FAMILY_SETTINGS_DEFINITION.actions:
            if action.name in write_actions:
                assert action.min_band == "AMBER"

    def test_read_actions_green(self):
        for action in FAMILY_SETTINGS_DEFINITION.actions:
            if action.kind == "read":
                assert action.min_band == "GREEN"

    def test_write_actions_have_sse(self):
        for action in FAMILY_SETTINGS_DEFINITION.actions:
            if action.kind == "write":
                assert action.sse is not None, f"{action.name} missing sse"
                assert len(action.sse.emits) >= 1

    def test_tables_sql_contains_schema_version(self):
        assert "family_settings_schema_version" in FAMILY_SETTINGS_DEFINITION.tables_sql

    def test_tables_sql_contains_both_tables(self):
        sql = FAMILY_SETTINGS_DEFINITION.tables_sql
        assert "visibility_policy_docs" in sql
        assert "feature_flags" in sql


# ===========================================================================
# Service CRUD tests
# ===========================================================================


class TestGetVisibilityPolicy:
    async def test_auto_seeds_doc_when_none_exists(self, svc):
        service, _, _, _ = svc
        ctx = _ctx(role="parent", band="GREEN")
        res = await service.dispatch("get_visibility_policy", {}, ctx)
        assert res["success"] is True
        assert res["policy"] is not None
        assert res["policy"]["rules"] == {}

    async def test_returns_existing_doc(self, svc):
        service, _, _, _ = svc
        ctx = _ctx(role="parent", band="AMBER")
        # First create a policy.
        await service.dispatch(
            "update_visibility_policy",
            {"rules": {"google_work": "adults"}},
            ctx,
        )
        get_ctx = _ctx(role="parent", band="GREEN")
        res = await service.dispatch("get_visibility_policy", {}, get_ctx)
        assert res["success"] is True
        assert res["policy"]["rules"]["google_work"] == "adults"


class TestUpdateVisibilityPolicy:
    async def test_happy_path_returns_success(self, svc):
        service, pub, _, _ = svc
        ctx = _ctx(role="parent", band="AMBER")
        res = await service.dispatch(
            "update_visibility_policy",
            {"rules": {"google_work": "adults", "outlook_default": "adults"}},
            ctx,
        )
        assert res["success"] is True
        assert res["version"] == 1
        assert "google_work" in res["applied_rules"]
        assert "outlook_default" in res["applied_rules"]

    async def test_emits_sse_on_update(self, svc):
        service, pub, _, _ = svc
        ctx = _ctx(role="parent", band="AMBER")
        await service.dispatch(
            "update_visibility_policy",
            {"rules": {"google_work": "adults"}},
            ctx,
        )
        topics = [t for t, _ in pub.published]
        assert any("update_visibility_policy" in t for t in topics)

    async def test_invalid_rule_key_fails(self, svc):
        service, _, _, _ = svc
        ctx = _ctx(role="parent", band="AMBER")
        res = await service.dispatch(
            "update_visibility_policy",
            {"rules": {"nonexistent_source": "adults"}},
            ctx,
        )
        assert res["success"] is False
        assert res["error_code"] == "dispatch_failed"

    async def test_invalid_band_value_fails(self, svc):
        service, _, _, _ = svc
        ctx = _ctx(role="parent", band="AMBER")
        res = await service.dispatch(
            "update_visibility_policy",
            {"rules": {"google_work": "super_private"}},
            ctx,
        )
        assert res["success"] is False

    async def test_sensitive_keywords_update(self, svc):
        service, _, _, _ = svc
        ctx = _ctx(role="parent", band="AMBER")
        res = await service.dispatch(
            "update_visibility_policy",
            {"sensitive_keywords": ["salary", "insurance", "therapy"]},
            ctx,
        )
        assert res["success"] is True
        assert res["sensitive_keyword_count"] == 3

    async def test_kid_capabilities_persisted(self, svc):
        service, _, _, _ = svc
        ctx = _ctx(role="parent", band="AMBER")
        await service.dispatch(
            "update_visibility_policy",
            {"kid_capabilities": {"can_create_reminders": False}},
            ctx,
        )
        get_res = await service.dispatch("get_visibility_policy", {}, _ctx(role="parent"))
        assert get_res["policy"]["kid_capabilities"]["can_create_reminders"] is False

    async def test_version_increments_on_second_update(self, svc):
        service, _, _, _ = svc
        ctx = _ctx(role="parent", band="AMBER")
        await service.dispatch(
            "update_visibility_policy",
            {"rules": {"google_work": "adults"}},
            ctx,
        )
        res2 = await service.dispatch(
            "update_visibility_policy",
            {"rules": {"outlook_default": "adults"}},
            ctx,
        )
        assert res2["version"] == 2

    async def test_rules_merge_across_updates(self, svc):
        service, _, _, _ = svc
        ctx = _ctx(role="parent", band="AMBER")
        await service.dispatch(
            "update_visibility_policy",
            {"rules": {"google_work": "adults"}},
            ctx,
        )
        await service.dispatch(
            "update_visibility_policy",
            {"rules": {"outlook_default": "adults"}},
            ctx,
        )
        res = await service.dispatch("get_visibility_policy", {}, _ctx(role="parent"))
        assert res["policy"]["rules"]["google_work"] == "adults"
        assert res["policy"]["rules"]["outlook_default"] == "adults"


# ===========================================================================
# Feature flags tests
# ===========================================================================


class TestSetFeatureFlag:
    async def test_create_new_flag(self, svc):
        service, pub, _, _ = svc
        ctx = _ctx(role="parent", band="AMBER")
        res = await service.dispatch(
            "set_feature_flag",
            {"flag_name": "health.dose_log_visible_to_kids", "enabled": True},
            ctx,
        )
        assert res["success"] is True
        assert res["flag_name"] == "health.dose_log_visible_to_kids"
        assert res["enabled"] is True

    async def test_emits_sse_on_set(self, svc):
        service, pub, _, _ = svc
        ctx = _ctx(role="parent", band="AMBER")
        await service.dispatch(
            "set_feature_flag",
            {"flag_name": "beta.feature", "enabled": False},
            ctx,
        )
        assert any("set_feature_flag" in t for t, _ in pub.published)

    async def test_update_existing_flag(self, svc):
        service, _, _, _ = svc
        ctx = _ctx(role="parent", band="AMBER")
        await service.dispatch(
            "set_feature_flag",
            {"flag_name": "my_flag", "enabled": True},
            ctx,
        )
        res = await service.dispatch(
            "set_feature_flag",
            {"flag_name": "my_flag", "enabled": False},
            ctx,
        )
        assert res["success"] is True
        assert res["enabled"] is False

    async def test_missing_flag_name_fails(self, svc):
        service, _, _, _ = svc
        ctx = _ctx(role="parent", band="AMBER")
        res = await service.dispatch(
            "set_feature_flag",
            {"enabled": True},
            ctx,
        )
        assert res["success"] is False

    async def test_missing_enabled_fails(self, svc):
        service, _, _, _ = svc
        ctx = _ctx(role="parent", band="AMBER")
        res = await service.dispatch(
            "set_feature_flag",
            {"flag_name": "some_flag"},
            ctx,
        )
        assert res["success"] is False


class TestListFeatureFlags:
    async def test_empty_list_on_fresh_space(self, svc):
        service, _, _, _ = svc
        ctx = _ctx(role="parent", band="GREEN")
        res = await service.dispatch("list_feature_flags", {}, ctx)
        assert res["success"] is True
        assert res["flags"] == []

    async def test_returns_created_flags(self, svc):
        service, _, _, _ = svc
        write_ctx = _ctx(role="parent", band="AMBER")
        await service.dispatch(
            "set_feature_flag",
            {"flag_name": "flag_a", "enabled": True},
            write_ctx,
        )
        await service.dispatch(
            "set_feature_flag",
            {"flag_name": "flag_b", "enabled": False},
            write_ctx,
        )
        read_ctx = _ctx(role="parent", band="GREEN")
        res = await service.dispatch("list_feature_flags", {}, read_ctx)
        assert res["success"] is True
        names = {f["flag_name"] for f in res["flags"]}
        assert names == {"flag_a", "flag_b"}

    async def test_flags_scoped_by_space(self, svc):
        service, _, _, _ = svc
        write_ctx = _ctx(role="parent", space_id="h1", band="AMBER")
        await service.dispatch(
            "set_feature_flag",
            {"flag_name": "scoped_flag", "enabled": True},
            write_ctx,
        )
        other_ctx = _ctx(role="parent", space_id="h2", band="GREEN")
        res = await service.dispatch("list_feature_flags", {}, other_ctx)
        assert res["flags"] == []


# ===========================================================================
# ACL / Role gate tests
# ===========================================================================


class TestRoleGates:
    @pytest.mark.parametrize(
        "action,params,band",
        [
            ("get_visibility_policy", {}, "GREEN"),
            ("update_visibility_policy", {"rules": {}}, "AMBER"),
            ("list_feature_flags", {}, "GREEN"),
            ("set_feature_flag", {"flag_name": "x", "enabled": True}, "AMBER"),
        ],
    )
    async def test_child_denied_all_actions(self, svc, action, params, band):
        service, _, _, _ = svc
        ctx = _ctx(role="child", band=band)
        res = await service.dispatch(action, params, ctx)
        assert res["success"] is False
        assert res["error_code"] in ("role_denied", "role_below_min")

    @pytest.mark.parametrize(
        "action,params,band",
        [
            ("get_visibility_policy", {}, "GREEN"),
            ("update_visibility_policy", {"rules": {}}, "AMBER"),
            ("list_feature_flags", {}, "GREEN"),
            ("set_feature_flag", {"flag_name": "x", "enabled": True}, "AMBER"),
        ],
    )
    async def test_elder_denied_all_actions(self, svc, action, params, band):
        service, _, _, _ = svc
        ctx = _ctx(role="elder", band=band)
        res = await service.dispatch(action, params, ctx)
        assert res["success"] is False

    @pytest.mark.parametrize(
        "action,params",
        [
            ("update_visibility_policy", {"rules": {"google_work": "adults"}}),
            ("set_feature_flag", {"flag_name": "x", "enabled": True}),
        ],
    )
    async def test_write_actions_blocked_at_red_band(self, svc, action, params):
        """AMBER write actions are blocked when session band has escalated to RED/CRISIS."""
        service, _, _, _ = svc
        ctx = _ctx(role="parent", band="RED")
        res = await service.dispatch(action, params, ctx)
        assert res["success"] is False
        assert res["error_code"] == "band_denied"

    @pytest.mark.parametrize(
        "action,params",
        [
            ("update_visibility_policy", {"rules": {"google_work": "adults"}}),
            ("set_feature_flag", {"flag_name": "x", "enabled": True}),
        ],
    )
    async def test_write_actions_allowed_at_green_band(self, svc, action, params):
        """AMBER write actions ARE allowed at GREEN (calm session)."""
        service, _, _, _ = svc
        ctx = _ctx(role="parent", band="GREEN")
        res = await service.dispatch(action, params, ctx)
        # Should not fail on band gate (may fail for other reasons like missing flag_name)
        assert res.get("error_code") != "band_denied"

    async def test_system_can_perform_all_actions(self, svc):
        service, _, _, _ = svc
        ctx_r = _ctx(role="system", band="GREEN")
        ctx_w = _ctx(role="system", band="AMBER")
        assert (await service.dispatch("get_visibility_policy", {}, ctx_r))["success"] is True
        assert (
            await service.dispatch(
                "update_visibility_policy",
                {"rules": {"google_work": "adults"}},
                ctx_w,
            )
        )["success"] is True
        assert (await service.dispatch("list_feature_flags", {}, ctx_r))["success"] is True
        assert (
            await service.dispatch(
                "set_feature_flag",
                {"flag_name": "f", "enabled": True},
                ctx_w,
            )
        )["success"] is True


# ===========================================================================
# Live policy reload tests
# ===========================================================================


class TestLivePolicyReload:
    async def test_update_policy_mutates_shared_policy_object(self, svc):
        """After update_visibility_policy, self._policy reflects the new rules."""
        service, _, _, policy = svc
        ctx = _ctx(role="parent", band="AMBER")

        # Confirm google_work is initially handled by the default rule (adults).
        from k1.tools.family.base import BaseEntity

        google_work_entity = BaseEntity(
            id="e1",
            space_id="h1",
            actor="u1",
            source="google",
            source_label="work",
            visibility="family",
        )
        # Default policy maps google_work → adults (rule is preserved).
        initial_vis = policy.apply(google_work_entity, "parent")
        assert initial_vis == "adults"

        # Override google_work → family.
        await service.dispatch(
            "update_visibility_policy",
            {"rules": {"google_work": "family"}},
            ctx,
        )

        # The SAME policy object (not a copy) should now return "family".
        new_vis = policy.apply(google_work_entity, "parent")
        assert new_vis == "family"

    async def test_sensitive_keywords_swap_affects_policy(self, svc):
        """After updating sensitive_keywords, the policy's rule fires for new words."""
        service, _, _, policy = svc
        ctx = _ctx(role="parent", band="AMBER")

        from k1.tools.family.base import BaseEntity

        entity = BaseEntity(
            id="e2",
            space_id="h1",
            actor="u1",
            source="native",
            source_label="",
            visibility="family",
            tags=["insurance"],
        )
        # "insurance" is NOT in the default keyword set.
        assert policy.apply(entity, "parent") == "family"

        await service.dispatch(
            "update_visibility_policy",
            {"sensitive_keywords": ["insurance"]},
            ctx,
        )

        # Now insurance is a sensitive keyword → band tightens to adults.
        assert policy.apply(entity, "parent") == "adults"

    async def test_source_rule_overrides_cover_all_configurable_sources(self, svc):
        service, _, _, policy = svc
        ctx = _ctx(role="parent", band="AMBER")

        from k1.tools.family.base import BaseEntity

        entities = {
            "native_default": BaseEntity(
                id="n1", space_id="h1", actor="u1", source="native", visibility="family"
            ),
            "google_work": BaseEntity(
                id="g1",
                space_id="h1",
                actor="u1",
                source="google",
                source_label="work",
                visibility="family",
            ),
            "google_personal": BaseEntity(
                id="g2",
                space_id="h1",
                actor="u1",
                source="google",
                source_label="personal",
                visibility="family",
            ),
            "outlook_default": BaseEntity(
                id="o1", space_id="h1", actor="u1", source="outlook", visibility="family"
            ),
            "classroom": BaseEntity(
                id="c1", space_id="h1", actor="u1", source="classroom", visibility="family"
            ),
        }

        await service.dispatch(
            "update_visibility_policy",
            {"rules": {key: "private" for key in entities}},
            ctx,
        )

        for entity in entities.values():
            assert policy.apply(entity, "parent") == "private"

    async def test_policy_sensitive_keywords_field_updated(self, svc):
        """policy.sensitive_keywords mirrors the active keyword set."""
        service, _, _, policy = svc
        ctx = _ctx(role="parent", band="AMBER")
        await service.dispatch(
            "update_visibility_policy",
            {"sensitive_keywords": ["testword1", "testword2"]},
            ctx,
        )
        assert "testword1" in policy.sensitive_keywords
        assert "testword2" in policy.sensitive_keywords

    async def test_rules_splice_does_not_grow_rules_list(self, svc):
        """Repeated updates don't accumulate stale rules in the list."""
        service, _, _, policy = svc
        ctx = _ctx(role="parent", band="AMBER")
        from k1.tools.family.policy import DEFAULT_RULES

        initial_len = len(list(DEFAULT_RULES))

        await service.dispatch(
            "update_visibility_policy",
            {"rules": {"google_work": "family"}},
            ctx,
        )
        after_first = len(policy.rules)

        await service.dispatch(
            "update_visibility_policy",
            {"rules": {"google_work": "adults"}},
            ctx,
        )
        after_second = len(policy.rules)

        assert after_first == initial_len
        assert after_second == initial_len
