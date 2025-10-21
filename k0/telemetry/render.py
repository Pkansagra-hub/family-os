"""CLI for rendering Grafana dashboards and Prometheus alert rules."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from mixins.alert_rules import build_slo_alert_rules
from mixins.alertmanager_config import generate_alertmanager_config
from mixins.recording_rules import generate_recording_rules
from mixins.slo_dashboards import (
    build_command_latency_dashboard,
    build_kernel_overview_dashboard,
    build_query_latency_dashboard,
    build_replay_throughput_dashboard,
    build_sse_health_dashboard,
)

__all__ = ["main", "compute_checksum"]

LOGGER = logging.getLogger(__name__)


def _compute_checksum(content: str) -> str:
    """Compute SHA256 checksum of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def compute_checksum(content: str) -> str:
    """Public wrapper for computing truncated SHA256 checksums."""
    return _compute_checksum(content)


def _write_json(path: Path, data: dict[str, Any]) -> str:
    """Write JSON with deterministic formatting and return checksum."""
    content = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    checksum = _compute_checksum(content)
    path.write_text(content, encoding="utf-8")
    LOGGER.info(f"Wrote {path} (checksum: {checksum})")
    return checksum


def _write_yaml(path: Path, data: dict[str, Any]) -> str:
    """Write YAML with deterministic formatting and return checksum."""
    content = yaml.dump(
        data, default_flow_style=False, sort_keys=True, allow_unicode=True
    )
    checksum = _compute_checksum(content)
    serialized = f"# Checksum: {checksum}\n{content}"
    path.write_text(serialized, encoding="utf-8")
    LOGGER.info(f"Wrote {path} (checksum: {checksum})")
    return checksum


def render_dashboards(output_dir: Path) -> None:
    """Render all Grafana dashboards to output directory."""
    LOGGER.info("Rendering Grafana dashboards...")
    output_dir.mkdir(parents=True, exist_ok=True)

    dashboards = [
        ("kernel_overview.json", build_kernel_overview_dashboard()),
        ("command_latency.json", build_command_latency_dashboard()),
        ("query_latency.json", build_query_latency_dashboard()),
        ("sse_health.json", build_sse_health_dashboard()),
        ("replay_throughput.json", build_replay_throughput_dashboard()),
    ]

    checksums = {}
    for filename, dashboard in dashboards:
        checksum = _write_json(output_dir / filename, dashboard)
        checksums[filename] = checksum

    # Write checksum manifest to parent directory (not in dashboards folder)
    manifest_path = output_dir.parent / "checksums_dashboards.json"
    manifest_path.write_text(json.dumps(checksums, indent=2, sort_keys=True))
    LOGGER.info(f"Wrote checksum manifest to {manifest_path}")

    LOGGER.info(f"Rendered {len(dashboards)} dashboards to {output_dir}")


def render_alert_rules(output_dir: Path) -> None:
    """Render Prometheus alert rules to output directory."""
    LOGGER.info("Rendering Prometheus alert rules...")
    output_dir.mkdir(parents=True, exist_ok=True)

    rules = build_slo_alert_rules()
    checksum = _write_yaml(output_dir / "slo_alerts.yaml", rules)

    # Write checksum manifest to parent directory (not in rules folder)
    manifest_path = output_dir.parent / "checksums_rules.json"
    checksums = {"slo_alerts.yaml": checksum}

    # Render recording rules
    recording_rules = generate_recording_rules()
    recording_checksum = _write_yaml(
        output_dir / "recording_rules.yaml", recording_rules
    )
    checksums["recording_rules.yaml"] = recording_checksum

    manifest_path.write_text(json.dumps(checksums, indent=2))
    LOGGER.info(f"Wrote checksum manifest to {manifest_path}")

    LOGGER.info(f"Rendered alert rules to {output_dir}")


def render_alertmanager_config(
    output_dir: Path,
    pagerduty_key: str | None = None,
    slack_webhook_url: str | None = None,
) -> None:
    """Render Alertmanager configuration to output directory."""
    LOGGER.info("Rendering Alertmanager configuration...")
    output_dir.mkdir(parents=True, exist_ok=True)

    alertmanager_cfg = generate_alertmanager_config(
        pagerduty_key=pagerduty_key or "PAGERDUTY_INTEGRATION_KEY_PLACEHOLDER",
        slack_webhook_url=slack_webhook_url
        or "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
        email_to=None,
        enable_maintenance_mode=False,
    )
    checksum = _write_yaml(output_dir / "alertmanager.yml", alertmanager_cfg)

    # Write checksum manifest
    manifest_path = output_dir.parent / "checksums_alertmanager.json"
    manifest_path.write_text(json.dumps({"alertmanager.yml": checksum}, indent=2))
    LOGGER.info(f"Wrote checksum manifest to {manifest_path}")

    LOGGER.info(f"Rendered Alertmanager config to {output_dir}")


def _extract_body(content: str) -> tuple[str | None, str]:
    """Split checksum header from body, returning checksum and body text."""
    if "\n" not in content:
        return None, content

    first_line, remainder = content.split("\n", 1)
    if "Checksum:" not in first_line:
        return None, content

    _, checksum_part = first_line.split("Checksum:", 1)
    return checksum_part.strip(), remainder


def verify_checksums(dashboards_dir: Path, rules_dir: Path) -> bool:
    """Verify checksums of rendered artifacts to detect drift."""
    LOGGER.info("Verifying checksums...")
    all_valid = True

    # Check dashboards
    manifest_path = dashboards_dir.parent / "checksums_dashboards.json"
    if not manifest_path.exists():
        LOGGER.error(f"Dashboard checksum manifest not found: {manifest_path}")
        return False

    manifest = json.loads(manifest_path.read_text())
    for filename, stored_cs in manifest.items():
        dashboard_file = dashboards_dir / filename
        if not dashboard_file.exists():
            LOGGER.error(f"{filename}: File missing")
            all_valid = False
            continue
        content = dashboard_file.read_text(encoding="utf-8")
        header_cs, body = _extract_body(content)
        computed_cs = _compute_checksum(body)
        if stored_cs != computed_cs:
            LOGGER.error(
                f"{filename}: Checksum mismatch (stored={stored_cs}, computed={computed_cs})"
            )
            all_valid = False
        elif header_cs and header_cs != stored_cs:
            LOGGER.error(
                f"{filename}: Header checksum mismatch (header={header_cs}, stored={stored_cs})"
            )
            all_valid = False
        else:
            LOGGER.info(f"{filename}: Checksum OK")

    # Check rules
    rules_manifest_path = rules_dir.parent / "checksums_rules.json"
    if not rules_manifest_path.exists():
        LOGGER.error(f"Rules checksum manifest not found: {rules_manifest_path}")
        return False

    rules_manifest = json.loads(rules_manifest_path.read_text())
    for filename, stored_cs in rules_manifest.items():
        rules_file = rules_dir / filename
        if not rules_file.exists():
            LOGGER.error(f"{filename}: File missing")
            all_valid = False
            continue
        content = rules_file.read_text(encoding="utf-8")
        header_cs, body = _extract_body(content)
        computed_cs = _compute_checksum(body)
        if stored_cs != computed_cs:
            LOGGER.error(
                f"{filename}: Checksum mismatch (stored={stored_cs}, computed={computed_cs})"
            )
            all_valid = False
        elif header_cs and header_cs != stored_cs:
            LOGGER.error(
                f"{filename}: Header checksum mismatch (header={header_cs}, stored={stored_cs})"
            )
            all_valid = False
        else:
            LOGGER.info(f"{filename}: Checksum OK")

    return all_valid


def main() -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Render Grafana dashboards and Prometheus alert rules for K0 kernel",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "generated",
        help="Output directory for rendered artifacts",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify checksums of existing artifacts instead of rendering",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--pagerduty-key",
        type=str,
        help="PagerDuty integration key for critical alerts",
    )
    parser.add_argument(
        "--slack-webhook-url",
        type=str,
        help="Slack webhook URL for warning/info alerts",
    )
    parser.add_argument(
        "--render-alertmanager",
        action="store_true",
        help="Render Alertmanager configuration (requires --pagerduty-key and --slack-webhook-url for production)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    dashboards_dir = args.output_dir / "dashboards"
    rules_dir = args.output_dir / "rules"
    alertmanager_dir = args.output_dir / "alertmanager"

    if args.verify:
        if not dashboards_dir.exists() or not rules_dir.exists():
            LOGGER.error("Output directories do not exist, cannot verify")
            return 1
        if verify_checksums(dashboards_dir, rules_dir):
            LOGGER.info("All checksums valid")
            return 0
        else:
            LOGGER.error("Checksum verification failed")
            return 1

    try:
        render_dashboards(dashboards_dir)
        render_alert_rules(rules_dir)

        if args.render_alertmanager:
            render_alertmanager_config(
                alertmanager_dir,
                pagerduty_key=args.pagerduty_key,
                slack_webhook_url=args.slack_webhook_url,
            )

        LOGGER.info("Render complete")
        return 0
    except Exception:
        LOGGER.exception("Render failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
