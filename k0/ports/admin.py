"""Admin endpoints for K0 kernel operations.

These endpoints are ONLY enabled in development/local environments.
In production, they are disabled by default for security.

Endpoints:
    POST /k0/admin/pipelines/{pipeline_id}/trigger - Fire a manual trigger
    GET /k0/admin/pipelines - List registered pipelines
    GET /k0/admin/scheduler/status - Get scheduler status

Security:
    - Development only by default (environment != "production")
    - No authentication required in development
    - Production deployment should not expose these endpoints

ADR Reference:
    - ADR-K004: Capability Mesh Architecture
    - P03 Dossier D.5.3: Manual Trigger API
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..scheduler import get_pipeline_scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/k0/admin", tags=["admin"])


class ManualTriggerRequest(BaseModel):
    """Request body for manual pipeline trigger.

    Matches dossier spec D.5.3.
    """

    reason: str = Field(
        ...,
        description="Human-readable reason for manual trigger (required for audit)",
        min_length=1,
        max_length=500,
    )
    options: dict[str, Any] | None = Field(
        default=None,
        description="Optional trigger options (skip_r5, max_events, space_id, tenant_id)",
    )


class ManualTriggerResponse(BaseModel):
    """Response for manual trigger request."""

    success: bool
    pipeline_id: str
    trigger_id: str
    message: str


class PipelineInfo(BaseModel):
    """Pipeline information."""

    pipeline_id: str
    state: str
    trigger_count: int
    trigger_ids: list[str]
    execution_count: int


class SchedulerStatus(BaseModel):
    """Scheduler status information."""

    running: bool
    pipeline_count: int
    pipelines: list[PipelineInfo]


def _check_development_mode(request: Request) -> None:
    """Ensure admin endpoints are only accessible in development mode.

    Raises:
        HTTPException: If not in development mode
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        # Allow if settings not available (testing)
        return

    environment = getattr(settings, "environment", "development")
    if environment.lower() == "production":
        logger.warning(
            "Admin endpoint access blocked in production",
            extra={"path": request.url.path},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin endpoints are disabled in production",
        )


@router.post(
    "/pipelines/{pipeline_id}/trigger",
    response_model=ManualTriggerResponse,
    summary="Fire a manual pipeline trigger",
    description=(
        "Manually trigger a pipeline execution. Only works for pipelines "
        "that have a manual trigger registered (e.g., P03_CONSOLIDATION)."
    ),
)
async def fire_manual_trigger(
    pipeline_id: str,
    request: Request,
    body: ManualTriggerRequest,
    trigger_id: str = "p03_manual",
) -> ManualTriggerResponse:
    """Fire a manual trigger for a pipeline.

    Args:
        pipeline_id: Pipeline ID (e.g., P03_CONSOLIDATION)
        trigger_id: Trigger ID (default: p03_manual)
        body: Trigger request with reason and optional options

    Returns:
        ManualTriggerResponse with success status

    Example:
        POST /k0/admin/pipelines/P03_CONSOLIDATION/trigger?trigger_id=p03_manual
        {
            "reason": "Manual consolidation before demo",
            "options": {
                "skip_r5": false,
                "max_events": 1000
            }
        }
    """
    _check_development_mode(request)

    scheduler = get_pipeline_scheduler()
    if scheduler is None:
        logger.error("PipelineScheduler not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipeline scheduler not initialized",
        )

    # Build context for trigger
    context: dict[str, Any] = {"reason": body.reason}
    if body.options:
        context["options"] = body.options

    logger.info(
        "Manual trigger requested",
        extra={
            "pipeline_id": pipeline_id,
            "trigger_id": trigger_id,
            "reason": body.reason,
            "options": body.options,
        },
    )

    success = scheduler.fire_manual_trigger(pipeline_id, trigger_id, context)

    if success:
        logger.info(
            "Manual trigger fired successfully",
            extra={"pipeline_id": pipeline_id, "trigger_id": trigger_id},
        )
        return ManualTriggerResponse(
            success=True,
            pipeline_id=pipeline_id,
            trigger_id=trigger_id,
            message=f"Manual trigger '{trigger_id}' fired for pipeline '{pipeline_id}'",
        )
    else:
        logger.warning(
            "Manual trigger failed",
            extra={"pipeline_id": pipeline_id, "trigger_id": trigger_id},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline '{pipeline_id}' not found or trigger '{trigger_id}' is not manual type",
        )


@router.get(
    "/pipelines",
    response_model=list[PipelineInfo],
    summary="List registered pipelines",
    description="Get information about all registered pipelines and their triggers.",
)
async def list_pipelines(request: Request) -> list[PipelineInfo]:
    """List all registered pipelines."""
    _check_development_mode(request)

    scheduler = get_pipeline_scheduler()
    if scheduler is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipeline scheduler not initialized",
        )

    pipelines = []
    for pipeline_id, scheduled in scheduler.pipelines.items():
        pipelines.append(
            PipelineInfo(
                pipeline_id=pipeline_id,
                state=(
                    scheduled.state.value
                    if hasattr(scheduled.state, "value")
                    else str(scheduled.state)
                ),
                trigger_count=len(scheduled.triggers),
                trigger_ids=[t.spec.id for t in scheduled.triggers],
                execution_count=scheduled.execution_count,
            )
        )

    return pipelines


@router.get(
    "/scheduler/status",
    response_model=SchedulerStatus,
    summary="Get scheduler status",
    description="Get the current status of the pipeline scheduler.",
)
async def get_scheduler_status(request: Request) -> SchedulerStatus:
    """Get scheduler status."""
    _check_development_mode(request)

    scheduler = get_pipeline_scheduler()
    if scheduler is None:
        return SchedulerStatus(running=False, pipeline_count=0, pipelines=[])

    pipelines = []
    for pipeline_id, scheduled in scheduler.pipelines.items():
        pipelines.append(
            PipelineInfo(
                pipeline_id=pipeline_id,
                state=(
                    scheduled.state.value
                    if hasattr(scheduled.state, "value")
                    else str(scheduled.state)
                ),
                trigger_count=len(scheduled.triggers),
                trigger_ids=[t.spec.id for t in scheduled.triggers],
                execution_count=scheduled.execution_count,
            )
        )

    return SchedulerStatus(
        running=scheduler.is_running,
        pipeline_count=len(scheduler.pipelines),
        pipelines=pipelines,
    )
