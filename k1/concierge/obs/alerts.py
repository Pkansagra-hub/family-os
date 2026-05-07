"""
k1.concierge.obs.alerts -- Alert rules, engine, and events.

M11 Stub -- placeholder for alert evaluation infrastructure.

AlertRule   -- Declarative rule definition (threshold, window, metric name).
AlertEngine -- Evaluates rules against MetricAggregator sliding windows.
AlertEvent  -- Fired when a rule condition is met.

V2 Design Ref: Section 15.4.C (Unified Metrics Emission Layer)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AlertRule:
    """Declarative alert rule definition.

    Attributes:
        rule_id: Unique identifier for the rule.
        metric_name: Metric to evaluate (dot-separated).
        threshold: Numeric threshold that triggers the alert.
        window_ms: Evaluation window in milliseconds.
        comparator: One of "gt", "lt", "gte", "lte", "eq".
        description: Human-readable description.
    """

    rule_id: str = ""
    metric_name: str = ""
    threshold: float = 0.0
    window_ms: int = 60000
    comparator: str = "gt"
    description: str = ""


@dataclass
class AlertEvent:
    """Fired when an AlertRule condition is met.

    Attributes:
        rule_id: The AlertRule that triggered.
        metric_name: Metric that exceeded the threshold.
        observed_value: The value that caused the alert.
        threshold: The threshold from the rule.
        timestamp_ms: Epoch milliseconds when the alert fired.
        labels: Labels from the triggering metric.
    """

    rule_id: str = ""
    metric_name: str = ""
    observed_value: float = 0.0
    threshold: float = 0.0
    timestamp_ms: int = 0
    labels: dict[str, str] = field(default_factory=dict)


class AlertEngine:
    """Evaluates AlertRules against metric aggregations.

    Stub implementation -- production will subscribe to MetricAggregator
    sliding windows and fire AlertEvents when thresholds are breached.
    """

    def __init__(self) -> None:
        self._rules: list[AlertRule] = []
        self._fired: list[AlertEvent] = []

    def register_rule(self, rule: AlertRule) -> None:
        """Register a rule for evaluation."""
        self._rules.append(rule)

    @property
    def rules(self) -> list[AlertRule]:
        """Return registered rules."""
        return list(self._rules)

    @property
    def fired_events(self) -> list[AlertEvent]:
        """Return fired alert events."""
        return list(self._fired)

    def evaluate(self, metric_name: str, value: float) -> list[AlertEvent]:
        """Evaluate all rules for a given metric observation.

        Returns list of AlertEvents for any triggered rules.
        """
        events: list[AlertEvent] = []
        for rule in self._rules:
            if rule.metric_name != metric_name:
                continue
            triggered = False
            if rule.comparator == "gt" and value > rule.threshold:
                triggered = True
            elif rule.comparator == "lt" and value < rule.threshold:
                triggered = True
            elif rule.comparator == "gte" and value >= rule.threshold:
                triggered = True
            elif rule.comparator == "lte" and value <= rule.threshold:
                triggered = True
            elif rule.comparator == "eq" and value == rule.threshold:
                triggered = True
            if triggered:
                event = AlertEvent(
                    rule_id=rule.rule_id,
                    metric_name=metric_name,
                    observed_value=value,
                    threshold=rule.threshold,
                )
                events.append(event)
                self._fired.append(event)
        return events
