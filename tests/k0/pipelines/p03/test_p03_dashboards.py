"""Tests for P03 Grafana Dashboards (Issue 6.1.17).

Validates dashboard JSON structure, required panels, and Prometheus queries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# Dashboard directory
DASHBOARD_DIR = Path(__file__).parents[4] / "k0" / "telemetry" / "generated" / "dashboards"


class TestP03DashboardsExist:
    """Tests that all required P03 dashboards exist."""

    EXPECTED_DASHBOARDS = [
        "p03_health.json",
        "p03_memory_growth.json",
        "p03_active_learning.json",
        "p03_learning_performance.json",
        "p03_formula_comparison.json",
    ]

    @pytest.mark.parametrize("dashboard_name", EXPECTED_DASHBOARDS)
    def test_dashboard_file_exists(self, dashboard_name: str) -> None:
        """Test each required dashboard file exists."""
        dashboard_path = DASHBOARD_DIR / dashboard_name
        assert dashboard_path.exists(), f"Dashboard {dashboard_name} not found at {dashboard_path}"

    @pytest.mark.parametrize("dashboard_name", EXPECTED_DASHBOARDS)
    def test_dashboard_valid_json(self, dashboard_name: str) -> None:
        """Test each dashboard is valid JSON."""
        dashboard_path = DASHBOARD_DIR / dashboard_name
        if not dashboard_path.exists():
            pytest.skip(f"Dashboard {dashboard_name} not found")

        with open(dashboard_path) as f:
            content = f.read()

        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            pytest.fail(f"Dashboard {dashboard_name} is not valid JSON: {e}")


class TestDashboardStructure:
    """Tests for Grafana dashboard JSON structure."""

    @pytest.fixture
    def load_dashboard(self) -> callable:
        """Factory to load dashboard JSON."""

        def _load(name: str) -> dict[str, Any]:
            path = DASHBOARD_DIR / name
            if not path.exists():
                pytest.skip(f"Dashboard {name} not found")
            with open(path) as f:
                return json.load(f)

        return _load

    def test_health_dashboard_structure(self, load_dashboard: callable) -> None:
        """Test p03_health dashboard has required structure."""
        dash = load_dashboard("p03_health.json")

        # Check required top-level keys
        assert "title" in dash
        assert "uid" in dash
        assert "panels" in dash
        assert "tags" in dash
        assert "schemaVersion" in dash

        # Check P03 tags
        assert "p03" in dash["tags"]
        assert "consolidation" in dash["tags"]

        # Check has panels
        assert len(dash["panels"]) > 0

    def test_memory_growth_dashboard_structure(self, load_dashboard: callable) -> None:
        """Test p03_memory_growth dashboard has required structure."""
        dash = load_dashboard("p03_memory_growth.json")

        assert dash["uid"] == "p03-memory-growth"
        assert "memory" in dash["tags"]
        assert len(dash["panels"]) > 0

    def test_active_learning_dashboard_structure(self, load_dashboard: callable) -> None:
        """Test p03_active_learning dashboard has required structure."""
        dash = load_dashboard("p03_active_learning.json")

        assert dash["uid"] == "p03-active-learning"
        assert "active-learning" in dash["tags"] or "gaps" in dash["tags"]
        assert len(dash["panels"]) > 0

    def test_learning_performance_dashboard_structure(self, load_dashboard: callable) -> None:
        """Test p03_learning_performance dashboard has required structure."""
        dash = load_dashboard("p03_learning_performance.json")

        assert dash["uid"] == "p03-learning-perf"
        assert "learning" in dash["tags"] or "performance" in dash["tags"]
        assert len(dash["panels"]) > 0

    def test_formula_comparison_dashboard_structure(self, load_dashboard: callable) -> None:
        """Test p03_formula_comparison dashboard has required structure."""
        dash = load_dashboard("p03_formula_comparison.json")

        assert dash["uid"] == "p03-formula-compare"
        assert "formula" in dash["tags"] or "comparison" in dash["tags"]
        assert len(dash["panels"]) > 0


class TestDashboardPanels:
    """Tests for dashboard panel configuration."""

    @pytest.fixture
    def load_dashboard(self) -> callable:
        """Factory to load dashboard JSON."""

        def _load(name: str) -> dict[str, Any]:
            path = DASHBOARD_DIR / name
            if not path.exists():
                pytest.skip(f"Dashboard {name} not found")
            with open(path) as f:
                return json.load(f)

        return _load

    def test_health_dashboard_has_cycle_panels(self, load_dashboard: callable) -> None:
        """Test health dashboard has cycle-related panels."""
        dash = load_dashboard("p03_health.json")
        panel_titles = [p.get("title", "").lower() for p in dash["panels"]]

        # Should have cycle-related panels
        assert any("cycle" in t for t in panel_titles), "No cycle panels found"

    def test_health_dashboard_has_pending_panels(self, load_dashboard: callable) -> None:
        """Test health dashboard has pending queue panels."""
        dash = load_dashboard("p03_health.json")
        panel_titles = [p.get("title", "").lower() for p in dash["panels"]]

        assert any("pending" in t for t in panel_titles), "No pending queue panels found"

    def test_memory_growth_has_layer_panels(self, load_dashboard: callable) -> None:
        """Test memory growth dashboard has layer-related panels."""
        dash = load_dashboard("p03_memory_growth.json")
        panel_titles = [p.get("title", "").lower() for p in dash["panels"]]

        assert any("layer" in t for t in panel_titles), "No layer panels found"

    def test_active_learning_has_gap_panels(self, load_dashboard: callable) -> None:
        """Test active learning dashboard has gap-related panels."""
        dash = load_dashboard("p03_active_learning.json")
        panel_titles = [p.get("title", "").lower() for p in dash["panels"]]

        assert any("gap" in t for t in panel_titles), "No gap panels found"

    def test_learning_performance_has_budget_panels(self, load_dashboard: callable) -> None:
        """Test learning performance dashboard has budget panels."""
        dash = load_dashboard("p03_learning_performance.json")
        panel_titles = [p.get("title", "").lower() for p in dash["panels"]]

        assert any("budget" in t for t in panel_titles), "No budget panels found"

    def test_formula_comparison_has_version_panels(self, load_dashboard: callable) -> None:
        """Test formula comparison dashboard has version comparison panels."""
        dash = load_dashboard("p03_formula_comparison.json")
        panel_titles = [p.get("title", "").lower() for p in dash["panels"]]

        # Should have comparison panels
        assert any(
            "comparison" in t or "version" in t or "current" in t or "candidate" in t
            for t in panel_titles
        ), "No version comparison panels found"


class TestDashboardPrometheusQueries:
    """Tests for Prometheus queries in dashboards."""

    @pytest.fixture
    def load_dashboard(self) -> callable:
        """Factory to load dashboard JSON."""

        def _load(name: str) -> dict[str, Any]:
            path = DASHBOARD_DIR / name
            if not path.exists():
                pytest.skip(f"Dashboard {name} not found")
            with open(path) as f:
                return json.load(f)

        return _load

    def _extract_queries(self, dashboard: dict[str, Any]) -> list[str]:
        """Extract all Prometheus queries from dashboard."""
        queries = []
        for panel in dashboard.get("panels", []):
            for target in panel.get("targets", []):
                if "expr" in target:
                    queries.append(target["expr"])
        return queries

    def test_health_dashboard_uses_p03_metrics(self, load_dashboard: callable) -> None:
        """Test health dashboard uses P03 metrics."""
        dash = load_dashboard("p03_health.json")
        queries = self._extract_queries(dash)

        # Should use P03 metrics
        p03_queries = [q for q in queries if "p03_" in q]
        assert len(p03_queries) > 0, "No P03 metrics found in queries"

    def test_formula_comparison_uses_formula_metrics(self, load_dashboard: callable) -> None:
        """Test formula comparison dashboard uses formula metrics."""
        dash = load_dashboard("p03_formula_comparison.json")
        queries = self._extract_queries(dash)

        # Should use formula comparison metrics
        formula_queries = [q for q in queries if "p03_formula" in q]
        assert len(formula_queries) > 0, "No formula metrics found in queries"

    def test_dashboards_use_prometheus_datasource(self, load_dashboard: callable) -> None:
        """Test all dashboards use prometheus datasource."""
        for dashboard_name in [
            "p03_health.json",
            "p03_memory_growth.json",
            "p03_active_learning.json",
            "p03_learning_performance.json",
            "p03_formula_comparison.json",
        ]:
            try:
                dash = load_dashboard(dashboard_name)
            except Exception:
                continue

            for panel in dash.get("panels", []):
                datasource = panel.get("datasource", {})
                if isinstance(datasource, dict):
                    ds_type = datasource.get("type", "")
                    assert ds_type == "prometheus", f"Panel {panel.get('title')} uses {ds_type}"


class TestDashboardRefreshAndTimeRange:
    """Tests for dashboard refresh and time range settings."""

    @pytest.fixture
    def load_dashboard(self) -> callable:
        """Factory to load dashboard JSON."""

        def _load(name: str) -> dict[str, Any]:
            path = DASHBOARD_DIR / name
            if not path.exists():
                pytest.skip(f"Dashboard {name} not found")
            with open(path) as f:
                return json.load(f)

        return _load

    def test_dashboards_have_refresh_setting(self, load_dashboard: callable) -> None:
        """Test all dashboards have refresh setting."""
        for dashboard_name in [
            "p03_health.json",
            "p03_memory_growth.json",
            "p03_active_learning.json",
            "p03_learning_performance.json",
            "p03_formula_comparison.json",
        ]:
            try:
                dash = load_dashboard(dashboard_name)
            except Exception:
                continue

            assert "refresh" in dash, f"{dashboard_name} missing refresh setting"
            # Refresh should be reasonable (not too fast)
            refresh = dash["refresh"]
            assert refresh in ["10s", "30s", "1m", "5m", "1h"], f"Unusual refresh: {refresh}"

    def test_dashboards_have_time_range(self, load_dashboard: callable) -> None:
        """Test all dashboards have time range."""
        for dashboard_name in [
            "p03_health.json",
            "p03_memory_growth.json",
            "p03_active_learning.json",
            "p03_learning_performance.json",
            "p03_formula_comparison.json",
        ]:
            try:
                dash = load_dashboard(dashboard_name)
            except Exception:
                continue

            assert "time" in dash, f"{dashboard_name} missing time setting"
            assert "from" in dash["time"]
            assert "to" in dash["time"]
