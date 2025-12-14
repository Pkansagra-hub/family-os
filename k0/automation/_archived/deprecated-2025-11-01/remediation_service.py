"""
K0 Remediation Service - Automated Alert Response

Receives webhooks from Alertmanager and executes automated remediation actions.
For a 2-person team, automation reduces toil and enables scale.

Safety features:
- Throttling (max 3 remediations per alert per hour)
- Dry-run mode for testing
- Manual override to disable automation
- Execution history for compliance
"""

import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request

app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration from environment
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
MAX_REMEDIATIONS_PER_HOUR = int(os.getenv("MAX_REMEDIATIONS_PER_HOUR", "3"))
AUTOMATION_ENABLED = os.getenv("AUTOMATION_ENABLED", "true").lower() == "true"
DB_PATH = os.getenv("DB_PATH", "k0/automation/remediation_history.db")

logger.info(
    f"Configuration: DRY_RUN={DRY_RUN}, MAX_REMEDIATIONS_PER_HOUR={MAX_REMEDIATIONS_PER_HOUR}, AUTOMATION_ENABLED={AUTOMATION_ENABLED}"
)


@dataclass
class RemediationResult:
    """Result of a remediation action"""

    success: bool
    action: str
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


def init_db():
    """Initialize remediation history database"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS remediation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            alertname TEXT NOT NULL,
            severity TEXT NOT NULL,
            component TEXT NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            duration_seconds REAL,
            dry_run INTEGER DEFAULT 0
        )
    """
    )
    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")


def log_remediation(
    alertname: str,
    severity: str,
    component: str,
    action: str,
    status: str,
    error: Optional[str] = None,
    duration: float = 0.0,
    dry_run: bool = False,
):
    """Log remediation execution to history database"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO remediation_history
        (timestamp, alertname, severity, component, action, status, error, duration_seconds, dry_run)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            datetime.utcnow().isoformat(),
            alertname,
            severity,
            component,
            action,
            status,
            error,
            duration,
            1 if dry_run else 0,
        ),
    )
    conn.commit()
    conn.close()


def check_throttle(alertname: str) -> bool:
    """Check if we've exceeded remediation limit for this alert"""
    conn = sqlite3.connect(DB_PATH)
    one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    cursor = conn.execute(
        """
        SELECT COUNT(*) FROM remediation_history
        WHERE alertname = ?
        AND timestamp > ?
        AND dry_run = 0
    """,
        (alertname, one_hour_ago),
    )
    count = cursor.fetchone()[0]
    conn.close()

    throttled = count >= MAX_REMEDIATIONS_PER_HOUR
    if throttled:
        logger.warning(
            f"Throttle limit exceeded for {alertname} ({count}/{MAX_REMEDIATIONS_PER_HOUR} in last hour)"
        )
    return not throttled


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return (
        jsonify(
            {
                "status": "healthy",
                "automation_enabled": AUTOMATION_ENABLED,
                "dry_run": DRY_RUN,
                "max_remediations_per_hour": MAX_REMEDIATIONS_PER_HOUR,
            }
        ),
        200,
    )


@app.route("/webhook", methods=["POST"])
def webhook():
    """Alertmanager webhook endpoint"""
    if not AUTOMATION_ENABLED:
        logger.info("Automation disabled, ignoring webhook")
        return jsonify({"status": "disabled", "message": "Automation is disabled"}), 200

    data = request.json
    if not data or "alerts" not in data:
        logger.error(f"Invalid webhook payload: {data}")
        return jsonify({"error": "Invalid payload", "expected": "alerts array"}), 400

    logger.info(
        f"Received webhook with {len(data['alerts'])} alerts (status: {data.get('status', 'unknown')})"
    )

    results = []
    for alert in data["alerts"]:
        if alert["status"] != "firing":
            logger.debug(
                f"Skipping non-firing alert: {alert['labels'].get('alertname')}"
            )
            continue

        alertname = alert["labels"].get("alertname", "unknown")
        severity = alert["labels"].get("severity", "unknown")
        component = alert["labels"].get("component", "unknown")

        logger.info(
            f"Processing alert: {alertname} (severity={severity}, component={component})"
        )

        # Safety check: throttle
        if not check_throttle(alertname):
            results.append(
                {
                    "alert": alertname,
                    "status": "throttled",
                    "message": f"Exceeded {MAX_REMEDIATIONS_PER_HOUR} remediations in last hour",
                }
            )
            continue

        # Safety check: only automate warning/info alerts (not critical)
        if severity == "critical":
            logger.info(f"Skipping critical alert {alertname} (requires human review)")
            results.append(
                {
                    "alert": alertname,
                    "status": "skipped",
                    "message": "Critical alerts require human review",
                }
            )
            continue

        # Route to remediation handler
        result = route_remediation(alert)
        results.append(result)

    return (
        jsonify(
            {
                "status": "processed",
                "automation_enabled": AUTOMATION_ENABLED,
                "dry_run": DRY_RUN,
                "results": results,
            }
        ),
        200,
    )


def route_remediation(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Route alert to appropriate remediation handler"""
    alertname = alert["labels"].get("alertname", "")
    severity = alert["labels"].get("severity", "unknown")
    component = alert["labels"].get("component", "unknown")

    # Import handlers here to avoid import errors
    try:
        from remediation_actions import RemediationActions
    except ImportError:
        # Fallback for when running as script
        import os
        import sys

        sys.path.insert(0, os.path.dirname(__file__))

    # Map alertnames to handlers
    handlers = {
        "K0MemoryUsageHigh": lambda: remediate_memory_usage(alert),
        "K0SSEConnectionStorm": lambda: remediate_sse_storm(alert),
        "K0QueryLatencyTrendIncreasing": lambda: remediate_slow_query(alert),
        "K0DiskSpaceExhaustionForecast": lambda: remediate_disk_space(alert),
        "K0TrafficSpikeAnomaly": lambda: remediate_traffic_spike(alert),
        "K0ErrorRateSpikeAnomaly": lambda: remediate_error_spike(alert),
    }

    handler = handlers.get(alertname)
    if not handler:
        logger.info(f"No automated remediation configured for {alertname}")
        return {
            "alert": alertname,
            "status": "no_handler",
            "message": f"No remediation handler for {alertname}",
        }

    try:
        start = datetime.utcnow()
        logger.info(f"Executing remediation for {alertname} (dry_run={DRY_RUN})")

        result = handler()

        duration = (datetime.utcnow() - start).total_seconds()

        status = "success" if result.success else "failed"
        logger.info(
            f"Remediation {status} for {alertname} in {duration:.2f}s (action={result.action})"
        )

        log_remediation(
            alertname=alertname,
            severity=severity,
            component=component,
            action=result.action,
            status=status,
            error=result.error,
            duration=duration,
            dry_run=DRY_RUN,
        )

        return {
            "alert": alertname,
            "status": status,
            "action": result.action,
            "duration_seconds": duration,
            "dry_run": DRY_RUN,
            "details": result.details,
        }

    except Exception as e:
        logger.error(f"Remediation exception for {alertname}: {e}", exc_info=True)

        log_remediation(
            alertname=alertname,
            severity=severity,
            component=component,
            action="unknown",
            status="error",
            error=str(e),
            duration=0.0,
            dry_run=DRY_RUN,
        )

        return {"alert": alertname, "status": "error", "error": str(e)}


def remediate_memory_usage(alert: Dict[str, Any]) -> RemediationResult:
    """Remediate high memory usage by clearing caches"""
    try:
        from remediation_actions import RemediationActions
    except ImportError:
        import os
        import sys

        sys.path.insert(0, os.path.dirname(__file__))
        from remediation_actions import RemediationActions

    logger.info("Remediating high memory usage: clearing caches")

    if DRY_RUN:
        logger.info("[DRY RUN] Would clear cache via SIGHUP")
        return RemediationResult(success=True, action="cache_clear_dry_run")

    # Try cache clear first (graceful)
    if RemediationActions.clear_cache():
        return RemediationResult(
            success=True, action="cache_clear", details={"method": "SIGHUP"}
        )

    # Fallback: restart service (more disruptive)
    logger.warning("Cache clear failed, falling back to service restart")
    if RemediationActions.restart_service():
        return RemediationResult(
            success=True,
            action="service_restart",
            details={"method": "docker-compose restart", "fallback": True},
        )

    return RemediationResult(
        success=False, action="cache_clear", error="Both cache clear and restart failed"
    )


def remediate_sse_storm(alert: Dict[str, Any]) -> RemediationResult:
    """Remediate SSE connection storm by enabling rate limiting"""
    try:
        from remediation_actions import RemediationActions
    except ImportError:
        import os
        import sys

        sys.path.insert(0, os.path.dirname(__file__))
        from remediation_actions import RemediationActions

    logger.info("Remediating SSE connection storm: enabling rate limiting")

    if DRY_RUN:
        logger.info("[DRY RUN] Would enable rate limiting (10 req/sec)")
        return RemediationResult(success=True, action="rate_limit_enable_dry_run")

    if RemediationActions.enable_rate_limiting(rate_limit=10):
        return RemediationResult(
            success=True,
            action="rate_limit_enable",
            details={"rate": "10 req/sec", "burst": "20 req"},
        )

    return RemediationResult(
        success=False,
        action="rate_limit_enable",
        error="Failed to enable rate limiting",
    )


def remediate_slow_query(alert: Dict[str, Any]) -> RemediationResult:
    """Remediate slow queries by canceling long-running queries"""
    from remediation_actions import RemediationActions

    logger.info("Remediating slow query: canceling long-running queries >5s")

    if DRY_RUN:
        logger.info("[DRY RUN] Would cancel queries running >5s")
        return RemediationResult(success=True, action="query_cancel_dry_run")

    if RemediationActions.cancel_slow_queries(threshold_seconds=5.0):
        return RemediationResult(
            success=True, action="query_cancel", details={"threshold_seconds": 5.0}
        )

    return RemediationResult(
        success=False,
        action="query_cancel",
        error="No slow queries found or cancellation failed",
    )


def remediate_disk_space(alert: Dict[str, Any]) -> RemediationResult:
    """Remediate disk space exhaustion by rotating logs and pruning WAL"""
    from remediation_actions import RemediationActions

    logger.info("Remediating disk space: rotating logs and pruning WAL")

    if DRY_RUN:
        logger.info("[DRY RUN] Would rotate logs and prune WAL segments >7d")
        return RemediationResult(success=True, action="log_rotate_dry_run")

    log_rotated = RemediationActions.rotate_logs()
    wal_pruned = RemediationActions.prune_wal(days=7)

    if log_rotated and wal_pruned:
        return RemediationResult(
            success=True,
            action="log_rotate_and_prune",
            details={"log_rotate": True, "wal_prune": True, "wal_days": 7},
        )
    elif log_rotated or wal_pruned:
        return RemediationResult(
            success=True,
            action="partial_cleanup",
            details={"log_rotate": log_rotated, "wal_prune": wal_pruned},
        )

    return RemediationResult(
        success=False,
        action="log_rotate_and_prune",
        error="Both log rotation and WAL pruning failed",
    )


def remediate_traffic_spike(alert: Dict[str, Any]) -> RemediationResult:
    """Remediate traffic spike by enabling circuit breaker"""
    from remediation_actions import RemediationActions

    logger.info("Remediating traffic spike: enabling circuit breaker")

    if DRY_RUN:
        logger.info("[DRY RUN] Would enable circuit breaker for 5m")
        return RemediationResult(success=True, action="circuit_breaker_enable_dry_run")

    if RemediationActions.enable_circuit_breaker(duration_minutes=5):
        return RemediationResult(
            success=True,
            action="circuit_breaker_enable",
            details={"duration_minutes": 5, "auto_disable": True},
        )

    return RemediationResult(
        success=False,
        action="circuit_breaker_enable",
        error="Failed to enable circuit breaker",
    )


def remediate_error_spike(alert: Dict[str, Any]) -> RemediationResult:
    """Remediate error spike by enabling circuit breaker"""
    from remediation_actions import RemediationActions

    logger.info("Remediating error spike: enabling circuit breaker")

    if DRY_RUN:
        logger.info("[DRY RUN] Would enable circuit breaker for 5m")
        return RemediationResult(success=True, action="circuit_breaker_enable_dry_run")

    if RemediationActions.enable_circuit_breaker(duration_minutes=5):
        return RemediationResult(
            success=True,
            action="circuit_breaker_enable",
            details={
                "duration_minutes": 5,
                "auto_disable": True,
                "reason": "error_spike",
            },
        )

    return RemediationResult(
        success=False,
        action="circuit_breaker_enable",
        error="Failed to enable circuit breaker",
    )


@app.route("/history", methods=["GET"])
def history():
    """Query remediation history"""
    limit = request.args.get("limit", 100, type=int)
    alertname = request.args.get("alertname")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if alertname:
        cursor = conn.execute(
            """
            SELECT * FROM remediation_history
            WHERE alertname = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """,
            (alertname, limit),
        )
    else:
        cursor = conn.execute(
            """
            SELECT * FROM remediation_history
            ORDER BY timestamp DESC
            LIMIT ?
        """,
            (limit,),
        )

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({"history": rows, "count": len(rows)}), 200


@app.route("/stats", methods=["GET"])
def stats():
    """Get remediation statistics"""
    conn = sqlite3.connect(DB_PATH)

    # Success rate (last 24h)
    cursor = conn.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success
        FROM remediation_history
        WHERE timestamp > datetime('now', '-24 hours')
    """
    )
    row = cursor.fetchone()
    total, success = row[0], row[1]
    success_rate = (success / total * 100) if total > 0 else 0

    # MTTR (mean time to remediation)
    cursor = conn.execute(
        """
        SELECT AVG(duration_seconds) as mttr
        FROM remediation_history
        WHERE status = 'success'
        AND timestamp > datetime('now', '-24 hours')
    """
    )
    mttr = cursor.fetchone()[0] or 0

    # Top alerts
    cursor = conn.execute(
        """
        SELECT alertname, COUNT(*) as count
        FROM remediation_history
        WHERE timestamp > datetime('now', '-24 hours')
        GROUP BY alertname
        ORDER BY count DESC
        LIMIT 5
    """
    )
    top_alerts = [{"alertname": row[0], "count": row[1]} for row in cursor.fetchall()]

    conn.close()

    return (
        jsonify(
            {
                "time_window": "24 hours",
                "total_remediations": total,
                "success_count": success,
                "success_rate_percent": round(success_rate, 2),
                "mean_time_to_remediation_seconds": round(mttr, 2),
                "top_alerts": top_alerts,
            }
        ),
        200,
    )


if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", "8081"))
    logger.info(f"Starting K0 Remediation Service on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
    app.run(host="0.0.0.0", port=port, debug=False)
    app.run(host="0.0.0.0", port=port, debug=False)
    app.run(host="0.0.0.0", port=port, debug=False)
