"""Alertmanager configuration generator with multi-tier routing.

Generates production-grade Alertmanager config with:
- Multi-tier alert routing (PagerDuty for critical, Slack for warnings)
- Team-based routing (SRE, Platform, Storage, QoS, Drivers)
- Alert grouping and inhibition rules
- Rate limiting and deduplication
- Maintenance window support

Usage:
    from k0.telemetry.mixins.alertmanager_config import generate_alertmanager_config
    config = generate_alertmanager_config(
        pagerduty_key="YOUR_INTEGRATION_KEY",
        slack_webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
    )
"""

from __future__ import annotations

from typing import Any

__all__ = ["generate_alertmanager_config", "get_routing_guide"]


def generate_alertmanager_config(
    pagerduty_key: str | None = None,
    slack_webhook_url: str | None = None,
    email_to: str | None = None,
    enable_maintenance_mode: bool = False,
) -> dict[str, Any]:
    """Generate Alertmanager configuration with multi-tier routing.

    Args:
        pagerduty_key: PagerDuty integration key for critical alerts
        slack_webhook_url: Slack webhook URL for warning/info alerts
        email_to: Email address for notification fallback
        enable_maintenance_mode: If True, suppress non-critical alerts

    Returns:
        Alertmanager configuration dict ready for YAML serialization
    """

    config: dict[str, Any] = {
        "global": _get_global_config(),
        "route": _get_root_route(enable_maintenance_mode),
        "receivers": _get_receivers(pagerduty_key, slack_webhook_url, email_to),
        "inhibit_rules": _get_inhibit_rules(),
        "templates": ["/etc/alertmanager/templates/*.tmpl"],
    }

    return config


def _get_global_config() -> dict[str, Any]:
    """Global Alertmanager configuration."""
    return {
        "resolve_timeout": "5m",
        "pagerduty_url": "https://events.pagerduty.com/v2/enqueue",
        "slack_api_url": "https://slack.com/api/chat.postMessage",
    }


def _get_root_route(enable_maintenance_mode: bool = False) -> dict[str, Any]:
    """Root routing tree with multi-tier severity-based routing.

    Routing Strategy:
    - critical + slo alerts → PagerDuty (immediate page)
    - warning + slo alerts → Slack SRE channel (async notification)
    - info + meta alerts → Slack ops channel (FYI only)
    - Maintenance mode: only critical alerts fire
    """

    root = {
        "receiver": "null",  # Default: discard unmatched alerts
        "group_by": ["alertname", "cluster", "component", "subsystem"],
        "group_wait": "30s",  # Wait before sending first notification
        "group_interval": "5m",  # Wait before sending updates
        "repeat_interval": "12h",  # Re-send if alert still firing
        "routes": [],
    }

    # Route 1: Critical SLO alerts → PagerDuty (immediate page)
    root["routes"].append(
        {
            "receiver": "pagerduty-critical",
            "matchers": [
                'severity="critical"',
                'slo=~".+"',  # Must have SLO label
            ],
            "group_by": ["alertname", "slo", "subsystem"],
            "group_wait": "10s",  # Faster grouping for critical
            "group_interval": "2m",
            "repeat_interval": "3h",  # More frequent for critical
            "continue": False,  # Stop routing here
        }
    )

    # Route 2: Critical non-SLO alerts → PagerDuty + Slack (page + notify)
    root["routes"].append(
        {
            "receiver": "pagerduty-critical",
            "matchers": ['severity="critical"'],
            "group_by": ["alertname", "component", "subsystem"],
            "group_wait": "10s",
            "group_interval": "2m",
            "repeat_interval": "6h",
            "continue": True,  # Also send to Slack
        }
    )

    if not enable_maintenance_mode:
        # Route 3: Warning SLO alerts → Slack SRE channel
        root["routes"].append(
            {
                "receiver": "slack-sre",
                "matchers": [
                    'severity="warning"',
                    'slo=~".+"',
                ],
                "group_by": ["alertname", "slo", "subsystem"],
                "group_wait": "30s",
                "group_interval": "5m",
                "repeat_interval": "12h",
            }
        )

        # Route 4: Warning non-SLO alerts → Slack ops channel
        root["routes"].append(
            {
                "receiver": "slack-ops",
                "matchers": ['severity="warning"'],
                "group_by": ["alertname", "component"],
                "group_wait": "1m",
                "group_interval": "10m",
                "repeat_interval": "24h",
            }
        )

        # Route 5: Info/meta alerts → Slack ops channel (low priority)
        root["routes"].append(
            {
                "receiver": "slack-ops",
                "matchers": ['severity=~"info|meta"'],
                "group_by": ["alertname"],
                "group_wait": "5m",
                "group_interval": "30m",
                "repeat_interval": "24h",
            }
        )

    # Route 6: Team-based routing overrides (by contact label)
    root["routes"].extend(_get_team_routes(enable_maintenance_mode))

    return root


def _get_team_routes(enable_maintenance_mode: bool = False) -> list[dict[str, Any]]:
    """Team-specific alert routing based on 'contact' label.

    Teams:
    - sre: Site Reliability Engineering (infrastructure, availability)
    - platform: Platform team (kernel, runtime)
    - storage: Storage team (WAL, outbox, replay)
    - qos: QoS team (scheduler, rate limiting)
    - drivers: Driver team (integrations)
    """

    team_routes = []

    # SRE team: critical infrastructure alerts → PagerDuty
    team_routes.append(
        {
            "receiver": "pagerduty-sre",
            "matchers": [
                'contact="sre"',
                'severity="critical"',
            ],
            "group_by": ["alertname", "subsystem"],
            "group_wait": "5s",
            "group_interval": "2m",
            "repeat_interval": "3h",
        }
    )

    if not enable_maintenance_mode:
        # Platform team: kernel/runtime warnings → Slack
        team_routes.append(
            {
                "receiver": "slack-platform",
                "matchers": [
                    'contact="platform"',
                    'severity="warning"',
                ],
                "group_by": ["alertname", "component"],
                "group_wait": "1m",
                "group_interval": "10m",
                "repeat_interval": "12h",
            }
        )

        # Storage team: data durability warnings → Slack
        team_routes.append(
            {
                "receiver": "slack-storage",
                "matchers": [
                    'contact="storage"',
                    'severity="warning"',
                ],
                "group_by": ["alertname", "subsystem"],
                "group_wait": "1m",
                "group_interval": "10m",
                "repeat_interval": "12h",
            }
        )

    return team_routes


def _get_receivers(
    pagerduty_key: str | None,
    slack_webhook_url: str | None,
    email_to: str | None,
) -> list[dict[str, Any]]:
    """Configure alert receivers (PagerDuty, Slack, email).

    Receivers:
    - pagerduty-critical: Critical alerts (high urgency)
    - pagerduty-sre: SRE team critical alerts
    - slack-sre: SRE channel (#k0-alerts-sre)
    - slack-ops: Ops channel (#k0-alerts-ops)
    - slack-platform: Platform team channel
    - slack-storage: Storage team channel
    - email-fallback: Email for delivery failures
    - null: Discard unmatched alerts
    """

    receivers = []

    # Null receiver (discard)
    receivers.append({"name": "null"})

    # PagerDuty receivers
    if pagerduty_key:
        receivers.append(
            {
                "name": "pagerduty-critical",
                "pagerduty_configs": [
                    {
                        "routing_key": pagerduty_key,
                        "severity": "critical",
                        "description": "{{ .GroupLabels.alertname }}: {{ .CommonAnnotations.summary }}",
                        "details": {
                            "firing": "{{ .Alerts.Firing | len }}",
                            "resolved": "{{ .Alerts.Resolved | len }}",
                            "runbook_url": "{{ .CommonAnnotations.runbook_url }}",
                            "description": "{{ .CommonAnnotations.description }}",
                        },
                        "send_resolved": True,
                    }
                ],
            }
        )

        receivers.append(
            {
                "name": "pagerduty-sre",
                "pagerduty_configs": [
                    {
                        "routing_key": pagerduty_key,
                        "severity": "error",
                        "description": "[SRE] {{ .GroupLabels.alertname }}",
                        "send_resolved": True,
                    }
                ],
            }
        )
    else:
        # Fallback to webhook if PagerDuty not configured
        receivers.extend(
            [
                {
                    "name": "pagerduty-critical",
                    "webhook_configs": [_get_webhook_fallback()],
                },
                {"name": "pagerduty-sre", "webhook_configs": [_get_webhook_fallback()]},
            ]
        )

    # Slack receivers
    if slack_webhook_url:
        slack_config = _get_slack_config(slack_webhook_url)

        receivers.append(
            {
                "name": "slack-sre",
                "slack_configs": [
                    {
                        **slack_config,
                        "channel": "#k0-alerts-sre",
                        "title": "🚨 K0 Alert: {{ .GroupLabels.alertname }}",
                        "text": (
                            "*Severity:* {{ .CommonLabels.severity }}\n"
                            "*SLO:* {{ .CommonLabels.slo }}\n"
                            "*Description:* {{ .CommonAnnotations.description }}\n"
                            "*Runbook:* {{ .CommonAnnotations.runbook_url }}"
                        ),
                        "color": '{{ if eq .Status "firing" }}danger{{ else }}good{{ end }}',
                    }
                ],
            }
        )

        receivers.append(
            {
                "name": "slack-ops",
                "slack_configs": [
                    {
                        **slack_config,
                        "channel": "#k0-alerts-ops",
                        "title": "⚠️  K0 Alert: {{ .GroupLabels.alertname }}",
                        "color": '{{ if eq .Status "firing" }}warning{{ else }}good{{ end }}',
                    }
                ],
            }
        )

        receivers.append(
            {
                "name": "slack-platform",
                "slack_configs": [
                    {
                        **slack_config,
                        "channel": "#k0-platform",
                        "title": "🔧 Platform Alert: {{ .GroupLabels.alertname }}",
                    }
                ],
            }
        )

        receivers.append(
            {
                "name": "slack-storage",
                "slack_configs": [
                    {
                        **slack_config,
                        "channel": "#k0-storage",
                        "title": "💾 Storage Alert: {{ .GroupLabels.alertname }}",
                    }
                ],
            }
        )
    else:
        # Fallback to webhook if Slack not configured
        webhook = _get_webhook_fallback()
        receivers.extend(
            [
                {"name": "slack-sre", "webhook_configs": [webhook]},
                {"name": "slack-ops", "webhook_configs": [webhook]},
                {"name": "slack-platform", "webhook_configs": [webhook]},
                {"name": "slack-storage", "webhook_configs": [webhook]},
            ]
        )

    # Email fallback
    if email_to:
        receivers.append(
            {
                "name": "email-fallback",
                "email_configs": [
                    {
                        "to": email_to,
                        "from": "k0-alertmanager@example.com",
                        "smarthost": "smtp.example.com:587",
                        "subject": "[K0] {{ .GroupLabels.alertname }}",
                        "html": "{{ range .Alerts }}{{ .Annotations.description }}<br/>{{ end }}",
                        "send_resolved": True,
                    }
                ],
            }
        )

    return receivers


def _get_slack_config(webhook_url: str) -> dict[str, Any]:
    """Base Slack configuration."""
    return {
        "api_url": webhook_url,
        "send_resolved": True,
        "title_link": "{{ .CommonAnnotations.runbook_url }}",
        "text": "{{ .CommonAnnotations.description }}",
        "footer": "K0 Alertmanager | {{ .Status | toUpper }}",
    }


def _get_webhook_fallback() -> dict[str, Any]:
    """Webhook fallback when PagerDuty/Slack not configured."""
    return {
        "url": "http://localhost:9093/api/v2/alerts",
        "send_resolved": True,
        "http_config": {"follow_redirects": True},
    }


def _get_inhibit_rules() -> list[dict[str, Any]]:
    """Inhibition rules to reduce alert fatigue.

    Rules:
    1. If cluster is down, suppress node-level alerts
    2. If API is unavailable, suppress latency alerts
    3. If WAL is lagging, suppress outbox backlog alerts
    4. If driver handshake fails, suppress driver-specific alerts
    5. During maintenance, suppress non-critical alerts
    """

    return [
        # Rule 1: Cluster down suppresses node alerts
        {
            "source_matchers": ['alertname="K0ClusterDown"'],
            "target_matchers": ['component="node"'],
            "equal": ["cluster"],
        },
        # Rule 2: API unavailability suppresses latency alerts
        {
            "source_matchers": [
                'alertname=~"K0ApiAvailability.*"',
                'severity="critical"',
            ],
            "target_matchers": ['alertname=~"K0.*Latency.*"'],
            "equal": ["subsystem"],
        },
        # Rule 3: WAL lag suppresses outbox backlog
        {
            "source_matchers": ['alertname="K0WalLagCritical"'],
            "target_matchers": ['alertname=~"K0OutboxBacklog.*"'],
            "equal": ["subsystem"],
        },
        # Rule 4: Driver handshake failure suppresses driver alerts
        {
            "source_matchers": ['alertname="K0DriverHandshakeFailureCritical"'],
            "target_matchers": ['component="drivers"'],
            "equal": ["driver"],
        },
        # Rule 5: Maintenance mode suppresses warnings
        {
            "source_matchers": ['alertname="K0MaintenanceMode"'],
            "target_matchers": ['severity="warning"'],
            "equal": ["cluster"],
        },
    ]


def get_routing_guide() -> str:
    """Get human-readable alert routing guide for documentation."""

    return """
# K0 Alertmanager Routing Guide

## Routing Strategy

### Critical SLO Alerts
**Route:** PagerDuty (immediate page)
**Criteria:** `severity="critical"` AND `slo=~".+"`
**Group By:** alertname, slo, subsystem
**Repeat:** Every 3 hours

**Examples:**
- K0ApiAvailabilityCritical (API <99% available)
- K0CommandLatencyCritical (p95 >250ms)
- K0QueryLatencyCritical (p95 >150ms)

### Critical Non-SLO Alerts
**Route:** PagerDuty + Slack SRE (page + notify)
**Criteria:** `severity="critical"`
**Group By:** alertname, component, subsystem
**Repeat:** Every 6 hours

**Examples:**
- K0SchedulerQuorumCritical (quorum <2)
- K0ZoneHealthCritical (zone health ≤0)
- K0WalReplicaLagCritical (replica lag >30s)

### Warning SLO Alerts
**Route:** Slack SRE channel
**Criteria:** `severity="warning"` AND `slo=~".+"`
**Group By:** alertname, slo, subsystem
**Repeat:** Every 12 hours

**Examples:**
- K0ApiAvailabilityWarning (API <99.5% available)
- K0CommandLatencyWarning (p95 >150ms)
- K0QueryLatencyWarning (p95 >75ms)

### Warning Non-SLO Alerts
**Route:** Slack ops channel
**Criteria:** `severity="warning"`
**Group By:** alertname, component
**Repeat:** Every 24 hours

**Examples:**
- K0OutboxBacklogWarning (pending >50k)
- K0ReplayThroughputWarning (rate <500 evt/s)
- K0SseDisconnectSpikeWarning (subscriptions <95% baseline)

### Info/Meta Alerts
**Route:** Slack ops channel (low priority)
**Criteria:** `severity=~"info|meta"`
**Group By:** alertname
**Repeat:** Every 24 hours

**Examples:**
- K0AlertingDeadman (heartbeat)

## Team-Based Routing

### SRE Team
**Contact Label:** `contact="sre"`
**Critical → PagerDuty:** pagerduty-sre
**Warning → Slack:** #k0-alerts-sre

**Responsibilities:**
- Infrastructure availability
- Multi-node topology
- Failover mechanisms

### Platform Team
**Contact Label:** `contact="platform"`
**Warning → Slack:** #k0-platform

**Responsibilities:**
- Kernel runtime
- Command/query latency
- API performance

### Storage Team
**Contact Label:** `contact="storage"`
**Warning → Slack:** #k0-storage

**Responsibilities:**
- WAL durability
- Outbox delivery
- Replay throughput

### QoS Team
**Contact Label:** `contact="qos"`
**Warning → Slack:** #k0-qos (if configured)

**Responsibilities:**
- Scheduler fairness
- Rate limiting
- Tenant isolation

### Drivers Team
**Contact Label:** `contact="drivers"`
**Warning → Slack:** #k0-drivers (if configured)

**Responsibilities:**
- Driver handshakes
- Integration health
- Connector stability

## Inhibition Rules

1. **Cluster Down** suppresses node-level alerts
2. **API Unavailable** suppresses latency alerts (cascade prevention)
3. **WAL Lag** suppresses outbox backlog (root cause focus)
4. **Driver Handshake Failure** suppresses driver alerts
5. **Maintenance Mode** suppresses warning alerts

## Configuration

### PagerDuty Setup
```yaml
pagerduty_key: "YOUR_INTEGRATION_KEY"
```

Get from: https://YOUR_ORG.pagerduty.com/services → K0 Service → Integrations → Events API v2

### Slack Setup
```yaml
slack_webhook_url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

Get from: https://api.slack.com/apps → Incoming Webhooks → Add New Webhook

### Email Fallback
```yaml
email_to: "sre-team@example.com"
```

Configure SMTP in Alertmanager global config.

## Maintenance Mode

Enable maintenance mode to suppress non-critical alerts during planned work:

```python
config = generate_alertmanager_config(
    pagerduty_key="...",
    slack_webhook_url="...",
    enable_maintenance_mode=True  # Suppress warnings
)
```

Only critical SLO alerts will fire during maintenance.
"""


if __name__ == "__main__":
    # Example: Generate config with placeholders
    config = generate_alertmanager_config(
        pagerduty_key="PAGERDUTY_INTEGRATION_KEY_PLACEHOLDER",
        slack_webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
        email_to="sre@example.com",
        enable_maintenance_mode=False,
    )

    import yaml

    print("# Generated Alertmanager Configuration")
    print(yaml.dump(config, default_flow_style=False, sort_keys=False))

    print("\n" + "=" * 80)
    print(get_routing_guide())
