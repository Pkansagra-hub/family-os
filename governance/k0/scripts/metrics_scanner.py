"""
Metrics Scanner for K0 Architecture Governance.

Scans Prometheus metrics, SLO definitions, alert rules, and dashboards from
Part 10 of k0_architecture_master.md and the observability codebase.

Scanner Categories:
- Prometheus Metrics: Part 10.1 inventory
- SLO Definitions: Part 10.2 registry
- Alert Rules: Part 10.3 registry
- Dashboards: Part 10.4 catalog

Usage:
    from governance.k0.scripts.metrics_scanner import (
        scan_prometheus_metrics_from_code,
        scan_metrics_from_master,
        diff_metrics_with_master,
    )
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _get_repo_root() -> Path:
    """Get the repository root directory."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


@dataclass
class MetricInfo:
    """Information about a Prometheus metric."""

    metric_id: str  # e.g., "MET-001"
    name: str  # e.g., "k0_api_request_latency_seconds"
    metric_type: str  # e.g., "histogram", "counter", "gauge"
    category: str  # e.g., "Latency", "Availability", "Saturation"
    labels: list[str]
    description: str = ""
    status: str = "Active"


@dataclass
class SloInfo:
    """Information about an SLO definition."""

    slo_id: str  # e.g., "SLO-001"
    name: str  # e.g., "api_availability"
    objective: str  # e.g., "99.9%"
    window: str  # e.g., "30d"
    category: str  # e.g., "Availability", "Latency"
    status: str = "Active"


@dataclass
class AlertInfo:
    """Information about an alert rule."""

    alert_id: str  # e.g., "ALT-001"
    name: str  # e.g., "K0ApiHighLatency"
    severity: str  # e.g., "warning", "critical"
    metric: str  # e.g., "k0_api_request_latency_seconds"
    threshold: str  # e.g., ">1s"
    related_slo: str = ""  # e.g., "SLO-001"
    status: str = "Active"


@dataclass
class DashboardInfo:
    """Information about a dashboard."""

    dashboard_id: str  # e.g., "DSH-001"
    name: str  # e.g., "K0 System Overview"
    platform: str  # e.g., "Grafana"
    category: str  # e.g., "Overview", "Pipeline", "Module"
    panels: int = 0
    status: str = "Active"


def scan_prometheus_metrics_from_code(obs_dir: Path | None = None) -> list[MetricInfo]:
    """
    Scan Prometheus metric definitions from k0/obs/metrics.py.

    Looks for Counter, Gauge, Histogram, and Summary definitions.
    """
    if obs_dir is None:
        obs_dir = _get_repo_root() / "k0" / "obs"

    metrics_file = obs_dir / "metrics.py"
    if not metrics_file.exists():
        return []

    content = metrics_file.read_text(encoding="utf-8")
    metrics: list[MetricInfo] = []
    metric_counter = 1

    # Pattern for metric definitions: Counter/Gauge/Histogram/Summary calls
    # Look for patterns like: Counter("k0_metric_name", "description", ["label1"])
    metric_pattern = re.compile(
        r'(Counter|Gauge|Histogram|Summary)\s*\(\s*["\']([^"\']+)["\']'
        r'(?:\s*,\s*["\']([^"\']+)["\'])?'
        r"(?:\s*,\s*\[([^\]]*)\])?",
        re.MULTILINE,
    )

    for match in metric_pattern.finditer(content):
        metric_type = match.group(1).lower()
        metric_name = match.group(2)
        description = match.group(3) or ""
        labels_str = match.group(4) or ""

        # Parse labels
        labels = []
        if labels_str:
            labels = [l.strip().strip("'\"") for l in labels_str.split(",") if l.strip()]

        # Categorize based on name
        category = _categorize_metric(metric_name)

        metrics.append(
            MetricInfo(
                metric_id=f"MET-{metric_counter:03d}",
                name=metric_name,
                metric_type=metric_type,
                category=category,
                labels=labels,
                description=description,
                status="Active",
            )
        )
        metric_counter += 1

    # Also look for lazy metric creation patterns like self._metrics[name]
    lazy_pattern = re.compile(r'["\']([a-z0-9_]+_(?:total|seconds|bytes|count|ratio))["\']')
    for match in lazy_pattern.finditer(content):
        metric_name = match.group(1)
        # Skip if already found
        if any(m.name == metric_name for m in metrics):
            continue

        # Try to determine type from name suffix
        if "_seconds" in metric_name:
            metric_type = "histogram"
        elif "_total" in metric_name:
            metric_type = "counter"
        elif "_bytes" in metric_name:
            metric_type = "gauge"
        else:
            metric_type = "gauge"

        category = _categorize_metric(metric_name)

        metrics.append(
            MetricInfo(
                metric_id=f"MET-{metric_counter:03d}",
                name=metric_name,
                metric_type=metric_type,
                category=category,
                labels=[],
                description="",
                status="Active",
            )
        )
        metric_counter += 1

    return metrics


def _categorize_metric(name: str) -> str:
    """Categorize a metric based on its name."""
    if "latency" in name or "duration" in name or "_seconds" in name:
        return "Latency"
    elif "error" in name or "failure" in name:
        return "Availability"
    elif "queue" in name or "pending" in name or "memory" in name:
        return "Saturation"
    elif "request" in name or "processed" in name:
        return "Throughput"
    elif "qos" in name or "quality" in name:
        return "QoS"
    else:
        return "Other"


def scan_metrics_from_master(master_path: Path) -> list[MetricInfo]:
    """
    Extract metric definitions from Part 10.1 of master document.
    """
    if not master_path.exists():
        return []

    content = master_path.read_text(encoding="utf-8")
    metrics: list[MetricInfo] = []

    # Find section 10.1
    section_match = re.search(
        r"## 10\.1 Prometheus Metrics Inventory.*?(?=## 10\.\d|# Part |\Z)",
        content,
        re.DOTALL,
    )

    if not section_match:
        return []

    section = section_match.group(0)

    # Look for metric entries in tables
    # Pattern: | MET-001 | k0_metric_name | histogram | Latency | label1,label2 | Active |
    metric_pattern = re.compile(
        r"\|\s*(MET-\d+)\s*\|\s*`?([^|`]+)`?\s*\|\s*[📊📈⏱️🔢]?\s*([^|]+)\s*\|\s*([^|]+)\s*\|"
        r"\s*([^|]+)\s*\|\s*([^|]+)\s*\|"
    )

    for match in metric_pattern.finditer(section):
        metric_id = match.group(1).strip()
        name = match.group(2).strip()
        metric_type = match.group(3).strip().lower()
        category = match.group(4).strip()
        labels_str = match.group(5).strip()
        status = match.group(6).strip()

        labels = [l.strip() for l in labels_str.split(",") if l.strip() and l.strip() != "-"]

        metrics.append(
            MetricInfo(
                metric_id=metric_id,
                name=name,
                metric_type=metric_type,
                category=category,
                labels=labels,
                description="",
                status=(
                    "Active"
                    if "Active" in status
                    else ("Deprecated" if "Deprecated" in status else "Planning")
                ),
            )
        )

    return metrics


def scan_slos_from_master(master_path: Path) -> list[SloInfo]:
    """
    Extract SLO definitions from Part 10.2 of master document.
    """
    if not master_path.exists():
        return []

    content = master_path.read_text(encoding="utf-8")
    slos: list[SloInfo] = []

    # Find section 10.2
    section_match = re.search(
        r"## 10\.2 SLO Definitions Registry.*?(?=## 10\.\d|# Part |\Z)",
        content,
        re.DOTALL,
    )

    if not section_match:
        return []

    section = section_match.group(0)

    # Pattern: | SLO-001 | name | objective | window | category | status |
    slo_pattern = re.compile(
        r"\|\s*(SLO-\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|"
    )

    for match in slo_pattern.finditer(section):
        slo_id = match.group(1).strip()
        name = match.group(2).strip()
        objective = match.group(3).strip()
        window = match.group(4).strip()
        category = match.group(5).strip()
        status = match.group(6).strip()

        slos.append(
            SloInfo(
                slo_id=slo_id,
                name=name,
                objective=objective,
                window=window,
                category=category,
                status="Active" if "Active" in status else "Planning",
            )
        )

    return slos


def scan_alerts_from_master(master_path: Path) -> list[AlertInfo]:
    """
    Extract alert rules from Part 10.3 of master document.
    """
    if not master_path.exists():
        return []

    content = master_path.read_text(encoding="utf-8")
    alerts: list[AlertInfo] = []

    # Find section 10.3
    section_match = re.search(
        r"## 10\.3 Alert Rules Registry.*?(?=## 10\.\d|# Part |\Z)",
        content,
        re.DOTALL,
    )

    if not section_match:
        return []

    section = section_match.group(0)

    # Pattern: | ALT-001 | name | severity | metric | threshold | slo | status |
    alert_pattern = re.compile(
        r"\|\s*(ALT-\d+)\s*\|\s*([^|]+)\s*\|\s*[⚠️🚨]?\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|"
        r"\s*([^|]+)\s*\|\s*([^|]+)\s*\|"
    )

    for match in alert_pattern.finditer(section):
        alert_id = match.group(1).strip()
        name = match.group(2).strip()
        severity = match.group(3).strip().lower()
        metric = match.group(4).strip()
        threshold = match.group(5).strip()
        related_slo = match.group(6).strip()
        status = match.group(7).strip()

        alerts.append(
            AlertInfo(
                alert_id=alert_id,
                name=name,
                severity=severity,
                metric=metric,
                threshold=threshold,
                related_slo=related_slo if related_slo != "-" else "",
                status="Active" if "Active" in status else "Planning",
            )
        )

    return alerts


def scan_dashboards_from_master(master_path: Path) -> list[DashboardInfo]:
    """
    Extract dashboard catalog from Part 10.4 of master document.
    """
    if not master_path.exists():
        return []

    content = master_path.read_text(encoding="utf-8")
    dashboards: list[DashboardInfo] = []

    # Find section 10.4
    section_match = re.search(
        r"## 10\.4 Dashboard Catalog.*?(?=## 10\.\d|# Part |\Z)",
        content,
        re.DOTALL,
    )

    if not section_match:
        return []

    section = section_match.group(0)

    # Pattern: | DSH-001 | name | platform | category | panels | status |
    dashboard_pattern = re.compile(
        r"\|\s*(DSH-\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*(\d+)\s*\|\s*([^|]+)\s*\|"
    )

    for match in dashboard_pattern.finditer(section):
        dashboard_id = match.group(1).strip()
        name = match.group(2).strip()
        platform = match.group(3).strip()
        category = match.group(4).strip()
        panels = int(match.group(5).strip())
        status = match.group(6).strip()

        dashboards.append(
            DashboardInfo(
                dashboard_id=dashboard_id,
                name=name,
                platform=platform,
                category=category,
                panels=panels,
                status="Active" if "Active" in status else "Planning",
            )
        )

    return dashboards


def diff_metrics_with_master(code_metrics: list[MetricInfo], master_path: Path) -> dict[str, Any]:
    """
    Compare scanned metrics from code with Part 10.1 registry.
    """
    master_metrics = scan_metrics_from_master(master_path)

    code_names = {m.name for m in code_metrics}
    master_names = {m.name for m in master_metrics}
    planning_names = {m.name for m in master_metrics if m.status == "Planning"}

    return {
        "missing_in_master": code_names - master_names,
        "missing_in_code": master_names - code_names - planning_names,
        "scanned_count": len(code_metrics),
        "registered_count": len(master_metrics),
        "planning_count": len(planning_names),
    }


if __name__ == "__main__":
    # Quick test
    print("=" * 60)
    print("Metrics Scanner Test")
    print("=" * 60)

    master_path = _get_repo_root() / "governance" / "k0" / "k0_architecture_master.md"

    print("\n[1] Scanning Prometheus metrics from code...")
    code_metrics = scan_prometheus_metrics_from_code()
    print(f"Found {len(code_metrics)} metrics in code:")
    for m in code_metrics[:10]:
        print(f"  {m.metric_id}: {m.name} ({m.metric_type}) [{m.category}]")
    if len(code_metrics) > 10:
        print(f"  ... and {len(code_metrics) - 10} more")

    print("\n[2] Scanning metrics from master...")
    master_metrics = scan_metrics_from_master(master_path)
    print(f"Found {len(master_metrics)} metrics in master:")
    for m in master_metrics[:5]:
        print(f"  {m.metric_id}: {m.name} ({m.status})")
    if len(master_metrics) > 5:
        print(f"  ... and {len(master_metrics) - 5} more")

    print("\n[3] Scanning SLOs from master...")
    slos = scan_slos_from_master(master_path)
    print(f"Found {len(slos)} SLOs:")
    for s in slos[:5]:
        print(f"  {s.slo_id}: {s.name} ({s.objective})")
    if len(slos) > 5:
        print(f"  ... and {len(slos) - 5} more")

    print("\n[4] Scanning alerts from master...")
    alerts = scan_alerts_from_master(master_path)
    print(f"Found {len(alerts)} alerts:")
    for a in alerts[:5]:
        print(f"  {a.alert_id}: {a.name} ({a.severity})")
    if len(alerts) > 5:
        print(f"  ... and {len(alerts) - 5} more")

    print("\n[5] Scanning dashboards from master...")
    dashboards = scan_dashboards_from_master(master_path)
    print(f"Found {len(dashboards)} dashboards:")
    for d in dashboards[:5]:
        print(f"  {d.dashboard_id}: {d.name}")
    if len(dashboards) > 5:
        print(f"  ... and {len(dashboards) - 5} more")

    print("\n[6] Testing diff...")
    if code_metrics:
        diff = diff_metrics_with_master(code_metrics, master_path)
        print(f"Metrics - Code: {diff['scanned_count']}, Master: {diff['registered_count']}")
        if diff["missing_in_master"]:
            print(f"  Missing in master: {len(diff['missing_in_master'])}")
        if diff["missing_in_code"]:
            print(f"  Missing in code: {len(diff['missing_in_code'])}")
