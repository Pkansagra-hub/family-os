"""Tests for Epic 2.5 Schema Tool: SCH-001.

Test classes:
    TestSCH001GetCapabilitySchema    -- get_capability_schema() for all 9 capabilities + unknown
    TestSCH001SchemaFields           -- required_inputs, optional_inputs, output_schema, safety_band_min
    TestSCH001Schema                 -- get_capability_schema LLM JSON schema
    TestSCHCapabilityRegistry        -- CAPABILITY_SCHEMAS dict coverage
    TestSCHSchemaList                -- SCHEMA_SCHEMAS list coverage
"""

from __future__ import annotations

import pytest

from poc.concierge_fsm_poc.tools.schema import (
    CAPABILITY_SCHEMAS,
    SCHEMA_SCHEMAS,
    get_capability_schema,
)

# The 5 core capabilities that match DEMO_CAPABILITIES in read_mock.py
CORE_CAPABILITIES = [
    "tool.execute.weather_lookup",
    "tool.execute.hotel_booking",
    "tool.execute.activity_search",
    "tool.execute.restaurant_search",
    "workflow.trip_planning",
]

# 4 additional story capabilities
STORY_CAPABILITIES = [
    "tool.execute.rental_lookup",
    "tool.execute.flight_search",
    "tool.execute.route_planner",
    "tool.execute.boat_tour",
]

ALL_CAPABILITIES = CORE_CAPABILITIES + STORY_CAPABILITIES


# ===========================================================================
# TestSCH001GetCapabilitySchema
# ===========================================================================


class TestSCH001GetCapabilitySchema:
    """SCH-001 AC: returns full schema for any of the demo capabilities."""

    # --- Output shape for known capabilities ---

    def test_returns_dict(self):
        result = get_capability_schema("tool.execute.weather_lookup")
        assert isinstance(result, dict)

    def test_found_true_for_known(self):
        result = get_capability_schema("tool.execute.weather_lookup")
        assert result["found"] is True

    def test_name_matches_input(self):
        result = get_capability_schema("tool.execute.weather_lookup")
        assert result["name"] == "tool.execute.weather_lookup"

    def test_query_latency_ms_present(self):
        result = get_capability_schema("tool.execute.weather_lookup")
        assert "query_latency_ms" in result
        assert isinstance(result["query_latency_ms"], int)
        assert result["query_latency_ms"] > 0

    # --- All 5 core capabilities found ---

    @pytest.mark.parametrize("cap_name", CORE_CAPABILITIES)
    def test_core_capability_found(self, cap_name: str):
        """AC: Returns full schema for any of the 5 demo capabilities."""
        result = get_capability_schema(cap_name)
        assert result["found"] is True
        assert result["name"] == cap_name

    # --- All 4 story capabilities found ---

    @pytest.mark.parametrize("cap_name", STORY_CAPABILITIES)
    def test_story_capability_found(self, cap_name: str):
        result = get_capability_schema(cap_name)
        assert result["found"] is True
        assert result["name"] == cap_name

    # --- Unknown capability returns not_found ---

    def test_unknown_capability_not_found(self):
        """AC: Returns not_found error for unknown capability names."""
        result = get_capability_schema("tool.execute.nonexistent")
        assert result["found"] is False

    def test_unknown_capability_error_field(self):
        result = get_capability_schema("tool.execute.nonexistent")
        assert result["error"] == "not_found"

    def test_unknown_capability_echoes_name(self):
        result = get_capability_schema("tool.execute.nonexistent")
        assert result["capability_name"] == "tool.execute.nonexistent"

    def test_unknown_capability_lists_available(self):
        result = get_capability_schema("tool.execute.nonexistent")
        assert "available_capabilities" in result
        assert isinstance(result["available_capabilities"], list)
        assert len(result["available_capabilities"]) == 9

    def test_unknown_capability_available_sorted(self):
        result = get_capability_schema("tool.execute.nonexistent")
        available = result["available_capabilities"]
        assert available == sorted(available)

    def test_unknown_capability_has_latency(self):
        result = get_capability_schema("tool.execute.nonexistent")
        assert isinstance(result["query_latency_ms"], int)


# ===========================================================================
# TestSCH001SchemaFields
# ===========================================================================


class TestSCH001SchemaFields:
    """AC: Schema includes required_inputs, optional_inputs, output_schema, safety_band_min."""

    @pytest.mark.parametrize("cap_name", ALL_CAPABILITIES)
    def test_has_required_inputs(self, cap_name: str):
        result = get_capability_schema(cap_name)
        assert "required_inputs" in result
        assert isinstance(result["required_inputs"], list)
        assert len(result["required_inputs"]) > 0

    @pytest.mark.parametrize("cap_name", ALL_CAPABILITIES)
    def test_has_optional_inputs(self, cap_name: str):
        result = get_capability_schema(cap_name)
        assert "optional_inputs" in result
        assert isinstance(result["optional_inputs"], list)

    @pytest.mark.parametrize("cap_name", ALL_CAPABILITIES)
    def test_has_output_schema(self, cap_name: str):
        result = get_capability_schema(cap_name)
        assert "output_schema" in result
        assert isinstance(result["output_schema"], dict)

    @pytest.mark.parametrize("cap_name", ALL_CAPABILITIES)
    def test_has_safety_band_min(self, cap_name: str):
        result = get_capability_schema(cap_name)
        assert "safety_band_min" in result
        assert result["safety_band_min"] in {"GREEN", "AMBER", "RED"}

    @pytest.mark.parametrize("cap_name", ALL_CAPABILITIES)
    def test_has_avg_latency_ms(self, cap_name: str):
        result = get_capability_schema(cap_name)
        assert "avg_latency_ms" in result
        assert isinstance(result["avg_latency_ms"], int)
        assert result["avg_latency_ms"] > 0

    # --- Specific schema values for clarification-driving capabilities ---

    def test_weather_required_inputs(self):
        result = get_capability_schema("tool.execute.weather_lookup")
        assert result["required_inputs"] == ["location", "date_range"]

    def test_hotel_required_inputs(self):
        """Hotel booking has 4 required inputs -- drives clarification in T4 (F4)."""
        result = get_capability_schema("tool.execute.hotel_booking")
        assert set(result["required_inputs"]) == {"location", "check_in", "check_out", "guests"}

    def test_hotel_safety_band_amber(self):
        result = get_capability_schema("tool.execute.hotel_booking")
        assert result["safety_band_min"] == "AMBER"

    def test_restaurant_required_inputs(self):
        """Restaurant has 4 required inputs -- drives clarification in T5 (F5)."""
        result = get_capability_schema("tool.execute.restaurant_search")
        assert set(result["required_inputs"]) == {"location", "cuisine_type", "party_size", "time"}

    def test_trip_planning_required_inputs(self):
        result = get_capability_schema("workflow.trip_planning")
        assert set(result["required_inputs"]) == {"destination", "dates", "family_size"}

    def test_trip_planning_safety_band_amber(self):
        result = get_capability_schema("workflow.trip_planning")
        assert result["safety_band_min"] == "AMBER"


# ===========================================================================
# TestSCH001Schema (LLM JSON schema)
# ===========================================================================


class TestSCH001Schema:
    """get_capability_schema JSON schema for Gemini function calling."""

    @pytest.fixture()
    def schema(self) -> dict:
        return next(s for s in SCHEMA_SCHEMAS if s["name"] == "get_capability_schema")

    def test_schema_name(self, schema):
        assert schema["name"] == "get_capability_schema"

    def test_schema_has_description(self, schema):
        assert "description" in schema
        assert len(schema["description"]) > 10

    def test_schema_parameters_type_object(self, schema):
        assert schema["parameters"]["type"] == "object"

    def test_schema_requires_capability_name(self, schema):
        assert "capability_name" in schema["parameters"].get("required", [])

    def test_schema_capability_name_is_string(self, schema):
        props = schema["parameters"]["properties"]
        assert props["capability_name"]["type"] == "string"


# ===========================================================================
# TestSCHCapabilityRegistry
# ===========================================================================


class TestSCHCapabilityRegistry:
    """CAPABILITY_SCHEMAS dict covers all 9 demo capabilities."""

    def test_nine_schemas_in_registry(self):
        assert len(CAPABILITY_SCHEMAS) == 9

    def test_all_capability_names_present(self):
        assert set(CAPABILITY_SCHEMAS.keys()) == set(ALL_CAPABILITIES)

    def test_each_entry_has_name_matching_key(self):
        for key, schema in CAPABILITY_SCHEMAS.items():
            assert schema["name"] == key, f"Name mismatch: key={key}, name={schema['name']}"

    def test_each_entry_has_all_required_fields(self):
        required_fields = {
            "name",
            "required_inputs",
            "optional_inputs",
            "output_schema",
            "safety_band_min",
            "avg_latency_ms",
        }
        for key, schema in CAPABILITY_SCHEMAS.items():
            missing = required_fields - set(schema.keys())
            assert not missing, f"{key} missing fields: {missing}"


# ===========================================================================
# TestSCHSchemaList
# ===========================================================================


class TestSCHSchemaList:
    """SCHEMA_SCHEMAS must cover the get_capability_schema tool."""

    def test_one_schema_present(self):
        assert len(SCHEMA_SCHEMAS) == 1

    def test_schema_name_is_get_capability_schema(self):
        assert SCHEMA_SCHEMAS[0]["name"] == "get_capability_schema"

    def test_schema_has_parameters(self):
        assert "parameters" in SCHEMA_SCHEMAS[0]
        assert SCHEMA_SCHEMAS[0]["parameters"]["type"] == "object"
