"""Tests for Epic 2.4 Action Tool Mocks: ACT-001, ACT-002, ACT-003.

Test classes:
    TestACT001InvokeCapability       -- invoke_capability() canned results, shape, CB error
    TestACT001Schema                 -- invoke_capability LLM JSON schema
    TestACT002SpawnViaFabric         -- spawn_via_fabric() always-success mock
    TestACT002Schema                 -- spawn_via_fabric LLM JSON schema
    TestACT003ExecuteWorkflow        -- execute_workflow() canned trip plan, rejection
    TestACT003Schema                 -- execute_workflow LLM JSON schema
    TestACTSchemaList                -- ACTION_SCHEMAS list coverage
"""

from __future__ import annotations

import pytest

from poc.concierge_fsm_poc.tools.action_mock import (
    ACTION_SCHEMAS,
    CircuitBreakerOpenError,
    execute_workflow,
    invoke_capability,
    spawn_via_fabric,
)

# ===========================================================================
# TestACT001InvokeCapability
# ===========================================================================


class TestACT001InvokeCapability:
    """ACT-001 AC: canned data keyed by capability, duration_ms, success/data/provider_id."""

    # --- Output shape ---

    def test_returns_dict(self):
        result = invoke_capability("tool.execute.weather_lookup")
        assert isinstance(result, dict)

    def test_success_key_present(self):
        result = invoke_capability("tool.execute.weather_lookup")
        assert "success" in result

    def test_data_key_present(self):
        result = invoke_capability("tool.execute.weather_lookup")
        assert "data" in result

    def test_provider_id_key_present(self):
        result = invoke_capability("tool.execute.weather_lookup")
        assert "provider_id" in result

    def test_duration_ms_key_present(self):
        """AC: Simulates latency field duration_ms."""
        result = invoke_capability("tool.execute.weather_lookup")
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], int)
        assert result["duration_ms"] > 0

    def test_capability_name_key_present(self):
        result = invoke_capability("tool.execute.weather_lookup")
        assert "capability_name" in result
        assert result["capability_name"] == "tool.execute.weather_lookup"

    # --- Weather lookup (T1, F1) ---

    def test_weather_lookup_success(self):
        result = invoke_capability("tool.execute.weather_lookup")
        assert result["success"] is True

    def test_weather_lookup_has_temperature(self):
        result = invoke_capability("tool.execute.weather_lookup")
        assert result["data"]["temperature"] == "45F"

    def test_weather_lookup_has_conditions(self):
        result = invoke_capability("tool.execute.weather_lookup")
        assert result["data"]["conditions"] == "Partly cloudy"

    def test_weather_lookup_has_snow(self):
        result = invoke_capability("tool.execute.weather_lookup")
        assert result["data"]["snow"] == "4 inches base"

    def test_weather_lookup_provider_id(self):
        result = invoke_capability("tool.execute.weather_lookup")
        assert result["provider_id"] == "provider-weather-001"

    # --- Hotel booking (T4, F4) ---

    def test_hotel_booking_success(self):
        result = invoke_capability("tool.execute.hotel_booking")
        assert result["success"] is True

    def test_hotel_booking_has_hotel_name(self):
        result = invoke_capability("tool.execute.hotel_booking")
        assert result["data"]["hotel"] == "Hyatt Regency Lake Tahoe"

    def test_hotel_booking_has_rate(self):
        result = invoke_capability("tool.execute.hotel_booking")
        assert result["data"]["rate"] == "$289/night"

    def test_hotel_booking_available(self):
        result = invoke_capability("tool.execute.hotel_booking")
        assert result["data"]["available"] is True

    # --- Activity search (T2, F2) ---

    def test_activity_search_success(self):
        result = invoke_capability("tool.execute.activity_search")
        assert result["success"] is True

    def test_activity_search_returns_activities_list(self):
        result = invoke_capability("tool.execute.activity_search")
        assert isinstance(result["data"]["activities"], list)
        assert len(result["data"]["activities"]) >= 2

    def test_activity_search_has_heavenly(self):
        result = invoke_capability("tool.execute.activity_search")
        names = [a["name"] for a in result["data"]["activities"]]
        assert "Heavenly Ski Resort" in names

    def test_activity_search_has_snowshoe_tour(self):
        result = invoke_capability("tool.execute.activity_search")
        names = [a["name"] for a in result["data"]["activities"]]
        assert "Lake Tahoe Snowshoe Tour" in names

    def test_activity_search_kid_friendly(self):
        result = invoke_capability("tool.execute.activity_search")
        assert all(a["kid_friendly"] for a in result["data"]["activities"])

    # --- Restaurant search (T7, F7) ---

    def test_restaurant_search_success(self):
        result = invoke_capability("tool.execute.restaurant_search")
        assert result["success"] is True

    def test_restaurant_search_returns_restaurants_list(self):
        result = invoke_capability("tool.execute.restaurant_search")
        assert isinstance(result["data"]["restaurants"], list)
        assert len(result["data"]["restaurants"]) >= 2

    def test_restaurant_search_has_gar_woods(self):
        result = invoke_capability("tool.execute.restaurant_search")
        names = [r["name"] for r in result["data"]["restaurants"]]
        assert "Gar Woods Grill" in names

    def test_restaurant_search_has_sunnyside(self):
        result = invoke_capability("tool.execute.restaurant_search")
        names = [r["name"] for r in result["data"]["restaurants"]]
        assert "Sunnyside Restaurant" in names

    # --- Unknown capability (default) ---

    def test_unknown_capability_returns_failure(self):
        """AC: Default returns error."""
        result = invoke_capability("tool.execute.nonexistent")
        assert result["success"] is False

    def test_unknown_capability_has_error_in_data(self):
        result = invoke_capability("tool.execute.nonexistent")
        assert "error" in result["data"]
        assert result["data"]["error"] == "Capability not found"

    def test_unknown_capability_provider_id_none(self):
        result = invoke_capability("tool.execute.nonexistent")
        assert result["provider_id"] is None

    def test_unknown_capability_still_has_duration(self):
        result = invoke_capability("tool.execute.nonexistent")
        assert isinstance(result["duration_ms"], int)

    # --- Circuit breaker (F24) ---

    def test_cb_open_raises_error(self):
        """AC: force_cb_open raises CircuitBreakerOpenError (F24 full fallback)."""
        with pytest.raises(CircuitBreakerOpenError):
            invoke_capability("tool.execute.weather_lookup", force_cb_open=True)

    def test_cb_open_error_has_capability_name(self):
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            invoke_capability("tool.execute.hotel_booking", force_cb_open=True)
        assert exc_info.value.capability_name == "tool.execute.hotel_booking"

    def test_cb_open_error_message_contains_capability(self):
        with pytest.raises(CircuitBreakerOpenError, match="hotel_booking"):
            invoke_capability("tool.execute.hotel_booking", force_cb_open=True)

    def test_cb_open_works_for_any_capability(self):
        """CB open affects ALL capabilities, not just known ones."""
        with pytest.raises(CircuitBreakerOpenError):
            invoke_capability("tool.execute.nonexistent", force_cb_open=True)

    # --- Extra inputs are accepted (kwargs) ---

    def test_extra_inputs_accepted(self):
        """invoke_capability accepts arbitrary kwargs without error."""
        result = invoke_capability(
            "tool.execute.weather_lookup",
            location="Lake Tahoe",
            date_range="2026-02-21/2026-02-22",
        )
        assert result["success"] is True


# ===========================================================================
# TestACT001Schema
# ===========================================================================


class TestACT001Schema:
    """invoke_capability JSON schema for Gemini function calling."""

    @pytest.fixture()
    def schema(self) -> dict:
        return next(s for s in ACTION_SCHEMAS if s["name"] == "invoke_capability")

    def test_schema_name(self, schema):
        assert schema["name"] == "invoke_capability"

    def test_schema_has_description(self, schema):
        assert "description" in schema
        assert len(schema["description"]) > 10

    def test_schema_parameters_type_object(self, schema):
        assert schema["parameters"]["type"] == "object"

    def test_schema_requires_capability_name(self, schema):
        assert "capability_name" in schema["parameters"].get("required", [])

    def test_schema_has_inputs_property(self, schema):
        assert "inputs" in schema["parameters"]["properties"]


# ===========================================================================
# TestACT002SpawnViaFabric
# ===========================================================================


class TestACT002SpawnViaFabric:
    """ACT-002 AC: returns success=True, agent_name, status=registered."""

    def test_returns_dict(self):
        result = spawn_via_fabric("planner_agent")
        assert isinstance(result, dict)

    def test_success_true(self):
        """AC: Always returns success=True."""
        result = spawn_via_fabric("planner_agent")
        assert result["success"] is True

    def test_agent_name_matches_input(self):
        """AC: agent_name echoes input."""
        result = spawn_via_fabric("weather_bot")
        assert result["agent_name"] == "weather_bot"

    def test_status_registered(self):
        """AC: status=registered."""
        result = spawn_via_fabric("planner_agent")
        assert result["status"] == "registered"

    def test_agent_id_present(self):
        result = spawn_via_fabric("planner_agent")
        assert "agent_id" in result
        assert result["agent_id"].startswith("agent-")

    def test_agent_id_unique_per_call(self):
        r1 = spawn_via_fabric("planner_agent")
        r2 = spawn_via_fabric("planner_agent")
        assert r1["agent_id"] != r2["agent_id"]

    def test_extra_kwargs_accepted(self):
        """spawn_via_fabric accepts extra config without error."""
        result = spawn_via_fabric("planner_agent", model="gemini-2.5-flash", timeout=30)
        assert result["success"] is True

    def test_various_agent_names(self):
        for name in ["trip_planner", "safety_monitor", "context_agent"]:
            result = spawn_via_fabric(name)
            assert result["agent_name"] == name
            assert result["success"] is True


# ===========================================================================
# TestACT002Schema
# ===========================================================================


class TestACT002Schema:
    """spawn_via_fabric JSON schema for Gemini function calling."""

    @pytest.fixture()
    def schema(self) -> dict:
        return next(s for s in ACTION_SCHEMAS if s["name"] == "spawn_via_fabric")

    def test_schema_name(self, schema):
        assert schema["name"] == "spawn_via_fabric"

    def test_schema_has_description(self, schema):
        assert "description" in schema
        assert len(schema["description"]) > 10

    def test_schema_parameters_type_object(self, schema):
        assert schema["parameters"]["type"] == "object"

    def test_schema_requires_agent_name(self, schema):
        assert "agent_name" in schema["parameters"].get("required", [])

    def test_schema_has_config_property(self, schema):
        assert "config" in schema["parameters"]["properties"]


# ===========================================================================
# TestACT003ExecuteWorkflow
# ===========================================================================


class TestACT003ExecuteWorkflow:
    """ACT-003 AC: canned trip planning results, rejected for unknown workflows."""

    # --- Output shape ---

    def test_returns_dict(self):
        result = execute_workflow("workflow.trip_planning")
        assert isinstance(result, dict)

    def test_success_key_present(self):
        result = execute_workflow("workflow.trip_planning")
        assert "success" in result

    def test_status_key_present(self):
        result = execute_workflow("workflow.trip_planning")
        assert "status" in result

    def test_envelope_id_key_present(self):
        result = execute_workflow("workflow.trip_planning")
        assert "envelope_id" in result

    def test_results_key_present(self):
        result = execute_workflow("workflow.trip_planning")
        assert "results" in result

    def test_workflow_name_key_present(self):
        result = execute_workflow("workflow.trip_planning")
        assert "workflow_name" in result
        assert result["workflow_name"] == "workflow.trip_planning"

    def test_duration_ms_key_present(self):
        result = execute_workflow("workflow.trip_planning")
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], int)
        assert result["duration_ms"] > 0

    # --- Trip planning happy path ---

    def test_trip_planning_success(self):
        """AC: Returns canned trip planning results."""
        result = execute_workflow("workflow.trip_planning")
        assert result["success"] is True

    def test_trip_planning_status_completed(self):
        result = execute_workflow("workflow.trip_planning")
        assert result["status"] == "completed"

    def test_trip_planning_envelope_id(self):
        result = execute_workflow("workflow.trip_planning")
        assert result["envelope_id"] == "env-trip-001"

    def test_trip_planning_hotel_name(self):
        result = execute_workflow("workflow.trip_planning")
        assert result["results"]["hotel"]["name"] == "Hyatt Regency Lake Tahoe"

    def test_trip_planning_hotel_rate(self):
        result = execute_workflow("workflow.trip_planning")
        assert result["results"]["hotel"]["rate"] == "$289/night"

    def test_trip_planning_hotel_confirmed(self):
        result = execute_workflow("workflow.trip_planning")
        assert result["results"]["hotel"]["confirmed"] is True

    def test_trip_planning_activities_count(self):
        result = execute_workflow("workflow.trip_planning")
        assert len(result["results"]["activities"]) == 2

    def test_trip_planning_activity_names(self):
        result = execute_workflow("workflow.trip_planning")
        names = [a["name"] for a in result["results"]["activities"]]
        assert "Heavenly Ski Resort - Kids Zone" in names
        assert "Lake Tahoe Snowshoe Tour" in names

    def test_trip_planning_cost_estimate(self):
        result = execute_workflow("workflow.trip_planning")
        assert result["results"]["total_cost_estimate"] == "$850"

    # --- Unknown workflow (rejected) ---

    def test_unknown_workflow_rejected(self):
        """AC: For unknown workflows, returns status=rejected."""
        result = execute_workflow("workflow.nonexistent")
        assert result["success"] is False

    def test_unknown_workflow_status_rejected(self):
        result = execute_workflow("workflow.nonexistent")
        assert result["status"] == "rejected"

    def test_unknown_workflow_envelope_id_none(self):
        result = execute_workflow("workflow.nonexistent")
        assert result["envelope_id"] is None

    def test_unknown_workflow_results_none(self):
        result = execute_workflow("workflow.nonexistent")
        assert result["results"] is None

    def test_unknown_workflow_has_name(self):
        result = execute_workflow("workflow.nonexistent")
        assert result["workflow_name"] == "workflow.nonexistent"

    def test_unknown_workflow_has_duration(self):
        result = execute_workflow("workflow.nonexistent")
        assert isinstance(result["duration_ms"], int)

    # --- Extra inputs are accepted (kwargs) ---

    def test_extra_inputs_accepted(self):
        """execute_workflow accepts arbitrary kwargs without error."""
        result = execute_workflow(
            "workflow.trip_planning",
            destination="Lake Tahoe",
            dates="Feb 21-22",
            family_size=4,
        )
        assert result["success"] is True


# ===========================================================================
# TestACT003Schema
# ===========================================================================


class TestACT003Schema:
    """execute_workflow JSON schema for Gemini function calling."""

    @pytest.fixture()
    def schema(self) -> dict:
        return next(s for s in ACTION_SCHEMAS if s["name"] == "execute_workflow")

    def test_schema_name(self, schema):
        assert schema["name"] == "execute_workflow"

    def test_schema_has_description(self, schema):
        assert "description" in schema
        assert len(schema["description"]) > 10

    def test_schema_parameters_type_object(self, schema):
        assert schema["parameters"]["type"] == "object"

    def test_schema_requires_workflow_name(self, schema):
        assert "workflow_name" in schema["parameters"].get("required", [])

    def test_schema_has_inputs_property(self, schema):
        assert "inputs" in schema["parameters"]["properties"]


# ===========================================================================
# TestACTSchemaList
# ===========================================================================


class TestACTSchemaList:
    """ACTION_SCHEMAS must cover all 3 action tools."""

    def test_three_schemas_present(self):
        assert len(ACTION_SCHEMAS) == 3

    def test_all_schema_names_present(self):
        names = {s["name"] for s in ACTION_SCHEMAS}
        assert names == {
            "invoke_capability",
            "spawn_via_fabric",
            "execute_workflow",
        }

    def test_each_schema_has_parameters(self):
        for s in ACTION_SCHEMAS:
            assert "parameters" in s, f"{s['name']} missing parameters"
            assert s["parameters"]["type"] == "object"
