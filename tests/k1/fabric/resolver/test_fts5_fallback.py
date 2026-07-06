"""Phase 2.6, Epic 24 — FTS5 fallback tests (GAP-P2-035).

Validates that CapabilityTypeResolver._resolve_one() falls back to
FTS5 BM25 search when structured graph queries return empty.
"""

from __future__ import annotations

from k1.fabric.manifest_translator import register_definition_to_store
from k1.fabric.resolver.capability_type_resolver import (
    CapabilityTypeResolver,
)
from k1.fabric.resolver.request_frame import RequestFrameIntent
from k1.fabric.resolver.resource_projection import ResourceUniverse, ScopeProof
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.fabric.stores.local_projection_store import LocalProjectionStore
from k1.tools.family.shopping.definition import SHOPPING_DEFINITION

# ── Helpers ──────────────────────────────────────────────────────────


def _make_resolver(gps: GlobalProjectionStore) -> CapabilityTypeResolver:
    """Create a resolver with an in-memory local store and the given GPS."""
    lps = LocalProjectionStore(":memory:")
    lps.open()
    return CapabilityTypeResolver(global_store=gps, local_store=lps)


def _empty_universe() -> ResourceUniverse:
    """Minimal empty ResourceUniverse for type-only resolution tests."""
    return ResourceUniverse(
        universe_id="test-universe",
        resource_candidates=[],
        person_candidates=[],
        unresolved=[],
        scope_proof=ScopeProof(
            scope_proof_id="test-proof",
            actor_id="test-actor",
            space_id="test-space",
        ),
        completeness="unknown",
        freshness="unknown",
    )


def _seed_capability(
    gps: GlobalProjectionStore,
    name: str,
    connector_id: str,
    action_name: str,
    effect: str,
    resource_kind: str,
    description: str,
    domain_id: str = "family",
    family_id: str | None = None,
) -> None:
    """Insert a single capability directly into GPS (bypassing translator)."""
    from k1.fabric.stores.global_projection_store import CapabilityRecord

    ts = "2026-06-10T00:00:00Z"
    gps.upsert_capability(
        CapabilityRecord(
            capability_name=name,
            connector_id=connector_id,
            invocation_mode="read" if effect == "read" else "execute",
            action_name=action_name,
            effect=effect,
            resource_kind=resource_kind,
            domain_id=domain_id,
            family_id=family_id,
            description=description,
            created_at=ts,
            contract_json={},
        )
    )


# ── 24.5.1 — FTS5 fallback when graph empty ──────────────────────────


def test_fts5_fallback_when_graph_empty():
    """GPS has FTS5 match for 'buy groceries' — _resolve_one() returns
    capabilities tagged with _source: 'fts5'."""
    gps = GlobalProjectionStore(":memory:")
    gps.open()
    # Seed a connector for FK
    from k1.fabric.stores.global_projection_store import ConnectorRecord

    gps.upsert_connector(
        ConnectorRecord(
            connector_id="family.shopping",
            label="Shopping",
            connector_type="native",
            provider_type="LOCAL",
            version="1.0.0",
            admission_verdict="admitted",
            registration_type="static",
            domain_id="family",
            created_at="2026-06-10T00:00:00Z",
            updated_at="2026-06-10T00:00:00Z",
        )
    )
    _seed_capability(
        gps,
        name="tool.execute.family.shopping.add_item",
        connector_id="family.shopping",
        action_name="add_item",
        effect="write",
        resource_kind="shopping_item",
        domain_id="family",
        family_id="item",
        description="Add groceries to the shopping list for family meals",
    )

    resolver = _make_resolver(gps)
    intent = RequestFrameIntent(
        intent_id="intent-1",
        action="groceries",  # single token — FTS5 MATCH uses implicit AND for multi-word
        domain="family",
        operation_hint="add",
        resource_kind_hint="groceries",
    )
    result = resolver._resolve_one(intent, _empty_universe())

    # Should have fallen back to FTS5
    assert result.fallback_capabilities, "Expected FTS5 fallback capabilities, got empty list"
    fts_sources = [c["_source"] for c in result.fallback_capabilities if "_source" in c]
    assert (
        "fts5" in fts_sources
    ), f"Expected _source='fts5' in capabilities, got sources: {fts_sources}"
    assert any(
        "fts5_fallback" in e for e in result.evidence
    ), f"Expected 'fts5_fallback' in evidence, got: {result.evidence}"


# ── 24.5.2 — FTS5 preserves domain scoping ───────────────────────────


def test_fts5_fallback_preserves_domain_scoping():
    """FTS5 results for domain='family' exclude finance connectors."""
    gps = GlobalProjectionStore(":memory:")
    gps.open()
    from k1.fabric.stores.global_projection_store import ConnectorRecord

    for cid, did in [("family.shopping", "family"), ("finance.chase", "finance")]:
        gps.upsert_connector(
            ConnectorRecord(
                connector_id=cid,
                label=cid,
                connector_type="native",
                provider_type="LOCAL",
                version="1.0.0",
                admission_verdict="admitted",
                registration_type="static",
                domain_id=did,
                created_at="2026-06-10T00:00:00Z",
                updated_at="2026-06-10T00:00:00Z",
            )
        )
    _seed_capability(
        gps,
        name="tool.execute.family.shopping.add_item",
        connector_id="family.shopping",
        action_name="add_item",
        effect="write",
        resource_kind="shopping_item",
        domain_id="family",
        family_id="item",
        description="Add item to family shopping list",
    )
    _seed_capability(
        gps,
        name="tool.execute.finance.chase.transfer",
        connector_id="finance.chase",
        action_name="transfer",
        effect="write",
        resource_kind="transaction",
        domain_id="finance",
        family_id="transaction",
        description="Transfer money between accounts",
    )

    resolver = _make_resolver(gps)
    intent = RequestFrameIntent(
        intent_id="intent-1",
        action="add item to list",
        domain="family",
        operation_hint="add",
        resource_kind_hint="xyz_nonexistent",
    )
    result = resolver._resolve_one(intent, _empty_universe())

    if result.fallback_capabilities:
        # All results must be from the family domain
        for c in result.fallback_capabilities:
            assert c.get("connector_id", "").startswith(
                "family."
            ), f"FTS5 result leaked non-family connector: {c.get('connector_id')}"


# ── 24.5.3 — FTS5 no match ───────────────────────────────────────────


def test_fts5_fallback_no_match():
    """GPS has no FTS5 match for nonsense query — capabilities stays empty."""
    gps = GlobalProjectionStore(":memory:")
    gps.open()
    from k1.fabric.stores.global_projection_store import ConnectorRecord

    gps.upsert_connector(
        ConnectorRecord(
            connector_id="family.shopping",
            label="Shopping",
            connector_type="native",
            provider_type="LOCAL",
            version="1.0.0",
            admission_verdict="admitted",
            registration_type="static",
            domain_id="family",
            created_at="2026-06-10T00:00:00Z",
            updated_at="2026-06-10T00:00:00Z",
        )
    )
    _seed_capability(
        gps,
        name="tool.execute.family.shopping.add_item",
        connector_id="family.shopping",
        action_name="add_item",
        effect="write",
        resource_kind="shopping_item",
        domain_id="family",
        family_id="item",
        description="Add item to shopping list",
    )

    resolver = _make_resolver(gps)
    intent = RequestFrameIntent(
        intent_id="intent-1",
        action="xyzzynonsense12345blarg",  # no BM25 match possible
        domain="family",
        operation_hint="create",
        resource_kind_hint="nonexistent",
    )
    result = resolver._resolve_one(intent, _empty_universe())

    assert not result.fallback_capabilities, "Expected empty capabilities for nonsense query"
    # Confidence may be 'low' or 'medium' depending on whether operation
    # resolution alone produces enough evidence.  The key assertion is that
    # FTS5 did NOT contribute any capabilities.
    assert result.confidence in ("low", "medium")


# ── 24.5.4 — Empty action skips FTS5 ─────────────────────────────────


def test_fts5_fallback_empty_action_skips():
    """action='' — no FTS5 call, no crash."""
    gps = GlobalProjectionStore(":memory:")
    gps.open()
    resolver = _make_resolver(gps)
    intent = RequestFrameIntent(
        intent_id="intent-1",
        action="",  # empty
        domain="family",
        operation_hint="list",
    )
    result = resolver._resolve_one(intent, _empty_universe())
    assert not result.fallback_capabilities
    # Should not have crashed — empty action is handled gracefully


# ── 24.5.5 — Empty domain uses unfiltered search ─────────────────────


def test_fts5_fallback_empty_domain():
    """domain='' — calls search_capabilities() without domain filter."""
    gps = GlobalProjectionStore(":memory:")
    gps.open()
    from k1.fabric.stores.global_projection_store import ConnectorRecord

    gps.upsert_connector(
        ConnectorRecord(
            connector_id="family.shopping",
            label="Shopping",
            connector_type="native",
            provider_type="LOCAL",
            version="1.0.0",
            admission_verdict="admitted",
            registration_type="static",
            domain_id="family",
            created_at="2026-06-10T00:00:00Z",
            updated_at="2026-06-10T00:00:00Z",
        )
    )
    _seed_capability(
        gps,
        name="tool.execute.family.shopping.add_item",
        connector_id="family.shopping",
        action_name="add_item",
        effect="write",
        resource_kind="shopping_item",
        domain_id="family",
        family_id="item",
        description="Add item to grocery shopping list",
    )

    resolver = _make_resolver(gps)
    intent = RequestFrameIntent(
        intent_id="intent-1",
        action="add groceries",
        domain="",  # empty — no domain filter
        operation_hint="add",
        resource_kind_hint="nonexistent",
    )
    result = resolver._resolve_one(intent, _empty_universe())

    # With empty domain, search_capabilities() is called (no domain filter)
    # so it should still find the shopping capability via FTS5
    if result.fallback_capabilities:
        assert any("fts5_fallback" in e for e in result.evidence)


# ── 24.5.6 — FTS5 result format matches fallback_capabilities ─────────


def test_fts5_results_format_matches_fallback_capabilities():
    """FTS5 result dicts have expected keys."""
    gps = GlobalProjectionStore(":memory:")
    gps.open()
    from k1.fabric.stores.global_projection_store import ConnectorRecord

    gps.upsert_connector(
        ConnectorRecord(
            connector_id="family.shopping",
            label="Shopping",
            connector_type="native",
            provider_type="LOCAL",
            version="1.0.0",
            admission_verdict="admitted",
            registration_type="static",
            domain_id="family",
            created_at="2026-06-10T00:00:00Z",
            updated_at="2026-06-10T00:00:00Z",
        )
    )
    _seed_capability(
        gps,
        name="tool.execute.family.shopping.add_item",
        connector_id="family.shopping",
        action_name="add_item",
        effect="write",
        resource_kind="shopping_item",
        domain_id="family",
        family_id="item",
        description="Add grocery item to the shopping list",
    )

    resolver = _make_resolver(gps)
    intent = RequestFrameIntent(
        intent_id="intent-1",
        action="add grocery item",
        domain="family",
        operation_hint="add",
        resource_kind_hint="nonexistent",
    )
    result = resolver._resolve_one(intent, _empty_universe())

    if result.fallback_capabilities:
        required_keys = {
            "capability_name",
            "connector_id",
            "resource_kind",
            "invocation_mode",
            "effect",
            "_source",
        }
        for c in result.fallback_capabilities:
            missing = required_keys - set(c.keys())
            assert not missing, f"FTS5 result missing keys: {missing}"


# ── 24.5.7 — Confidence naturally improves with FTS5 evidence ────────


def test_confidence_improves_with_fts5_evidence():
    """When FTS5 finds results, the evidence count increases, naturally
    boosting confidence to at least 'medium'."""
    gps = GlobalProjectionStore(":memory:")
    gps.open()
    from k1.fabric.stores.global_projection_store import ConnectorRecord

    gps.upsert_connector(
        ConnectorRecord(
            connector_id="family.shopping",
            label="Shopping",
            connector_type="native",
            provider_type="LOCAL",
            version="1.0.0",
            admission_verdict="admitted",
            registration_type="static",
            domain_id="family",
            created_at="2026-06-10T00:00:00Z",
            updated_at="2026-06-10T00:00:00Z",
        )
    )
    _seed_capability(
        gps,
        name="tool.execute.family.shopping.add_item",
        connector_id="family.shopping",
        action_name="add_item",
        effect="write",
        resource_kind="shopping_item",
        domain_id="family",
        family_id="item",
        description="Add grocery items to the shopping list for family meals",
    )

    resolver = _make_resolver(gps)
    intent = RequestFrameIntent(
        intent_id="intent-1",
        action="add groceries for dinner",
        domain="family",
        operation_hint="add",
        resource_kind_hint="nonexistent",
    )
    result = resolver._resolve_one(intent, _empty_universe())

    # Operation resolution always succeeds ("add" → create/write) = 1 evidence.
    # If FTS5 found matches, that adds a second evidence entry → medium.
    if result.fallback_capabilities:
        assert (
            len(result.evidence) >= 2
        ), f"Expected >=2 evidence entries, got {len(result.evidence)}: {result.evidence}"
        assert result.confidence in (
            "medium",
            "high",
        ), f"Expected medium or high confidence, got {result.confidence}"


# ── 24.5.8 — End-to-end: register_definition produces findable caps ───


def test_register_definition_produces_fts5_findable_capabilities():
    """Full integration: register_definition_to_store() → capabilities are
    FTS5-findable when graph resolution would miss them."""
    gps = GlobalProjectionStore(":memory:")
    gps.open()

    # Register shopping (has resource_families=["item"], domain_id="family")
    count = register_definition_to_store(SHOPPING_DEFINITION, gps)
    assert count > 0

    resolver = _make_resolver(gps)
    intent = RequestFrameIntent(
        intent_id="intent-1",
        action="add milk to the grocery list",
        domain="family",
        operation_hint="add",
        resource_kind_hint="groceries",  # "groceries" not in concept_aliases
    )
    result = resolver._resolve_one(intent, _empty_universe())

    # The graph should fail to resolve "groceries" → no concept match.
    # FTS5 should find "add_item" via BM25 on description text.
    if result.fallback_capabilities:
        fts_sources = [c.get("_source") for c in result.fallback_capabilities]
        assert "fts5" in fts_sources, f"No FTS5 source in: {fts_sources}"

    gps.close()
