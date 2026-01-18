"""
Tests for SubtypeClassifier — GAP-005.

Tests fine-grained subtype classification for:
- st_sem.pattern_subtype
- st_kg_dom.entity_subtype
"""

from k0.modules.consolidation.algorithms.subtype_classifier import (
    EMOTIONAL_KEYWORDS,
    LESSON_KEYWORDS,
    ROUTINE_KEYWORDS,
    THEME_KEYWORDS,
    EntityClassificationInput,
    EntitySubtype,
    EntitySubtypeClassifier,
    KeywordDatabase,
    PatternClassificationInput,
    PatternSubtype,
    PatternSubtypeClassifier,
    SubtypeClassifier,
    get_subtype_classifier,
)

# =============================================================================
# KEYWORD DATABASE TESTS
# =============================================================================


class TestKeywordDatabase:
    """Tests for KeywordDatabase."""

    def test_match_single_keyword(self):
        """Matches text with single keyword."""
        db = KeywordDatabase(
            keywords={
                "HEALTH": frozenset({"health", "exercise", "doctor"}),
                "WORK": frozenset({"work", "office", "meeting"}),
            }
        )

        result = db.match("I went to the doctor today")
        assert result == "HEALTH"

    def test_match_multiple_keywords_picks_highest(self):
        """Picks subtype with most keyword matches."""
        db = KeywordDatabase(
            keywords={
                "HEALTH": frozenset({"health", "exercise", "doctor"}),
                "WORK": frozenset({"work", "office", "meeting", "deadline"}),
            }
        )

        # Two work keywords, one health keyword
        result = db.match("Work meeting at the office, then doctor")
        assert result == "WORK"  # 3 matches vs 1

    def test_match_no_keywords(self):
        """Returns None when no keywords match."""
        db = KeywordDatabase(
            keywords={
                "HEALTH": frozenset({"health", "exercise"}),
            }
        )

        result = db.match("I watched a movie yesterday")
        assert result is None

    def test_match_empty_text(self):
        """Returns None for empty text."""
        db = KeywordDatabase(
            keywords={
                "HEALTH": frozenset({"health"}),
            }
        )

        assert db.match("") is None
        assert db.match(None) is None  # type: ignore

    def test_match_case_insensitive(self):
        """Matching is case insensitive."""
        db = KeywordDatabase(
            keywords={
                "HEALTH": frozenset({"health", "exercise"}),
            }
        )

        assert db.match("HEALTH is important") == "HEALTH"
        assert db.match("My Exercise routine") == "HEALTH"


# =============================================================================
# THEME KEYWORDS TESTS
# =============================================================================


class TestThemeKeywords:
    """Tests for THEME_KEYWORDS database."""

    def test_health_theme(self):
        """Detects health-related themes."""
        result = THEME_KEYWORDS.match("Went to the gym for a workout")
        assert result == PatternSubtype.HEALTH_THEME.value

    def test_work_theme(self):
        """Detects work-related themes."""
        result = THEME_KEYWORDS.match("Had a meeting with the boss about the project deadline")
        assert result == PatternSubtype.WORK_THEME.value

    def test_relationship_theme(self):
        """Detects relationship themes."""
        result = THEME_KEYWORDS.match("Called mom to talk about family plans")
        assert result == PatternSubtype.RELATIONSHIP_THEME.value

    def test_finance_theme(self):
        """Detects finance themes."""
        result = THEME_KEYWORDS.match("Reviewed budget and savings for retirement")
        assert result == PatternSubtype.FINANCE_THEME.value

    def test_leisure_theme(self):
        """Detects leisure themes."""
        result = THEME_KEYWORDS.match("Watched a great movie and read a book")
        assert result == PatternSubtype.LEISURE_THEME.value

    def test_learning_theme(self):
        """Detects learning themes."""
        result = THEME_KEYWORDS.match("Taking an online course to learn new skills")
        assert result == PatternSubtype.LEARNING_THEME.value


# =============================================================================
# ROUTINE KEYWORDS TESTS
# =============================================================================


class TestRoutineKeywords:
    """Tests for ROUTINE_KEYWORDS database."""

    def test_morning_routine(self):
        """Detects morning routines."""
        result = ROUTINE_KEYWORDS.match("Wake up, coffee, breakfast, shower")
        assert result == PatternSubtype.MORNING_ROUTINE.value

    def test_evening_routine(self):
        """Detects evening routines."""
        result = ROUTINE_KEYWORDS.match("Dinner at home, relax, bed")
        assert result == PatternSubtype.EVENING_ROUTINE.value

    def test_exercise_routine(self):
        """Detects exercise routines."""
        result = ROUTINE_KEYWORDS.match("Gym workout with cardio and weights")
        assert result == PatternSubtype.EXERCISE_ROUTINE.value

    def test_work_routine(self):
        """Detects work routines."""
        result = ROUTINE_KEYWORDS.match("Office meeting, email, project tasks")
        assert result == PatternSubtype.WORK_ROUTINE.value

    def test_social_routine(self):
        """Detects social routines."""
        result = ROUTINE_KEYWORDS.match("Coffee with friend, dinner visit")
        assert result == PatternSubtype.SOCIAL_ROUTINE.value


# =============================================================================
# LESSON KEYWORDS TESTS
# =============================================================================


class TestLessonKeywords:
    """Tests for LESSON_KEYWORDS database."""

    def test_cautionary_tale(self):
        """Detects cautionary tales."""
        result = LESSON_KEYWORDS.match("That was a mistake I regret. Should have avoided it.")
        assert result == PatternSubtype.CAUTIONARY_TALE.value

    def test_best_practice(self):
        """Detects best practices."""
        result = LESSON_KEYWORDS.match("This strategy worked really well. I recommend it.")
        assert result == PatternSubtype.BEST_PRACTICE.value

    def test_insight(self):
        """Detects insights."""
        result = LESSON_KEYWORDS.match("I realized there's an interesting pattern here.")
        assert result == PatternSubtype.INSIGHT.value


# =============================================================================
# EMOTIONAL KEYWORDS TESTS
# =============================================================================


class TestEmotionalKeywords:
    """Tests for EMOTIONAL_KEYWORDS database."""

    def test_stress_pattern(self):
        """Detects stress patterns."""
        result = EMOTIONAL_KEYWORDS.match("Feeling overwhelmed and stressed by pressure")
        assert result == PatternSubtype.STRESS_PATTERN.value

    def test_joy_pattern(self):
        """Detects joy patterns."""
        result = EMOTIONAL_KEYWORDS.match("So happy and grateful for this wonderful day")
        assert result == PatternSubtype.JOY_PATTERN.value

    def test_anxiety_pattern(self):
        """Detects anxiety patterns."""
        result = EMOTIONAL_KEYWORDS.match("Worried and anxious about uncertain future")
        assert result == PatternSubtype.ANXIETY_PATTERN.value

    def test_burnout_pattern(self):
        """Detects burnout patterns."""
        result = EMOTIONAL_KEYWORDS.match("Completely exhausted and drained, need a break")
        assert result == PatternSubtype.BURNOUT_PATTERN.value


# =============================================================================
# PATTERN SUBTYPE CLASSIFIER TESTS
# =============================================================================


class TestPatternSubtypeClassifier:
    """Tests for PatternSubtypeClassifier."""

    def test_classify_theme_from_name(self):
        """Classifies THEME subtype from pattern name."""
        classifier = PatternSubtypeClassifier()

        input_data = PatternClassificationInput(
            pattern_type="THEME",
            pattern_name="Weekly gym workout routine",
        )

        result = classifier.classify(input_data)
        assert result == PatternSubtype.HEALTH_THEME.value

    def test_classify_theme_from_description(self):
        """Classifies THEME subtype from description."""
        classifier = PatternSubtypeClassifier()

        input_data = PatternClassificationInput(
            pattern_type="THEME",
            pattern_name="Pattern A",
            pattern_description="Discussions about career and job promotions",
        )

        result = classifier.classify(input_data)
        assert result == PatternSubtype.WORK_THEME.value

    def test_classify_theme_from_source_texts(self):
        """Classifies THEME subtype from source texts."""
        classifier = PatternSubtypeClassifier()

        input_data = PatternClassificationInput(
            pattern_type="THEME",
            pattern_name="Family pattern",
            source_texts=[
                "Called mom today",
                "Visited dad over the weekend",
                "Family dinner with brother",
            ],
        )

        result = classifier.classify(input_data)
        assert result == PatternSubtype.RELATIONSHIP_THEME.value

    def test_classify_routine(self):
        """Classifies ROUTINE subtype."""
        classifier = PatternSubtypeClassifier()

        input_data = PatternClassificationInput(
            pattern_type="ROUTINE",
            pattern_name="Morning coffee and breakfast",
        )

        result = classifier.classify(input_data)
        assert result == PatternSubtype.MORNING_ROUTINE.value

    def test_classify_lesson(self):
        """Classifies LESSON subtype."""
        classifier = PatternSubtypeClassifier()

        input_data = PatternClassificationInput(
            pattern_type="LESSON",
            pattern_name="Learned to always double-check",
            pattern_description="Made a mistake and regretted not checking earlier",
        )

        result = classifier.classify(input_data)
        assert result == PatternSubtype.CAUTIONARY_TALE.value

    def test_classify_goal(self):
        """Classifies GOAL subtype."""
        classifier = PatternSubtypeClassifier()

        input_data = PatternClassificationInput(
            pattern_type="GOAL",
            pattern_name="Get promoted at work",
            pattern_description="Career advancement goal for next year",
        )

        result = classifier.classify(input_data)
        assert result == PatternSubtype.CAREER_GOAL.value

    def test_classify_unknown_type_returns_none(self):
        """Returns None for unknown pattern type."""
        classifier = PatternSubtypeClassifier()

        input_data = PatternClassificationInput(
            pattern_type="UNKNOWN",
            pattern_name="Some pattern",
        )

        result = classifier.classify(input_data)
        assert result is None

    def test_classify_with_fallback(self):
        """Returns fallback when no keywords match."""
        classifier = PatternSubtypeClassifier()

        input_data = PatternClassificationInput(
            pattern_type="THEME",
            pattern_name="xyzabc123",  # No keywords match
        )

        # Without fallback
        result = classifier.classify(input_data)
        assert result is None

        # With fallback
        result = classifier.classify_with_fallback(input_data)
        assert result == PatternSubtype.LEISURE_THEME.value


# =============================================================================
# ENTITY SUBTYPE CLASSIFIER TESTS
# =============================================================================


class TestEntitySubtypeClassifier:
    """Tests for EntitySubtypeClassifier."""

    def test_classify_person_from_relationship(self):
        """Classifies PERSON based on relationship type."""
        classifier = EntitySubtypeClassifier()

        # Family member
        input_data = EntityClassificationInput(
            entity_type="PERSON",
            canonical_name="Sarah",
            relationship_types=["FAMILY"],
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.FAMILY_MEMBER.value

        # Friend
        input_data = EntityClassificationInput(
            entity_type="PERSON",
            canonical_name="Bob",
            relationship_types=["FRIEND"],
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.FRIEND.value

        # Colleague
        input_data = EntityClassificationInput(
            entity_type="PERSON",
            canonical_name="John",
            relationship_types=["COLLEAGUE"],
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.PROFESSIONAL.value

    def test_classify_person_from_name(self):
        """Classifies PERSON based on name indicators."""
        classifier = EntitySubtypeClassifier()

        # Family indicator in name
        input_data = EntityClassificationInput(
            entity_type="PERSON",
            canonical_name="Mom",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.FAMILY_MEMBER.value

        # Another family term
        input_data = EntityClassificationInput(
            entity_type="PERSON",
            canonical_name="Grandma Jones",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.FAMILY_MEMBER.value

    def test_classify_person_professional_from_context(self):
        """Classifies PERSON as professional from work context."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="PERSON",
            canonical_name="Mike",
            contexts=["work meeting", "office discussion"],
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.PROFESSIONAL.value

    def test_classify_person_service_provider(self):
        """Classifies service providers."""
        classifier = EntitySubtypeClassifier()

        # Use "Doctor Smith" (full word) to trigger SERVICE_PROVIDER
        input_data = EntityClassificationInput(
            entity_type="PERSON",
            canonical_name="Doctor Smith",
        )
        result = classifier.classify(input_data)
        # "doctor" matches SERVICE_INDICATORS
        assert result == EntitySubtype.SERVICE_PROVIDER.value

    def test_classify_person_professional_title(self):
        """Classifies professional titles like Dr."""
        classifier = EntitySubtypeClassifier()

        # "Dr." only yields "dr" token which matches PROFESSIONAL_INDICATORS
        input_data = EntityClassificationInput(
            entity_type="PERSON",
            canonical_name="Dr. Smith",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.PROFESSIONAL.value

    def test_classify_person_default_acquaintance(self):
        """Defaults to ACQUAINTANCE for unknown persons."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="PERSON",
            canonical_name="Random Person XYZ",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.ACQUAINTANCE.value

    def test_classify_location_home(self):
        """Classifies HOME locations."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="LOCATION",
            canonical_name="Home",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.HOME.value

    def test_classify_location_workplace(self):
        """Classifies WORKPLACE locations."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="LOCATION",
            canonical_name="Office Building",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.WORKPLACE.value

    def test_classify_location_recreational(self):
        """Classifies RECREATIONAL locations."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="LOCATION",
            canonical_name="Central Park",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.RECREATIONAL.value

    def test_classify_location_healthcare(self):
        """Classifies HEALTHCARE locations."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="LOCATION",
            canonical_name="City Hospital",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.HEALTHCARE.value

    def test_classify_location_commercial(self):
        """Classifies COMMERCIAL locations."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="LOCATION",
            canonical_name="Shopping Mall",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.COMMERCIAL.value

    def test_classify_location_transit(self):
        """Classifies TRANSIT locations."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="LOCATION",
            canonical_name="JFK Airport",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.TRANSIT.value

    def test_classify_organization_employer(self):
        """Classifies employer organizations."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="ORGANIZATION",
            canonical_name="My Company",
            contexts=["employer", "work"],
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.EMPLOYER.value

    def test_classify_organization_school(self):
        """Classifies educational organizations."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="ORGANIZATION",
            canonical_name="State University",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.SCHOOL.value

    def test_classify_organization_government(self):
        """Classifies government organizations."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="ORGANIZATION",
            canonical_name="Federal Agency",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.GOVERNMENT.value

    def test_classify_thing_vehicle(self):
        """Classifies THING as vehicle."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="THING",
            canonical_name="My Car",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.VEHICLE.value

    def test_classify_thing_device(self):
        """Classifies THING as device."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="THING",
            canonical_name="New Phone",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.DEVICE.value

    def test_classify_event_holiday(self):
        """Classifies EVENT as holiday."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="EVENT",
            canonical_name="Christmas 2025",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.HOLIDAY.value

    def test_classify_event_celebration(self):
        """Classifies EVENT as celebration."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="EVENT",
            canonical_name="Birthday Party",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.CELEBRATION.value

    def test_classify_event_meeting(self):
        """Classifies EVENT as meeting."""
        classifier = EntitySubtypeClassifier()

        input_data = EntityClassificationInput(
            entity_type="EVENT",
            canonical_name="Team Sync Meeting",
        )
        result = classifier.classify(input_data)
        assert result == EntitySubtype.MEETING.value


# =============================================================================
# UNIFIED SUBTYPE CLASSIFIER TESTS
# =============================================================================


class TestSubtypeClassifier:
    """Tests for unified SubtypeClassifier."""

    def test_classify_pattern_convenience(self):
        """Tests convenience method for pattern classification."""
        classifier = SubtypeClassifier()

        result = classifier.classify_pattern(
            pattern_type="THEME",
            pattern_name="Going to the gym regularly",
        )
        assert result == PatternSubtype.HEALTH_THEME.value

    def test_classify_entity_convenience(self):
        """Tests convenience method for entity classification."""
        classifier = SubtypeClassifier()

        result = classifier.classify_entity(
            entity_type="PERSON",
            canonical_name="Mom",
        )
        assert result == EntitySubtype.FAMILY_MEMBER.value

    def test_singleton(self):
        """Tests singleton pattern."""
        c1 = get_subtype_classifier()
        c2 = get_subtype_classifier()
        assert c1 is c2


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestSubtypeClassifierIntegration:
    """Integration tests for SubtypeClassifier."""

    def test_real_world_theme_classification(self):
        """Tests with real-world-like theme patterns."""
        classifier = get_subtype_classifier()

        # Health theme from real episode
        result = classifier.classify_pattern(
            pattern_type="THEME",
            pattern_name="Morning workout routine",
            source_texts=[
                "Went to the gym at 6am",
                "Did cardio and weights",
                "Feeling energized after exercise",
            ],
        )
        assert result == PatternSubtype.HEALTH_THEME.value

        # Work theme
        result = classifier.classify_pattern(
            pattern_type="THEME",
            pattern_name="Project deadline stress",
            source_texts=[
                "Meeting with boss about project",
                "Deadline is approaching",
                "Working late at office",
            ],
        )
        assert result == PatternSubtype.WORK_THEME.value

    def test_real_world_entity_classification(self):
        """Tests with real-world-like entities."""
        classifier = get_subtype_classifier()

        # Family member from relationship
        result = classifier.classify_entity(
            entity_type="PERSON",
            canonical_name="Sarah Johnson",
            relationship_types=["FAMILY"],
        )
        assert result == EntitySubtype.FAMILY_MEMBER.value

        # Location from name
        result = classifier.classify_entity(
            entity_type="LOCATION",
            canonical_name="Starbucks on Main Street",
        )
        # No specific match, returns None
        assert result is None

        # Location with context
        result = classifier.classify_entity(
            entity_type="LOCATION",
            canonical_name="Building A",
            contexts=["work", "office", "meeting room"],
        )
        assert result == EntitySubtype.WORKPLACE.value

    def test_classification_handles_edge_cases(self):
        """Tests edge case handling."""
        classifier = get_subtype_classifier()

        # Empty pattern name
        result = classifier.classify_pattern(
            pattern_type="THEME",
            pattern_name="",
        )
        assert result is None

        # Unknown entity type
        result = classifier.classify_entity(
            entity_type="UNKNOWN",
            canonical_name="Something",
        )
        assert result is None

        # Case insensitivity
        result = classifier.classify_pattern(
            pattern_type="theme",  # lowercase
            pattern_name="HEALTH and EXERCISE",
        )
        assert result == PatternSubtype.HEALTH_THEME.value
