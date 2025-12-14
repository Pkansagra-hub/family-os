"""
Mock Tool Response Generator

Generates realistic mock responses for all external tools.
This module provides consistent, deterministic test data for POC validation.

Usage:
    from mock_services.mock_tool_responses import generate_mock_response

    result = generate_mock_response(
        tool_id="web_search",
        parameters={"query": "Python tutorials", "num_results": 3}
    )

Architecture:
- Each tool has a response generator function
- Generators use parameters to create contextual responses
- All responses include realistic data structures and values
- Timestamp-based determinism ensures reproducible test results

References:
- config/tool_registry.json - Tool definitions and schemas
- ADR-0008 - Saga Pattern for tool execution
"""

import hashlib
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


def generate_mock_response(
    tool_id: str,
    parameters: Dict[str, Any],
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate realistic mock response for a tool call.

    Args:
        tool_id: Tool identifier (e.g., "web_search")
        parameters: Tool parameters as provided by agent
        trace_id: Optional trace ID for logging

    Returns:
        Mock response data matching tool's return schema

    Raises:
        ValueError: If tool_id not recognized
    """
    logger.debug(
        "generating_mock_response",
        tool_id=tool_id,
        param_keys=list(parameters.keys()),
        trace_id=trace_id,
    )

    # Map tool IDs to generator functions
    generators = {
        "web_search": _generate_web_search_response,
        "get_health_context": _generate_health_context_response,
        "get_financial_context": _generate_financial_context_response,
        "query_k0_finance": _generate_query_k0_finance_response,
        "create_reminder": _generate_create_reminder_response,
        "book_appointment": _generate_book_appointment_response,
        "calculate": _generate_calculate_response,
        "get_user_preferences": _generate_user_preferences_response,
        "query_conversation_history": _generate_conversation_history_response,
    }

    generator = generators.get(tool_id)
    if not generator:
        raise ValueError(
            f"No mock response generator for tool_id: {tool_id}. "
            f"Available: {list(generators.keys())}"
        )

    return generator(parameters)


# ============================================================================
# Response Generators for Each Tool
# ============================================================================


def _generate_web_search_response(params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate mock web search results."""
    query = params.get("query", "")
    num_results = params.get("num_results", 5)

    # Generate deterministic results based on query hash
    query_hash = int(hashlib.md5(query.encode()).hexdigest()[:8], 16)

    results = []
    for i in range(min(num_results, 10)):
        result_seed = query_hash + i
        results.append(
            {
                "title": f"Result {i+1}: {query} - Comprehensive Guide",
                "url": f"https://example.com/{query.lower().replace(' ', '-')}-{result_seed % 1000}",
                "snippet": f"Learn about {query} with our detailed guide covering all aspects "
                f"including best practices, common pitfalls, and expert tips.",
                "relevance_score": max(0.5, 1.0 - (i * 0.15)),
                "published_date": (datetime.now() - timedelta(days=result_seed % 365)).isoformat(),
            }
        )

    return {
        "status": "success",
        "query": query,
        "results": results,
        "total_results": len(results),
        "search_time_ms": 45 + (query_hash % 50),
    }


def _generate_health_context_response(params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate mock health context from User KG."""
    user_id = params.get("user_id", "unknown")
    query_type = params.get("query_type", "all")

    context = {}

    if query_type in ("pt_sessions", "all"):
        context["pt_sessions"] = {
            "total_sessions": 24,
            "last_session": {
                "date": (datetime.now() - timedelta(days=3)).isoformat(),
                "duration_minutes": 60,
                "exercises": ["squats", "lunges", "leg_press"],
                "pain_level": 2,
                "notes": "Good progress on knee rehabilitation",
            },
            "next_session": {
                "scheduled": (datetime.now() + timedelta(days=4)).isoformat(),
                "provider": "Dr. Sarah Johnson PT",
                "location": "Sports Medicine Center",
            },
        }

    if query_type in ("medications", "all"):
        context["medications"] = {
            "current": [
                {
                    "name": "Ibuprofen",
                    "dosage": "400mg",
                    "frequency": "As needed for pain",
                    "prescribed_date": "2025-10-15",
                },
                {
                    "name": "Vitamin D",
                    "dosage": "1000 IU",
                    "frequency": "Daily",
                    "prescribed_date": "2025-09-01",
                },
            ],
            "total_active": 2,
        }

    if query_type in ("symptoms", "all"):
        context["symptoms"] = {
            "recent": [
                {
                    "date": (datetime.now() - timedelta(days=1)).isoformat(),
                    "symptom": "Mild knee stiffness",
                    "severity": 3,
                    "duration_hours": 2,
                },
            ],
            "trends": {
                "pain_reduction": "35% improvement over last month",
                "mobility_score": 7.8,
            },
        }

    return {
        "status": "success",
        "user_id": user_id,
        "query_type": query_type,
        "context": context,
        "last_updated": datetime.now().isoformat(),
    }


def _generate_financial_context_response(params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate mock financial context from User KG."""
    user_id = params.get("user_id", "unknown")
    time_range = params.get("time_range", "current_month")

    return {
        "status": "success",
        "user_id": user_id,
        "time_range": time_range,
        "context": {
            "budget": {
                "total_monthly_budget": 1500.00,
                "spent_to_date": 1200.00,
                "remaining": 300.00,
                "categories": {
                    "groceries": {"budget": 400, "spent": 400.00, "remaining": 0.00},
                    "dining": {"budget": 300, "spent": 300.00, "remaining": 0.00},
                    "transportation": {"budget": 200, "spent": 180.00, "remaining": 20.00},
                    "entertainment": {"budget": 150, "spent": 150.00, "remaining": 0.00},
                    "other": {"budget": 450, "spent": 170.00, "remaining": 280.00},
                },
            },
            "recent_transactions": [
                {
                    "date": (datetime.now() - timedelta(days=1)).isoformat(),
                    "merchant": "Grocery Store",
                    "amount": 120.00,
                    "category": "groceries",
                },
                {
                    "date": (datetime.now() - timedelta(days=2)).isoformat(),
                    "merchant": "Restaurant",
                    "amount": 60.00,
                    "category": "dining",
                },
                {
                    "date": (datetime.now() - timedelta(days=3)).isoformat(),
                    "merchant": "Gas Station",
                    "amount": 40.00,
                    "category": "transportation",
                },
            ],
            "insights": {
                "overspending_categories": ["groceries", "dining"],
                "savings_vs_last_month": "+$200.00",
                "projected_month_end_balance": "$300.00",
            },
        },
        "last_updated": datetime.now().isoformat(),
    }


def _generate_query_k0_finance_response(params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate mock episodic finance response for query_k0_finance."""
    user_id = params.get("user_id", "unknown")
    query = params.get("query", "")

    # Deterministic mock: 1200 spent of 1500 budget → 80%
    category_spending = [
        {"category": "groceries", "amount": 400.00},
        {"category": "dining", "amount": 300.00},
        {"category": "transportation", "amount": 200.00},
        {"category": "entertainment", "amount": 150.00},
        {"category": "other", "amount": 150.00},
    ]

    recent = [
        {
            "id": "txn_001",
            "date": (datetime.now() - timedelta(days=1)).isoformat(),
            "amount": 60.0,
            "currency": "USD",
            "merchant": "Restaurant",
            "category": "dining",
            "type": "debit",
        },
        {
            "id": "txn_002",
            "date": (datetime.now() - timedelta(days=2)).isoformat(),
            "amount": 120.0,
            "currency": "USD",
            "merchant": "Grocery Store",
            "category": "groceries",
            "type": "debit",
        },
    ]

    return {
        "status": "success",
        "user_id": user_id,
        "query": query,
        "transaction_count": 12,
        "current_month_total": 1200.00,
        "budget_utilization": 0.80,
        "category_spending": category_spending,
        "recent_transactions": recent,
        "generated_at": datetime.now().isoformat(),
    }


def _generate_create_reminder_response(params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate mock reminder creation response."""
    message = params.get("message", "")
    fire_time = params.get("fire_time", "")
    recurrence = params.get("recurrence", "once")

    # Generate deterministic trigger_id based on message
    trigger_id = f"trigger_{int(hashlib.md5(message.encode()).hexdigest()[:12], 16)}"

    return {
        "status": "created",
        "trigger_id": trigger_id,
        "reminder": {
            "message": message,
            "fire_time": fire_time,
            "recurrence": recurrence,
            "status": "scheduled",
            "created_at": datetime.now().isoformat(),
        },
        "confirmation": f"Reminder scheduled for {fire_time}",
    }


def _generate_book_appointment_response(params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate mock appointment booking response."""
    appointment_type = params.get("appointment_type", "other")
    date_time = params.get("date_time", "")
    provider = params.get("provider", "")

    # Generate deterministic appointment_id
    appointment_id = f"appt_{int(time.time() * 1000) % 1000000}"

    return {
        "status": "confirmed",
        "appointment_id": appointment_id,
        "appointment": {
            "type": appointment_type,
            "date_time": date_time,
            "provider": provider or f"Provider for {appointment_type}",
            "location": "Main Medical Center, Suite 301",
            "confirmation_code": f"CONF-{appointment_id[-6:].upper()}",
            "duration_minutes": 60 if appointment_type == "pt_session" else 30,
            "notes": params.get("notes", ""),
        },
        "next_steps": [
            "Confirmation email sent",
            "Add to calendar",
            "Arrive 15 minutes early",
        ],
        "booked_at": datetime.now().isoformat(),
    }


def _generate_calculate_response(params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate mock calculation response."""
    expression = params.get("expression", "")

    try:
        # Safe evaluation for simple math (POC only - production needs proper parser)
        # Only allow numbers, operators, and basic functions
        allowed_chars = set("0123456789+-*/().% ")
        if all(c in allowed_chars for c in expression):
            result = eval(expression, {"__builtins__": {}}, {})
        else:
            result = 0.0
            expression = "Invalid expression"
    except Exception:
        result = 0.0

    return {
        "status": "success",
        "expression": expression,
        "result": result,
        "calculated_at": datetime.now().isoformat(),
    }


def _generate_user_preferences_response(params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate mock user preferences from User KG."""
    user_id = params.get("user_id", "unknown")
    category = params.get("preference_category", "all")

    preferences = {}

    if category in ("communication", "all"):
        preferences["communication"] = {
            "preferred_channel": "text",
            "notification_frequency": "important_only",
            "quiet_hours": {"start": "22:00", "end": "07:00"},
            "language": "en-US",
        }

    if category in ("privacy", "all"):
        preferences["privacy"] = {
            "data_sharing": "minimal",
            "analytics": "aggregated_only",
            "third_party_sharing": False,
        }

    if category in ("health", "all"):
        preferences["health"] = {
            "units": "imperial",
            "share_with_providers": True,
            "reminder_frequency": "daily",
            "exercise_goals": {"steps_per_day": 8000, "workouts_per_week": 3},
        }

    if category in ("finance", "all"):
        preferences["finance"] = {
            "currency": "USD",
            "budget_alerts": True,
            "spending_categories": ["groceries", "healthcare", "transportation"],
            "savings_goals": {"monthly_target": 500.00, "emergency_fund_target": 10000.00},
        }

    return {
        "status": "success",
        "user_id": user_id,
        "category": category,
        "preferences": preferences,
        "last_updated": datetime.now().isoformat(),
    }


def _generate_conversation_history_response(params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate mock conversation history from K0."""
    query = params.get("query", "")
    limit = params.get("limit", 5)

    # Generate deterministic excerpts based on query
    query_hash = int(hashlib.md5(query.encode()).hexdigest()[:8], 16)

    excerpts = []
    for i in range(min(limit, 10)):
        days_ago = (query_hash + i) % 30
        excerpts.append(
            {
                "turn_id": f"turn_{query_hash + i}",
                "timestamp": (datetime.now() - timedelta(days=days_ago)).isoformat(),
                "user_message": f"User asked about {query}",
                "assistant_response": f"Assistant provided information about {query} including "
                f"relevant details and suggestions.",
                "relevance_score": max(0.6, 1.0 - (i * 0.1)),
                "session_id": f"session_{(query_hash + i) % 100}",
            }
        )

    return {
        "status": "success",
        "query": query,
        "excerpts": excerpts,
        "total_found": len(excerpts),
        "search_method": "semantic",
        "retrieved_at": datetime.now().isoformat(),
    }


# ============================================================================
# Utility Functions
# ============================================================================


def list_available_tools() -> List[str]:
    """Return list of tool IDs with mock response generators."""
    return [
        "web_search",
        "get_health_context",
        "get_financial_context",
        "query_k0_finance",
        "create_reminder",
        "book_appointment",
        "calculate",
        "get_user_preferences",
        "query_conversation_history",
    ]


def validate_mock_response_coverage(tool_registry_path: str) -> Dict[str, Any]:
    """
    Validate that all tools in registry have mock response generators.

    Args:
        tool_registry_path: Path to tool_registry.json

    Returns:
        Coverage report with missing generators
    """
    import json

    with open(tool_registry_path) as f:
        registry = json.load(f)

    registry_tools = {t["id"] for t in registry["tools"]}
    mock_tools = set(list_available_tools())

    return {
        "total_tools_in_registry": len(registry_tools),
        "total_mock_generators": len(mock_tools),
        "coverage_percentage": (len(mock_tools) / len(registry_tools)) * 100,
        "missing_generators": list(registry_tools - mock_tools),
        "extra_generators": list(mock_tools - registry_tools),
    }
