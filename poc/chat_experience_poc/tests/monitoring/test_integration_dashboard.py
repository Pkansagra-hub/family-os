"""
Integration Dashboard Test

Validates dashboard health monitoring and status display functionality.
"""

import pytest


@pytest.mark.asyncio
async def test_integration_dashboard_initialization():
    """Test dashboard initializes correctly."""
    from monitoring.integration_dashboard import get_integration_dashboard

    dashboard = get_integration_dashboard()

    assert dashboard is not None
    assert dashboard.alert_threshold_seconds == 30
    assert dashboard.performance_degradation_factor == 2.0
    assert len(dashboard.performance_budgets) > 0
    assert "Intent Router" in dashboard.performance_budgets
    assert "Concierge Agent" in dashboard.performance_budgets


@pytest.mark.asyncio
async def test_dashboard_display_status():
    """Test dashboard generates status table."""
    from monitoring.integration_dashboard import get_integration_dashboard

    dashboard = get_integration_dashboard()

    # Generate status (non-refresh mode)
    status = await dashboard.display_status(refresh=False)

    # Verify table structure
    assert "K1 Intelligence Module - System Status" in status
    assert "Component" in status
    assert "Status" in status
    assert "Latency (P95)" in status
    assert "Details" in status
    assert "Overall System Health:" in status

    # Verify some expected components appear
    assert "Intent Router" in status
    assert "Concierge Agent" in status
    assert "SessionState Manager" in status
    assert "DeltaBus" in status
    assert "User KG Database" in status


@pytest.mark.asyncio
async def test_dashboard_component_health_unknown():
    """Test dashboard handles uninitialized components gracefully."""
    from monitoring.integration_dashboard import get_integration_dashboard

    dashboard = get_integration_dashboard()

    # Check individual component (most will be UNKNOWN in test environment)
    health = await dashboard._check_intent_router()

    assert health is not None
    assert health.name == "Intent Router"
    # Status will be UNKNOWN in test environment without full system init
    assert health.status.value in ["UNKNOWN", "HEALTHY"]
    assert health.latency_p95_ms >= 0.0


@pytest.mark.asyncio
async def test_dashboard_mock_mcp_server_check():
    """Test dashboard checks Mock MCP Server availability."""
    from monitoring.integration_dashboard import get_integration_dashboard

    dashboard = get_integration_dashboard()

    # Check Mock MCP Server (will be DOWN if not running)
    health = await dashboard._check_mock_mcp_server()

    assert health is not None
    assert health.name == "Mock MCP Server (8001)"
    # Status depends on whether Mock MCP is running
    assert health.status.value in ["UP", "DOWN"]


@pytest.mark.asyncio
async def test_dashboard_overall_health_calculation():
    """Test overall health calculation logic."""
    from datetime import datetime

    from monitoring.integration_dashboard import (
        ComponentHealth,
        ComponentStatus,
        get_integration_dashboard,
    )

    dashboard = get_integration_dashboard()

    # All healthy
    components = [
        ComponentHealth(
            name="Test1",
            status=ComponentStatus.HEALTHY,
            latency_p95_ms=5.0,
            details="OK",
            last_check=datetime.utcnow(),
        ),
        ComponentHealth(
            name="Test2",
            status=ComponentStatus.ACTIVE,
            latency_p95_ms=10.0,
            details="OK",
            last_check=datetime.utcnow(),
        ),
    ]

    overall = dashboard._calculate_overall_health(components)
    assert "ALL SYSTEMS OPERATIONAL" in overall
    assert "✅" in overall

    # Some degraded
    components.append(
        ComponentHealth(
            name="Test3",
            status=ComponentStatus.DEGRADED,
            latency_p95_ms=50.0,
            details="Slow",
            last_check=datetime.utcnow(),
        )
    )

    overall = dashboard._calculate_overall_health(components)
    assert "DEGRADED" in overall
    assert "⚠️" in overall

    # Some failed
    components.append(
        ComponentHealth(
            name="Test4",
            status=ComponentStatus.FAILED,
            latency_p95_ms=0.0,
            details="Down",
            last_check=datetime.utcnow(),
        )
    )

    overall = dashboard._calculate_overall_health(components)
    assert "FAILED" in overall
    assert "❌" in overall


@pytest.mark.asyncio
async def test_dashboard_alert_tracking():
    """Test dashboard tracks unhealthy components over time."""
    from datetime import datetime

    from monitoring.integration_dashboard import (
        ComponentHealth,
        ComponentStatus,
        get_integration_dashboard,
    )

    dashboard = get_integration_dashboard()

    # Clear any existing tracking
    dashboard.unhealthy_start_times.clear()

    # Create unhealthy component
    components = [
        ComponentHealth(
            name="TestFailed",
            status=ComponentStatus.FAILED,
            latency_p95_ms=0.0,
            details="Down",
            last_check=datetime.utcnow(),
        )
    ]

    # First check - should start tracking
    await dashboard._check_alerts(components)
    assert "TestFailed" in dashboard.unhealthy_start_times

    # Component recovers
    components[0].status = ComponentStatus.HEALTHY
    await dashboard._check_alerts(components)
    assert "TestFailed" not in dashboard.unhealthy_start_times


@pytest.mark.asyncio
async def test_dashboard_performance_budget_alerts():
    """Test dashboard alerts on performance degradation."""
    from datetime import datetime

    from monitoring.integration_dashboard import (
        ComponentHealth,
        ComponentStatus,
        get_integration_dashboard,
    )

    dashboard = get_integration_dashboard()

    # Create component with latency exceeding 2x budget
    # Intent Router budget: 5ms, so 12ms should trigger warning
    components = [
        ComponentHealth(
            name="Intent Router",
            status=ComponentStatus.HEALTHY,
            latency_p95_ms=12.0,  # >2x budget of 5ms
            details="Slow",
            last_check=datetime.utcnow(),
        )
    ]

    # Should log performance degradation warning (check via logs if needed)
    await dashboard._check_alerts(components)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
