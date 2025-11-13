"""K0 Memory System Schema Definitions.

Defines the 8 memory types and table schemas for the K0 data access layer.
This schema simulates K0's actual memory architecture for the PoC.
"""

from typing import Any

# K0's 8 Memory Types
MEMORY_TYPES: dict[str, dict[str, Any]] = {
    "episodic": {
        "tables": ["diet_logs", "health_events", "activities", "sleep_logs"],
        "description": "Time-stamped personal events and experiences",
    },
    "semantic": {
        "tables": ["food_nutrition", "health_conditions", "medications", "symptoms"],
        "description": "General knowledge and facts",
    },
    "autobiographical": {
        "tables": ["user_profile", "life_events", "family_history"],
        "description": "Personal history and identity",
    },
    "working": {
        "tables": ["recent_conversations", "active_goals", "pending_tasks"],
        "description": "Recent context and short-term memory",
    },
    "prospective": {
        "tables": ["reminders", "appointments", "planned_activities"],
        "description": "Future-oriented intentions and plans",
    },
    "spatial": {
        "tables": ["places_visited", "activity_locations", "home_zones"],
        "description": "Location-based memories",
    },
    "emotional": {
        "tables": ["mood_logs", "stress_events", "emotional_triggers"],
        "description": "Affective states and emotional experiences",
    },
    "procedural": {
        "tables": ["routines", "habit_patterns", "learned_behaviors"],
        "description": "Skills, habits, and learned procedures",
    },
}

# Detailed table schemas with columns and available filters
TABLE_SCHEMAS: dict[str, dict[str, Any]] = {
    # Episodic Memory Tables
    "episodic.diet_logs": {
        "columns": ["id", "timestamp", "food_item", "meal_type", "portion", "location", "notes"],
        "filters": ["food_item", "meal_type", "time_range", "location"],
        "description": "Personal diet and meal history",
    },
    "episodic.health_events": {
        "columns": [
            "id",
            "timestamp",
            "event_type",
            "severity",
            "symptoms",
            "duration_minutes",
            "notes",
        ],
        "filters": ["event_type", "severity", "time_range", "symptoms"],
        "description": "Health incidents and symptoms",
    },
    "episodic.activities": {
        "columns": [
            "id",
            "timestamp",
            "activity_type",
            "duration_minutes",
            "location",
            "intensity",
            "notes",
        ],
        "filters": ["activity_type", "time_range", "location", "intensity"],
        "description": "Physical activities and exercise",
    },
    "episodic.sleep_logs": {
        "columns": ["id", "date", "bedtime", "wake_time", "duration_hours", "quality", "notes"],
        "filters": ["time_range", "quality"],
        "description": "Sleep patterns and quality",
    },
    # Semantic Memory Tables
    "semantic.food_nutrition": {
        "columns": [
            "food_item",
            "calories",
            "protein_g",
            "carbs_g",
            "fat_g",
            "caffeine_mg",
            "acidity",
            "ph_level",
            "gerd_risk",
            "trigger_compounds",
            "notes",
        ],
        "filters": ["food_item", "gerd_risk", "acidity"],
        "description": "Nutritional information database",
    },
    "semantic.health_conditions": {
        "columns": [
            "condition_name",
            "category",
            "symptoms",
            "triggers",
            "treatments",
            "severity_range",
            "chronic",
            "notes",
        ],
        "filters": ["condition_name", "category", "chronic"],
        "description": "Medical conditions database",
    },
    "semantic.medications": {
        "columns": [
            "medication_name",
            "drug_class",
            "purpose",
            "dosage_form",
            "side_effects",
            "interactions",
            "notes",
        ],
        "filters": ["medication_name", "drug_class", "purpose"],
        "description": "Medication information",
    },
    "semantic.symptoms": {
        "columns": [
            "symptom_name",
            "category",
            "severity_range",
            "related_conditions",
            "common_triggers",
            "notes",
        ],
        "filters": ["symptom_name", "category", "related_conditions"],
        "description": "Symptom catalog",
    },
    # Autobiographical Memory Tables
    "autobiographical.user_profile": {
        "columns": [
            "user_id",
            "name",
            "age",
            "gender",
            "height_cm",
            "weight_kg",
            "allergies",
            "chronic_conditions",
            "created_at",
            "updated_at",
        ],
        "filters": ["user_id"],
        "description": "User personal information",
    },
    "autobiographical.life_events": {
        "columns": [
            "id",
            "event_date",
            "event_type",
            "description",
            "significance",
            "location",
            "notes",
        ],
        "filters": ["event_type", "time_range", "significance"],
        "description": "Significant life events",
    },
    "autobiographical.family_history": {
        "columns": ["id", "relation", "condition", "age_of_onset", "severity", "notes"],
        "filters": ["relation", "condition"],
        "description": "Family medical history",
    },
    # Working Memory Tables
    "working.recent_conversations": {
        "columns": [
            "id",
            "timestamp",
            "turn_count",
            "qud",
            "active_referents",
            "pending_specialists",
            "notes",
        ],
        "filters": ["time_range"],
        "description": "Recent conversation state",
    },
    "working.active_goals": {
        "columns": [
            "id",
            "goal",
            "category",
            "priority",
            "status",
            "created_at",
            "target_date",
            "progress_percent",
        ],
        "filters": ["category", "status", "priority"],
        "description": "Current user goals",
    },
    "working.pending_tasks": {
        "columns": [
            "id",
            "task",
            "category",
            "priority",
            "status",
            "created_at",
            "due_date",
            "notes",
        ],
        "filters": ["category", "status", "priority"],
        "description": "Tasks awaiting completion",
    },
    # Prospective Memory Tables
    "prospective.reminders": {
        "columns": [
            "id",
            "reminder_text",
            "reminder_time",
            "category",
            "priority",
            "recurring",
            "status",
            "notes",
        ],
        "filters": ["time_range", "category", "status", "priority"],
        "description": "Future reminders",
    },
    "prospective.appointments": {
        "columns": [
            "id",
            "appointment_type",
            "provider",
            "datetime",
            "location",
            "purpose",
            "status",
            "notes",
        ],
        "filters": ["time_range", "appointment_type", "status"],
        "description": "Scheduled appointments",
    },
    "prospective.planned_activities": {
        "columns": [
            "id",
            "activity",
            "planned_date",
            "category",
            "location",
            "participants",
            "notes",
        ],
        "filters": ["time_range", "category"],
        "description": "Planned future activities",
    },
    # Spatial Memory Tables
    "spatial.places_visited": {
        "columns": [
            "id",
            "place_name",
            "address",
            "category",
            "first_visit",
            "last_visit",
            "visit_count",
            "notes",
        ],
        "filters": ["category", "time_range"],
        "description": "Places user has visited",
    },
    "spatial.activity_locations": {
        "columns": ["id", "activity_type", "location", "frequency", "last_visit", "notes"],
        "filters": ["activity_type"],
        "description": "Locations for specific activities",
    },
    "spatial.home_zones": {
        "columns": ["id", "zone_name", "address", "zone_type", "radius_meters", "notes"],
        "filters": ["zone_type"],
        "description": "Important location zones",
    },
    # Emotional Memory Tables
    "emotional.mood_logs": {
        "columns": ["id", "timestamp", "mood", "energy", "stress_level", "anxiety_level", "notes"],
        "filters": ["time_range", "mood", "stress_level"],
        "description": "Mood and emotional state logs",
    },
    "emotional.stress_events": {
        "columns": [
            "id",
            "timestamp",
            "event",
            "severity",
            "duration_minutes",
            "category",
            "coping_method",
            "notes",
        ],
        "filters": ["time_range", "severity", "category"],
        "description": "Stressful events",
    },
    "emotional.emotional_triggers": {
        "columns": ["id", "trigger", "emotion", "intensity", "frequency", "last_occurred", "notes"],
        "filters": ["emotion", "intensity"],
        "description": "Known emotional triggers",
    },
    # Procedural Memory Tables
    "procedural.routines": {
        "columns": [
            "id",
            "routine_name",
            "time_of_day",
            "steps",
            "frequency",
            "adherence_rate",
            "notes",
        ],
        "filters": ["time_of_day", "frequency"],
        "description": "Daily routines",
    },
    "procedural.habit_patterns": {
        "columns": [
            "id",
            "habit",
            "category",
            "frequency",
            "streak_days",
            "success_rate",
            "started_at",
            "notes",
        ],
        "filters": ["category", "frequency"],
        "description": "Habit tracking",
    },
    "procedural.learned_behaviors": {
        "columns": ["id", "behavior", "category", "skill_level", "last_practiced", "notes"],
        "filters": ["category", "skill_level"],
        "description": "Learned skills and behaviors",
    },
}


# Keyword mapping for table discovery
TABLE_KEYWORDS: dict[str, list[str]] = {
    "episodic.diet_logs": [
        "diet",
        "food",
        "meal",
        "eating",
        "nutrition",
        "breakfast",
        "lunch",
        "dinner",
        "snack",
    ],
    "episodic.health_events": [
        "health",
        "symptom",
        "pain",
        "sick",
        "illness",
        "event",
        "episode",
        "medical",
        "GERD",
        "heartburn",
        "digestive",
    ],
    "episodic.activities": ["activity", "exercise", "workout", "physical", "movement", "sport"],
    "episodic.sleep_logs": ["sleep", "rest", "bedtime", "wake", "insomnia", "tired"],
    "semantic.food_nutrition": [
        "nutrition",
        "nutrient",
        "calorie",
        "caffeine",
        "acidity",
        "vitamin",
        "protein",
        "carb",
        "fat",
    ],
    "semantic.health_conditions": [
        "condition",
        "disease",
        "diagnosis",
        "chronic",
        "medical",
        "health",
        "GERD",
        "illness",
    ],
    "semantic.medications": ["medication", "drug", "prescription", "pill", "treatment", "medicine"],
    "semantic.symptoms": ["symptom", "sign", "indicator", "manifestation"],
    "autobiographical.user_profile": ["profile", "personal", "user", "identity", "demographic"],
    "autobiographical.life_events": ["event", "milestone", "life", "significant", "important"],
    "autobiographical.family_history": ["family", "genetic", "hereditary", "parent", "sibling"],
    "working.recent_conversations": ["conversation", "chat", "dialogue", "recent", "talk"],
    "working.active_goals": ["goal", "objective", "target", "aim", "active"],
    "working.pending_tasks": ["task", "todo", "pending", "action", "item"],
    "prospective.reminders": ["reminder", "alert", "notification", "remember"],
    "prospective.appointments": ["appointment", "meeting", "scheduled", "doctor", "visit"],
    "prospective.planned_activities": ["plan", "future", "upcoming", "scheduled"],
    "spatial.places_visited": ["place", "location", "visited", "been", "where"],
    "spatial.activity_locations": ["where", "location", "place", "venue"],
    "spatial.home_zones": ["home", "zone", "area", "neighborhood"],
    "emotional.mood_logs": ["mood", "feeling", "emotion", "emotional", "mental", "state"],
    "emotional.stress_events": ["stress", "anxiety", "pressure", "tension", "worried"],
    "emotional.emotional_triggers": ["trigger", "cause", "provoke", "set off"],
    "procedural.routines": ["routine", "habit", "regular", "daily", "schedule"],
    "procedural.habit_patterns": ["habit", "pattern", "practice", "regular"],
    "procedural.learned_behaviors": ["skill", "learned", "behavior", "ability", "practice"],
}


def get_memory_type_for_table(table_name: str) -> str | None:
    """Get the memory type for a given table name.

    Args:
        table_name: Full table name (e.g., "episodic.diet_logs")

    Returns:
        Memory type (e.g., "episodic") or None if not found
    """
    if "." in table_name:
        return table_name.split(".")[0]
    return None


def get_all_tables() -> list[str]:
    """Get list of all available table names.

    Returns:
        List of all table names (e.g., ["episodic.diet_logs", ...])
    """
    return list(TABLE_SCHEMAS.keys())


def search_tables_by_keywords(keywords: list[str]) -> list[tuple[str, int]]:
    """Search for relevant tables by keywords.

    Args:
        keywords: List of search keywords

    Returns:
        List of (table_name, score) tuples sorted by relevance
    """
    scores: dict[str, int] = {}

    keywords_lower = [k.lower() for k in keywords]

    for table_name, table_keywords in TABLE_KEYWORDS.items():
        score = 0
        for keyword in keywords_lower:
            for table_keyword in table_keywords:
                if keyword in table_keyword or table_keyword in keyword:
                    score += 1

        if score > 0:
            scores[table_name] = score

    # Sort by score descending
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
