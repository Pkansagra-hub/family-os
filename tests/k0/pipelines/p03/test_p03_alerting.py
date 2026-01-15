"""Tests for P03 Alerting Rules (Issue 6.1.18).

Validates alert rule structure, thresholds, and Prometheus query syntax.
"""

from __future__ import annotations

from typing import Any

import pytest

from k0.pipelines.p03.ops.alerting import (
    P03_ALERT_THRESHOLDS,
    P03_SLO_TARGETS,
    build_p03_alert_rules,
)


class TestBuildP03AlertRules:
    """Tests for build_p03_alert_rules function."""

    @pytest.fixture
    def alert_rules(self) -> dict[str, Any]:
        """Build alert rules once for testing."""
        return build_p03_alert_rules()

    def test_returns_dict_with_groups(self, alert_rules: dict[str, Any]) -> None:
        """Test build_p03_alert_rules returns dict with groups key."""
        assert isinstance(alert_rules, dict)
        assert "groups" in alert_rules
        assert isinstance(alert_rules["groups"], list)

    def test_has_expected_groups(self, alert_rules: dict[str, Any]) -> None:
        """Test alert rules has expected group categories."""
        group_names = [g["name"] for g in alert_rules["groups"]]

        expected_groups = [
            "p03-cycle",
            "p03-queue",
            "p03-learning",
            "p03-security",
            "p03-performance",
        ]

        for expected in expected_groups:
            assert expected in group_names, f"Missing group: {expected}"

    def test_each_group_has_rules(self, alert_rules: dict[str, Any]) -> None:
        """Test each group has at least one rule."""
        for group in alert_rules["groups"]:
            assert "rules" in group
            assert len(group["rules"]) > 0, f"Group {group['name']} has no rules"

    def test_each_group_has_interval(self, alert_rules: dict[str, Any]) -> None:
        """Test each group has evaluation interval."""
        for group in alert_rules["groups"]:
            assert "interval" in group
            assert group["interval"], f"Group {group['name']} missing interval"


class TestAlertRuleStructure:
    """Tests for individual alert rule structure."""

    @pytest.fixture
    def all_rules(self) -> list[dict[str, Any]]:
        """Get all rules from all groups."""
        rules = build_p03_alert_rules()
        all_rules = []
        for group in rules["groups"]:
            all_rules.extend(group["rules"])
        return all_rules

    def test_all_rules_have_required_fields(self, all_rules: list[dict[str, Any]]) -> None:
        """Test all rules have required fields."""
        required_fields = ["alert", "expr", "for", "labels", "annotations"]

        for rule in all_rules:
            for field in required_fields:
                assert field in rule, f"Rule {rule.get('alert', 'unknown')} missing {field}"

    def test_all_rules_have_alert_name_prefix(self, all_rules: list[dict[str, Any]]) -> None:
        """Test all alert names start with P03."""
        for rule in all_rules:
            assert rule["alert"].startswith("P03"), f"Alert {rule['alert']} doesn't start with P03"

    def test_all_rules_have_severity(self, all_rules: list[dict[str, Any]]) -> None:
        """Test all rules have severity label."""
        valid_severities = ["info", "warning", "critical"]

        for rule in all_rules:
            severity = rule["labels"].get("severity")
            assert (
                severity in valid_severities
            ), f"Rule {rule['alert']} has invalid severity: {severity}"

    def test_all_rules_have_pipeline_label(self, all_rules: list[dict[str, Any]]) -> None:
        """Test all rules have pipeline label set to p03."""
        for rule in all_rules:
            assert (
                rule["labels"].get("pipeline") == "p03"
            ), f"Rule {rule['alert']} missing pipeline=p03 label"

    def test_all_rules_have_runbook(self, all_rules: list[dict[str, Any]]) -> None:
        """Test all rules have runbook reference."""
        for rule in all_rules:
            runbook = rule["labels"].get("runbook")
            assert runbook, f"Rule {rule['alert']} missing runbook label"
            assert runbook.endswith(".md"), f"Runbook {runbook} should end with .md"

    def test_all_rules_have_annotations(self, all_rules: list[dict[str, Any]]) -> None:
        """Test all rules have required annotations."""
        for rule in all_rules:
            annotations = rule["annotations"]
            assert "summary" in annotations, f"Rule {rule['alert']} missing summary"
            assert "description" in annotations, f"Rule {rule['alert']} missing description"
            assert "runbook_url" in annotations, f"Rule {rule['alert']} missing runbook_url"


class TestAlertCategories:
    """Tests for alert categories."""

    @pytest.fixture
    def alert_rules(self) -> dict[str, Any]:
        return build_p03_alert_rules()

    def _get_group_rules(
        self, alert_rules: dict[str, Any], group_name: str
    ) -> list[dict[str, Any]]:
        """Get rules for a specific group."""
        for group in alert_rules["groups"]:
            if group["name"] == group_name:
                return group["rules"]
        return []

    def test_cycle_alerts_exist(self, alert_rules: dict[str, Any]) -> None:
        """Test cycle-related alerts exist."""
        rules = self._get_group_rules(alert_rules, "p03-cycle")
        rule_names = [r["alert"] for r in rules]

        # Should have failure rate and duration alerts
        assert any("Failure" in name for name in rule_names)
        assert any("Duration" in name for name in rule_names)

    def test_queue_alerts_exist(self, alert_rules: dict[str, Any]) -> None:
        """Test queue-related alerts exist."""
        rules = self._get_group_rules(alert_rules, "p03-queue")
        rule_names = [r["alert"] for r in rules]

        # Should have pending queue alerts
        assert any("Pending" in name or "Queue" in name for name in rule_names)

    def test_learning_alerts_exist(self, alert_rules: dict[str, Any]) -> None:
        """Test learning-related alerts exist."""
        rules = self._get_group_rules(alert_rules, "p03-learning")
        rule_names = [r["alert"] for r in rules]

        # Should have divergence and regret alerts
        assert any("Divergence" in name for name in rule_names)
        assert any("Regret" in name for name in rule_names)

    def test_security_alerts_exist(self, alert_rules: dict[str, Any]) -> None:
        """Test security-related alerts exist."""
        rules = self._get_group_rules(alert_rules, "p03-security")
        rule_names = [r["alert"] for r in rules]

        # Should have cross-space leakage alert
        assert any("CrossSpace" in name or "Leakage" in name for name in rule_names)

    def test_performance_alerts_exist(self, alert_rules: dict[str, Any]) -> None:
        """Test performance-related alerts exist."""
        rules = self._get_group_rules(alert_rules, "p03-performance")
        rule_names = [r["alert"] for r in rules]

        # Should have latency and budget alerts
        assert any("Latency" in name for name in rule_names)
        assert any("Budget" in name for name in rule_names)


class TestAlertThresholds:
    """Tests for alert thresholds configuration."""

    def test_thresholds_dict_not_empty(self) -> None:
        """Test P03_ALERT_THRESHOLDS is not empty."""
        assert len(P03_ALERT_THRESHOLDS) > 0

    def test_each_threshold_has_warning_and_critical(self) -> None:
        """Test each threshold has warning and critical levels."""
        for name, levels in P03_ALERT_THRESHOLDS.items():
            assert "warning" in levels, f"Threshold {name} missing warning level"
            assert "critical" in levels, f"Threshold {name} missing critical level"

    def test_warning_less_severe_than_critical(self) -> None:
        """Test warning thresholds are less severe than critical."""
        # For rate thresholds (higher is worse)
        rate_thresholds = [
            "cycle_failure_rate_percent",
            "divergence_rate_percent",
            "regret_rate_percent",
        ]
        for name in rate_thresholds:
            if name in P03_ALERT_THRESHOLDS:
                levels = P03_ALERT_THRESHOLDS[name]
                assert (
                    levels["warning"] < levels["critical"]
                ), f"Threshold {name}: warning should be < critical"

        # For inverse thresholds (lower is worse)
        inverse_thresholds = [
            "gap_resolution_rate_percent",
        ]
        for name in inverse_thresholds:
            if name in P03_ALERT_THRESHOLDS:
                levels = P03_ALERT_THRESHOLDS[name]
                assert (
                    levels["warning"] > levels["critical"]
                ), f"Threshold {name}: warning should be > critical"


class TestSLOTargets:
    """Tests for SLO targets configuration."""

    def test_slo_targets_not_empty(self) -> None:
        """Test P03_SLO_TARGETS is not empty."""
        assert len(P03_SLO_TARGETS) > 0

    def test_cycle_slo_exists(self) -> None:
        """Test cycle success rate SLO exists."""
        assert "cycle_success_rate_percent" in P03_SLO_TARGETS
        assert P03_SLO_TARGETS["cycle_success_rate_percent"] >= 99.0

    def test_regret_slo_exists(self) -> None:
        """Test regret rate SLO exists."""
        assert "regret_rate_percent" in P03_SLO_TARGETS
        assert P03_SLO_TARGETS["regret_rate_percent"] <= 5.0

    def test_leakage_slo_is_zero(self) -> None:
        """Test cross-space leakage SLO is zero tolerance."""
        assert "cross_space_leakage_rate" in P03_SLO_TARGETS
        assert P03_SLO_TARGETS["cross_space_leakage_rate"] == 0.0


class TestPrometheusExpressions:
    """Tests for Prometheus expression validity."""

    @pytest.fixture
    def all_rules(self) -> list[dict[str, Any]]:
        """Get all rules from all groups."""
        rules = build_p03_alert_rules()
        all_rules = []
        for group in rules["groups"]:
            all_rules.extend(group["rules"])
        return all_rules

    def test_expressions_use_p03_metrics(self, all_rules: list[dict[str, Any]]) -> None:
        """Test expressions reference P03 metrics."""
        for rule in all_rules:
            expr = rule["expr"]
            # Most rules should use p03_ prefix metrics
            # Some may use other metrics, so we check majority
            assert (
                "p03_" in expr.lower() or "rate(" in expr or "sum(" in expr
            ), f"Rule {rule['alert']} expression doesn't look like P03 metric"

    def test_expressions_have_balanced_parentheses(self, all_rules: list[dict[str, Any]]) -> None:
        """Test expressions have balanced parentheses."""
        for rule in all_rules:
            expr = rule["expr"]
            open_count = expr.count("(")
            close_count = expr.count(")")
            assert open_count == close_count, f"Rule {rule['alert']} has unbalanced parentheses"

    def test_expressions_have_balanced_brackets(self, all_rules: list[dict[str, Any]]) -> None:
        """Test expressions have balanced brackets."""
        for rule in all_rules:
            expr = rule["expr"]
            open_count = expr.count("[")
            close_count = expr.count("]")
            assert open_count == close_count, f"Rule {rule['alert']} has unbalanced brackets"

    def test_expressions_have_balanced_braces(self, all_rules: list[dict[str, Any]]) -> None:
        """Test expressions have balanced braces."""
        for rule in all_rules:
            expr = rule["expr"]
            open_count = expr.count("{")
            close_count = expr.count("}")
            assert open_count == close_count, f"Rule {rule['alert']} has unbalanced braces"


class TestAlertDurations:
    """Tests for alert firing durations."""

    @pytest.fixture
    def all_rules(self) -> list[dict[str, Any]]:
        """Get all rules from all groups."""
        rules = build_p03_alert_rules()
        all_rules = []
        for group in rules["groups"]:
            all_rules.extend(group["rules"])
        return all_rules

    def test_durations_are_valid_format(self, all_rules: list[dict[str, Any]]) -> None:
        """Test duration strings are valid Prometheus format."""
        valid_suffixes = ["s", "m", "h", "d"]

        for rule in all_rules:
            duration = rule["for"]
            assert any(
                duration.endswith(s) for s in valid_suffixes
            ), f"Rule {rule['alert']} has invalid duration: {duration}"
            # Check numeric prefix
            numeric_part = duration[:-1]
            if duration[-2:] in ["ms", "us", "ns"]:
                numeric_part = duration[:-2]
            assert (
                numeric_part.isdigit()
            ), f"Rule {rule['alert']} duration has non-numeric prefix: {duration}"

    def test_critical_alerts_have_shorter_durations(self, all_rules: list[dict[str, Any]]) -> None:
        """Test critical alerts generally fire faster than warnings."""
        # Group rules by base name (without Warning/Critical suffix)
        rule_pairs: dict[str, dict[str, str]] = {}

        for rule in all_rules:
            name = rule["alert"]
            severity = rule["labels"]["severity"]
            duration = rule["for"]

            # Extract base name
            if "Warning" in name:
                base = name.replace("Warning", "")
            elif "Critical" in name:
                base = name.replace("Critical", "")
            else:
                continue

            if base not in rule_pairs:
                rule_pairs[base] = {}
            rule_pairs[base][severity] = duration

        # For pairs, critical should have <= duration than warning
        for base, severities in rule_pairs.items():
            if "warning" in severities and "critical" in severities:
                warn_dur = self._duration_to_seconds(severities["warning"])
                crit_dur = self._duration_to_seconds(severities["critical"])
                assert (
                    crit_dur <= warn_dur
                ), f"Alert {base}: critical ({crit_dur}s) should fire before warning ({warn_dur}s)"

    def _duration_to_seconds(self, duration: str) -> int:
        """Convert duration string to seconds."""
        if duration.endswith("h"):
            return int(duration[:-1]) * 3600
        elif duration.endswith("m"):
            return int(duration[:-1]) * 60
        elif duration.endswith("s"):
            return int(duration[:-1])
        elif duration.endswith("d"):
            return int(duration[:-1]) * 86400
        return 0


class TestSecurityAlertsSeverity:
    """Tests for security alert configurations."""

    @pytest.fixture
    def security_rules(self) -> list[dict[str, Any]]:
        """Get security group rules."""
        rules = build_p03_alert_rules()
        for group in rules["groups"]:
            if group["name"] == "p03-security":
                return group["rules"]
        return []

    def test_security_alerts_have_security_contact(
        self, security_rules: list[dict[str, Any]]
    ) -> None:
        """Test security alerts route to security contact."""
        for rule in security_rules:
            if rule["labels"]["severity"] == "critical":
                assert (
                    rule["labels"]["contact"] == "security-oncall"
                ), f"Critical security alert {rule['alert']} should route to security-oncall"

    def test_cross_space_leakage_is_critical(self, security_rules: list[dict[str, Any]]) -> None:
        """Test cross-space leakage has critical severity option."""
        leakage_rules = [r for r in security_rules if "Leakage" in r["alert"]]
        severities = [r["labels"]["severity"] for r in leakage_rules]

        assert "critical" in severities, "Cross-space leakage should have critical alert"
