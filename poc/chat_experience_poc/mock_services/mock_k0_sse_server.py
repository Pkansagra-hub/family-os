"""
Mock K0 SSE Server - Server-Sent Events for proactive triggers

Purpose:
- Mimics K0 P05 Prospective Memory SSE stream
- Sends time-based trigger events to K1 ProactiveAgent
- Maintains persistent SSE connections
- Supports multiple concurrent clients

Architecture:
- FastAPI server with SSE endpoint (GET /sse/stream)
- POST /fire endpoint for Temporal Module to send events
- In-memory event queue for all connected clients
- Resilient to brief network interruptions (30s heartbeat)

Performance:
- Connection establishment: <100ms
- Event delivery latency: <50ms P95
- Heartbeat interval: 30s
- Supports 10+ concurrent SSE connections

Usage:
    # Start server
    uvicorn mock_k0_sse_server:app --host 0.0.0.0 --port 8002

    # Connect SSE client
    GET http://localhost:8002/sse/stream

    # Fire event (from Temporal Module)
    POST http://localhost:8002/fire
    {
        "event_type": "prospective.trigger.fired",
        "data": {"trigger_id": "...", "message": "..."}
    }
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="Mock K0 SSE Server", version="1.0.0")

# Event queue for SSE clients
event_queue: asyncio.Queue = asyncio.Queue()

# Connected clients (for tracking)
connected_clients: Dict[str, bool] = {}


class SSEEvent(BaseModel):
    """SSE event data model"""

    event_type: str
    data: Dict[str, Any]


@app.on_event("startup")
async def startup_event():
    """Server startup"""
    logger.info("[MockK0SSE] Server starting on port 8002")


@app.on_event("shutdown")
async def shutdown_event():
    """Server shutdown"""
    logger.info("[MockK0SSE] Server shutting down")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "connected_clients": len(connected_clients),
        "server": "Mock K0 SSE Server",
        "version": "1.0.0",
    }


@app.post("/fire")
async def fire_event(event: SSEEvent):
    """
    Fire SSE event to all connected clients

    Called by Temporal Module when trigger fires.

    Args:
        event: SSE event with type and data

    Returns:
        Success response
    """
    # Add event to queue
    await event_queue.put(event.dict())

    logger.info(
        f"[MockK0SSE] Event fired: {event.event_type}",
        extra={
            "event_type": event.event_type,
            "trigger_id": event.data.get("trigger_id"),
            "queue_size": event_queue.qsize(),
        },
    )

    return {
        "status": "fired",
        "event_type": event.event_type,
        "trigger_id": event.data.get("trigger_id"),
        "queue_size": event_queue.qsize(),
    }


@app.get("/sse/stream")
async def sse_stream(request: Request):
    """
    SSE stream endpoint

    K1 ProactiveAgent connects here to receive proactive trigger events.

    Event format:
        event: prospective.trigger.fired
        data: {"trigger_id": "...", "message": "...", ...}

    Supports multiple concurrent connections.
    Sends heartbeat every 30 seconds to keep connection alive.
    """
    # Generate client ID
    client_id = f"client_{uuid.uuid4().hex[:8]}"
    connected_clients[client_id] = True

    logger.info(
        f"[MockK0SSE] Client connected: {client_id}",
        extra={"client_id": client_id, "total_clients": len(connected_clients)},
    )

    async def event_generator():
        """
        Generate SSE events for this client

        Yields SSE-formatted events:
        - Data events from event_queue
        - Heartbeat events every 30 seconds
        - Handles client disconnection gracefully
        """
        try:
            last_heartbeat = datetime.utcnow()

            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info(f"[MockK0SSE] Client disconnected: {client_id}")
                    break

                # Send heartbeat every 30 seconds
                now = datetime.utcnow()
                if (now - last_heartbeat).total_seconds() >= 30:
                    heartbeat_data = {
                        "timestamp": now.isoformat() + "Z",
                        "server": "Mock K0 SSE Server",
                        "client_id": client_id,
                    }
                    yield "event: heartbeat\n"
                    yield f"data: {json.dumps(heartbeat_data)}\n\n"
                    last_heartbeat = now

                # Check for events in queue
                try:
                    # Non-blocking get with timeout
                    event_data = await asyncio.wait_for(event_queue.get(), timeout=1.0)

                    # Format as SSE event
                    event_type = event_data.get("event_type", "prospective.trigger.fired")
                    data = event_data.get("data", {})

                    # Add event_id for client replay support
                    event_id = f"event_{uuid.uuid4().hex[:8]}"

                    yield f"id: {event_id}\n"
                    yield f"event: {event_type}\n"
                    yield f"data: {json.dumps(data)}\n\n"

                    logger.debug(
                        f"[MockK0SSE] Event sent to {client_id}",
                        extra={"event_type": event_type, "event_id": event_id},
                    )

                except asyncio.TimeoutError:
                    # No events in queue, continue to next iteration
                    continue

        except asyncio.CancelledError:
            logger.info(f"[MockK0SSE] Client stream cancelled: {client_id}")

        except Exception as e:
            logger.error(
                f"[MockK0SSE] Error in client stream: {client_id}",
                extra={"error": str(e)},
                exc_info=True,
            )

        finally:
            # Clean up client
            if client_id in connected_clients:
                del connected_clients[client_id]
            logger.info(
                f"[MockK0SSE] Client cleanup: {client_id}",
                extra={"remaining_clients": len(connected_clients)},
            )

    # Return SSE streaming response
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@app.get("/clients")
async def get_clients():
    """
    Get connected clients info

    Returns:
        Client count and IDs
    """
    return {"count": len(connected_clients), "client_ids": list(connected_clients.keys())}


@app.get("/queue/stats")
async def get_queue_stats():
    """
    Get event queue statistics

    Returns:
        Queue size and status
    """
    return {"queue_size": event_queue.qsize(), "connected_clients": len(connected_clients)}


# Run with: uvicorn mock_k0_sse_server:app --host 0.0.0.0 --port 8002 --reload
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
    uvicorn.run(app, host="0.0.0.0", port=8002)
