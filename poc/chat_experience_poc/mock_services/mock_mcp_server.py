"""
Mock MCP Server for External Tools

Validates EXTERNAL tool call request formats (web_search, calendar_add, email_send, etc.)
This is NOT for K0 communication - K0 queries use K0 Bridge ports (P01/P02), not MCP.

Endpoints:
- POST /tools/{tool_id} - Validate tool request
- GET /health - Health check
- GET /tools - List all registered tools

The server validates request format against tool schema and returns:
- {"status": "accepted", "tool": "<tool_name>"} for valid requests
- {"status": "error", "reason": "..."} for invalid requests

References:
- docs/whiteboard/chat_experience.md - Tool call flow (EXTERNAL tools only)
- MCP Protocol: https://modelcontextprotocol.io/
- FastAPI: https://fastapi.tiangolo.com
"""

import uuid
from datetime import datetime
from typing import Any, Dict

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from l5_infrastructure.registries.tool_registry import get_tool_registry
from l5_infrastructure.user_kg import get_user_kg
from mock_services.mock_tool_responses import generate_mock_response
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Mock MCP Server",
    description="Validates external tool requests (NOT K0 communication)",
    version="1.0.0",
)

# Get tool registry
tool_registry = get_tool_registry()

# Call statistics for test assertions
call_stats = {
    "total_calls": 0,
    "successful_calls": 0,
    "validation_errors": 0,
    "not_found_errors": 0,
}


class ToolRequest(BaseModel):
    """Generic tool request."""

    parameters: Dict[str, Any]


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "mock-mcp-server",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/tools")
async def list_tools():
    """List all registered tools."""
    tools = tool_registry.list_all_tools()
    return {
        "tools": [
            {
                "tool_id": t.tool_id,
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "required_fields": t.required_fields,
            }
            for t in tools
        ],
        "total_tools": len(tools),
    }


@app.post("/tools/{tool_id}")
async def validate_tool_request(tool_id: str, request: ToolRequest):
    """
    Validate tool request against registered tool schema.

    Args:
        tool_id: Tool identifier
        request: Request body with parameters

    Returns:
        {
            "status": "success" | "error",
            "request_id": "<uuid>",  # For request tracing
            "receipt_id": "<uuid>",  # For successful calls only
            "tool": "<name>",
            "reason": "<error message>"  # For errors only
        }
    """
    # Generate request_id for tracing
    request_id = str(uuid.uuid4())
    call_stats["total_calls"] += 1

    logger.info(
        "tool_request_received",
        tool_id=tool_id,
        request_id=request_id,
        param_keys=list(request.parameters.keys()),
    )

    # Check if tool exists
    tool = tool_registry.get_tool(tool_id)
    if not tool:
        call_stats["not_found_errors"] += 1
        logger.warning("tool_not_found", tool_id=tool_id, request_id=request_id)
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "request_id": request_id,
                "reason": f"Tool not found: {tool_id}",
                "available_tools": [t.tool_id for t in tool_registry.list_all_tools()],
            },
        )

    # Validate request against tool schema
    is_valid, error_message = tool_registry.validate_tool_request(
        tool_id,
        request.parameters,
    )

    if is_valid:
        # Generate receipt_id for successful call
        receipt_id = str(uuid.uuid4())
        call_stats["successful_calls"] += 1

        logger.info(
            "tool_request_valid",
            tool_id=tool_id,
            tool_name=tool.name,
            request_id=request_id,
            receipt_id=receipt_id,
        )

        # If this is a k0 UserKG tool, return real data from UserKG
        if tool_id in {"get_health_context", "get_financial_context", "get_user_preferences"}:
            try:
                kg = get_user_kg()
                params = request.parameters or {}
                user_id = params.get("user_id") or "user_001"

                if tool_id == "get_health_context":
                    days_val = params.get("days")
                    try:
                        days = int(days_val) if days_val is not None else 30
                    except Exception:
                        days = 30
                    data = kg.get_health_context(user_id, days=days)
                elif tool_id == "get_financial_context":
                    # POC mapping: preferences in 'finance' category as financial context
                    data = {
                        "preferences_finance": kg.get_preferences(user_id, category="finance"),
                        "goals": kg.get_active_goals(user_id),
                    }
                else:  # get_user_preferences
                    category = params.get("preference_category")
                    if category and category != "all":
                        data = kg.get_preferences(user_id, category=category)
                    else:
                        data = kg.get_preferences(user_id, category=None)

                return {
                    "status": "success",
                    "request_id": request_id,
                    "receipt_id": receipt_id,
                    "tool": tool.name,
                    "tool_id": tool_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "result": {"data": data},
                }
            except Exception as e:
                call_stats["validation_errors"] += 1
                logger.error(
                    "userkg_adapter_failed", tool_id=tool_id, request_id=request_id, error=str(e)
                )
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "request_id": request_id,
                        "tool_id": tool_id,
                        "reason": f"UserKG adapter error: {str(e)}",
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

        # Default: Generate mock response data
        try:
            mock_data = generate_mock_response(
                tool_id=tool_id,
                parameters=request.parameters,
                trace_id=request.parameters.get("trace_id"),
            )
            logger.debug(
                "mock_response_generated",
                tool_id=tool_id,
                request_id=request_id,
                response_keys=list(mock_data.keys()),
            )
        except Exception as e:
            logger.error(
                "mock_response_generation_failed",
                tool_id=tool_id,
                request_id=request_id,
                error=str(e),
            )
            mock_data = {"status": "error", "message": f"Mock generation failed: {str(e)}"}

        return {
            "status": "success",
            "request_id": request_id,
            "receipt_id": receipt_id,
            "tool": tool.name,
            "tool_id": tool_id,
            "timestamp": datetime.utcnow().isoformat(),
            "result": mock_data,  # Include mock response data
        }
    else:
        call_stats["validation_errors"] += 1
        logger.warning(
            "tool_request_invalid",
            tool_id=tool_id,
            request_id=request_id,
            error=error_message,
        )
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "request_id": request_id,
                "tool_id": tool_id,
                "reason": error_message,
                "required_fields": tool.required_fields,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@app.post("/tools/{tool_id}/web_search")
async def web_search(tool_id: str, request: ToolRequest):
    """Endpoint for web_search tool."""
    return await validate_tool_request(tool_id, request)


@app.post("/tools/{tool_id}/calendar_add")
async def calendar_add(tool_id: str, request: ToolRequest):
    """Endpoint for calendar_add tool."""
    return await validate_tool_request(tool_id, request)


@app.post("/tools/{tool_id}/email_send")
async def email_send(tool_id: str, request: ToolRequest):
    """Endpoint for email_send tool."""
    return await validate_tool_request(tool_id, request)


@app.post("/tools/{tool_id}/reminder_set")
async def reminder_set(tool_id: str, request: ToolRequest):
    """Endpoint for reminder_set tool."""
    return await validate_tool_request(tool_id, request)


@app.post("/tools/{tool_id}/sms_send")
async def sms_send(tool_id: str, request: ToolRequest):
    """Endpoint for sms_send tool."""
    return await validate_tool_request(tool_id, request)


@app.post("/tools/{tool_id}/weather_get")
async def weather_get(tool_id: str, request: ToolRequest):
    """Endpoint for weather_get tool."""
    return await validate_tool_request(tool_id, request)


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """Custom Swagger UI documentation."""
    return JSONResponse(
        content={
            "message": "Mock MCP Server - External Tool Validation",
            "endpoints": {
                "health": "GET /health",
                "list_tools": "GET /tools",
                "validate_tool": "POST /tools/{tool_id}",
                "stats": "GET /stats",
            },
            "note": "This server validates EXTERNAL tools only (web_search, calendar_add, email_send, etc.)",
            "k0_note": "K0 queries use K0 Bridge (port 5201), NOT MCP",
        }
    )


@app.get("/stats")
async def get_stats():
    """
    Get call statistics for test assertions

    Returns call counts, success rate, and error breakdown.
    Useful for integration tests to verify expected call patterns.
    """
    success_rate = (
        (call_stats["successful_calls"] / call_stats["total_calls"] * 100)
        if call_stats["total_calls"] > 0
        else 0.0
    )

    return {
        "total_calls": call_stats["total_calls"],
        "successful_calls": call_stats["successful_calls"],
        "validation_errors": call_stats["validation_errors"],
        "not_found_errors": call_stats["not_found_errors"],
        "success_rate_percent": round(success_rate, 2),
        "timestamp": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("starting_mock_mcp_server", port=8001)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info",
    )
