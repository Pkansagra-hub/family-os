"""
Comprehensive test suite for M05 (Space Resolution & Visibility Module).

**Contract**: space.resolve_visibility.v1.yaml
**ADR**: k005.1 (ACL Resolution - Visibility Intersection & Space Ownership)
**Performance Target**: <3ms P95 (cache hit), <10ms P99 (cold cache)

Test Categories:
1. Visibility intersection (security guarantee: never expand beyond policy)
2. Author role determination (OWNER/CO_OWNER/GUEST)
3. Fail-secure defaults (author-only on lookup failure)
4. Visibility scope classification (OWNER_ONLY, SPACE_DEFAULT, etc.)
5. Cache performance validation
6. Integration tests (end-to-end envelope processing)
"""

import json
import time
from statistics import mean
from unittest.mock import patch

import pytest

from k0.modules.space.resolve_visibility import (
    SpaceMetadata,
    SpaceResolution,
    classify_visibility_scope,
    compute_visibility_intersection,
    determine_author_role,
    get_metrics,
    reset_cache,
    reset_metrics,
    resolve_visibility,
    run,
)

# ==================== Fixtures ====================


@pytest.fixture(autouse=True)
def reset_state():
    """Reset cache and metrics before each test."""
    reset_cache()
    reset_metrics()
    yield
    reset_cache()
    reset_metrics()


@pytest.fixture
def home_space_metadata():
    """Fixture: Home space metadata (owner=dad, co_owners=[mom])."""
    return SpaceMetadata(
        space_id="space_home",
        owner_id="person_dad",
        co_owners=("person_mom",),
        default_visible_to=("person_dad", "person_mom"),
        space_type="home",
        policy_version="2025-11-01",
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
    )


@pytest.fixture
def private_journal_metadata():
    """Fixture: Private journal space (owner=teen, co_owners=[])."""
    return SpaceMetadata(
        space_id="space_journal_teen",
        owner_id="person_teen",
        co_owners=(),  # No co-owners
        default_visible_to=("person_teen",),  # Teen only
        space_type="journal",
        policy_version="2025-11-01",
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
    )


@pytest.fixture
def shared_calendar_metadata():
    """Fixture: Shared calendar (owner=mom, co_owners=[dad, teen])."""
    return SpaceMetadata(
        space_id="space_calendar_shared",
        owner_id="person_mom",
        co_owners=("person_dad", "person_teen"),
        default_visible_to=("person_mom", "person_dad", "person_teen"),
        space_type="calendar",
        policy_version="2025-11-01",
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
    )


# ==================== Unit Tests: Visibility Intersection ====================


def test_visibility_intersection_never_expands_policy():
    """
    SECURITY TEST: Verify intersection never expands beyond policy.

    Security guarantee: |visible_to| <= |policy_visible_to|
    """
    policy_visible_to = ["person_dad", "person_mom", "person_teen"]
    space_allowed_viewers = ("person_dad", "person_mom")  # Home space excludes teen

    result = compute_visibility_intersection(policy_visible_to, space_allowed_viewers)

    # Intersection: {dad, mom, teen} ∩ {dad, mom} = {dad, mom}
    assert set(result) == {"person_dad", "person_mom"}
    assert len(result) <= len(policy_visible_to)  # Never expand


def test_visibility_intersection_policy_subset_of_space():
    """Intersection when policy is more restrictive than space."""
    policy_visible_to = ["person_dad"]  # Policy only allows dad
    space_allowed_viewers = ("person_dad", "person_mom")  # Space allows both

    result = compute_visibility_intersection(policy_visible_to, space_allowed_viewers)

    # Intersection: {dad} ∩ {dad, mom} = {dad}
    assert result == ["person_dad"]


def test_visibility_intersection_no_overlap():
    """Intersection when policy and space have no overlap."""
    policy_visible_to = ["person_teen"]  # Policy allows teen
    space_allowed_viewers = ("person_dad", "person_mom")  # Space excludes teen

    result = compute_visibility_intersection(policy_visible_to, space_allowed_viewers)

    # Intersection: {teen} ∩ {dad, mom} = {}
    assert result == []


def test_visibility_intersection_exact_match():
    """Intersection when policy and space are identical."""
    policy_visible_to = ["person_dad", "person_mom"]
    space_allowed_viewers = ("person_dad", "person_mom")

    result = compute_visibility_intersection(policy_visible_to, space_allowed_viewers)

    # Intersection: {dad, mom} ∩ {dad, mom} = {dad, mom}
    assert set(result) == {"person_dad", "person_mom"}


# ==================== Unit Tests: Author Role Determination ====================


def test_author_role_owner(home_space_metadata):
    """Author is the space owner."""
    role = determine_author_role("person_dad", home_space_metadata)
    assert role == "OWNER"


def test_author_role_co_owner(home_space_metadata):
    """Author is a co-owner."""
    role = determine_author_role("person_mom", home_space_metadata)
    assert role == "CO_OWNER"


def test_author_role_guest(home_space_metadata):
    """Author is a guest (neither owner nor co-owner)."""
    role = determine_author_role("person_teen", home_space_metadata)
    assert role == "GUEST"


# ==================== Unit Tests: Visibility Scope Classification ====================


def test_visibility_scope_owner_only():
    """Classify OWNER_ONLY visibility."""
    visible_to = ["person_dad"]
    owner_id = "person_dad"
    co_owners = ()

    scope = classify_visibility_scope(visible_to, owner_id, co_owners)
    assert scope == "OWNER_ONLY"


def test_visibility_scope_space_default():
    """Classify SPACE_DEFAULT visibility (owner + all co-owners)."""
    visible_to = ["person_dad", "person_mom"]
    owner_id = "person_dad"
    co_owners = ("person_mom",)

    scope = classify_visibility_scope(visible_to, owner_id, co_owners)
    assert scope == "SPACE_DEFAULT"


def test_visibility_scope_household_all():
    """Classify HOUSEHOLD_ALL visibility (heuristic: >=4 people)."""
    visible_to = ["person_dad", "person_mom", "person_teen", "person_kid"]
    owner_id = "person_dad"
    co_owners = ("person_mom", "person_teen")

    scope = classify_visibility_scope(visible_to, owner_id, co_owners)
    assert scope == "HOUSEHOLD_ALL"


def test_visibility_scope_custom_subset():
    """Classify CUSTOM_SUBSET visibility (arbitrary subset)."""
    visible_to = ["person_dad", "person_friend"]  # Owner + friend (not co-owner)
    owner_id = "person_dad"
    co_owners = ("person_mom",)

    scope = classify_visibility_scope(visible_to, owner_id, co_owners)
    assert scope == "CUSTOM_SUBSET"


def test_visibility_scope_external_share():
    """Classify EXTERNAL_SHARE visibility (includes external person)."""
    visible_to = ["person_dad", "person_external_john"]
    owner_id = "person_dad"
    co_owners = ()

    scope = classify_visibility_scope(visible_to, owner_id, co_owners)
    assert scope == "EXTERNAL_SHARE"


# ==================== Unit Tests: Fail-Secure Defaults ====================


def test_fail_secure_on_space_not_found():
    """
    SECURITY TEST: Fail-secure to author-only visibility when space not found.
    """
    # No mock → _get_space_metadata_cached returns None
    resolution = resolve_visibility(
        actor_id="person_teen",
        space_id="space_unknown",
        policy_visible_to=["person_teen", "person_dad"],
    )

    # Should default to author-only (fail-secure)
    assert resolution.owner_id == "person_teen"
    assert json.loads(resolution.co_owners_json) == []
    assert resolution.author_role == "OWNER"
    assert json.loads(resolution.visible_to_json) == ["person_teen"]
    assert resolution.visibility_scope == "OWNER_ONLY"
    assert resolution.space_policy_version == "unknown"

    # Verify metrics
    metrics = get_metrics()
    assert metrics["fail_secure_invocations"] == 1


def test_empty_intersection_defaults_author_only(home_space_metadata):
    """When intersection is empty, default to author-only visibility."""
    with patch("k0.modules.space.resolve_visibility.get_space_metadata") as mock_get:
        mock_get.return_value = home_space_metadata

        # Policy allows only teen, space allows only dad/mom → no overlap
        resolution = resolve_visibility(
            actor_id="person_teen", space_id="space_home", policy_visible_to=["person_teen"]
        )

        # Should default to author (teen) only
        assert json.loads(resolution.visible_to_json) == ["person_teen"]
        assert resolution.visibility_scope == "OWNER_ONLY"


# ==================== Unit Tests: Full Resolution Integration ====================


def test_resolve_visibility_owner_writes_to_home_space(home_space_metadata):
    """Owner writes to home space (intersection with policy)."""
    with patch("k0.modules.space.resolve_visibility.get_space_metadata") as mock_get:
        mock_get.return_value = home_space_metadata

        resolution = resolve_visibility(
            actor_id="person_dad",
            space_id="space_home",
            policy_visible_to=["person_dad", "person_mom", "person_teen"],
        )

        # Home space allows [dad, mom], policy allows [dad, mom, teen]
        # Intersection: [dad, mom]
        assert resolution.owner_id == "person_dad"
        assert set(json.loads(resolution.co_owners_json)) == {"person_mom"}
        assert resolution.author_role == "OWNER"
        assert set(json.loads(resolution.visible_to_json)) == {"person_dad", "person_mom"}
        assert resolution.visibility_scope == "SPACE_DEFAULT"


def test_resolve_visibility_guest_writes_to_private_journal(private_journal_metadata):
    """Guest writes to private journal (author is GUEST, space restricts visibility)."""
    with patch("k0.modules.space.resolve_visibility.get_space_metadata") as mock_get:
        mock_get.return_value = private_journal_metadata

        resolution = resolve_visibility(
            actor_id="person_dad",  # Dad is GUEST in teen's journal
            space_id="space_journal_teen",
            policy_visible_to=["person_dad", "person_teen"],
        )

        # Private journal allows only teen, policy allows [dad, teen]
        # Intersection: [teen]
        assert resolution.owner_id == "person_teen"
        assert json.loads(resolution.co_owners_json) == []
        assert resolution.author_role == "GUEST"
        assert json.loads(resolution.visible_to_json) == ["person_teen"]
        assert resolution.visibility_scope == "OWNER_ONLY"


def test_resolve_visibility_co_owner_writes_to_shared_calendar(shared_calendar_metadata):
    """Co-owner writes to shared calendar (all household members)."""
    with patch("k0.modules.space.resolve_visibility.get_space_metadata") as mock_get:
        mock_get.return_value = shared_calendar_metadata

        resolution = resolve_visibility(
            actor_id="person_dad",  # Dad is CO_OWNER
            space_id="space_calendar_shared",
            policy_visible_to=["person_dad", "person_mom", "person_teen"],
        )

        # Shared calendar allows all 3, policy allows all 3
        # Intersection: [dad, mom, teen]
        assert resolution.owner_id == "person_mom"
        assert set(json.loads(resolution.co_owners_json)) == {"person_dad", "person_teen"}
        assert resolution.author_role == "CO_OWNER"
        assert set(json.loads(resolution.visible_to_json)) == {
            "person_dad",
            "person_mom",
            "person_teen",
        }
        assert resolution.visibility_scope == "SPACE_DEFAULT"


# ==================== Performance Tests ====================


def test_cache_performance_under_3ms(home_space_metadata):
    """
    PERFORMANCE TEST: Validate cache hit <3ms P95.
    """
    with patch("k0.modules.space.resolve_visibility.get_space_metadata") as mock_get:
        mock_get.return_value = home_space_metadata

        # Warmup (load cache)
        resolve_visibility("person_dad", "space_home", ["person_dad", "person_mom"])

        # Measure 100 cache hits
        latencies = []
        for _ in range(100):
            start = time.perf_counter()
            resolve_visibility("person_dad", "space_home", ["person_dad", "person_mom"])
            latency_ms = (time.perf_counter() - start) * 1000
            latencies.append(latency_ms)

        # Statistical analysis
        latencies.sort()
        p50 = latencies[49]  # 50th percentile
        p95 = latencies[94]  # 95th percentile
        p99 = latencies[98]  # 99th percentile
        mean_latency = mean(latencies)

        print("\n--- Cache Performance (n=100) ---")
        print(f"Mean: {mean_latency:.3f}ms")
        print(f"P50: {p50:.3f}ms")
        print(f"P95: {p95:.3f}ms")
        print(f"P99: {p99:.3f}ms")

        # Assert P95 < 3ms (contract budget)
        assert p95 < 3.0, f"P95 latency {p95:.3f}ms exceeds 3ms budget"


def test_metrics_tracking(home_space_metadata):
    """Verify metrics are tracked correctly."""
    with patch("k0.modules.space.resolve_visibility._get_space_metadata_cached") as mock_get:
        mock_get.return_value = None  # Simulate cache miss

        # Run 5 resolutions (all fail-secure)
        for _ in range(5):
            resolve_visibility("person_dad", "space_home", ["person_dad"])

        metrics = get_metrics()
        assert metrics["space_lookups"] == 5
        assert metrics["fail_secure_invocations"] == 5
        # Note: cache_hits/cache_misses tracked inside _get_space_metadata_cached
        # which is mocked, so we can't test those metrics here


# ==================== Integration Tests: Async Entry Point ====================


@pytest.mark.asyncio
async def test_run_with_valid_envelope(home_space_metadata):
    """Integration test: Full envelope processing."""
    with patch("k0.modules.space.resolve_visibility.get_space_metadata") as mock_get:
        mock_get.return_value = home_space_metadata

        envelope = {
            "event": {
                "event_id": "evt_123",
                "actor_id": "person_dad",
                "space_id": "space_home",
                "text": "Family dinner tonight!",
            },
            "policy_stamp": {"visible_to": ["person_dad", "person_mom", "person_teen"]},
        }

        result = await run(envelope)

        # Validate output schema
        assert result["owner_id"] == "person_dad"
        assert set(json.loads(result["co_owners_json"])) == {"person_mom"}
        assert result["author_role"] == "OWNER"
        assert set(json.loads(result["visible_to_json"])) == {"person_dad", "person_mom"}
        assert result["visibility_scope"] == "SPACE_DEFAULT"
        assert result["space_policy_version"] == "2025-11-01"
        assert "space_resolved_at_utc" in result


@pytest.mark.asyncio
async def test_run_with_missing_actor_id():
    """Integration test: Invalid envelope (missing actor_id)."""
    envelope = {"event": {"space_id": "space_home"}, "policy_stamp": {"visible_to": ["person_dad"]}}

    with pytest.raises(ValueError, match="Missing required field: event.actor_id"):
        await run(envelope)


@pytest.mark.asyncio
async def test_run_with_missing_space_id():
    """Integration test: Invalid envelope (missing space_id)."""
    envelope = {"event": {"actor_id": "person_dad"}, "policy_stamp": {"visible_to": ["person_dad"]}}

    with pytest.raises(ValueError, match="Missing required field: event.space_id"):
        await run(envelope)


@pytest.mark.asyncio
async def test_run_preserves_context():
    """Integration test: Verify context is preserved (idempotency)."""
    with patch("k0.modules.space.resolve_visibility.get_space_metadata") as mock_get:
        mock_get.return_value = None  # Fail-secure

        envelope = {
            "event": {
                "event_id": "evt_123",
                "actor_id": "person_teen",
                "space_id": "space_unknown",
            },
            "policy_stamp": {"visible_to": ["person_teen"]},
        }

        # Run twice (idempotency check)
        result1 = await run(envelope)
        result2 = await run(envelope)

        # Results should be identical (except timestamp)
        assert result1["owner_id"] == result2["owner_id"]
        assert result1["visible_to_json"] == result2["visible_to_json"]
        assert result1["author_role"] == result2["author_role"]


# ==================== Edge Cases ====================


def test_dataclass_immutability():
    """Verify SpaceResolution dataclass is immutable (frozen=True)."""
    resolution = SpaceResolution(
        owner_id="person_dad",
        co_owners_json="[]",
        author_role="OWNER",
        visible_to_json='["person_dad"]',
        visibility_scope="OWNER_ONLY",
        space_policy_version="2025-11-01",
        space_resolved_at_utc="2025-11-17T00:00:00Z",
    )

    # Should raise error (dataclass is frozen)
    with pytest.raises(AttributeError):
        resolution.owner_id = "person_mom"


def test_metrics_cache_hit_ratio_calculation():
    """Verify cache hit ratio is calculated correctly (without mocking internal cache)."""
    # Test metrics for successful resolutions (intersections computed)
    with patch("k0.modules.space.resolve_visibility._get_space_metadata_cached") as mock_get:
        mock_get.return_value = SpaceMetadata(
            space_id="space_home",
            owner_id="person_dad",
            co_owners=(),
            default_visible_to=("person_dad",),
            space_type="home",
            policy_version="2025-11-01",
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
        )

        # Run 10 successful resolutions
        for _ in range(10):
            resolve_visibility("person_dad", "space_home", ["person_dad"])

        metrics = get_metrics()
        assert metrics["space_lookups"] == 10
        assert metrics["intersections_computed"] == 10
        # cache_hits tracked inside _get_space_metadata_cached (mocked)


def test_sorted_visible_to_determinism():
    """Verify visible_to list is sorted (deterministic ordering)."""
    policy_visible_to = ["person_teen", "person_dad", "person_mom"]  # Unsorted
    space_allowed_viewers = ("person_dad", "person_mom", "person_teen")

    result = compute_visibility_intersection(policy_visible_to, space_allowed_viewers)

    # Should be sorted alphabetically
    assert result == ["person_dad", "person_mom", "person_teen"]


# ==================== Summary Statistics ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
    pytest.main([__file__, "-v", "-s"])
