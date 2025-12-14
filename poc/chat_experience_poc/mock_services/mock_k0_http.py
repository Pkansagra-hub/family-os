"""
Mock K0 HTTP Server - WAL and Batch Operations

Purpose:
- Mimics K0 Write-Ahead Log (WAL) commit endpoint
- Supports batch operations for memory/semantic writers
- Validates schema for all operations
- Returns consistent receipt IDs for downstream assertions
- Lightweight logging for request tracing

Endpoints:
- POST /api/wal/commit - Commit plan to WAL (used by Planner)
- POST /api/wal/batch - Batch operation for writers
- GET /health - Health check
- GET /stats - Statistics for test assertions

Architecture:
- FastAPI server on port 5202 (K0 WAL port)
- Schema validation for all operations
- Consistent receipt_id generation (UUID)
- Call statistics tracking
- Request ID tracing

Performance:
- Commit latency: <10ms P95
- Batch latency: <50ms P95
- Validation: <5ms

Usage:
    # Start server
    uvicorn mock_k0_http:app --host 0.0.0.0 --port 5202

    # Commit plan
    POST http://localhost:5202/api/wal/commit
    {
        "operation": "plan_commit",
        "plan_id": "...",
        "payload": {...},
        "trace_id": "..."
    }

    # Batch operation
    POST http://localhost:5202/api/wal/batch
    {
        "batch_type": "episodic_memory",
        "operations": [...],
        "trace_id": "..."
    }
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

# Configure logging
logger = structlog.get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Mock K0 HTTP Server",
    description="WAL and batch operations for K0 integration",
    version="1.0.0",
)

# Call statistics for test assertions
call_stats = {
    "total_commits": 0,
    "successful_commits": 0,
    "failed_commits": 0,
    "total_batches": 0,
    "successful_batches": 0,
    "failed_batches": 0,
}


# ========== DATA MODELS ==========


class WALCommitRequest(BaseModel):
    """Request to commit operation to WAL"""

    operation: str = Field(..., description="Operation type (e.g., 'plan_commit')")
    plan_id: Optional[str] = Field(None, description="Plan ID for plan commits")
    payload: Dict[str, Any] = Field(..., description="Operation payload")
    trace_id: str = Field(..., description="Cognitive trace ID for request tracing")

    @validator("operation")
    def validate_operation(cls, v):
        allowed_operations = {"plan_commit", "memory_write", "semantic_write", "goal_update"}
        if v not in allowed_operations:
            raise ValueError(f"Invalid operation: {v}. Allowed: {allowed_operations}")
        return v


class BatchOperation(BaseModel):
    """Single operation in a batch"""

    operation_id: str
    operation_type: str
    data: Dict[str, Any]


class BatchRequest(BaseModel):
    """Request for batch operations"""

    batch_type: str = Field(..., description="Batch type (episodic_memory, semantic_memory, etc.)")
    operations: List[BatchOperation] = Field(..., description="List of operations in batch")
    trace_id: str = Field(..., description="Cognitive trace ID for request tracing")

    @validator("batch_type")
    def validate_batch_type(cls, v):
        allowed_types = {"episodic_memory", "semantic_memory", "goal_tracking", "preference_update"}
        if v not in allowed_types:
            raise ValueError(f"Invalid batch_type: {v}. Allowed: {allowed_types}")
        return v

    @validator("operations")
    def validate_operations(cls, v):
        if len(v) == 0:
            raise ValueError("Batch must contain at least one operation")
        if len(v) > 100:
            raise ValueError("Batch size exceeds limit of 100 operations")
        return v


# ========== ENDPOINTS ==========


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "mock-k0-http",
        "version": "1.0.0",
        "port": 5202,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/wal/commit")
async def commit_to_wal(request: WALCommitRequest):
    """
    Commit operation to Write-Ahead Log

    Used by Planner to persist committed plans.
    Returns receipt_id for confirmation and tracking.

    Args:
        request: WAL commit request with operation, payload, trace_id

    Returns:
        {
            "status": "committed",
            "request_id": "<uuid>",
            "receipt_id": "<uuid>",
            "operation": "<operation_type>",
            "trace_id": "<trace_id>",
            "timestamp": "<iso_timestamp>"
        }
    """
    # Generate request_id and receipt_id
    request_id = str(uuid.uuid4())
    receipt_id = str(uuid.uuid4())
    call_stats["total_commits"] += 1

    logger.info(
        "wal_commit_received",
        operation=request.operation,
        request_id=request_id,
        plan_id=request.plan_id,
        trace_id=request.trace_id,
    )

    # Validate payload (basic checks)
    if not request.payload:
        call_stats["failed_commits"] += 1
        logger.warning(
            "wal_commit_invalid",
            request_id=request_id,
            reason="Empty payload",
        )
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "request_id": request_id,
                "reason": "Payload cannot be empty",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    # Simulate WAL write (in production: actual persistence)
    call_stats["successful_commits"] += 1

    logger.info(
        "wal_commit_success",
        request_id=request_id,
        receipt_id=receipt_id,
        operation=request.operation,
        trace_id=request.trace_id,
    )

    return {
        "status": "committed",
        "request_id": request_id,
        "receipt_id": receipt_id,
        "operation": request.operation,
        "plan_id": request.plan_id,
        "trace_id": request.trace_id,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/wal/batch")
async def batch_operation(request: BatchRequest):
    """
    Execute batch operations

    Used by memory/semantic writers to batch multiple operations.
    Returns batch_id and individual receipt_ids.

    Args:
        request: Batch request with batch_type, operations, trace_id

    Returns:
        {
            "status": "completed",
            "request_id": "<uuid>",
            "batch_id": "<uuid>",
            "batch_type": "<batch_type>",
            "operation_count": <int>,
            "receipts": [{"operation_id": "...", "receipt_id": "..."}],
            "trace_id": "<trace_id>",
            "timestamp": "<iso_timestamp>"
        }
    """
    # Generate request_id and batch_id
    request_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())
    call_stats["total_batches"] += 1

    logger.info(
        "batch_operation_received",
        batch_type=request.batch_type,
        request_id=request_id,
        operation_count=len(request.operations),
        trace_id=request.trace_id,
    )

    # Generate receipt_id for each operation
    receipts = []
    for op in request.operations:
        receipt_id = str(uuid.uuid4())
        receipts.append(
            {
                "operation_id": op.operation_id,
                "operation_type": op.operation_type,
                "receipt_id": receipt_id,
            }
        )

    # Simulate batch processing (in production: actual execution)
    call_stats["successful_batches"] += 1

    logger.info(
        "batch_operation_success",
        request_id=request_id,
        batch_id=batch_id,
        batch_type=request.batch_type,
        operation_count=len(request.operations),
        trace_id=request.trace_id,
    )

    return {
        "status": "completed",
        "request_id": request_id,
        "batch_id": batch_id,
        "batch_type": request.batch_type,
        "operation_count": len(request.operations),
        "receipts": receipts,
        "trace_id": request.trace_id,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/stats")
async def get_stats():
    """
    Get call statistics for test assertions

    Returns commit/batch counts, success rates, and error breakdown.
    Useful for integration tests to verify expected call patterns.
    """
    commit_success_rate = (
        (call_stats["successful_commits"] / call_stats["total_commits"] * 100)
        if call_stats["total_commits"] > 0
        else 0.0
    )
    batch_success_rate = (
        (call_stats["successful_batches"] / call_stats["total_batches"] * 100)
        if call_stats["total_batches"] > 0
        else 0.0
    )

    return {
        "commits": {
            "total": call_stats["total_commits"],
            "successful": call_stats["successful_commits"],
            "failed": call_stats["failed_commits"],
            "success_rate_percent": round(commit_success_rate, 2),
        },
        "batches": {
            "total": call_stats["total_batches"],
            "successful": call_stats["successful_batches"],
            "failed": call_stats["failed_batches"],
            "success_rate_percent": round(batch_success_rate, 2),
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


# Run with: uvicorn mock_k0_http:app --host 0.0.0.0 --port 5202 --reload
if __name__ == "__main__":
    import uvicorn

    logger.info("starting_mock_k0_http_server", port=5202)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=5202,
        log_level="info",
    )
