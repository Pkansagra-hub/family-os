"""
LLM Tool Definitions for Session State Demo
=============================================

EPIC: 2 - LLM Tool Definitions
ISSUES: 2.1, 2.2, 2.3, 2.4

Defines tools the LLM can call to update session state:
- update_persona: Learn user preferences
- update_emotion: Track emotional state
- add_belief: Record learned facts

Tools are defined in Google AI / Gemini function calling format.
"""

from typing import Any, Dict, List

# =============================================================================
# TOOL DEFINITIONS (Google AI Format)
# =============================================================================


SESSIONSTATE_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "update_persona",
        "description": (
            "Record user preferences, interests, or personal information you've learned. "
            "Use this when the user shares information about themselves that should be "
            "remembered for future conversations. Examples: travel interests, family size, "
            "dietary restrictions, hobbies, communication preferences."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "preference_name": {
                    "type": "string",
                    "description": "Name of the preference (e.g., 'travel_interest', 'family_size', 'diet')",
                },
                "preference_value": {
                    "type": "string",
                    "description": "Value of the preference (e.g., 'Japan', '4', 'vegetarian')",
                },
                "context": {
                    "type": "string",
                    "description": "Optional context about when/why this preference applies",
                },
            },
            "required": ["preference_name", "preference_value"],
        },
    },
    {
        "name": "update_emotion",
        "description": (
            "Update the emotional context of the conversation. Use this when you detect "
            "a shift in the user's emotional state or when the conversation topic is "
            "emotionally significant. This helps calibrate response tone."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "emotion": {
                    "type": "string",
                    "enum": [
                        "excited",
                        "happy",
                        "neutral",
                        "concerned",
                        "frustrated",
                        "sad",
                        "anxious",
                        "hopeful",
                    ],
                    "description": "The detected emotional state",
                },
                "intensity": {
                    "type": "number",
                    "description": "Intensity of the emotion from 0.0 (mild) to 1.0 (strong)",
                },
                "reason": {
                    "type": "string",
                    "description": "Brief reason for the emotional assessment",
                },
            },
            "required": ["emotion"],
        },
    },
    {
        "name": "add_belief",
        "description": (
            "Record a fact or belief you've learned about the user that should be "
            "remembered. Use this for specific facts rather than preferences. "
            "Examples: 'has two children ages 8 and 12', 'works from home', "
            "'allergic to shellfish'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fact": {
                    "type": "string",
                    "description": "The fact or belief to record",
                },
                "category": {
                    "type": "string",
                    "enum": ["family", "work", "health", "travel", "preferences", "general"],
                    "description": "Category of the fact",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence in this fact from 0.0 to 1.0 (default 0.8)",
                },
            },
            "required": ["fact", "category"],
        },
    },
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_tools() -> List[Dict[str, Any]]:
    """Get all tool definitions for LLM."""
    return SESSIONSTATE_TOOLS


def parse_tool_call(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parse tool calls from LLM response.

    Args:
        response: LLM response dict with potential 'tool_calls' key

    Returns:
        List of {"name": "tool_name", "args": {...}}
    """
    raw_calls = response.get("tool_calls", [])
    if not raw_calls:
        return []

    parsed = []
    for call in raw_calls:
        if isinstance(call, dict):
            parsed.append(
                {
                    "name": call.get("name", ""),
                    "args": call.get("args", {}),
                }
            )
    return parsed


def format_tool_result(name: str, success: bool, message: str) -> Dict[str, Any]:
    """
    Format a tool execution result for LLM context.

    Args:
        name: Tool name
        success: Whether execution succeeded
        message: Result message

    Returns:
        Dict to add to conversation context
    """
    return {
        "role": "tool",
        "name": name,
        "content": f"{'Success' if success else 'Failed'}: {message}",
    }
