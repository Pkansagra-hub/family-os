#!/usr/bin/env python3
"""
K1 Intelligence Module - WebSocket Streaming API

FastAPI-based WebSocket API for real-time chat streaming.
Reuses SystemCoordinator initialization and DeltaBus event streaming.

Architecture:
- Startup: Initialize SystemCoordinator once (7-phase init)
- WebSocket: Stream DeltaBus events in real-time
- Message Routing: IntentRouter mailbox flow (from run_e2e_paths.py)
- Session Management: Per-connection SessionStateManager

Endpoints:
- WebSocket /ws/chat/{user_id} - Real-time streaming chat
- GET /health - System health status
- POST /chat - REST fallback (non-streaming)

References:
- scripts/run_e2e_paths.py - DeltaBus subscription pattern (lines 106-117)
- system_coordinator.py - Singleton initialization (lines 1144-1172)
- l1_input/intent_router.py - Mailbox routing
"""

import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure PoC package is importable
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configure structlog (match run_e2e_paths.py configuration)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)
logger = structlog.get_logger(__name__)

# ========================================================================
# FastAPI App
# ========================================================================

app = FastAPI(
    title="K1 Intelligence API",
    description="Real-time WebSocket streaming chat powered by K1 Intelligence Module",
    version="1.0.0",
)

# CORS middleware for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================================================================
# Global State (Singletons from SystemCoordinator)
# ========================================================================

coordinator = None
deltabus = None
mailbox_manager = None

# ========================================================================
# Pydantic Models
# ========================================================================


class ChatRequest(BaseModel):
    """REST API chat request"""

    message: str
    user_id: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """REST API chat response"""

    message: str
    trace_id: str
    session_id: str
    envelope_id: Optional[str]
    latency_ms: float
    metadata: dict


class HealthResponse(BaseModel):
    """System health status"""

    status: str
    components: dict
    uptime_seconds: float


# ========================================================================
# Startup & Shutdown (SystemCoordinator Integration)
# ========================================================================


@app.on_event("startup")
async def startup():
    """
    Initialize K1 system on FastAPI startup.

    Pattern: Reuses system_coordinator.py lines 1144-1172
    - 7-Phase initialization (config, runtime, mocks, agents, services, orchestration, health)
    - Singleton components retained for all connections
    - DeltaBus and MailboxManager available globally
    """
    global coordinator, deltabus, mailbox_manager

    logger.info("=" * 70)
    logger.info("🚀 K1 Intelligence API - Starting...")
    logger.info("=" * 70)

    try:
        # Import here to avoid circular dependencies
        from system_coordinator import get_system_coordinator

        # Initialize SystemCoordinator (singleton)
        coordinator = get_system_coordinator()
        success = await coordinator.initialize_system()

        if not success:
            logger.error("❌ System initialization failed")
            raise RuntimeError("Failed to initialize K1 system")

        # Get shared singletons (from run_e2e_paths.py pattern line 195-199)
        deltabus = coordinator.get_deltabus()
        mailbox_manager = coordinator.get_mailbox_manager()

        logger.info("✅ K1 Intelligence API ready!")
        logger.info(f"   - DeltaBus: {deltabus}")
        logger.info(f"   - MailboxManager: {mailbox_manager}")
        logger.info(f"   - Concierge: {coordinator.get_concierge_agent()}")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}", exc_info=True)
        raise


@app.on_event("shutdown")
async def shutdown():
    """
    Graceful shutdown on FastAPI shutdown.

    Pattern: Reuses system_coordinator.py shutdown_system() (lines 1209+)
    - Drains agents
    - Flushes writers
    - Stops services
    - Closes connections
    """
    global coordinator

    logger.info("=" * 70)
    logger.info("🛑 K1 Intelligence API - Shutting down...")
    logger.info("=" * 70)

    if coordinator:
        try:
            await coordinator.shutdown_system()
            logger.info("✅ Shutdown complete")
        except Exception as e:
            logger.error(f"❌ Shutdown error: {e}", exc_info=True)


# ========================================================================
# WebSocket Endpoint (Real-Time Streaming)
# ========================================================================


@app.websocket("/ws/chat/{user_id}")
async def websocket_chat(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for real-time streaming chat.

    Pattern: Combines patterns from:
    - run_e2e_paths.py lines 106-117 (DeltaBus subscription)
    - run_e2e_paths.py lines 154-170 (IntentRouter mailbox flow)

    Protocol:
    1. Client connects: {"type": "connect", "user_id": "..."}
    2. Client sends: {"type": "message", "text": "..."}
    3. Server streams:
       - {"type": "processing", "agent": "concierge", "status": "thinking"}
       - {"type": "agent_event", "event": "agent.task_received", ...}
       - {"type": "response", "content": "...", "final": true}
       - {"type": "delta", "delta_type": "episodic", ...}
    4. Client can send multiple messages (multi-turn)
    5. Client disconnects

    Args:
        websocket: WebSocket connection
        user_id: User identifier (from URL path)
    """
    await websocket.accept()
    logger.info(f"[WebSocket] Client connected: user_id={user_id}")

    # Import here to avoid startup issues
    from l1_input.intent_router import IntentRouter
    from l4_runtime.session_state.session_state_manager import SessionStateManager

    # Create session manager for this connection (per-connection instance)
    ssm = SessionStateManager(deltabus=deltabus)
    router = IntentRouter(session_manager=ssm, deltabus=deltabus, mailbox_manager=mailbox_manager)

    # Track session and subscriptions
    session_id = None
    subscription_ids = []

    # DeltaBus event handler (pattern from run_e2e_paths.py lines 109-116)
    async def stream_event_to_websocket(event):
        """Stream DeltaBus events to WebSocket client"""
        try:
            event_type = getattr(event, "event_type", "unknown")
            event_session = getattr(event, "session_id", None)
            event_trace = getattr(event, "trace_id", None)
            event_payload = getattr(event, "payload", {})

            # Filter by session (only stream events for this user's session)
            if session_id and event_session != session_id:
                return

            # Format event for WebSocket client
            ws_event = {
                "type": "event",
                "event_type": event_type,
                "session_id": event_session,
                "trace_id": event_trace,
                "payload": event_payload,
                "timestamp": time.time(),
            }

            # Send specific event types with custom formatting
            if event_type.startswith("agent.task_received"):
                ws_event["type"] = "processing"
                ws_event["agent"] = event_payload.get("agent_type", "unknown")
                ws_event["status"] = "thinking"

            elif event_type.startswith("response."):
                ws_event["type"] = "response"
                ws_event["content"] = event_payload.get("message", "")
                ws_event["final"] = True
                ws_event["metadata"] = event_payload.get("metadata", {})

            elif event_type.startswith("session.delta"):
                ws_event["type"] = "delta"
                ws_event["delta_type"] = event_payload.get("delta_type", "unknown")

            elif event_type == "tool.called":
                ws_event["type"] = "tool_call"
                ws_event["tool"] = event_payload.get("tool_name", "unknown")

            elif event_type.startswith("agent.task_completed"):
                ws_event["type"] = "completed"
                ws_event["agent"] = event_payload.get("agent_id", "unknown")
                ws_event["latency_ms"] = event_payload.get("latency_ms", 0)

            # Send to WebSocket
            await websocket.send_json(ws_event)

        except Exception as e:
            logger.error(f"[WebSocket] Error streaming event: {e}")

    # Subscribe to DeltaBus events (pattern from run_e2e_paths.py lines 110-116)
    try:
        sub_response = deltabus.subscribe("response.*", stream_event_to_websocket)
        sub_session = deltabus.subscribe("session.*", stream_event_to_websocket)
        sub_agent = deltabus.subscribe("agent.*", stream_event_to_websocket)
        sub_tool = deltabus.subscribe("tool.called", stream_event_to_websocket)

        subscription_ids = [sub_response, sub_session, sub_agent, sub_tool]
        logger.info(f"[WebSocket] Subscribed to DeltaBus: {subscription_ids}")

        # Send connection confirmation
        await websocket.send_json(
            {
                "type": "connected",
                "user_id": user_id,
                "message": "Connected to K1 Intelligence Module",
                "capabilities": ["streaming", "multi_turn", "memory"],
            }
        )

        # Message loop (multi-turn support)
        turn_count = 0
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_json()
                msg_type = data.get("type", "message")

                if msg_type == "message":
                    turn_count += 1
                    text = data.get("text", "")
                    logger.info(f"[WebSocket] Turn {turn_count}: {text[:100]}")

                    # Send acknowledgment
                    await websocket.send_json(
                        {
                            "type": "ack",
                            "turn": turn_count,
                            "message": "Processing your request...",
                        }
                    )

                    # Route message through IntentRouter (pattern from run_e2e_paths.py line 167)
                    reply, meta = await router.route_user_input(
                        user_input=text, user_id=user_id, session_id=session_id
                    )

                    # Update session ID (from first response)
                    if not session_id:
                        session_id = meta.get("session_id")
                        logger.info(f"[WebSocket] Session created: {session_id}")

                    # Send final response (in case DeltaBus event was missed)
                    await websocket.send_json(
                        {
                            "type": "response_final",
                            "content": reply,
                            "trace_id": meta.get("trace_id"),
                            "envelope_id": meta.get("envelope_id"),
                            "latency_ms": meta.get("latency_ms", 0),
                            "turn": turn_count,
                        }
                    )

                elif msg_type == "ping":
                    # Heartbeat support
                    await websocket.send_json({"type": "pong"})

                else:
                    logger.warning(f"[WebSocket] Unknown message type: {msg_type}")

            except WebSocketDisconnect:
                logger.info(f"[WebSocket] Client disconnected: user_id={user_id}")
                break

            except json.JSONDecodeError as e:
                logger.error(f"[WebSocket] Invalid JSON: {e}")
                await websocket.send_json({"type": "error", "message": "Invalid JSON format"})

            except Exception as e:
                logger.error(f"[WebSocket] Error processing message: {e}", exc_info=True)
                await websocket.send_json({"type": "error", "message": f"Error: {str(e)}"})

    finally:
        # Cleanup: Unsubscribe from DeltaBus (pattern from run_e2e_paths.py line 122)
        for sub_id in subscription_ids:
            try:
                deltabus.unsubscribe(sub_id)
            except Exception as e:
                logger.error(f"[WebSocket] Error unsubscribing: {e}")

        logger.info(f"[WebSocket] Connection closed: user_id={user_id}, turns={turn_count}")


# ========================================================================
# REST Endpoints (Non-Streaming Fallback)
# ========================================================================


@app.post("/chat", response_model=ChatResponse)
async def chat_rest(request: ChatRequest):
    """
    REST API endpoint for non-streaming chat.

    Fallback for clients that don't support WebSocket.
    Uses same IntentRouter mailbox flow as WebSocket.

    Args:
        request: ChatRequest with message and user_id

    Returns:
        ChatResponse with message, trace_id, metadata
    """
    if not coordinator or not coordinator.system_ready:
        raise HTTPException(status_code=503, detail="System not ready")

    try:
        # Import here to avoid startup issues
        from l1_input.intent_router import IntentRouter
        from l4_runtime.session_state.session_state_manager import SessionStateManager

        # Create session manager (per-request instance)
        ssm = SessionStateManager(deltabus=deltabus)
        router = IntentRouter(
            session_manager=ssm, deltabus=deltabus, mailbox_manager=mailbox_manager
        )

        # Route message (same pattern as WebSocket)
        reply, meta = await router.route_user_input(
            user_input=request.message,
            user_id=request.user_id,
            session_id=request.session_id,
        )

        return ChatResponse(
            message=reply,
            trace_id=meta.get("trace_id", ""),
            session_id=meta.get("session_id", ""),
            envelope_id=meta.get("envelope_id"),
            latency_ms=meta.get("latency_ms", 0.0),
            metadata=meta,
        )

    except Exception as e:
        logger.error(f"[REST] Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


@app.get("/health", response_model=HealthResponse)
async def health():
    """
    System health check endpoint.

    Returns:
        HealthResponse with status and component health
    """
    if not coordinator:
        raise HTTPException(status_code=503, detail="System not initialized")

    try:
        # Get health status from integration dashboard
        from monitoring.integration_dashboard import get_integration_dashboard

        dashboard = get_integration_dashboard()
        health_data = await dashboard.get_system_health()

        # Calculate uptime
        uptime = 0.0
        if hasattr(coordinator, "startup_times") and coordinator.startup_times:
            startup_total = sum(coordinator.startup_times.values())
            uptime = time.time() - startup_total

        return HealthResponse(
            status=health_data.get("overall_status", "unknown"),
            components=health_data.get("components", {}),
            uptime_seconds=uptime,
        )

    except Exception as e:
        logger.error(f"[Health] Error: {e}", exc_info=True)
        return HealthResponse(status="error", components={"error": str(e)}, uptime_seconds=0.0)


@app.get("/")
async def root():
    """Root endpoint - API info"""
    return {
        "name": "K1 Intelligence API",
        "version": "1.0.0",
        "endpoints": {
            "websocket": "/ws/chat/{user_id}",
            "rest": "/chat",
            "health": "/health",
            "docs": "/docs",
        },
        "status": "ready" if coordinator and coordinator.system_ready else "initializing",
    }


# ========================================================================
# Main Entry Point (for uvicorn)
# ========================================================================

if __name__ == "__main__":
    import uvicorn

    # Run with uvicorn
    # Note: Use --workers 1 to preserve SystemCoordinator singleton
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # Disable reload to preserve singletons
        log_level="info",
    )
