"""
Tests for ImmunityChecker.

Issue: 4.3.9
Spec Reference: Dossier §4.4.3.1 (lines 3887-3980)
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.algorithms.immunity_checker import (
    ATTRIBUTE_LEVEL_IMMUNITY,
    ENTITY_LEVEL_IMMUNE_TYPES,
    IMMUNITY_ONTOLOGY,
    ImmunityChecker,
    ImmunityCheckerConfig,
    ImmunityLevel,
    ImmunityMetricsCollector,
    ImmunityResult,
    auto_mark_immunity,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def checker() -> ImmunityChecker:
    """Default immunity checker fixture."""
    return ImmunityChecker()


@pytest.fixture
def disabled_checker() -> ImmunityChecker:
    """Checker with immunity disabled."""
    return ImmunityChecker(config=ImmunityCheckerConfig(enabled=False))


# =============================================================================
# 4.3.9.T1: FAMILY_MEMBER Always Immune
# =============================================================================


class TestFamilyMemberImmunity:
    """Test FAMILY_MEMBER entity-level immunity."""

    def test_family_member_always_immune(self, checker: ImmunityChecker) -> None:
        """FAMILY_MEMBER returns entity-level immunity."""
        result = checker.should_mark_immune(
            entity_type="FAMILY_MEMBER",
            entity_attributes={"name": "Mom", "relationship": "mother"},
        )

        assert result.is_immune is True
        assert result.level == ImmunityLevel.ENTITY
        assert "FAMILY_MEMBER" in result.reason
        assert "entity immunity" in result.reason.lower()

    def test_family_member_empty_attributes(self, checker: ImmunityChecker) -> None:
        """FAMILY_MEMBER immune even with empty attributes."""
        result = checker.should_mark_immune(
            entity_type="FAMILY_MEMBER",
            entity_attributes={},
        )

        assert result.is_immune is True
        assert result.level == ImmunityLevel.ENTITY

    def test_family_member_lowercase(self, checker: ImmunityChecker) -> None:
        """Case-insensitive entity type matching."""
        result = checker.should_mark_immune(
            entity_type="family_member",
            entity_attributes={"name": "Dad"},
        )

        assert result.is_immune is True

    def test_family_member_in_entity_level_set(self) -> None:
        """Verify FAMILY_MEMBER in entity-level immune set."""
        assert "FAMILY_MEMBER" in ENTITY_LEVEL_IMMUNE_TYPES


# =============================================================================
# 4.3.9.T2: PERSON with Birthday Immune
# =============================================================================


class TestPersonBirthdayImmunity:
    """Test PERSON attribute-level immunity."""

    def test_person_with_birthday_immune(self, checker: ImmunityChecker) -> None:
        """PERSON with birthday attribute is immune."""
        result = checker.should_mark_immune(
            entity_type="PERSON",
            entity_attributes={"birthday": "1990-01-01", "occupation": "engineer"},
        )

        assert result.is_immune is True
        assert result.level == ImmunityLevel.ATTRIBUTE
        assert "birthday" in result.protected_attributes

    def test_person_with_name_immune(self, checker: ImmunityChecker) -> None:
        """PERSON with name attribute is immune."""
        result = checker.should_mark_immune(
            entity_type="PERSON",
            entity_attributes={"name": "John Doe"},
        )

        assert result.is_immune is True
        assert "name" in result.protected_attributes

    def test_person_with_relationship_immune(self, checker: ImmunityChecker) -> None:
        """PERSON with relationship_to_user is immune."""
        result = checker.should_mark_immune(
            entity_type="PERSON",
            entity_attributes={"relationship_to_user": "friend"},
        )

        assert result.is_immune is True
        assert "relationship_to_user" in result.protected_attributes


# =============================================================================
# 4.3.9.T3: PERSON Without Protected Attrs Not Immune
# =============================================================================


class TestPersonNotImmune:
    """Test PERSON without protected attributes."""

    def test_person_without_protected_attrs_not_immune(self, checker: ImmunityChecker) -> None:
        """PERSON with only occupation is not immune."""
        result = checker.should_mark_immune(
            entity_type="PERSON",
            entity_attributes={"occupation": "engineer", "company": "ACME"},
        )

        assert result.is_immune is False
        assert result.level == ImmunityLevel.NONE
        assert len(result.protected_attributes) == 0

    def test_person_with_empty_birthday_not_immune(self, checker: ImmunityChecker) -> None:
        """PERSON with empty birthday value is not immune."""
        result = checker.should_mark_immune(
            entity_type="PERSON",
            entity_attributes={"birthday": "", "name": None},
        )

        assert result.is_immune is False

    def test_person_with_none_values_not_immune(self, checker: ImmunityChecker) -> None:
        """PERSON with None protected values is not immune."""
        result = checker.should_mark_immune(
            entity_type="PERSON",
            entity_attributes={"birthday": None, "name": None},
        )

        assert result.is_immune is False


# =============================================================================
# 4.3.9.T4: PLACE with Home Address Immune
# =============================================================================


class TestPlaceImmunity:
    """Test PLACE attribute-level immunity."""

    def test_place_with_home_address_immune(self, checker: ImmunityChecker) -> None:
        """PLACE with home_address is immune."""
        result = checker.should_mark_immune(
            entity_type="PLACE",
            entity_attributes={"home_address": "123 Main St"},
        )

        assert result.is_immune is True
        assert result.level == ImmunityLevel.ATTRIBUTE
        assert "home_address" in result.protected_attributes

    def test_place_with_work_address_immune(self, checker: ImmunityChecker) -> None:
        """PLACE with work_address is immune."""
        result = checker.should_mark_immune(
            entity_type="PLACE",
            entity_attributes={"work_address": "456 Office Blvd"},
        )

        assert result.is_immune is True
        assert "work_address" in result.protected_attributes

    def test_place_without_protected_not_immune(self, checker: ImmunityChecker) -> None:
        """PLACE with only vacation_spot is not immune."""
        result = checker.should_mark_immune(
            entity_type="PLACE",
            entity_attributes={"vacation_spot": "Hawaii"},
        )

        assert result.is_immune is False


# =============================================================================
# 4.3.9.T5: EVENT with Milestone Date Immune
# =============================================================================


class TestEventImmunity:
    """Test EVENT attribute-level immunity."""

    def test_event_with_wedding_date_immune(self, checker: ImmunityChecker) -> None:
        """EVENT with wedding_date is immune."""
        result = checker.should_mark_immune(
            entity_type="EVENT",
            entity_attributes={"wedding_date": "2020-06-15"},
        )

        assert result.is_immune is True
        assert "wedding_date" in result.protected_attributes

    def test_event_with_birth_date_immune(self, checker: ImmunityChecker) -> None:
        """EVENT with birth_date is immune."""
        result = checker.should_mark_immune(
            entity_type="EVENT",
            entity_attributes={"birth_date": "2021-03-10"},
        )

        assert result.is_immune is True
        assert "birth_date" in result.protected_attributes

    def test_event_with_death_date_immune(self, checker: ImmunityChecker) -> None:
        """EVENT with death_date is immune."""
        result = checker.should_mark_immune(
            entity_type="EVENT",
            entity_attributes={"death_date": "2022-01-01"},
        )

        assert result.is_immune is True
        assert "death_date" in result.protected_attributes

    def test_regular_event_not_immune(self, checker: ImmunityChecker) -> None:
        """Regular EVENT without milestone is not immune."""
        result = checker.should_mark_immune(
            entity_type="EVENT",
            entity_attributes={"meeting": "Team standup", "date": "2024-01-15"},
        )

        assert result.is_immune is False


# =============================================================================
# 4.3.9.T6: Unknown Entity Type Not Immune
# =============================================================================


class TestUnknownEntityType:
    """Test unknown entity types."""

    def test_unknown_entity_type_not_immune(self, checker: ImmunityChecker) -> None:
        """WIDGET entity type returns not immune."""
        result = checker.should_mark_immune(
            entity_type="WIDGET",
            entity_attributes={"name": "My Widget", "color": "blue"},
        )

        assert result.is_immune is False
        assert result.level == ImmunityLevel.NONE
        assert "not in ontology" in result.reason

    def test_empty_entity_type(self, checker: ImmunityChecker) -> None:
        """Empty entity type returns not immune."""
        result = checker.should_mark_immune(
            entity_type="",
            entity_attributes={},
        )

        assert result.is_immune is False


# =============================================================================
# 4.3.9.T7: ORGANIZATION Immunity
# =============================================================================


class TestOrganizationImmunity:
    """Test ORGANIZATION attribute-level immunity."""

    def test_organization_with_employer_immune(self, checker: ImmunityChecker) -> None:
        """ORGANIZATION with employer is immune."""
        result = checker.should_mark_immune(
            entity_type="ORGANIZATION",
            entity_attributes={"employer": "ACME Corp"},
        )

        assert result.is_immune is True
        assert "employer" in result.protected_attributes

    def test_organization_with_school_immune(self, checker: ImmunityChecker) -> None:
        """ORGANIZATION with school is immune."""
        result = checker.should_mark_immune(
            entity_type="ORGANIZATION",
            entity_attributes={"school": "MIT"},
        )

        assert result.is_immune is True
        assert "school" in result.protected_attributes


# =============================================================================
# 4.3.9.T8: CONCEPT Immunity
# =============================================================================


class TestConceptImmunity:
    """Test CONCEPT attribute-level immunity."""

    def test_concept_with_core_value_immune(self, checker: ImmunityChecker) -> None:
        """CONCEPT with core_value is immune."""
        result = checker.should_mark_immune(
            entity_type="CONCEPT",
            entity_attributes={"core_value": "integrity"},
        )

        assert result.is_immune is True
        assert "core_value" in result.protected_attributes

    def test_concept_with_religion_immune(self, checker: ImmunityChecker) -> None:
        """CONCEPT with religion is immune."""
        result = checker.should_mark_immune(
            entity_type="CONCEPT",
            entity_attributes={"religion": "Buddhism"},
        )

        assert result.is_immune is True

    def test_concept_with_political_immune(self, checker: ImmunityChecker) -> None:
        """CONCEPT with political_affiliation is immune."""
        result = checker.should_mark_immune(
            entity_type="CONCEPT",
            entity_attributes={"political_affiliation": "Independent"},
        )

        assert result.is_immune is True


# =============================================================================
# 4.3.9.T9: Config Disabled
# =============================================================================


class TestConfigDisabled:
    """Test immunity when disabled."""

    def test_immunity_disabled_returns_false(self, disabled_checker: ImmunityChecker) -> None:
        """Disabled checker returns not immune."""
        result = disabled_checker.should_mark_immune(
            entity_type="FAMILY_MEMBER",
            entity_attributes={"name": "Mom"},
        )

        assert result.is_immune is False
        assert "disabled" in result.reason.lower()

    def test_family_member_disabled_by_config(self) -> None:
        """FAMILY_MEMBER immunity can be disabled."""
        config = ImmunityCheckerConfig(
            enabled=True,
            family_member_immune=False,
        )
        checker = ImmunityChecker(config=config)

        result = checker.should_mark_immune(
            entity_type="FAMILY_MEMBER",
            entity_attributes={"name": "Mom"},
        )

        assert result.is_immune is False
        assert "disabled by config" in result.reason.lower()

    def test_milestone_events_disabled_by_config(self) -> None:
        """Milestone events immunity can be disabled."""
        config = ImmunityCheckerConfig(
            enabled=True,
            milestone_events_immune=False,
        )
        checker = ImmunityChecker(config=config)

        result = checker.should_mark_immune(
            entity_type="EVENT",
            entity_attributes={"wedding_date": "2020-06-15"},
        )

        assert result.is_immune is False


# =============================================================================
# 4.3.9.T10: Helper Methods
# =============================================================================


class TestHelperMethods:
    """Test helper methods."""

    def test_get_immune_entity_types(self, checker: ImmunityChecker) -> None:
        """Returns set of entity-level immune types."""
        immune_types = checker.get_immune_entity_types()

        assert "FAMILY_MEMBER" in immune_types
        assert "PERSON" not in immune_types  # Attribute-level only

    def test_get_protected_attributes_person(self, checker: ImmunityChecker) -> None:
        """Returns protected attributes for PERSON."""
        attrs = checker.get_protected_attributes("PERSON")

        assert "birthday" in attrs
        assert "name" in attrs
        assert "relationship_to_user" in attrs

    def test_get_protected_attributes_family_member(self, checker: ImmunityChecker) -> None:
        """Returns '*' for entity-level immune types."""
        attrs = checker.get_protected_attributes("FAMILY_MEMBER")

        assert attrs == ["*"]

    def test_get_protected_attributes_unknown(self, checker: ImmunityChecker) -> None:
        """Returns empty list for unknown types."""
        attrs = checker.get_protected_attributes("WIDGET")

        assert attrs == []

    def test_is_entity_type_immune(self, checker: ImmunityChecker) -> None:
        """Test is_entity_type_immune method."""
        assert checker.is_entity_type_immune("FAMILY_MEMBER") is True
        assert checker.is_entity_type_immune("PERSON") is False
        assert checker.is_entity_type_immune("UNKNOWN") is False


# =============================================================================
# 4.3.9.T11: Auto-Mark Helper
# =============================================================================


class TestAutoMarkHelper:
    """Test auto_mark_immunity helper function."""

    def test_auto_mark_family_member(self) -> None:
        """Auto-mark returns True for FAMILY_MEMBER."""
        result = auto_mark_immunity(
            entity_type="FAMILY_MEMBER",
            attributes={"name": "Sister"},
        )

        assert result is True

    def test_auto_mark_person_with_birthday(self) -> None:
        """Auto-mark returns True for PERSON with birthday."""
        result = auto_mark_immunity(
            entity_type="PERSON",
            attributes={"birthday": "1990-01-01"},
        )

        assert result is True

    def test_auto_mark_regular_person(self) -> None:
        """Auto-mark returns False for regular PERSON."""
        result = auto_mark_immunity(
            entity_type="PERSON",
            attributes={"occupation": "engineer"},
        )

        assert result is False


# =============================================================================
# 4.3.9.T12: ImmunityResult
# =============================================================================


class TestImmunityResult:
    """Test ImmunityResult dataclass."""

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        result = ImmunityResult(
            is_immune=True,
            level=ImmunityLevel.ATTRIBUTE,
            reason="Protected attributes present",
            protected_attributes=("birthday", "name"),
        )

        d = result.to_dict()

        assert d["is_immune"] is True
        assert d["level"] == "attribute"
        assert d["reason"] == "Protected attributes present"
        assert d["protected_attributes"] == ["birthday", "name"]

    def test_frozen(self) -> None:
        """ImmunityResult is immutable."""
        result = ImmunityResult(
            is_immune=True,
            level=ImmunityLevel.ENTITY,
            reason="Test",
        )

        with pytest.raises(AttributeError):
            result.is_immune = False  # type: ignore


# =============================================================================
# 4.3.9.T13: Ontology Constants
# =============================================================================


class TestOntologyConstants:
    """Test ontology constants from spec."""

    def test_entity_level_immune_types(self) -> None:
        """Verify entity-level immune types from spec."""
        assert "FAMILY_MEMBER" in ENTITY_LEVEL_IMMUNE_TYPES

    def test_person_attributes(self) -> None:
        """Verify PERSON protected attributes from spec."""
        person_attrs = ATTRIBUTE_LEVEL_IMMUNITY["PERSON"]
        assert "birthday" in person_attrs
        assert "name" in person_attrs
        assert "relationship_to_user" in person_attrs

    def test_place_attributes(self) -> None:
        """Verify PLACE protected attributes from spec."""
        place_attrs = ATTRIBUTE_LEVEL_IMMUNITY["PLACE"]
        assert "home_address" in place_attrs
        assert "work_address" in place_attrs

    def test_event_attributes(self) -> None:
        """Verify EVENT protected attributes from spec."""
        event_attrs = ATTRIBUTE_LEVEL_IMMUNITY["EVENT"]
        assert "wedding_date" in event_attrs
        assert "birth_date" in event_attrs
        assert "death_date" in event_attrs

    def test_ontology_complete(self) -> None:
        """Verify all entity types in ontology."""
        expected_types = {"FAMILY_MEMBER", "PERSON", "PLACE", "EVENT", "ORGANIZATION", "CONCEPT"}
        assert set(IMMUNITY_ONTOLOGY.keys()) == expected_types


# =============================================================================
# 4.3.9.T14: Metrics Collector
# =============================================================================


class TestMetricsCollector:
    """Test ImmunityMetricsCollector."""

    def test_record_auto_marked(self) -> None:
        """Test recording auto-marked entities."""
        collector = ImmunityMetricsCollector()

        collector.record_auto_marked("FAMILY_MEMBER", ImmunityLevel.ENTITY)
        collector.record_auto_marked("FAMILY_MEMBER", ImmunityLevel.ENTITY)
        collector.record_auto_marked("PERSON", ImmunityLevel.ATTRIBUTE)

        assert collector.get_auto_marked_count("FAMILY_MEMBER", ImmunityLevel.ENTITY) == 2
        assert collector.get_auto_marked_count("PERSON", ImmunityLevel.ATTRIBUTE) == 1

    def test_record_decay_skipped(self) -> None:
        """Test recording skipped decay updates."""
        collector = ImmunityMetricsCollector()

        collector.record_decay_skipped("st_epi")
        collector.record_decay_skipped("st_epi")
        collector.record_decay_skipped("st_kg_dom")

        assert collector.get_skipped_count("st_epi") == 2
        assert collector.get_skipped_count("st_kg_dom") == 1

    def test_reset(self) -> None:
        """Test reset clears counters."""
        collector = ImmunityMetricsCollector()

        collector.record_auto_marked("PERSON", ImmunityLevel.ATTRIBUTE)
        collector.record_decay_skipped("st_epi")
        collector.reset()

        assert collector.get_auto_marked_count("PERSON", ImmunityLevel.ATTRIBUTE) == 0
        assert collector.get_skipped_count("st_epi") == 0
