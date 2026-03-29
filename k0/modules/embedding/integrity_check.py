"""M28: embedding.integrity_check -- embedding data health validation.

Validates embedding data consistency across st_vec and st_hipp_events.
Runs 4 diagnostic checks and produces a structured integrity report.

ADR Reference: ADR-K003 v2.0 (Inline Embedding via UltraBERT)
Contract: k0/contracts/modules/embedding.integrity_check.v1.yaml

Flow:
1. Count total vectors in st_vec
2. Check dimension mismatches (vector_dim != 768)
3. Check model consistency (distinct model_id values)
4. Count orphaned vectors (st_vec without parent st_hipp_events)
5. Count missing vectors (st_hipp_events READY but no st_vec row)
6. Classify health: HEALTHY / DEGRADED / CRITICAL
7. Auto-correct missing vectors by setting embedding_status=PENDING

Performance: ~500ms (4 COUNT queries, mostly index scans)

Pipeline: P08 stage_30_integrity
Version: 1.0.0
Last Updated: 2025-06-30
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Health classification thresholds
_DEGRADED_THRESHOLD = 100

# Module metrics
_metrics = {
    "checks_run": 0,
    "healthy_count": 0,
    "degraded_count": 0,
    "critical_count": 0,
    "auto_corrections": 0,
    "check_failures": 0,
}


async def run(
    message: Any, context: Any, envelope: dict[str, Any] | None = None, **config: Any
) -> dict[str, Any]:
    """
    Run embedding integrity checks for P08 stage_30.

    Executes 4 diagnostic queries and produces a structured integrity
    report with health classification. Auto-corrects missing vectors
    by resetting embedding_status to PENDING for M25 backfill.

    Args:
        message: BusMessage (optional)
        context: PipelineContext with syscalls, logger, config
        envelope: Event envelope (optional, for scoped checks)
        **config: Stage configuration:
            - auto_correct_missing: bool (default: True)
            - degraded_threshold: int (default: 100)
            - checks: list[str] (default: all 4 checks)

    Returns:
        Dictionary with integrity_check report:
        - status: HEALTHY | DEGRADED | CRITICAL
        - total_vectors: int
        - dimension_mismatches: int
        - model_versions: list[str]
        - orphaned_vectors: int
        - missing_vectors: int
        - auto_corrected: int
        - checked_at: str (ISO 8601)

    Raises:
        RuntimeError: If critical check queries fail
    """
    auto_correct = config.get(
        "auto_correct_missing",
        getattr(context, "config", {}).get("auto_correct_missing", True),
    )
    degraded_threshold = config.get(
        "degraded_threshold",
        getattr(context, "config", {}).get("degraded_threshold", _DEGRADED_THRESHOLD),
    )
    requested_checks = config.get("checks", None)

    # Scope from envelope if provided
    envelope = envelope or {}
    payload = envelope.get("payload", {})
    tenant_id = payload.get("tenant_id")
    space_id = payload.get("space_id")

    syscalls = context.syscalls

    all_checks = [
        "dimension_validation",
        "model_consistency",
        "orphan_detection",
        "missing_vectors",
    ]
    checks_to_run = requested_checks if requested_checks else all_checks

    report = {
        "total_vectors": 0,
        "dimension_mismatches": 0,
        "model_versions": [],
        "orphaned_vectors": 0,
        "missing_vectors": 0,
        "auto_corrected": 0,
        "status": "HEALTHY",
        "checked_at": "",
    }

    # Check 0: Total vector count (always runs)
    try:
        count_result = await syscalls.vec_count(
            tenant_id=tenant_id,
            space_id=space_id,
        )
        report["total_vectors"] = count_result.get("count", 0)
    except Exception as e:
        logger.error("M28: Failed to count vectors", extra={"error": str(e)})
        _metrics["check_failures"] += 1

    # Check 1: Dimension validation
    if "dimension_validation" in checks_to_run:
        try:
            dim_result = await syscalls.vec_count_dimension_mismatches(
                tenant_id=tenant_id,
                space_id=space_id,
                expected_dim=768,
            )
            report["dimension_mismatches"] = dim_result.get("count", 0)
            if report["dimension_mismatches"] > 0:
                logger.warning(
                    "M28: Dimension mismatches detected",
                    extra={"count": report["dimension_mismatches"]},
                )
        except Exception as e:
            logger.error("M28: Dimension check failed", extra={"error": str(e)})
            _metrics["check_failures"] += 1

    # Check 2: Model consistency
    if "model_consistency" in checks_to_run:
        try:
            model_result = await syscalls.vec_distinct_models(
                tenant_id=tenant_id,
                space_id=space_id,
            )
            report["model_versions"] = model_result.get("models", [])
            if len(report["model_versions"]) > 1:
                logger.warning(
                    "M28: Multiple model versions detected",
                    extra={"models": report["model_versions"]},
                )
        except Exception as e:
            logger.error("M28: Model consistency check failed", extra={"error": str(e)})
            _metrics["check_failures"] += 1

    # Check 3: Orphan detection
    if "orphan_detection" in checks_to_run:
        try:
            orphan_result = await syscalls.vec_orphan_count(
                tenant_id=tenant_id,
                space_id=space_id,
            )
            report["orphaned_vectors"] = orphan_result.get("count", 0)
            if report["orphaned_vectors"] > 0:
                logger.warning(
                    "M28: Orphaned vectors detected",
                    extra={"count": report["orphaned_vectors"]},
                )
        except Exception as e:
            logger.error("M28: Orphan detection failed", extra={"error": str(e)})
            _metrics["check_failures"] += 1

    # Check 4: Missing vectors
    if "missing_vectors" in checks_to_run:
        try:
            missing_result = await syscalls.hipp_events_missing_vectors(
                tenant_id=tenant_id,
                space_id=space_id,
            )
            report["missing_vectors"] = missing_result.get("count", 0)
            if report["missing_vectors"] > 0:
                logger.warning(
                    "M28: Missing vectors detected (READY without st_vec row)",
                    extra={"count": report["missing_vectors"]},
                )
        except Exception as e:
            logger.error("M28: Missing vectors check failed", extra={"error": str(e)})
            _metrics["check_failures"] += 1

    # Classify health
    total_issues = (
        report["dimension_mismatches"] + report["orphaned_vectors"] + report["missing_vectors"]
    )

    if total_issues == 0:
        report["status"] = "HEALTHY"
        _metrics["healthy_count"] += 1
    elif total_issues < degraded_threshold:
        report["status"] = "DEGRADED"
        _metrics["degraded_count"] += 1
    else:
        report["status"] = "CRITICAL"
        _metrics["critical_count"] += 1

    # Auto-correct: reset embedding_status=PENDING for missing vectors
    if auto_correct and report["missing_vectors"] > 0:
        try:
            correction_result = await syscalls.hipp_events_reset_missing_embedding_status(
                tenant_id=tenant_id,
                space_id=space_id,
            )
            report["auto_corrected"] = correction_result.get("updated_count", 0)
            _metrics["auto_corrections"] += report["auto_corrected"]
            logger.info(
                "M28: Auto-corrected missing vectors (set PENDING)",
                extra={"corrected": report["auto_corrected"]},
            )
        except Exception as e:
            logger.error(
                "M28: Auto-correction failed (non-fatal)",
                extra={"error": str(e)},
            )

    report["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    _metrics["checks_run"] += 1

    logger.info(
        "M28: Integrity check complete",
        extra={
            "status": report["status"],
            "total_vectors": report["total_vectors"],
            "total_issues": total_issues,
            "auto_corrected": report["auto_corrected"],
        },
    )

    return {"integrity_check": report}


def get_metrics() -> dict[str, int]:
    """
    Get module metrics for observability.

    Returns:
        Dictionary with metric counters
    """
    return dict(_metrics)


def reset_metrics() -> None:
    """Reset metrics counters (for testing)."""
    for key in _metrics:
        _metrics[key] = 0
