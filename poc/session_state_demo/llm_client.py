"""
Simple Google AI Client for Session State Demo
================================================

A minimal wrapper around google-generativeai that doesn't depend
on the chat_experience_poc config structure.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

try:
    import google.generativeai as genai
    from google.generativeai.protos import FunctionCallingConfig, ToolConfig
    from google.generativeai.types import HarmBlockThreshold, HarmCategory

    GOOGLE_AI_AVAILABLE = True
except ImportError:
    GOOGLE_AI_AVAILABLE = False


class SimpleLLMClient:
    """
    Simple async wrapper for Google AI with tool calling support.

    Usage:
        client = SimpleLLMClient(api_key="...")
        response = await client.complete_with_tools(
            system_prompt="You are helpful.",
            messages=[{"role": "user", "content": "Hello"}],
            tools=[...],
        )
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-pro-preview-05-06",
    ):
        """
        Initialize client.

        Args:
            api_key: Google AI API key
            model: Model name to use
        """
        if not GOOGLE_AI_AVAILABLE:
            raise ImportError(
                "google-generativeai package not installed. " "Run: pip install google-generativeai"
            )

        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("API key required")

        genai.configure(api_key=self.api_key)
        self.model_name = model
        self._model = genai.GenerativeModel(model)

    async def complete_with_tools(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Get LLM completion with tool calling support.

        Args:
            system_prompt: System prompt
            messages: Conversation history
            tools: Tool definitions

        Returns:
            Dict with 'content' and/or 'tool_calls'
        """
        # Convert messages to Google format
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                continue  # Handle separately
            elif role == "assistant":
                contents.append({"role": "model", "parts": [content]})
            else:
                contents.append({"role": "user", "parts": [content]})

        # Convert tools to Google format - consolidate all function declarations
        function_declarations = []
        for tool in tools:
            function_declarations.append(
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                }
            )

        # Single tool object with all functions
        google_tools = (
            [{"function_declarations": function_declarations}] if function_declarations else None
        )

        # Configure function calling mode to AUTO (allows text OR function calls)
        tool_config = (
            ToolConfig(
                function_calling_config=FunctionCallingConfig(mode=FunctionCallingConfig.Mode.AUTO)
            )
            if google_tools
            else None
        )

        # Create model with system instruction
        model = genai.GenerativeModel(
            self.model_name,
            system_instruction=system_prompt,
        )

        try:
            response = model.generate_content(
                contents,
                tools=google_tools,
                tool_config=tool_config,
                safety_settings=[
                    {
                        "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
                        "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    },
                    {
                        "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                        "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    },
                ],
            )

            # Parse response
            result: Dict[str, Any] = {"content": "", "tool_calls": []}

            if response.candidates:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, "text"):
                            result["content"] += part.text
                        if hasattr(part, "function_call") and part.function_call:
                            fc = part.function_call
                            result["tool_calls"].append(
                                {
                                    "name": fc.name,
                                    "args": dict(fc.args) if fc.args else {},
                                }
                            )

            return result

        except Exception as e:
            return {"content": f"Error: {e}", "tool_calls": []}

    async def complete(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
    ) -> str:
        """Simple completion without tools."""
        result = await self.complete_with_tools(system_prompt, messages, [])
        return result.get("content", "")
