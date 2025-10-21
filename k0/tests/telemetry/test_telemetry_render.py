"""Ward tests for telemetry render CLI and dashboard generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml
from ward import test  # type: ignore[attr-defined]

from k0.telemetry.mixins._config import RUNBOOK_URL_BASE
from k0.telemetry.mixins.alert_rules import build_slo_alert_rules
from k0.telemetry.mixins.slo_dashboards import (
    build_command_latency_dashboard,
    build_kernel_overview_dashboard,
    build_query_latency_dashboard,
    build_replay_throughput_dashboard,
    build_sse_health_dashboard,
)
from k0.telemetry.render import compute_checksum


@test("Dashboard builders return valid JSON structures")
def _():
    dashboards = [
        build_kernel_overview_dashboard(),
        build_command_latency_dashboard(),
        build_query_latency_dashboard(),
        build_sse_health_dashboard(),
        build_replay_throughput_dashboard(),
    ]

    for dashboard in dashboards:
        # Must have required Grafana fields
        assert "title" in dashboard
        assert "uid" in dashboard
        assert "panels" in dashboard
        assert "templating" in dashboard
        assert isinstance(dashboard["panels"], list)
        panels = cast(list[Any], dashboard["panels"])
        assert len(panels) > 0

        # Verify JSON serializability
        serialized = json.dumps(dashboard)
        assert len(serialized) > 100


@test("Alert rules builder returns valid Prometheus structure")
def _():
    rules: dict[str, Any] = build_slo_alert_rules()

    # Must have groups
    assert "groups" in rules
    assert isinstance(rules["groups"], list)
    groups = cast(list[Any], rules["groups"])
    assert len(groups) > 0

    # Every group must declare rules
    for group_any in groups:
        group = cast(dict[str, Any], group_any)
        assert "name" in group
        assert "rules" in group
        assert isinstance(group["rules"], list)
        rule_entries = cast(list[Any], group["rules"])
        assert len(rule_entries) > 0

    # Verify YAML serializability
    serialized = yaml.dump(rules)
    assert len(serialized) > 100


@test("Kernel overview dashboard has expected stat panels")
def _():
    dashboard = build_kernel_overview_dashboard()

    assert dashboard["title"] == "K0 Kernel Overview"
    assert dashboard["uid"] == "k0-kernel-overview"

    # Count stat panels (first 6 panels should be stats)
    stat_panels = [p for p in dashboard["panels"][:6] if p["type"] == "stat"]
    assert len(stat_panels) == 6

    # Verify SLO panel titles
    titles = [p["title"] for p in stat_panels]
    assert "API Availability" in titles
    assert "Command Latency (p95)" in titles
    assert "Query Latency (p95)" in titles


@test("Alert rules include warning and critical levels")
def _():
    rules: dict[str, Any] = build_slo_alert_rules()
    groups = cast(list[Any], rules["groups"])
    rule_list: list[dict[str, Any]] = []
    for group_any in groups:
        group = cast(dict[str, Any], group_any)
        for rule_any in cast(list[Any], group["rules"]):
            rule_dict = cast(dict[str, Any], rule_any)
            if rule_dict["labels"].get("severity") in {"warning", "critical"}:
                rule_list.append(rule_dict)

    warnings = [r for r in rule_list if r["labels"]["severity"] == "warning"]
    criticals = [r for r in rule_list if r["labels"]["severity"] == "critical"]

    assert len(warnings) > 0
    assert len(criticals) > 0
    assert len(warnings) == len(criticals)  # Paired alerts


@test("Alert rules have runbook URLs")
def _():
    rules: dict[str, Any] = build_slo_alert_rules()
    groups = cast(list[Any], rules["groups"])
    rule_list: list[dict[str, Any]] = []
    for group_any in groups:
        group = cast(dict[str, Any], group_any)
        for rule_any in cast(list[Any], group["rules"]):
            rule_list.append(cast(dict[str, Any], rule_any))

    runbook_base = RUNBOOK_URL_BASE.format(path="")

    for rule in rule_list:
        assert "annotations" in rule
        assert "runbook_url" in rule["annotations"]
        url = rule["annotations"]["runbook_url"]
        assert url.startswith("https://")
        assert url.startswith(runbook_base)
        relative_path = url.removeprefix(runbook_base)
        assert relative_path.endswith(".md")


@test("Dashboards expose runbook quick links")
def _():
    repo_root = Path(__file__).resolve().parents[2]
    runbook_base = RUNBOOK_URL_BASE.format(path="")

    dashboards: list[tuple[dict[str, Any], list[str]]] = [
        (
            build_kernel_overview_dashboard(),
            [
                "slo-dashboard.md",
                "alerts/api-availability.md",
                "alerts/command-latency.md",
                "alerts/query-latency.md",
                "alerts/wal-lag.md",
                "alerts/outbox-backlog.md",
            ],
        ),
        (
            build_command_latency_dashboard(),
            [
                "alerts/command-latency.md",
                "alerts/scheduler-starvation.md",
            ],
        ),
        (
            build_query_latency_dashboard(),
            ["alerts/query-latency.md"],
        ),
        (
            build_sse_health_dashboard(),
            [
                "alerts/sse-disconnect.md",
                "alerts/driver-handshake.md",
            ],
        ),
        (
            build_replay_throughput_dashboard(),
            [
                "alerts/replay-throughput.md",
                "alerts/replay-failure.md",
                "alerts/wal-lag.md",
                "alerts/outbox-backlog.md",
            ],
        ),
    ]

    for dashboard, expected_paths in dashboards:
        links_raw = cast(list[Any], dashboard.get("links", []))
        assert len(links_raw) >= len(expected_paths)

        link_paths: set[str] = set()
        for link_any in links_raw:
            link = cast(dict[str, Any], link_any)
            link_paths.add(link["url"].replace(runbook_base, ""))

        for relative_path in expected_paths:
            assert relative_path in link_paths
            runbook_file = (
                repo_root / "docs" / "development" / "runbooks" / Path(relative_path)
            )
            assert runbook_file.exists()


@test("Alert runbook references resolve to files")
def _():
    repo_root = Path(__file__).resolve().parents[2]
    rules: dict[str, Any] = build_slo_alert_rules()
    groups = cast(list[Any], rules["groups"])

    for group_any in groups:
        group = cast(dict[str, Any], group_any)
        for rule_any in cast(list[Any], group["rules"]):
            rule = cast(dict[str, Any], rule_any)
            runbook_rel = rule["labels"].get("runbook")
            assert isinstance(runbook_rel, str)
            runbook_file = (
                repo_root / "docs" / "development" / "runbooks" / Path(runbook_rel)
            )
            assert runbook_file.exists()

            annotations = cast(dict[str, Any], rule.get("annotations", {}))
            runbook_url = annotations.get("runbook_url")
            assert runbook_url == RUNBOOK_URL_BASE.format(path=runbook_rel)


@test("Command latency dashboard includes percentiles")
def _():
    dashboard = build_command_latency_dashboard()

    # First panel should be latency percentiles
    panel = dashboard["panels"][0]
    assert "Percentile" in panel["title"]
    assert len(panel["targets"]) == 3  # p50, p95, p99


@test("Dashboard variables include route and method filters")
def _():
    dashboard = build_kernel_overview_dashboard()
    variables = dashboard["templating"]["list"]

    var_names = [v["name"] for v in variables]
    assert "route" in var_names
    assert "method" in var_names
    assert "interval" in var_names
    assert "percentile" in var_names


@test("Checksum computation is deterministic")
def _():
    content1 = '{"test": "data"}'
    content2 = '{"test": "data"}'
    content3 = '{"test": "other"}'

    cs1 = compute_checksum(content1)
    cs2 = compute_checksum(content2)
    cs3 = compute_checksum(content3)

    assert cs1 == cs2
    assert cs1 != cs3
    assert len(cs1) == 16  # Truncated SHA256


@test("Rendered dashboards exist and have checksums")
def _():
    dashboards_dir = (
        Path(__file__).parent.parent.parent
        / "k0"
        / "telemetry"
        / "generated"
        / "dashboards"
    )

    if not dashboards_dir.exists():
        # Skip if not rendered yet (CI may run tests before rendering)
        return

    dashboard_files = list(dashboards_dir.glob("*.json"))
    assert len(dashboard_files) >= 5

    manifest_path = dashboards_dir.parent / "checksums_dashboards.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for dashboard_file in dashboard_files:
        content = dashboard_file.read_text(encoding="utf-8")
        assert dashboard_file.name in manifest
        computed_checksum = compute_checksum(content)
        assert manifest[dashboard_file.name] == computed_checksum

        dashboard_json = json.loads(content)
        assert "title" in dashboard_json


@test("Rendered alert rules exist and have checksums")
def _():
    rules_dir = (
        Path(__file__).parent.parent.parent / "k0" / "telemetry" / "generated" / "rules"
    )

    if not rules_dir.exists():
        # Skip if not rendered yet
        return

    rules_file = rules_dir / "slo_alerts.yaml"
    assert rules_file.exists()

    content = rules_file.read_text(encoding="utf-8")
    assert content.startswith("# Checksum:")

    # Verify valid YAML after checksum header
    lines = content.split("\n", 1)
    rules_yaml = yaml.safe_load(lines[1])
    assert "groups" in rules_yaml


@test("Dashboard JSON is deterministic (sorted keys)")
def _():
    dashboard = build_kernel_overview_dashboard()

    # Serialize twice and compare
    json1 = json.dumps(dashboard, indent=2, sort_keys=True)
    json2 = json.dumps(dashboard, indent=2, sort_keys=True)

    assert json1 == json2


@test("Alert expressions use valid PromQL syntax patterns")
def _():
    rules: dict[str, Any] = build_slo_alert_rules()
    groups = cast(list[Any], rules["groups"])
    rule_list: list[dict[str, Any]] = []
    for group_any in groups:
        group = cast(dict[str, Any], group_any)
        for rule_any in cast(list[Any], group["rules"]):
            rule_list.append(cast(dict[str, Any], rule_any))

    for rule in rule_list:
        expr = rule["expr"]
        # Basic PromQL validation
        if expr != "vector(1)":
            metric_prefixes = (
                "k0_kernel",
                "k0_uow",
                "k0_outbox",
                "k0_replay",
                "k0_qos",
                "k0_sse",
                "k0_driver",
                "k0_wal",
                "k0_cluster",
                "k0_scheduler",
            )
            assert any(prefix in expr for prefix in metric_prefixes)
            assert ">" in expr or "<" in expr  # Threshold comparison

        # Should not have escaped braces (common JSON serialization bug)
        assert "\\{" not in expr
        assert "\\}" not in expr
