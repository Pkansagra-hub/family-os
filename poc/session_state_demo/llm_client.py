"""
Simple Google AI Client for Session State Demo
================================================

A minimal wrapper around google-genai (new SDK) that doesn't depend
on the chat_experience_poc config structure.

Supports:
  - Single-turn tool calling (complete_with_tools)
  - Multi-turn agentic loops (agentic_loop) -- model calls tools,
    we execute them and feed results back until the model stops calling tools

SDK: google-genai (new SDK)
  - Client: genai.Client(api_key=...)
  - Call:   client.models.generate_content(model=..., contents=..., config=...)
  - Types:  google.genai.types (Content, Part, Tool, FunctionDeclaration, etc.)
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, List, Optional

try:
    from google import genai
    from google.genai import types

    GOOGLE_AI_AVAILABLE = True
except ImportError:
    GOOGLE_AI_AVAILABLE = False


class SimpleLLMClient:
    """
    Simple async wrapper for Google AI with tool calling support.

    Uses the new google-genai SDK (genai.Client) instead of the old
    google-generativeai (genai.configure + GenerativeModel).

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
        Initialize client with new google-genai SDK.

        Args:
            api_key: Google AI API key
            model: Model name to use
        """
        if not GOOGLE_AI_AVAILABLE:
            raise ImportError(
                "google-genai package not installed. " "Run: pip install google-genai"
            )

        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("API key required")

        self._client = genai.Client(api_key=self.api_key)
        self.model_name = model

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
        # Convert messages to google-genai Content objects
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                continue  # Handle via system_instruction in config
            elif role == "assistant":
                contents.append(
                    types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=content)],
                    )
                )
            else:
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=content)],
                    )
                )

        # Build tool declarations using new SDK types
        func_decls = []
        for tool in tools:
            func_decls.append(
                types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=tool.get("parameters", {"type": "object", "properties": {}}),
                )
            )

        # Build tools list for config
        gemini_tools = [types.Tool(function_declarations=func_decls)] if func_decls else None

        # Configure function calling mode
        # ANY = MUST call a function (no text fallback)
        # AUTO = can choose text OR function call
        tool_config_obj = None
        if gemini_tools and force_tool_call:
            tool_config_obj = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=types.FunctionCallingConfigMode.ANY
                )
            )

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=gemini_tools,
            tool_config=tool_config_obj,
        )

        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )

            # Parse response -- same output contract as before
            result: Dict[str, Any] = {"content": "", "tool_calls": []}

            if response.candidates:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            result["content"] += part.text
                        if (
                            hasattr(part, "function_call")
                            and part.function_call
                            and getattr(part.function_call, "name", None)
                        ):
                            fc = part.function_call
                            # New SDK returns native Python dicts from fc.args
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

    async def generate_stream(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        force_tool_call: bool = False,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Streaming completion with tool calling support.

        Uses ``client.models.generate_content_stream()`` for real-time
        text delivery.  Function-call responses are accumulated across
        chunks -- text deltas are NOT emitted when the response contains
        tool calls (since the text is not a final answer).

        Args:
            system_prompt: System prompt
            messages: Conversation history
            tools: Tool definitions
            force_tool_call: If True, forces LLM to call a tool (ANY mode)
            on_text_delta: Callable[[str], None] called for each text chunk
                           during streaming. Only called for text-only
                           responses (not when the response contains
                           function calls).

        Returns:
            Dict with 'content' and/or 'tool_calls' -- identical contract
            to complete_with_tools().
        """
        # Build contents -- same as complete_with_tools()
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                continue
            elif role == "assistant":
                contents.append(
                    types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=content)],
                    )
                )
            else:
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=content)],
                    )
                )

        # Build tool declarations -- same as complete_with_tools()
        func_decls = []
        for tool in tools:
            func_decls.append(
                types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=tool.get("parameters", {"type": "object", "properties": {}}),
                )
            )

        gemini_tools = [types.Tool(function_declarations=func_decls)] if func_decls else None

        tool_config_obj = None
        if gemini_tools and force_tool_call:
            tool_config_obj = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=types.FunctionCallingConfigMode.ANY
                )
            )

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=gemini_tools,
            tool_config=tool_config_obj,
        )

        # Attempt streaming call
        try:
            stream = self._client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=config,
            )
        except Exception:
            # Stream setup failed -- fall back to non-streaming
            return await self.complete_with_tools(
                system_prompt, messages, tools, force_tool_call
            )

        # Accumulate all parts across chunks.  We buffer everything
        # because function_call parts can appear in any chunk and we
        # must NOT emit text deltas if the response contains tool calls.
        all_text_parts: List[str] = []
        all_tool_calls: List[Dict[str, Any]] = []
        has_function_calls = False

        try:
            for chunk in stream:
                if not chunk.candidates:
                    continue

                candidate = chunk.candidates[0]
                if not candidate.content or not candidate.content.parts:
                    continue

                for part in candidate.content.parts:
                    if (
                        hasattr(part, "function_call")
                        and part.function_call
                        and getattr(part.function_call, "name", None)
                    ):
                        has_function_calls = True
                        fc = part.function_call
                        all_tool_calls.append(
                            {
                                "name": fc.name,
                                "args": dict(fc.args) if fc.args else {},
                            }
                        )
                    elif hasattr(part, "text") and part.text:
                        all_text_parts.append(part.text)

        except Exception:
            pass  # Use partial data collected so far

        # Emit text deltas retroactively only for text-only responses.
        # For FC responses the text is thinking/reasoning -- not for display.
        if not has_function_calls and on_text_delta and all_text_parts:
            for text_chunk in all_text_parts:
                on_text_delta(text_chunk)

        result: Dict[str, Any] = {
            "content": "".join(all_text_parts),
            "tool_calls": all_tool_calls,
        }
        return result

    async def summarize_messages(
        self,
        messages: List[Dict[str, str]],
    ) -> str:
        """Summarise conversation messages into a concise digest.

        Used by scratchpad compaction to replace older turns with a brief
        summary, preserving key information while reducing token count.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.

        Returns:
            A 2-3 sentence summary string.
        """
        formatted = []
        for m in messages:
            role_label = m.get("role", "user").upper()
            content = m.get("content", "")[:500]
            formatted.append(f"[{role_label}]: {content}")

        messages_text = "\n".join(formatted)

        prompt = (
            "Summarize the following conversation excerpt in 2-3 sentences. "
            "Focus on: what was asked, what tools were called, what was found. "
            "Be factual and concise. Do not add opinions.\n\n"
            f"CONVERSATION:\n{messages_text}\n\n"
            "SUMMARY:"
        )

        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            if response.candidates and response.candidates[0].content.parts:
                return response.candidates[0].content.parts[0].text.strip()
        except Exception:
            return f"Previous conversation covered: {messages_text[:200]}..."

        return "Previous conversation context (summarization failed)."

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
        start = time.monotonic()

        # Build tool declarations using new SDK types
        func_decls = []
        for tool in tools:
            func_decls.append(
                types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=tool.get("parameters", {"type": "object", "properties": {}}),
                )
            )

        gemini_tools = [types.Tool(function_declarations=func_decls)]
        tool_config_obj = types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.ANY
            )
        )

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=gemini_tools,
            tool_config=tool_config_obj,
        )

        # Build initial contents
        contents: list[Any] = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_message)],
            )
        ]

        tool_calls_log: List[Dict[str, Any]] = []
        terminal_tool: str | None = None
        terminal_args: Dict[str, Any] = {}
        final_content = ""

        for turn in range(max_turns):
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
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
                if (
                    hasattr(part, "function_call")
                    and part.function_call
                    and getattr(part.function_call, "name", None)
                ):
                    fc = part.function_call
                    turn_function_calls.append(
                        {
                            "name": fc.name,
                            "args": dict(fc.args) if fc.args else {},
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

                # Build function response part using new SDK
                function_response_parts.append(
                    types.Part.from_function_response(
                        name=fn_name,
                        response={"result": result},
                    )
                )

            # If we hit a terminal tool, stop the loop
            if terminal_tool:
                break

            # Send function responses back to model
            if function_response_parts:
                contents.append(
                    types.Content(
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
