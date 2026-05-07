"""
Tests for Background Monitor Tools (Epic 2.4)
==============================================

Tests for start_background_monitor, stop_background_monitor,
and weather monitor implementation.

Key scenarios:
- Starting monitors of different types
- Stopping active monitors
- Weather forecast simulation (Turn 24 change)
- Alert generation for rain/storm conditions
"""

import pytest

from poc.session_state_demo.anniversary_demo.tools.monitors import (
    MONITOR_TOOLS,
    AlertSeverity,
    BackgroundMonitor,
    MonitorAlert,
    MonitorStatus,
    MonitorStore,
    MonitorType,
    WeatherForecast,
    check_monitors,
    execute_monitor_tool,
    get_initial_forecast,
    get_monitor_status,
    get_updated_forecast,
    get_weather_forecast,
    list_active_monitors,
    start_background_monitor,
    stop_background_monitor,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def reset_store():
    """Reset the MonitorStore singleton before each test."""
    MonitorStore.reset()
    yield
    MonitorStore.reset()


# ============================================================================
# WeatherForecast Tests
# ============================================================================


class TestWeatherForecast:
    """Tests for WeatherForecast data class."""

    def test_create_weather_forecast(self):
        """Test creating a weather forecast."""
        forecast = WeatherForecast(
            date="next_saturday",
            condition="sunny",
            high_temp_f=72,
            low_temp_f=55,
            precipitation_chance=5,
            description="Beautiful day",
        )

        assert forecast.date == "next_saturday"
        assert forecast.condition == "sunny"
        assert forecast.high_temp_f == 72
        assert forecast.low_temp_f == 55
        assert forecast.precipitation_chance == 5

    def test_forecast_to_dict(self):
        """Test forecast serialization."""
        forecast = WeatherForecast(
            date="next_sunday",
            condition="rainy",
            high_temp_f=65,
            low_temp_f=50,
            precipitation_chance=60,
            description="Rain expected",
        )

        data = forecast.to_dict()

        assert data["date"] == "next_sunday"
        assert data["condition"] == "rainy"
        assert data["precipitation_chance"] == 60


class TestInitialForecast:
    """Tests for initial forecast (before Turn 24)."""

    def test_initial_forecast_saturday_sunny(self):
        """Saturday should show sunny weather initially."""
        forecasts = get_initial_forecast("Sonoma", ["next_saturday", "next_sunday"])

        saturday = forecasts[0]
        assert saturday.condition == "sunny"
        assert saturday.high_temp_f == 72
        assert saturday.precipitation_chance == 5

    def test_initial_forecast_sunday_sunny(self):
        """Sunday should show sunny weather initially."""
        forecasts = get_initial_forecast("Sonoma", ["next_saturday", "next_sunday"])

        sunday = forecasts[1]
        assert sunday.condition == "sunny"
        assert sunday.precipitation_chance == 10

    def test_initial_forecast_includes_location(self):
        """Description should include the location."""
        forecasts = get_initial_forecast("Napa Valley", ["saturday"])

        assert "Napa Valley" in forecasts[0].description


class TestUpdatedForecast:
    """Tests for updated forecast (at Turn 24)."""

    def test_updated_forecast_saturday_still_sunny(self):
        """Saturday should still be sunny after update."""
        forecasts = get_updated_forecast("Sonoma", ["next_saturday", "next_sunday"])

        saturday = forecasts[0]
        assert saturday.condition == "sunny"
        assert saturday.precipitation_chance == 5

    def test_updated_forecast_sunday_rainy(self):
        """Sunday should show rain after Turn 24."""
        forecasts = get_updated_forecast("Sonoma", ["next_saturday", "next_sunday"])

        sunday = forecasts[1]
        assert sunday.condition == "rainy"
        assert sunday.precipitation_chance == 60

    def test_updated_forecast_mentions_afternoon(self):
        """Sunday description should mention afternoon rain."""
        forecasts = get_updated_forecast("Sonoma", ["saturday", "sunday"])

        sunday = forecasts[1]
        assert "afternoon" in sunday.description.lower()


# ============================================================================
# MonitorStore Tests
# ============================================================================


class TestMonitorStore:
    """Tests for MonitorStore singleton."""

    def test_store_singleton(self):
        """Store should be a singleton."""
        store1 = MonitorStore()
        store2 = MonitorStore()

        assert store1 is store2

    def test_add_and_get_monitor(self):
        """Test adding and retrieving a monitor."""
        store = MonitorStore()
        monitor = BackgroundMonitor(
            monitor_id="test-123",
            monitor_type=MonitorType.WEATHER,
            target="Sonoma",
        )

        store.add_monitor(monitor)
        retrieved = store.get_monitor("test-123")

        assert retrieved is not None
        assert retrieved.monitor_id == "test-123"

    def test_get_active_monitors(self):
        """Test getting active monitors."""
        store = MonitorStore()

        # Add running monitor
        running = BackgroundMonitor(
            monitor_id="running-1",
            monitor_type=MonitorType.WEATHER,
            target="Sonoma",
            status=MonitorStatus.RUNNING,
        )
        store.add_monitor(running)

        # Add cancelled monitor
        cancelled = BackgroundMonitor(
            monitor_id="cancelled-1",
            monitor_type=MonitorType.PRICE,
            target="Hotel",
            status=MonitorStatus.CANCELLED,
        )
        store.add_monitor(cancelled)

        active = store.get_active_monitors()

        assert len(active) == 1
        assert active[0].monitor_id == "running-1"

    def test_get_monitors_by_type(self):
        """Test filtering monitors by type."""
        store = MonitorStore()

        store.add_monitor(BackgroundMonitor("w1", MonitorType.WEATHER, "Sonoma"))
        store.add_monitor(BackgroundMonitor("p1", MonitorType.PRICE, "Hotel"))
        store.add_monitor(BackgroundMonitor("w2", MonitorType.WEATHER, "Napa"))

        weather_monitors = store.get_monitors_by_type(MonitorType.WEATHER)

        assert len(weather_monitors) == 2
        assert all(m.monitor_type == MonitorType.WEATHER for m in weather_monitors)

    def test_add_and_get_alerts(self):
        """Test alert management."""
        store = MonitorStore()

        alert = MonitorAlert(
            alert_id="alert-1",
            monitor_id="mon-1",
            monitor_type=MonitorType.WEATHER,
            severity=AlertSeverity.WARNING,
            message="Rain expected",
            data={},
        )

        store.add_alert(alert)
        pending = store.get_pending_alerts()

        assert len(pending) == 1
        assert pending[0].alert_id == "alert-1"

    def test_acknowledge_alert(self):
        """Test acknowledging an alert."""
        store = MonitorStore()

        alert = MonitorAlert(
            alert_id="alert-2",
            monitor_id="mon-1",
            monitor_type=MonitorType.WEATHER,
            severity=AlertSeverity.WARNING,
            message="Rain expected",
            data={},
        )

        store.add_alert(alert)
        store.acknowledge_alert("alert-2")

        pending = store.get_pending_alerts()
        assert len(pending) == 0

    def test_demo_turn_tracking(self):
        """Test demo turn tracking for weather simulation."""
        store = MonitorStore()

        store.set_demo_turn(15)
        assert store.get_demo_turn() == 15

        store.set_demo_turn(24)
        assert store.get_demo_turn() == 24


# ============================================================================
# start_background_monitor Tests
# ============================================================================


class TestStartBackgroundMonitor:
    """Tests for start_background_monitor tool."""

    def test_start_weather_monitor_success(self):
        """Test starting a weather monitor."""
        result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["next_saturday", "next_sunday"],
            alert_conditions=["rain", "storm"],
        )

        assert result["success"] is True
        assert result["monitor_type"] == "weather"
        assert result["target"] == "Sonoma"
        assert result["status"] == "running"
        assert "monitor_id" in result

    def test_start_weather_monitor_stored(self):
        """Monitor should be stored in MonitorStore."""
        result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["saturday"],
            alert_conditions=["rain"],
        )

        store = MonitorStore()
        monitor = store.get_monitor(result["monitor_id"])

        assert monitor is not None
        assert monitor.status == MonitorStatus.RUNNING

    def test_start_price_monitor(self):
        """Test starting a price monitor."""
        result = start_background_monitor(
            monitor_type="price",
            target="Vineyard Inn",
        )

        assert result["success"] is True
        assert result["monitor_type"] == "price"
        assert "price" in result["message"].lower()

    def test_start_availability_monitor(self):
        """Test starting an availability monitor."""
        result = start_background_monitor(
            monitor_type="availability",
            target="Spa Appointment",
        )

        assert result["success"] is True
        assert result["monitor_type"] == "availability"

    def test_start_invalid_monitor_type(self):
        """Invalid monitor type should fail."""
        result = start_background_monitor(
            monitor_type="invalid_type",
            target="Something",
        )

        assert result["success"] is False
        assert "Invalid monitor type" in result["error"]

    def test_weather_monitor_stores_initial_forecast(self):
        """Weather monitor should store initial forecast."""
        result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["saturday", "sunday"],
            alert_conditions=["rain"],
        )

        store = MonitorStore()
        monitor = store.get_monitor(result["monitor_id"])

        assert "current_forecast" in monitor.metadata
        assert len(monitor.metadata["current_forecast"]) == 2

    def test_start_monitor_confirmation_message(self):
        """Confirmation message should mention key details."""
        result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["saturday", "sunday"],
            alert_conditions=["rain", "storm"],
        )

        assert "Sonoma" in result["message"]
        assert "saturday" in result["message"].lower() or "sunday" in result["message"].lower()


# ============================================================================
# stop_background_monitor Tests
# ============================================================================


class TestStopBackgroundMonitor:
    """Tests for stop_background_monitor tool."""

    def test_stop_running_monitor_success(self):
        """Test stopping a running monitor."""
        # Start a monitor first
        start_result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
        )
        monitor_id = start_result["monitor_id"]

        # Stop it
        result = stop_background_monitor(monitor_id=monitor_id)

        assert result["success"] is True
        assert result["new_status"] == "cancelled"

    def test_stop_monitor_updates_store(self):
        """Stopping should update monitor status in store."""
        start_result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
        )
        monitor_id = start_result["monitor_id"]

        stop_background_monitor(monitor_id=monitor_id)

        store = MonitorStore()
        monitor = store.get_monitor(monitor_id)

        assert monitor.status == MonitorStatus.CANCELLED
        assert monitor.stopped_at is not None

    def test_stop_monitor_with_reason(self):
        """Test stopping with a reason."""
        start_result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
        )
        monitor_id = start_result["monitor_id"]

        stop_background_monitor(monitor_id=monitor_id, reason="User requested")

        store = MonitorStore()
        monitor = store.get_monitor(monitor_id)

        assert monitor.metadata.get("cancel_reason") == "User requested"

    def test_stop_nonexistent_monitor(self):
        """Stopping nonexistent monitor should fail."""
        result = stop_background_monitor(monitor_id="fake-id-123")

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_stop_already_cancelled_monitor(self):
        """Stopping already cancelled monitor should fail."""
        # Start and stop
        start_result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
        )
        monitor_id = start_result["monitor_id"]
        stop_background_monitor(monitor_id=monitor_id)

        # Try to stop again
        result = stop_background_monitor(monitor_id=monitor_id)

        assert result["success"] is False
        assert "already stopped" in result["error"]


# ============================================================================
# check_monitors Tests
# ============================================================================


class TestCheckMonitors:
    """Tests for check_monitors function."""

    def test_check_monitors_before_turn_24_no_alerts(self):
        """Before Turn 24, no weather alerts should fire."""
        start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["saturday", "sunday"],
            alert_conditions=["rain"],
        )

        alerts = check_monitors(demo_turn=15)

        assert len(alerts) == 0

    def test_check_monitors_at_turn_24_generates_alert(self):
        """At Turn 24, weather alert should fire."""
        start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["saturday", "sunday"],
            alert_conditions=["rain"],
        )

        alerts = check_monitors(demo_turn=24)

        assert len(alerts) == 1
        assert alerts[0].severity == AlertSeverity.WARNING
        assert "60%" in alerts[0].message or "rain" in alerts[0].message.lower()

    def test_check_monitors_increments_check_count(self):
        """Each check should increment the check count."""
        result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["saturday"],
            alert_conditions=["rain"],
        )
        monitor_id = result["monitor_id"]

        check_monitors(demo_turn=10)
        check_monitors(demo_turn=11)
        check_monitors(demo_turn=12)

        store = MonitorStore()
        monitor = store.get_monitor(monitor_id)

        assert monitor.check_count == 3

    def test_check_monitors_only_alerts_once(self):
        """Same alert should not fire multiple times."""
        start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["saturday", "sunday"],
            alert_conditions=["rain"],
        )

        # First check at Turn 24
        alerts1 = check_monitors(demo_turn=24)
        assert len(alerts1) == 1

        # Second check at Turn 25
        alerts2 = check_monitors(demo_turn=25)
        assert len(alerts2) == 0  # No new alerts

    def test_check_monitors_alert_has_suggested_action(self):
        """Weather alert should suggest booking spa."""
        start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["saturday", "sunday"],
            alert_conditions=["rain"],
        )

        alerts = check_monitors(demo_turn=24)

        assert alerts[0].suggested_action == "book_spa_service"


# ============================================================================
# get_weather_forecast Tests
# ============================================================================


class TestGetWeatherForecast:
    """Tests for get_weather_forecast tool."""

    def test_get_forecast_before_turn_24(self):
        """Before Turn 24, forecast shows good weather."""
        result = get_weather_forecast(
            location="Sonoma",
            dates=["saturday", "sunday"],
            demo_turn=15,
        )

        assert result["success"] is True
        sunday = result["forecast"][1]
        assert sunday["precipitation_chance"] == 10

    def test_get_forecast_at_turn_24(self):
        """At Turn 24, forecast shows rain Sunday."""
        result = get_weather_forecast(
            location="Sonoma",
            dates=["saturday", "sunday"],
            demo_turn=24,
        )

        assert result["success"] is True
        sunday = result["forecast"][1]
        assert sunday["condition"] == "rainy"
        assert sunday["precipitation_chance"] == 60

    def test_get_forecast_includes_location(self):
        """Result should include location."""
        result = get_weather_forecast(
            location="Napa Valley",
            dates=["saturday"],
            demo_turn=10,
        )

        assert result["location"] == "Napa Valley"


# ============================================================================
# get_monitor_status Tests
# ============================================================================


class TestGetMonitorStatus:
    """Tests for get_monitor_status tool."""

    def test_get_status_success(self):
        """Test getting monitor status."""
        start_result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["saturday"],
            alert_conditions=["rain"],
        )
        monitor_id = start_result["monitor_id"]

        result = get_monitor_status(monitor_id)

        assert result["success"] is True
        assert result["status"] == "RUNNING"
        assert result["target"] == "Sonoma"

    def test_get_status_nonexistent(self):
        """Nonexistent monitor should return error."""
        result = get_monitor_status("fake-id")

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_get_status_includes_pending_alerts(self):
        """Status should include pending alert count."""
        start_result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["saturday", "sunday"],
            alert_conditions=["rain"],
        )
        monitor_id = start_result["monitor_id"]

        # Generate an alert
        check_monitors(demo_turn=24)

        result = get_monitor_status(monitor_id)

        assert result["pending_alerts"] == 1


# ============================================================================
# list_active_monitors Tests
# ============================================================================


class TestListActiveMonitors:
    """Tests for list_active_monitors tool."""

    def test_list_empty_when_no_monitors(self):
        """Empty list when no monitors running."""
        result = list_active_monitors()

        assert result["success"] is True
        assert result["count"] == 0
        assert result["monitors"] == []

    def test_list_includes_running_monitors(self):
        """Should list running monitors."""
        start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
        )
        start_background_monitor(
            monitor_type="price",
            target="Hotel",
        )

        result = list_active_monitors()

        assert result["count"] == 2
        targets = [m["target"] for m in result["monitors"]]
        assert "Sonoma" in targets
        assert "Hotel" in targets

    def test_list_excludes_cancelled_monitors(self):
        """Cancelled monitors should not appear in list."""
        start_result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
        )
        stop_background_monitor(start_result["monitor_id"])

        start_background_monitor(
            monitor_type="price",
            target="Hotel",
        )

        result = list_active_monitors()

        assert result["count"] == 1
        assert result["monitors"][0]["target"] == "Hotel"


# ============================================================================
# execute_monitor_tool Tests
# ============================================================================


class TestExecuteMonitorTool:
    """Tests for execute_monitor_tool dispatcher."""

    def test_execute_start_monitor(self):
        """Test executing start_background_monitor via dispatcher."""
        result = execute_monitor_tool(
            "start_background_monitor",
            {
                "monitor_type": "weather",
                "target": "Sonoma",
                "dates": ["saturday"],
                "alert_conditions": ["rain"],
            },
        )

        assert result["success"] is True
        assert result["monitor_type"] == "weather"

    def test_execute_stop_monitor(self):
        """Test executing stop_background_monitor via dispatcher."""
        start_result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
        )

        result = execute_monitor_tool(
            "stop_background_monitor",
            {"monitor_id": start_result["monitor_id"]},
        )

        assert result["success"] is True
        assert result["new_status"] == "cancelled"

    def test_execute_list_monitors(self):
        """Test executing list_active_monitors via dispatcher."""
        result = execute_monitor_tool("list_active_monitors", {})

        assert result["success"] is True
        assert "count" in result

    def test_execute_unknown_tool(self):
        """Unknown tool should return error."""
        result = execute_monitor_tool("unknown_tool", {})

        assert result["success"] is False
        assert "Unknown" in result["error"]


# ============================================================================
# MONITOR_TOOLS Schema Tests
# ============================================================================


class TestMonitorToolSchemas:
    """Tests for MONITOR_TOOLS schemas."""

    def test_start_monitor_schema_exists(self):
        """start_background_monitor schema should exist."""
        assert "start_background_monitor" in MONITOR_TOOLS

    def test_start_monitor_required_params(self):
        """start_background_monitor should have required params."""
        schema = MONITOR_TOOLS["start_background_monitor"]
        required = schema["parameters"]["required"]

        assert "monitor_type" in required
        assert "target" in required

    def test_stop_monitor_schema_exists(self):
        """stop_background_monitor schema should exist."""
        assert "stop_background_monitor" in MONITOR_TOOLS

    def test_stop_monitor_required_params(self):
        """stop_background_monitor should require monitor_id."""
        schema = MONITOR_TOOLS["stop_background_monitor"]
        required = schema["parameters"]["required"]

        assert "monitor_id" in required

    def test_monitor_type_enum(self):
        """monitor_type should have enum values."""
        schema = MONITOR_TOOLS["start_background_monitor"]
        enum_values = schema["parameters"]["properties"]["monitor_type"]["enum"]

        assert "weather" in enum_values
        assert "price" in enum_values
        assert "availability" in enum_values


# ============================================================================
# Demo Scenario Integration Tests
# ============================================================================


class TestDemoScenario:
    """Integration tests matching the demo script."""

    def test_turn_15_start_weather_monitor(self):
        """Turn 15: Sarah asks to monitor weather."""
        result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["next_saturday", "next_sunday"],
            alert_conditions=["rain", "storm"],
        )

        assert result["success"] is True
        assert "monitor_id" in result
        assert "weather" in result["message"].lower()

    def test_turn_24_weather_alert_triggers(self):
        """Turn 24: Weather changes and alert fires."""
        # Setup from Turn 15
        start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["next_saturday", "next_sunday"],
            alert_conditions=["rain", "storm"],
        )

        # Turns pass without alerts
        for turn in range(15, 24):
            alerts = check_monitors(demo_turn=turn)
            assert len(alerts) == 0

        # Turn 24: Alert fires!
        alerts = check_monitors(demo_turn=24)

        assert len(alerts) == 1
        alert = alerts[0]
        assert "60%" in alert.message
        assert "rain" in alert.message.lower()
        assert "Saturday" in alert.message
        assert alert.suggested_action == "book_spa_service"

    def test_full_weather_flow(self):
        """Complete weather monitoring flow for demo."""
        # 1. Start monitor
        start_result = start_background_monitor(
            monitor_type="weather",
            target="Sonoma",
            dates=["next_saturday", "next_sunday"],
            alert_conditions=["rain"],
        )
        monitor_id = start_result["monitor_id"]

        # 2. Check status
        status = get_monitor_status(monitor_id)
        assert status["status"] == "RUNNING"

        # 3. List active monitors
        active = list_active_monitors()
        assert active["count"] == 1

        # 4. Weather changes at Turn 24
        alerts = check_monitors(demo_turn=24)
        assert len(alerts) == 1
        assert "rain" in alerts[0].message.lower()

        # 5. Verify forecast changed
        forecast = get_weather_forecast("Sonoma", ["saturday", "sunday"], demo_turn=24)
        sunday = forecast["forecast"][1]
        assert sunday["condition"] == "rainy"
        assert sunday["precipitation_chance"] == 60
