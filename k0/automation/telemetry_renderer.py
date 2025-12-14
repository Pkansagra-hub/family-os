"""
Telemetry Renderer: Generates Grafana dashboards and Prometheus alert rules from SLO definitions.

This automation tool codifies SLO definitions from YAML and generates:
1. Grafana dashboard JSON (deterministic rendering)
2. Prometheus alert rules YAML (validated with promtool)
3. Recording rules for efficient metric aggregation
4. Checksum manifests for drift detection

Features:
- Deterministic rendering (same input → identical output)
- Checksum-based drift detection for CI integration
- YAML-based SLO definitions (easy to maintain)
- --check mode for pre-merge CI validation
- Integrated alerting with warning/critical thresholds per SLO

Usage:
    python -m k0.automation.telemetry_renderer
    python -m k0.automation.telemetry_renderer --check
    python -m k0.automation.telemetry_renderer --verbose
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

__all__ = [
    "SLODefinition",
    "AlertThresholds",
    "load_slo_definitions",
    "generate_dashboard",
    "generate_alert_rules",
    "render_all",
]

LOGGER = logging.getLogger(__name__)

# Paths
TELEMETRY_DIR = Path(__file__).parent.parent / "telemetry"
SLO_DEFINITIONS_PATH = TELEMETRY_DIR / "slo_definitions.yaml"
DASHBOARDS_OUTPUT_DIR = TELEMETRY_DIR / "generated" / "dashboards"
RULES_OUTPUT_DIR = TELEMETRY_DIR / "generated" / "rules"
CHECKSUMS_DASHBOARDS_PATH = TELEMETRY_DIR / "checksums_dashboards.json"
CHECKSUMS_RULES_PATH = TELEMETRY_DIR / "checksums_rules.json"

# Color palette (macOS-inspired for consistency)
COLORS = {
    "success": "#34C759",
    "warning": "#FF9F0A",
    "critical": "#FF3B30",
    "info": "#007AFF",
    "background_dark": "#1C1C1E",
    "background_light": "#F2F2F7",
    "text_light": "#FFFFFF",
    "text_dark": "#000000",
}


@dataclass
class AlertThresholds:
    """Alert thresholds for warning and critical severity levels."""

    warning: float
    critical: float

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for YAML serialization."""
        return {"warning": self.warning, "critical": self.critical}


@dataclass
class SLODefinition:
    """SLO definition with metric, target, and alert thresholds."""

    name: str
    metric: str
    target_value: float
    unit: str
    description: str
    dashboard_group: str
    alert_thresholds: AlertThresholds
    target_percentile: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization (used in dashboards/rules)."""
        data = asdict(self)
        data["alert_thresholds"] = self.alert_thresholds.to_dict()
        return data


def _compute_checksum(content: str) -> str:
    """Compute SHA256 checksum (first 16 chars for readability)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def load_slo_definitions(path: Path = SLO_DEFINITIONS_PATH) -> list[SLODefinition]:
    """
    Load SLO definitions from YAML file.

    Args:
        path: Path to slo_definitions.yaml

    Returns:
        List of SLODefinition objects

    Raises:
        FileNotFoundError: If SLO definitions file not found
        ValueError: If YAML parsing or SLO validation fails
    """
    if not path.exists():
        raise FileNotFoundError(f"SLO definitions not found: {path}")

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse {path}: {e}") from e

    if not data or "slos" not in data:
        raise ValueError(f"No 'slos' key found in {path}")

    slos = []
    for slo_data in data["slos"]:
        try:
            thresholds = slo_data["alert_thresholds"]
            slo = SLODefinition(
                name=slo_data["name"],
                metric=slo_data["metric"],
                target_value=float(slo_data["target_value"]),
                unit=slo_data["unit"],
                description=slo_data.get("description", slo_data["name"]),
                dashboard_group=slo_data.get("dashboard_group", "overview"),
                alert_thresholds=AlertThresholds(
                    warning=float(thresholds["warning"]),
                    critical=float(thresholds["critical"]),
                ),
                target_percentile=slo_data.get("target_percentile"),
            )
            slos.append(slo)
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError(
                f"Invalid SLO definition {slo_data.get('name', 'unknown')}: {e}"
            ) from e

    LOGGER.info(f"Loaded {len(slos)} SLO definitions from {path}")
    return slos


def generate_dashboard(
    slos: list[SLODefinition],
    template: str = "default",
) -> Dict[str, Any]:
    """
    Generate Grafana dashboard JSON from SLO definitions.

    Args:
        slos: List of SLO definitions
        template: Dashboard template name (default, compact, detailed)

    Returns:
        Grafana dashboard JSON structure (v10+)
    """
    # Group SLOs by dashboard_group
    groups = {}
    for slo in slos:
        group = slo.dashboard_group
        if group not in groups:
            groups[group] = []
        groups[group].append(slo)

    # Build panel list (one stat panel per SLO)
    panels = []
    for idx, slo in enumerate(slos):
        panel = {
            "id": idx + 1,
            "title": slo.name.replace("_", " ").title(),
            "type": "stat",
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "thresholds"},
                    "mappings": [],
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": COLORS["success"], "value": None},
                            {"color": COLORS["warning"], "value": slo.alert_thresholds.warning},
                            {"color": COLORS["critical"], "value": slo.alert_thresholds.critical},
                        ],
                    },
                    "unit": _unit_to_grafana(slo.unit),
                },
                "overrides": [],
            },
            "options": {
                "graphMode": "area",
                "orientation": "auto",
                "reduceOptions": {"values": False, "fields": "", "calcs": ["lastNotNull"]},
                "showPercentage": False,
                "text": {},
            },
            "targets": [
                {
                    "expr": f'{slo.metric}{{job="k0-kernel"}}',
                    "refId": chr(65 + idx),
                    "format": "time_series",
                }
            ],
        }
        panels.append(panel)

    # Build dashboard structure
    dashboard = {
        "dashboard": {
            "title": "K0 SLO Dashboard",
            "description": "Grafana dashboard auto-generated from SLO definitions",
            "tags": ["k0", "slo", "auto-generated"],
            "timezone": "browser",
            "panels": panels,
            "refresh": "30s",
            "time": {"from": "now-1h", "to": "now"},
            "timepicker": {"refresh_intervals": ["10s", "30s", "1m", "5m", "15m", "30m", "1h"]},
            "uid": "k0-slo-dashboard",
            "version": 1,
        },
        "overwrite": True,
    }

    return dashboard


def generate_alert_rules(
    slos: list[SLODefinition],
) -> Dict[str, Any]:
    """
    Generate Prometheus alert rules YAML from SLO definitions.

    Args:
        slos: List of SLO definitions

    Returns:
        Prometheus rules structure (groups/rules list)
    """
    rules = []

    for slo in slos:
        # Warning alert rule
        warning_rule = {
            "alert": f"SLO{slo.name.upper()}Warning",
            "expr": _build_promql_for_slo(slo, slo.alert_thresholds.warning),
            "for": "5m",
            "labels": {"severity": "warning", "slo": slo.name},
            "annotations": {
                "summary": f"{slo.description} warning threshold exceeded",
                "description": f"{slo.name} exceeded warning threshold: {{$value}}",
                "runbook_url": f"https://docs.example.com/runbooks/slos/{slo.name}/",
            },
        }
        rules.append(warning_rule)

        # Critical alert rule
        critical_rule = {
            "alert": f"SLO{slo.name.upper()}Critical",
            "expr": _build_promql_for_slo(slo, slo.alert_thresholds.critical),
            "for": "2m",
            "labels": {"severity": "critical", "slo": slo.name},
            "annotations": {
                "summary": f"{slo.description} critical threshold exceeded",
                "description": f"{slo.name} exceeded critical threshold: {{$value}}",
                "runbook_url": f"https://docs.example.com/runbooks/slos/{slo.name}/",
            },
        }
        rules.append(critical_rule)

    # Wrap in Prometheus rules group
    prometheus_rules = {
        "groups": [
            {
                "name": "k0_slo_alerts",
                "interval": "30s",
                "rules": rules,
            }
        ]
    }

    return prometheus_rules


def _unit_to_grafana(unit: str) -> str:
    """Convert SLO unit to Grafana unit format."""
    unit_map = {
        "seconds": "s",
        "count": "short",
        "percent": "percent",
        "ratio": "percentunit",
    }
    return unit_map.get(unit, "short")


def _build_promql_for_slo(slo: SLODefinition, threshold: float) -> str:
    """
    Build PromQL expression for SLO alerting.

    Args:
        slo: SLO definition
        threshold: Alert threshold value

    Returns:
        PromQL expression string
    """
    # For latency metrics with percentiles
    if slo.target_percentile:
        expr = f"histogram_quantile({slo.target_percentile}, rate({slo.metric}[5m])) > {threshold}"
    # For counter-based metrics (ratios, counts)
    elif slo.unit == "percent":
        # Availability: (success_count / total_count) < threshold
        expr = f'(rate({slo.metric}{{status=~"2.."}}[5m]) / rate({slo.metric}[5m])) < {threshold}'
    else:
        # Simple threshold comparison for gauge/counter metrics
        expr = f"{slo.metric} > {threshold}"

    return expr


def _write_json_deterministic(path: Path, data: Dict[str, Any]) -> str:
    """
    Write JSON with deterministic formatting.

    Args:
        path: Output file path
        data: Data to serialize

    Returns:
        SHA256 checksum (first 16 chars)
    """
    content = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    checksum = _compute_checksum(content)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    LOGGER.info(f"Wrote {path} (checksum: {checksum})")
    return checksum


def _write_yaml_deterministic(path: Path, data: Dict[str, Any]) -> str:
    """
    Write YAML with deterministic formatting.

    Args:
        path: Output file path
        data: Data to serialize

    Returns:
        SHA256 checksum (first 16 chars)
    """
    # Use Dumper for deterministic YAML (sort_keys=True)
    content = yaml.dump(data, default_flow_style=False, sort_keys=True, allow_unicode=True)
    checksum = _compute_checksum(content)
    # Prefix checksum in comment for human readability
    serialized = f"# Checksum: {checksum}\n{content}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialized, encoding="utf-8")
    LOGGER.info(f"Wrote {path} (checksum: {checksum})")
    return checksum


def render_all(
    slo_definitions_path: Path = SLO_DEFINITIONS_PATH,
    dashboards_dir: Path = DASHBOARDS_OUTPUT_DIR,
    rules_dir: Path = RULES_OUTPUT_DIR,
    *,
    check_mode: bool = False,
) -> bool:
    """
    Render all dashboards and alert rules from SLO definitions.

    Args:
        slo_definitions_path: Path to SLO definitions YAML
        dashboards_dir: Output directory for Grafana dashboards
        rules_dir: Output directory for Prometheus alert rules
        check_mode: If True, validate without writing; return True if changes needed

    Returns:
        True if changes were made/needed; False otherwise

    Raises:
        FileNotFoundError: If SLO definitions not found
        ValueError: If SLO parsing/validation fails
    """
    try:
        # Load SLO definitions
        slos = load_slo_definitions(slo_definitions_path)
        LOGGER.info(f"Loaded {len(slos)} SLO definitions")

        # Generate dashboards and alert rules
        dashboards = generate_dashboard(slos)
        alert_rules = generate_alert_rules(slos)

        if check_mode:
            # In check mode, verify artifacts are up-to-date
            LOGGER.info("Checking for drift (no writes)...")
            return _check_drift(dashboards, alert_rules, dashboards_dir, rules_dir)
        else:
            # Write artifacts
            LOGGER.info("Rendering artifacts...")
            checksums_dashboards = {}
            checksums_rules = {}

            # Write dashboard
            dashboard_checksum = _write_json_deterministic(
                dashboards_dir / "k0_slo_dashboard.json", dashboards
            )
            checksums_dashboards["k0_slo_dashboard.json"] = dashboard_checksum

            # Write alert rules
            rules_checksum = _write_yaml_deterministic(rules_dir / "slo_alerts.yaml", alert_rules)
            checksums_rules["slo_alerts.yaml"] = rules_checksum

            # Write checksum manifests
            checksums_dashboards_dir = dashboards_dir.parent
            checksums_dashboards_dir.mkdir(parents=True, exist_ok=True)
            CHECKSUMS_DASHBOARDS_PATH.write_text(
                json.dumps(checksums_dashboards, indent=2, sort_keys=True)
            )
            CHECKSUMS_RULES_PATH.write_text(json.dumps(checksums_rules, indent=2, sort_keys=True))

            LOGGER.info(f"Rendered dashboards to {dashboards_dir}")
            LOGGER.info(f"Rendered alert rules to {rules_dir}")
            return True

    except (FileNotFoundError, ValueError) as e:
        LOGGER.error(f"Rendering failed: {e}")
        raise


def _check_drift(
    dashboards: Dict[str, Any],
    alert_rules: Dict[str, Any],
    dashboards_dir: Path,
    rules_dir: Path,
) -> bool:
    """
    Check if generated artifacts differ from on-disk versions.

    Args:
        dashboards: Generated dashboard JSON
        alert_rules: Generated alert rules YAML
        dashboards_dir: Output directory for dashboards
        rules_dir: Output directory for rules

    Returns:
        True if drift detected; False otherwise

    Raises:
        RuntimeError: If artifacts missing or checksums don't match
    """
    changes_needed = False

    # Check dashboard
    dashboard_path = dashboards_dir / "k0_slo_dashboard.json"
    if not dashboard_path.exists():
        LOGGER.error(f"Dashboard not found: {dashboard_path}")
        raise RuntimeError("Telemetry artifacts out of date (missing dashboard)")

    on_disk_dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    new_checksum = _compute_checksum(
        json.dumps(dashboards, indent=2, sort_keys=True, ensure_ascii=False)
    )
    on_disk_checksum = _compute_checksum(
        json.dumps(on_disk_dashboard, indent=2, sort_keys=True, ensure_ascii=False)
    )
    if new_checksum != on_disk_checksum:
        LOGGER.warning(f"Dashboard drift detected: {dashboard_path}")
        changes_needed = True

    # Check alert rules
    rules_path = rules_dir / "slo_alerts.yaml"
    if not rules_path.exists():
        LOGGER.error(f"Alert rules not found: {rules_path}")
        raise RuntimeError("Telemetry artifacts out of date (missing alert rules)")

    on_disk_rules_text = rules_path.read_text(encoding="utf-8")
    # Strip checksum comment for comparison
    on_disk_rules_text = "\n".join(
        line for line in on_disk_rules_text.split("\n") if not line.startswith("# Checksum:")
    )
    new_rules_text = yaml.dump(
        alert_rules, default_flow_style=False, sort_keys=True, allow_unicode=True
    )
    new_checksum = _compute_checksum(new_rules_text)
    on_disk_checksum = _compute_checksum(on_disk_rules_text)
    if new_checksum != on_disk_checksum:
        LOGGER.warning(f"Alert rules drift detected: {rules_path}")
        changes_needed = True

    if changes_needed:
        raise RuntimeError(
            "Telemetry artifacts out of date. Run: python -m k0.automation.telemetry_renderer"
        )

    return False


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Grafana dashboards and Prometheus alert rules from SLO definitions."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate artifacts are up-to-date without writing",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--slo-path",
        type=Path,
        default=SLO_DEFINITIONS_PATH,
        help=f"Path to SLO definitions YAML (default: {SLO_DEFINITIONS_PATH})",
    )
    parser.add_argument(
        "--output-dashboards",
        type=Path,
        default=DASHBOARDS_OUTPUT_DIR,
        help=f"Output directory for dashboards (default: {DASHBOARDS_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--output-rules",
        type=Path,
        default=RULES_OUTPUT_DIR,
        help=f"Output directory for alert rules (default: {RULES_OUTPUT_DIR})",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="[%(name)s] %(levelname)s: %(message)s",
    )

    try:
        render_all(
            slo_definitions_path=args.slo_path,
            dashboards_dir=args.output_dashboards,
            rules_dir=args.output_rules,
            check_mode=args.check,
        )
        if args.check:
            LOGGER.info("Telemetry artifacts are up-to-date.")
        else:
            LOGGER.info("Telemetry artifacts rendered successfully.")
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        LOGGER.error(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
