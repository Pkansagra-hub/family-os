"""
Simple Google AI Client for Session State Demo
================================================

A minimal wrapper around google-generativeai that doesn't depend
on the chat_experience_poc config structure.

Supports:
  - Single-turn tool calling (complete_with_tools)
  - Multi-turn agentic loops (agentic_loop) -- model calls tools,
    we execute them and feed results back until the model stops calling tools
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, List, Optional

try:
    import google.generativeai as genai
    from google.generativeai.protos import FunctionCallingConfig, ToolConfig
    from google.generativeai.types import HarmBlockThreshold, HarmCategory

    GOOGLE_AI_AVAILABLE = True
except ImportError:
    GOOGLE_AI_AVAILABLE = False


class SimpleLLMClient:

    @staticmethod
    def _deep_proto_to_dict(obj: Any) -> Any:
        """
        Recursively convert protobuf MapComposite/RepeatedComposite to
        plain Python dicts/lists.

        Google's ``dict(fc.args)`` only does a shallow conversion --
        nested structures like ``steps[].params`` remain as
        MapComposite with inaccessible data. This walks the tree
        and converts everything to native types.
        """
        # MapComposite -> dict
        if hasattr(obj, "keys") and hasattr(obj, "values") and not isinstance(obj, dict):
            return {str(k): SimpleLLMClient._deep_proto_to_dict(v) for k, v in obj.items()}
        # RepeatedComposite -> list
        if (
            hasattr(obj, "pb")
            and hasattr(obj, "__iter__")
            and not isinstance(obj, (str, bytes, dict))
        ):
            return [SimpleLLMClient._deep_proto_to_dict(item) for item in obj]
        # Plain list (already converted)
        if isinstance(obj, list):
            return [SimpleLLMClient._deep_proto_to_dict(item) for item in obj]
        # Plain dict (already converted)
        if isinstance(obj, dict):
            return {str(k): SimpleLLMClient._deep_proto_to_dict(v) for k, v in obj.items()}
        return obj

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
        force_tool_call: bool = False,
    ) -> Dict[str, Any]:
        """
        Get LLM completion with tool calling support.

        Args:
            system_prompt: System prompt
            messages: Conversation history
            tools: Tool definitions
            force_tool_call: If True, forces LLM to call a tool (ANY mode)
                             instead of allowing text responses (AUTO mode)

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

        # Configure function calling mode
        # ANY = MUST call a function (no text fallback)
        # AUTO = can choose text OR function call
        if google_tools:
            mode = (
                FunctionCallingConfig.Mode.ANY
                if force_tool_call
                else FunctionCallingConfig.Mode.AUTO
            )
            tool_config = ToolConfig(function_calling_config=FunctionCallingConfig(mode=mode))
        else:
            tool_config = None

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
                                    "args": self._deep_proto_to_dict(fc.args) if fc.args else {},
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

    async def agentic_loop(
        self,
        system_prompt: str,
        user_message: str,
        tools: List[Dict[str, Any]],
        tool_handlers: Dict[str, Callable[..., Any]],
        max_turns: int = 10,
        on_tool_call: Optional[Callable[[str, Dict, Any, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Multi-turn agentic conversation loop.

        The model calls tools, we execute them via tool_handlers,
        send results back, and repeat until the model either:
          - stops calling tools (returns text)
          - calls a terminal tool (like commit_plan)
          - hits max_turns

        This is compositional function calling per Gemini docs:
        model calls discover -> we return results -> model calls commit.

        Args:
            system_prompt: System instruction for the model.
            user_message: Initial user message.
            tools: Tool declarations (list of dicts with name/description/parameters).
            tool_handlers: Map of tool_name -> callable that executes the tool.
                           Each handler receives **args and returns a result dict.
            max_turns: Max conversation turns to prevent runaway loops.
            on_tool_call: Optional callback(tool_name, args, result, turn) for
                          observability -- the runner uses this to display each
                          discovery call in the terminal.

        Returns:
            Dict with:
              - 'terminal_tool': name of the final tool called (e.g. 'commit_plan')
              - 'terminal_args': args of the final tool call
              - 'content': any text the model produced
              - 'tool_calls_log': list of all tool calls made
              - 'turns': number of conversation turns
              - 'total_ms': total wall-clock time
        """
        import google.generativeai as genai
        from google.generativeai import protos

        start = time.monotonic()

        # Build Google-format tool declarations
        function_declarations = []
        for tool in tools:
            function_declarations.append(
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                }
            )

        google_tools = [{"function_declarations": function_declarations}]
        tool_config = ToolConfig(
            function_calling_config=FunctionCallingConfig(mode=FunctionCallingConfig.Mode.ANY)
        )

        model = genai.GenerativeModel(
            self.model_name,
            system_instruction=system_prompt,
        )

        # Build initial contents
        contents = [{"role": "user", "parts": [user_message]}]

        tool_calls_log: List[Dict[str, Any]] = []
        terminal_tool: str | None = None
        terminal_args: Dict[str, Any] = {}
        final_content = ""

        for turn in range(max_turns):
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

            if not response.candidates:
                break

            candidate = response.candidates[0]
            if not candidate.content or not candidate.content.parts:
                break

            # Collect all function calls and text from this turn
            turn_function_calls = []
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    final_content += part.text
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    turn_function_calls.append(
                        {
                            "name": fc.name,
                            "args": self._deep_proto_to_dict(fc.args) if fc.args else {},
                        }
                    )

            if not turn_function_calls:
                # Model produced text only -- conversation done
                break

            # Append the model's response to contents (preserves thought signatures)
            contents.append(candidate.content)

            # Execute each function call and build function response parts
            function_response_parts = []
            for fc_info in turn_function_calls:
                fn_name = fc_info["name"]
                fn_args = fc_info["args"]

                # Check if this is a terminal tool (like commit_plan)
                handler = tool_handlers.get(fn_name)
                if handler is None:
                    # Unknown tool -- treat as terminal
                    terminal_tool = fn_name
                    terminal_args = fn_args
                    tool_calls_log.append(
                        {
                            "turn": turn,
                            "tool": fn_name,
                            "args": fn_args,
                            "result": None,
                            "terminal": True,
                        }
                    )
                    if on_tool_call:
                        on_tool_call(fn_name, fn_args, None, turn)
                    break

                # Execute the handler
                try:
                    result = handler(**fn_args)
                except Exception as exc:
                    result = {"error": str(exc)}

                tool_calls_log.append(
                    {
                        "turn": turn,
                        "tool": fn_name,
                        "args": fn_args,
                        "result": result,
                        "terminal": False,
                    }
                )

                if on_tool_call:
                    on_tool_call(fn_name, fn_args, result, turn)

                # Build function response part for Gemini
                function_response_parts.append(
                    protos.Part(
                        function_response=protos.FunctionResponse(
                            name=fn_name,
                            response={"result": result},
                        )
                    )
                )

            # If we hit a terminal tool, stop the loop
            if terminal_tool:
                break

            # Send function responses back to model
            if function_response_parts:
                contents.append(
                    protos.Content(
                        role="user",
                        parts=function_response_parts,
                    )
                )

        total_ms = int((time.monotonic() - start) * 1000)

        return {
            "terminal_tool": terminal_tool,
            "terminal_args": terminal_args,
            "content": final_content,
            "tool_calls_log": tool_calls_log,
            "turns": min(turn + 1, max_turns) if "turn" in dir() else 0,
            "total_ms": total_ms,
        }
