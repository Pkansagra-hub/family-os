"""Comprehensive tests for telemetry_renderer.py - SLO-based dashboard and alert generation."""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from k0.automation.telemetry_renderer import (
    AlertThresholds,
    SLODefinition,
    _build_promql_for_slo,
    _compute_checksum,
    _write_json_deterministic,
    _write_yaml_deterministic,
    generate_alert_rules,
    generate_dashboard,
    load_slo_definitions,
    render_all,
)


class TestSLODefinition:
    """Tests for SLODefinition dataclass."""

    def test_slo_definition_creation(self):
        """Test creating an SLO definition with all fields."""
        slo = SLODefinition(
            name="test_latency",
            metric="test_metric_seconds",
            target_value=0.100,
            unit="seconds",
            description="Test latency SLO",
            dashboard_group="latency",
            alert_thresholds=AlertThresholds(warning=0.150, critical=0.250),
            target_percentile=0.95,
        )

        assert slo.name == "test_latency"
        assert slo.metric == "test_metric_seconds"
        assert slo.target_value == 0.100
        assert slo.unit == "seconds"
        assert slo.target_percentile == 0.95

    def test_slo_definition_to_dict(self):
        """Test SLO definition serialization to dict."""
        slo = SLODefinition(
            name="test_slo",
            metric="test_metric",
            target_value=100.0,
            unit="count",
            description="Test SLO",
            dashboard_group="overview",
            alert_thresholds=AlertThresholds(warning=150.0, critical=200.0),
        )

        slo_dict = slo.to_dict()
        assert slo_dict["name"] == "test_slo"
        assert slo_dict["alert_thresholds"]["warning"] == 150.0
        assert slo_dict["alert_thresholds"]["critical"] == 200.0


class TestAlertThresholds:
    """Tests for AlertThresholds dataclass."""

    def test_alert_thresholds_creation(self):
        """Test creating alert thresholds."""
        thresholds = AlertThresholds(warning=0.150, critical=0.250)
        assert thresholds.warning == 0.150
        assert thresholds.critical == 0.250

    def test_alert_thresholds_to_dict(self):
        """Test alert thresholds serialization."""
        thresholds = AlertThresholds(warning=100.0, critical=200.0)
        thresholds_dict = thresholds.to_dict()
        assert thresholds_dict == {"warning": 100.0, "critical": 200.0}


class TestLoadSLODefinitions:
    """Tests for loading SLO definitions from YAML."""

    def test_load_valid_slo_definitions(self):
        """Test loading valid SLO definitions."""
        yaml_content = """
slos:
  - name: test_latency
    metric: k0_test_duration_seconds
    target_percentile: 0.95
    target_value: 0.100
    unit: seconds
    description: Test latency
    dashboard_group: latency
    alert_thresholds:
      warning: 0.150
      critical: 0.250
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = Path(f.name)

        try:
            slos = load_slo_definitions(path)
            assert len(slos) == 1
            assert slos[0].name == "test_latency"
            assert slos[0].target_percentile == 0.95
        finally:
            path.unlink()

    def test_load_multiple_slos(self):
        """Test loading multiple SLO definitions."""
        yaml_content = """
slos:
  - name: slo1
    metric: metric1
    target_value: 100
    unit: count
    description: SLO 1
    dashboard_group: group1
    alert_thresholds:
      warning: 150
      critical: 200
  - name: slo2
    metric: metric2
    target_value: 50
    unit: seconds
    description: SLO 2
    dashboard_group: group2
    alert_thresholds:
      warning: 75
      critical: 100
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = Path(f.name)

        try:
            slos = load_slo_definitions(path)
            assert len(slos) == 2
            assert slos[0].name == "slo1"
            assert slos[1].name == "slo2"
        finally:
            path.unlink()

    def test_load_slo_missing_file(self):
        """Test loading from non-existent file."""
        with pytest.raises(FileNotFoundError):
            load_slo_definitions(Path("/nonexistent/path/slos.yaml"))

    def test_load_slo_invalid_yaml(self):
        """Test loading invalid YAML."""
        invalid_yaml = "{ invalid yaml: : :"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(invalid_yaml)
            path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Failed to parse"):
                load_slo_definitions(path)
        finally:
            path.unlink()

    def test_load_slo_missing_slos_key(self):
        """Test loading YAML without 'slos' key."""
        yaml_content = "not_slos: []"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="No 'slos' key found"):
                load_slo_definitions(path)
        finally:
            path.unlink()

    def test_load_slo_missing_required_field(self):
        """Test loading SLO with missing required field."""
        yaml_content = """
slos:
  - name: incomplete_slo
    metric: metric
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Invalid SLO definition"):
                load_slo_definitions(path)
        finally:
            path.unlink()


class TestGenerateDashboard:
    """Tests for Grafana dashboard generation from SLO definitions."""

    def test_generate_dashboard_basic(self):
        """Test generating a basic dashboard from SLOs."""
        slos = [
            SLODefinition(
                name="test_latency",
                metric="k0_test_latency_seconds",
                target_value=0.100,
                unit="seconds",
                description="Test latency",
                dashboard_group="latency",
                alert_thresholds=AlertThresholds(warning=0.150, critical=0.250),
            ),
        ]

        dashboard = generate_dashboard(slos)

        assert "dashboard" in dashboard
        assert dashboard["dashboard"]["title"] == "K0 SLO Dashboard"
        assert len(dashboard["dashboard"]["panels"]) == 1
        assert dashboard["dashboard"]["panels"][0]["title"] == "Test Latency"

    def test_generate_dashboard_multiple_slos(self):
        """Test generating dashboard with multiple SLOs."""
        slos = [
            SLODefinition(
                name="latency1",
                metric="metric1",
                target_value=0.100,
                unit="seconds",
                description="Latency 1",
                dashboard_group="latency",
                alert_thresholds=AlertThresholds(warning=0.150, critical=0.250),
            ),
            SLODefinition(
                name="latency2",
                metric="metric2",
                target_value=0.050,
                unit="seconds",
                description="Latency 2",
                dashboard_group="latency",
                alert_thresholds=AlertThresholds(warning=0.100, critical=0.150),
            ),
        ]

        dashboard = generate_dashboard(slos)

        assert len(dashboard["dashboard"]["panels"]) == 2

    def test_dashboard_panel_structure(self):
        """Test that dashboard panels have correct structure."""
        slos = [
            SLODefinition(
                name="test_slo",
                metric="test_metric",
                target_value=100.0,
                unit="count",
                description="Test SLO",
                dashboard_group="overview",
                alert_thresholds=AlertThresholds(warning=150.0, critical=200.0),
            ),
        ]

        dashboard = generate_dashboard(slos)
        panel = dashboard["dashboard"]["panels"][0]

        # Verify required panel fields
        assert panel["type"] == "stat"
        assert "fieldConfig" in panel
        assert "targets" in panel
        assert len(panel["targets"]) > 0


class TestGenerateAlertRules:
    """Tests for Prometheus alert rule generation."""

    def test_generate_alert_rules_basic(self):
        """Test generating alert rules from SLOs."""
        slos = [
            SLODefinition(
                name="test_latency",
                metric="k0_test_latency_seconds",
                target_value=0.100,
                unit="seconds",
                description="Test latency",
                dashboard_group="latency",
                alert_thresholds=AlertThresholds(warning=0.150, critical=0.250),
                target_percentile=0.95,
            ),
        ]

        alert_rules = generate_alert_rules(slos)

        assert "groups" in alert_rules
        assert len(alert_rules["groups"]) == 1
        assert alert_rules["groups"][0]["name"] == "k0_slo_alerts"
        # Should have warning + critical for each SLO
        assert len(alert_rules["groups"][0]["rules"]) == 2

    def test_alert_rule_structure(self):
        """Test that alert rules have correct Prometheus structure."""
        slos = [
            SLODefinition(
                name="availability",
                metric="k0_http_requests_total",
                target_value=0.999,
                unit="percent",
                description="API availability",
                dashboard_group="overview",
                alert_thresholds=AlertThresholds(warning=0.995, critical=0.990),
            ),
        ]

        alert_rules = generate_alert_rules(slos)
        rules = alert_rules["groups"][0]["rules"]

        # Check warning rule
        warning_rule = rules[0]
        assert "alert" in warning_rule
        assert "expr" in warning_rule
        assert "for" in warning_rule
        assert "labels" in warning_rule
        assert "annotations" in warning_rule
        assert warning_rule["labels"]["severity"] == "warning"

        # Check critical rule
        critical_rule = rules[1]
        assert critical_rule["labels"]["severity"] == "critical"

    def test_alert_rule_multiple_slos(self):
        """Test alert rules with multiple SLOs."""
        slos = [
            SLODefinition(
                name="slo1",
                metric="metric1",
                target_value=100.0,
                unit="count",
                description="SLO 1",
                dashboard_group="group1",
                alert_thresholds=AlertThresholds(warning=150.0, critical=200.0),
            ),
            SLODefinition(
                name="slo2",
                metric="metric2",
                target_value=50.0,
                unit="seconds",
                description="SLO 2",
                dashboard_group="group2",
                alert_thresholds=AlertThresholds(warning=75.0, critical=100.0),
            ),
        ]

        alert_rules = generate_alert_rules(slos)
        rules = alert_rules["groups"][0]["rules"]

        # 2 SLOs × 2 severities = 4 rules
        assert len(rules) == 4


class TestBuildPromQL:
    """Tests for PromQL expression building."""

    def test_build_promql_latency_metric(self):
        """Test PromQL for latency metrics with percentile."""
        slo = SLODefinition(
            name="latency",
            metric="k0_latency_seconds",
            target_value=0.100,
            unit="seconds",
            description="Latency",
            dashboard_group="latency",
            alert_thresholds=AlertThresholds(warning=0.150, critical=0.250),
            target_percentile=0.95,
        )

        expr = _build_promql_for_slo(slo, 0.150)

        assert "histogram_quantile" in expr
        assert "0.95" in expr
        assert "> 0.15" in expr

    def test_build_promql_availability_metric(self):
        """Test PromQL for availability (percent) metrics."""
        slo = SLODefinition(
            name="availability",
            metric="k0_http_requests_total",
            target_value=0.999,
            unit="percent",
            description="Availability",
            dashboard_group="overview",
            alert_thresholds=AlertThresholds(warning=0.995, critical=0.990),
        )

        expr = _build_promql_for_slo(slo, 0.995)

        assert "rate(" in expr
        assert "status=~" in expr
        assert "< 0.995" in expr

    def test_build_promql_count_metric(self):
        """Test PromQL for count-based metrics."""
        slo = SLODefinition(
            name="throughput",
            metric="k0_throughput_total",
            target_value=1000.0,
            unit="count",
            description="Throughput",
            dashboard_group="performance",
            alert_thresholds=AlertThresholds(warning=500.0, critical=100.0),
        )

        expr = _build_promql_for_slo(slo, 500.0)

        assert "k0_throughput_total" in expr
        assert "> 500" in expr


class TestDeterministicRendering:
    """Tests for deterministic rendering (checksum verification)."""

    def test_compute_checksum(self):
        """Test checksum computation is deterministic."""
        content = "test content"
        checksum1 = _compute_checksum(content)
        checksum2 = _compute_checksum(content)
        assert checksum1 == checksum2

    def test_compute_checksum_length(self):
        """Test checksum is truncated to 16 chars."""
        content = "test"
        checksum = _compute_checksum(content)
        assert len(checksum) == 16

    def test_write_json_deterministic(self):
        """Test deterministic JSON writing."""
        data = {"z": 1, "a": 2, "m": 3}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            checksum1 = _write_json_deterministic(path, data)
            checksum2 = _write_json_deterministic(path, data)
            assert checksum1 == checksum2

    def test_write_yaml_deterministic(self):
        """Test deterministic YAML writing."""
        data = {"groups": [{"name": "test", "rules": []}]}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.yaml"
            checksum1 = _write_yaml_deterministic(path, data)
            checksum2 = _write_yaml_deterministic(path, data)
            assert checksum1 == checksum2


class TestCheckMode:
    """Tests for --check mode (drift detection)."""

    def test_check_mode_no_changes(self):
        """Test check mode when artifacts are current."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            dashboards_dir = tmpdir_path / "dashboards"
            rules_dir = tmpdir_path / "rules"

            # Create minimal SLO definitions
            yaml_content = """
slos:
  - name: test_slo
    metric: test_metric
    target_value: 100
    unit: count
    description: Test
    dashboard_group: overview
    alert_thresholds:
      warning: 150
      critical: 200
"""
            slo_path = tmpdir_path / "slos.yaml"
            slo_path.write_text(yaml_content)

            # First render
            render_all(
                slo_definitions_path=slo_path,
                dashboards_dir=dashboards_dir,
                rules_dir=rules_dir,
                check_mode=False,
            )

            # Check mode should succeed (no changes)
            result = render_all(
                slo_definitions_path=slo_path,
                dashboards_dir=dashboards_dir,
                rules_dir=rules_dir,
                check_mode=True,
            )
            assert result is False

    def test_check_mode_detects_drift(self):
        """Test check mode detects drift in artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            dashboards_dir = tmpdir_path / "dashboards"
            rules_dir = tmpdir_path / "rules"

            # Create minimal SLO definitions
            yaml_content = """
slos:
  - name: test_slo
    metric: test_metric
    target_value: 100
    unit: count
    description: Test
    dashboard_group: overview
    alert_thresholds:
      warning: 150
      critical: 200
"""
            slo_path = tmpdir_path / "slos.yaml"
            slo_path.write_text(yaml_content)

            # First render
            render_all(
                slo_definitions_path=slo_path,
                dashboards_dir=dashboards_dir,
                rules_dir=rules_dir,
                check_mode=False,
            )

            # Corrupt a file
            dashboard_file = dashboards_dir / "k0_slo_dashboard.json"
            corrupted = json.loads(dashboard_file.read_text())
            corrupted["dashboard"]["title"] = "Modified Title"
            dashboard_file.write_text(json.dumps(corrupted))

            # Check mode should fail (drift detected)
            with pytest.raises(RuntimeError, match="Telemetry artifacts out of date"):
                render_all(
                    slo_definitions_path=slo_path,
                    dashboards_dir=dashboards_dir,
                    rules_dir=rules_dir,
                    check_mode=True,
                )


class TestRenderAll:
    """Integration tests for full rendering pipeline."""

    def test_render_all_creates_files(self):
        """Test render_all creates all expected output files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            dashboards_dir = tmpdir_path / "dashboards"
            rules_dir = tmpdir_path / "rules"

            yaml_content = """
slos:
  - name: test_slo
    metric: test_metric
    target_value: 100
    unit: count
    description: Test SLO
    dashboard_group: overview
    alert_thresholds:
      warning: 150
      critical: 200
"""
            slo_path = tmpdir_path / "slos.yaml"
            slo_path.write_text(yaml_content)

            render_all(
                slo_definitions_path=slo_path,
                dashboards_dir=dashboards_dir,
                rules_dir=rules_dir,
            )

            # Verify files were created
            assert (dashboards_dir / "k0_slo_dashboard.json").exists()
            assert (rules_dir / "slo_alerts.yaml").exists()

    def test_render_all_files_are_valid_json_yaml(self):
        """Test that generated files are valid JSON/YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            dashboards_dir = tmpdir_path / "dashboards"
            rules_dir = tmpdir_path / "rules"

            yaml_content = """
slos:
  - name: test_slo
    metric: test_metric
    target_value: 100
    unit: count
    description: Test
    dashboard_group: overview
    alert_thresholds:
      warning: 150
      critical: 200
"""
            slo_path = tmpdir_path / "slos.yaml"
            slo_path.write_text(yaml_content)

            render_all(
                slo_definitions_path=slo_path,
                dashboards_dir=dashboards_dir,
                rules_dir=rules_dir,
            )

            # Verify JSON validity
            dashboard_file = dashboards_dir / "k0_slo_dashboard.json"
            dashboard_data = json.loads(dashboard_file.read_text())
            assert "dashboard" in dashboard_data

            # Verify YAML validity
            rules_file = rules_dir / "slo_alerts.yaml"
            rules_text = rules_file.read_text()
            # Skip checksum comment
            rules_text = "\n".join(
                line for line in rules_text.split("\n") if not line.startswith("# Checksum:")
            )
            rules_data = yaml.safe_load(rules_text)
            assert "groups" in rules_data

    def test_render_all_idempotent(self):
        """Test that running render_all twice produces identical output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            dashboards_dir = tmpdir_path / "dashboards"
            rules_dir = tmpdir_path / "rules"

            yaml_content = """
slos:
  - name: test_slo
    metric: test_metric
    target_value: 100
    unit: count
    description: Test
    dashboard_group: overview
    alert_thresholds:
      warning: 150
      critical: 200
"""
            slo_path = tmpdir_path / "slos.yaml"
            slo_path.write_text(yaml_content)

            # First render
            render_all(
                slo_definitions_path=slo_path,
                dashboards_dir=dashboards_dir,
                rules_dir=rules_dir,
            )
            dashboard1 = (dashboards_dir / "k0_slo_dashboard.json").read_text()

            # Second render
            render_all(
                slo_definitions_path=slo_path,
                dashboards_dir=dashboards_dir,
                rules_dir=rules_dir,
            )
            dashboard2 = (dashboards_dir / "k0_slo_dashboard.json").read_text()

            # Should be identical (checksums in YAML comment may differ, so compare content)
            dashboard_data1 = json.loads(dashboard1)
            dashboard_data2 = json.loads(dashboard2)
            assert dashboard_data1 == dashboard_data2
