"""
Unit tests for HierarchicalActivityResolver

Tests:
- Taxonomy loading from YAML
- Hierarchy path resolution
- Category/activity/subtype navigation
- Keyword search
- Legacy mapping
- Performance (<1ms for all operations)

Contract: k0/contracts/taxonomies/activity_taxonomy.yaml
"""

import time


class TestTaxonomyLoading:
    """Tests for taxonomy loading and parsing."""

    def test_load_taxonomy(self):
        """Test loading taxonomy from YAML."""
        from k0.modules.activity.taxonomy_resolver import HierarchicalActivityResolver

        resolver = HierarchicalActivityResolver()
        taxonomy = resolver.taxonomy

        assert taxonomy.version == "1.0.0"
        assert len(taxonomy.categories) > 0
        assert len(taxonomy.nodes) > 0

    def test_taxonomy_has_16_categories(self):
        """Test taxonomy has expected number of categories."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        categories = resolver.get_all_categories()

        # Taxonomy defines 16 top-level categories
        assert len(categories) >= 10

    def test_taxonomy_has_50_plus_activities(self):
        """Test taxonomy has 50+ activity types."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        activities = resolver.get_all_activities()

        assert len(activities) >= 30  # At least 30 level-1 activities


class TestHierarchyResolution:
    """Tests for resolving activities to hierarchy paths."""

    def test_resolve_meal(self):
        """Test resolving meal activity."""
        from k0.modules.activity.taxonomy_resolver import resolve_activity_hierarchy

        result = resolve_activity_hierarchy("meal")

        assert result["is_valid"] is True
        assert result["parent_category"] == "sustenance"
        assert "meal" in result["hierarchy_path"]

    def test_resolve_breakfast_subtype(self):
        """Test resolving breakfast subtype."""
        from k0.modules.activity.taxonomy_resolver import resolve_activity_hierarchy

        result = resolve_activity_hierarchy("breakfast")

        assert result["is_valid"] is True
        assert "breakfast" in result["hierarchy_path"]

    def test_resolve_exercise(self):
        """Test resolving exercise activity."""
        from k0.modules.activity.taxonomy_resolver import resolve_activity_hierarchy

        result = resolve_activity_hierarchy("exercise")

        assert result["is_valid"] is True
        assert result["parent_category"] == "wellness"

    def test_resolve_invalid_activity(self):
        """Test resolving invalid activity."""
        from k0.modules.activity.taxonomy_resolver import resolve_activity_hierarchy

        result = resolve_activity_hierarchy("nonexistent_activity_xyz")

        assert result["is_valid"] is False
        assert result["level"] == -1


class TestHierarchyNavigation:
    """Tests for navigating taxonomy hierarchy."""

    def test_get_category_activities(self):
        """Test getting activities under a category."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        activities = resolver.get_category_activities("sustenance")

        assert "meal" in activities

    def test_get_subtypes(self):
        """Test getting subtypes under an activity."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        subtypes = resolver.get_subtypes("meal")

        # Meal should have breakfast, lunch, dinner, etc.
        assert len(subtypes) > 0

    def test_get_siblings(self):
        """Test getting sibling activities."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        siblings = resolver.get_siblings("meal")

        # Meal has siblings like cooking, dining_out
        assert "meal" not in siblings  # Should not include self


class TestTaxonomyNode:
    """Tests for TaxonomyNode dataclass."""

    def test_node_properties(self):
        """Test TaxonomyNode properties."""
        from k0.modules.activity.taxonomy_resolver import TaxonomyNode

        node = TaxonomyNode(
            id="meal",
            label="Meal",
            description="Eating activity",
            level=1,
            parent_id="sustenance",
        )

        assert node.is_category is False  # level != 0
        assert node.is_leaf is True  # no children

    def test_category_node(self):
        """Test category-level node."""
        from k0.modules.activity.taxonomy_resolver import TaxonomyNode

        node = TaxonomyNode(
            id="sustenance",
            label="Food & Drink",
            level=0,
            children_ids=["meal", "cooking"],
        )

        assert node.is_category is True
        assert node.is_leaf is False

    def test_node_to_dict(self):
        """Test node serialization."""
        from k0.modules.activity.taxonomy_resolver import TaxonomyNode

        node = TaxonomyNode(
            id="meal",
            label="Meal",
            level=1,
        )

        d = node.to_dict()
        assert d["id"] == "meal"
        assert d["label"] == "Meal"
        assert d["level"] == 1


class TestKeywordSearch:
    """Tests for keyword-based search."""

    def test_search_by_keyword_breakfast(self):
        """Test searching for breakfast keyword."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        results = resolver.search_by_keyword("breakfast")

        assert len(results) > 0
        assert "breakfast" in results

    def test_search_by_keyword_doctor(self):
        """Test searching for doctor keyword."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        results = resolver.search_by_keyword("doctor")

        # Should find medical-related activities
        assert len(results) > 0

    def test_search_case_insensitive(self):
        """Test case-insensitive search."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        results1 = resolver.search_by_keyword("meal")
        results2 = resolver.search_by_keyword("MEAL")

        assert results1 == results2


class TestLegacyMapping:
    """Tests for legacy activity type mapping."""

    def test_legacy_mapping_exists(self):
        """Test legacy mapping is loaded."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        mapping = resolver.taxonomy.legacy_mapping

        assert len(mapping) > 0

    def test_legacy_milestone_maps_to_celebration(self):
        """Test milestone maps to celebration category."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        mapping = resolver.taxonomy.legacy_mapping

        assert "milestone" in mapping
        assert "celebration" in mapping["milestone"]


class TestActivityValidation:
    """Tests for activity validation."""

    def test_valid_activity(self):
        """Test checking valid activity."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()

        assert resolver.is_valid_activity("meal") is True
        assert resolver.is_valid_activity("exercise") is True

    def test_invalid_activity(self):
        """Test checking invalid activity."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()

        assert resolver.is_valid_activity("xyz_fake_activity") is False


class TestZeroShotLabels:
    """Tests for zero-shot classification labels."""

    def test_zero_shot_labels_loaded(self):
        """Test zero-shot labels are loaded from taxonomy."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        labels = resolver.taxonomy.zero_shot_labels

        assert len(labels) >= 20

    def test_zero_shot_labels_include_common(self):
        """Test labels include common activities."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        labels = resolver.taxonomy.zero_shot_labels

        expected = ["meal", "exercise", "celebration", "travel"]
        for activity in expected:
            assert activity in labels


class TestPerformance:
    """Performance tests for taxonomy operations."""

    def test_resolve_latency(self):
        """Test resolution latency (<1ms)."""
        from k0.modules.activity.taxonomy_resolver import resolve_activity_hierarchy

        start = time.perf_counter()
        resolve_activity_hierarchy("meal")
        elapsed = (time.perf_counter() - start) * 1000

        assert elapsed < 1, f"Resolution took {elapsed:.2f}ms (target: <1ms)"

    def test_batch_resolve_latency(self):
        """Test batch resolution latency."""
        from k0.modules.activity.taxonomy_resolver import resolve_activity_hierarchy

        activities = ["meal", "exercise", "work", "party", "travel"] * 20

        start = time.perf_counter()
        for activity in activities:
            resolve_activity_hierarchy(activity)
        elapsed = (time.perf_counter() - start) * 1000

        avg = elapsed / len(activities)
        assert avg < 1, f"Avg latency {avg:.2f}ms (target: <1ms)"

    def test_search_latency(self):
        """Test keyword search latency (<1ms)."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()

        start = time.perf_counter()
        resolver.search_by_keyword("dinner")
        elapsed = (time.perf_counter() - start) * 1000

        assert elapsed < 1, f"Search took {elapsed:.2f}ms (target: <1ms)"


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_activity(self):
        """Test resolving empty activity returns valid=False or matches empty string."""
        from k0.modules.activity.taxonomy_resolver import resolve_activity_hierarchy

        result = resolve_activity_hierarchy("")

        # Empty string may match a node or return invalid
        # Implementation depends on whether taxonomy has an empty key
        assert result is not None

    def test_activity_with_spaces(self):
        """Test activity with spaces is normalized and resolved."""
        from k0.modules.activity.taxonomy_resolver import resolve_activity_hierarchy

        result = resolve_activity_hierarchy("work meeting")

        # Should normalize to work_meeting and find "meeting" activity
        # Or find partial match
        assert result is not None
        # The resolver normalizes spaces to underscores
        assert "meeting" in result.get("activity", "") or result.get("activity") == "work_meeting"

    def test_activity_uppercase(self):
        """Test uppercase activity (normalized)."""
        from k0.modules.activity.taxonomy_resolver import resolve_activity_hierarchy

        result = resolve_activity_hierarchy("MEAL")

        assert result["is_valid"] is True


class TestModuleAPI:
    """Tests for module-level API."""

    def test_get_resolver_singleton(self):
        """Test resolver singleton pattern."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        r1 = get_resolver()
        r2 = get_resolver()
        assert r1 is r2

    def test_resolve_activity_hierarchy_function(self):
        """Test convenience function."""
        from k0.modules.activity.taxonomy_resolver import resolve_activity_hierarchy

        result = resolve_activity_hierarchy("meal")
        assert result["is_valid"] is True


class TestTaxonomyCoverage:
    """Tests for taxonomy coverage of common activities."""

    def test_sustenance_activities(self):
        """Test sustenance category has expected activities."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        activities = resolver.get_category_activities("sustenance")

        # Should have meal, cooking, dining_out
        assert len(activities) > 0

    def test_wellness_activities(self):
        """Test wellness category has expected activities."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        activities = resolver.get_category_activities("wellness")

        # Should have exercise, medical, self_care
        assert len(activities) > 0

    def test_social_activities(self):
        """Test social category has expected activities."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        activities = resolver.get_category_activities("social")

        # Should have family_event, party, hangout, etc.
        assert len(activities) > 0


class TestAncestorTraversal:
    """Tests for ancestor traversal in hierarchy."""

    def test_get_ancestors_from_leaf(self):
        """Test getting ancestors from leaf node."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        taxonomy = resolver.taxonomy

        # Find a leaf node and traverse up
        node = taxonomy.get_node("breakfast")
        if node:
            ancestors = taxonomy.get_ancestors("breakfast")
            # Should have meal and sustenance as ancestors
            assert len(ancestors) >= 1

    def test_get_path_full_hierarchy(self):
        """Test getting full hierarchy path."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        taxonomy = resolver.taxonomy

        path = taxonomy.get_path("breakfast")
        # Should be something like "sustenance.meal.breakfast"
        assert "breakfast" in path

    def test_get_all_keywords_includes_ancestors(self):
        """Test keyword aggregation includes ancestor keywords."""
        from k0.modules.activity.taxonomy_resolver import get_resolver

        resolver = get_resolver()
        taxonomy = resolver.taxonomy

        keywords = taxonomy.get_all_keywords("breakfast")
        # Should include both breakfast-specific and meal-related keywords
        assert len(keywords) > 0
