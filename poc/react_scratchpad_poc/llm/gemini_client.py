"""
Gemini LLM client for the ReactLoopScratchpad PoC.

Wraps google-generativeai SDK for:
  - Function-calling generation (the core ReAct loop LLM call)
  - Message summarization (for scratchpad compaction)
  - Finding extraction (structured fact extraction from tool results)

Uses Gemini 2.5 Flash via API key from chat_experience_poc/.env
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from core.models import Finding, Message, ToolCall
from core.protocols import LLMResponse
from google.generativeai import protos

logger = logging.getLogger("react_poc.llm")

# ---------------------------------------------------------------------------
# Load environment
# ---------------------------------------------------------------------------

_ENV_PATH = Path(__file__).parent.parent.parent / "chat_experience_poc" / ".env"


def _load_env() -> None:
    """Load .env from chat_experience_poc directory."""
    if _ENV_PATH.exists():
        from dotenv import load_dotenv

        load_dotenv(_ENV_PATH, override=False)


_load_env()


# ---------------------------------------------------------------------------
# Gemini Client
# ---------------------------------------------------------------------------


class GeminiClient:
    """
    LLM client wrapping Google Gemini for the scratchpad PoC.

    Provides three capabilities:
      1. generate() - Function-calling LLM calls for the ReAct loop
      2. summarize_messages() - Compress old messages into a digest
      3. extract_findings() - Pull structured facts from raw tool output
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY", "")
        self.model_name = model_name or os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")

        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not set. Check .env file.")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_name)

        # Lightweight model for summarization & extraction (same model, lower temp)
        self.utility_model = genai.GenerativeModel(self.model_name)

        # Stats
        self.total_calls = 0
        self.total_tokens_in = 0
        self.total_tokens_out = 0

    # ------------------------------------------------------------------
    # 1. Core generation (function calling)
    # ------------------------------------------------------------------

    async def generate(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        force_tool_call: bool = False,
    ) -> LLMResponse:
        """
        Call Gemini with messages and optional tool declarations.

        Args:
            messages: List of {"role": "system"|"user"|"assistant", "content": "..."}
            tools: List of function declaration dicts in Google AI format
            force_tool_call: If True, forces the model to call a tool

        Returns:
            LLMResponse with text, tool_calls, and token counts
        """
        # Build Gemini contents from messages
        contents, system_instruction = self._build_contents(messages)

        # DEBUG: Log model input
        logger.debug("=" * 80)
        logger.debug("[LLM CALL #%d] force_tool_call=%s", self.total_calls + 1, force_tool_call)
        logger.debug(
            "--- SYSTEM INSTRUCTION (%d chars) ---",
            len(system_instruction) if system_instruction else 0,
        )
        if system_instruction:
            logger.debug("%s", system_instruction[:500])
        logger.debug("--- MESSAGES (%d) ---", len(messages))
        for i, m in enumerate(messages):
            content = m.get("content", "")
            logger.debug(
                "  msg[%d] role=%s len=%d: %s", i, m.get("role"), len(content), content[:200]
            )
        logger.debug("--- TOOLS (%d) ---", len(tools) if tools else 0)
        if tools:
            tool_names = [t.get("name", "?") for t in tools]
            logger.debug("  tool_names=%s", tool_names)
        logger.debug("--- CONTENTS TO GEMINI (%d parts) ---", len(contents))
        for i, c in enumerate(contents):
            if isinstance(c, dict):
                logger.debug(
                    "  content[%d] role=%s parts=%d", i, c.get("role", "?"), len(c.get("parts", []))
                )
            else:
                logger.debug(
                    "  content[%d] role=%s parts=%s",
                    i,
                    getattr(c, "role", "?"),
                    len(getattr(c, "parts", [])),
                )

        # Build tool config
        gemini_tools = None
        tool_config = None

        if tools:
            gemini_tools = [
                genai.protos.Tool(
                    function_declarations=[self._to_function_declaration(t) for t in tools]
                )
            ]

            if force_tool_call:
                tool_config = genai.protos.ToolConfig(
                    function_calling_config=genai.protos.FunctionCallingConfig(
                        mode=genai.protos.FunctionCallingConfig.Mode.ANY
                    )
                )

        logger.debug("--- TOOL CONFIG ---")
        logger.debug("  gemini_tools=%s, tool_config=%s", gemini_tools is not None, tool_config)

        # Safety settings -- permissive for PoC
        safety = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        # Call Gemini
        self.total_calls += 1
        try:
            generation_config = {}
            if system_instruction:
                generation_config["system_instruction"] = system_instruction

            # Use model with system instruction if provided
            model = self.model
            if system_instruction:
                model = genai.GenerativeModel(
                    self.model_name,
                    system_instruction=system_instruction,
                )

            response = model.generate_content(
                contents,
                tools=gemini_tools,
                tool_config=tool_config,
                safety_settings=safety,
            )
            logger.debug("--- RAW RESPONSE TYPE: %s ---", type(response).__name__)
            logger.debug("--- RAW RESPONSE repr (first 500 chars): %s", repr(response)[:500])
        except Exception as e:
            logger.debug("--- LLM EXCEPTION: %s ---", str(e))
            return LLMResponse(
                text=f"LLM_ERROR: {str(e)}",
                tool_calls=[],
                tokens_in=0,
                tokens_out=0,
            )

        # Extract token counts
        tokens_in = 0
        tokens_out = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            tokens_in = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            tokens_out = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

        self.total_tokens_in += tokens_in
        self.total_tokens_out += tokens_out

        # Extract tool calls and text
        tool_calls = []
        text_parts = []

        # DEBUG: Log raw response structure
        logger.debug("--- RAW RESPONSE ---")
        logger.debug("  candidates=%d", len(response.candidates) if response.candidates else 0)
        if response.candidates:
            candidate = response.candidates[0]
            logger.debug("  candidate.finish_reason=%s", getattr(candidate, "finish_reason", "?"))
            if candidate.content:
                logger.debug("  candidate.content.role=%s", getattr(candidate.content, "role", "?"))
                logger.debug(
                    "  candidate.content.parts=%d",
                    len(candidate.content.parts) if candidate.content.parts else 0,
                )
                if candidate.content.parts:
                    for pi, part in enumerate(candidate.content.parts):
                        has_fc = hasattr(part, "function_call") and part.function_call.name
                        has_text = hasattr(part, "text") and part.text
                        logger.debug(
                            "    part[%d] has_function_call=%s has_text=%s", pi, has_fc, has_text
                        )
                        if has_fc:
                            fc = part.function_call
                            logger.debug(
                                "      -> function_call: name=%s args=%s",
                                fc.name,
                                dict(fc.args) if fc.args else {},
                            )
                        if has_text:
                            logger.debug(
                                "      -> text (%d chars): %s", len(part.text), part.text[:300]
                            )
            else:
                logger.debug("  candidate.content is None")

        if response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if hasattr(part, "function_call") and part.function_call.name:
                        fc = part.function_call
                        args = dict(fc.args) if fc.args else {}
                        tool_calls.append(
                            ToolCall(
                                name=fc.name,
                                arguments=args,
                            )
                        )
                    elif hasattr(part, "text") and part.text:
                        text_parts.append(part.text)

        # DEBUG: Log parsed output
        logger.debug("--- PARSED OUTPUT ---")
        logger.debug("  tool_calls=%d: %s", len(tool_calls), [tc.name for tc in tool_calls])
        logger.debug(
            "  text_parts=%d, total_text_len=%d", len(text_parts), sum(len(t) for t in text_parts)
        )
        if text_parts:
            logger.debug("  text_preview: %s", text_parts[0][:300])
        logger.debug("  tokens_in=%d tokens_out=%d", tokens_in, tokens_out)
        logger.debug("=" * 80)

        return LLMResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            raw=response,
        )

    # ------------------------------------------------------------------
    # 2. Message summarization (for compaction)
    # ------------------------------------------------------------------

    async def summarize_messages(self, messages: List[Message]) -> str:
        """
        Summarize a list of conversation messages into a concise digest.

        Used by the scratchpad compaction step to replace older turns
        with a brief summary, preserving key information while reducing tokens.
        """
        # Format messages for summarization
        formatted = []
        for m in messages:
            role_label = m.role.upper()
            content = m.content[:500]  # truncate long messages
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
            response = self.utility_model.generate_content(prompt)
            if response.candidates and response.candidates[0].content.parts:
                summary = response.candidates[0].content.parts[0].text
                # Track tokens
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    self.total_tokens_in += (
                        getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                    )
                    self.total_tokens_out += (
                        getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                    )
                return summary.strip()
        except Exception:
            # Fallback: simple truncation
            return f"Previous conversation covered: {messages_text[:200]}..."

        return "Previous conversation context (summarization failed)."

    # ------------------------------------------------------------------
    # 3. Finding extraction
    # ------------------------------------------------------------------

    async def extract_findings(
        self,
        tool_name: str,
        raw_result: Any,
    ) -> List[Finding]:
        """
        Extract structured findings from a single tool result.

        Prefer extract_findings_batch() for multiple results in one LLM call.
        """
        return await self.extract_findings_batch([(tool_name, raw_result)])

    async def extract_findings_batch(
        self,
        tool_results: List[tuple],
    ) -> List[Finding]:
        """
        Extract structured findings from multiple tool results in ONE LLM call.

        Args:
            tool_results: List of (tool_name, raw_result) tuples.

        Returns:
            Flat list of Finding objects from all results combined.
        """
        if not tool_results:
            return []

        # Build a single prompt with all tool results
        result_sections = []
        for i, (tool_name, raw_result) in enumerate(tool_results, 1):
            result_str = json.dumps(raw_result) if not isinstance(raw_result, str) else raw_result
            # Cap each result to avoid blowing up the extraction prompt
            if len(result_str) > 3000:
                result_str = result_str[:3000] + "... [truncated]"
            result_sections.append(f"TOOL_{i}: {tool_name}\nRESULT_{i}: {result_str}")

        all_results_text = "\n\n".join(result_sections)

        prompt = (
            f"Extract key facts from these {len(tool_results)} tool results as a JSON array of objects.\n"
            "Each object must have: key (snake_case identifier), value (the fact), "
            "type (category like 'weather', 'flight', 'fact', 'price', 'location', 'error'), "
            "source_tool (the tool name that produced this fact).\n\n"
            "IMPORTANT: Keys MUST be globally unique and descriptive.\n"
            "- If the result is about a specific entity (person, place, etc), PREFIX the key "
            "with the entity name. Example: mom_entity_id, jake_allergy, sarah_diet.\n"
            "- NEVER use generic keys like 'entity_id', 'name', 'result' -- always scope them.\n"
            "- If an ID or reference is returned, ALWAYS extract it with the entity prefix.\n\n"
            "Be concise. Only extract facts that would be useful to remember.\n\n"
            f"{all_results_text}\n\n"
            "Respond with ONLY a JSON array, no markdown formatting:\n"
        )

        # Map tool names for fallback
        tool_names = [tn for tn, _ in tool_results]

        try:
            response = self.utility_model.generate_content(prompt)
            if response.candidates and response.candidates[0].content.parts:
                text = response.candidates[0].content.parts[0].text.strip()
                # Track tokens
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    self.total_tokens_in += (
                        getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                    )
                    self.total_tokens_out += (
                        getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                    )

                # Parse JSON (handle markdown code blocks)
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

                findings_data = json.loads(text)
                findings = []
                for fd in findings_data:
                    source = fd.get(
                        "source_tool", tool_names[0] if len(tool_names) == 1 else "unknown"
                    )
                    findings.append(
                        Finding(
                            key=fd.get("key", "unknown"),
                            value=fd.get("value", ""),
                            type=fd.get("type", "fact"),
                            source_tool=source,
                        )
                    )
                return findings
        except Exception:
            pass

        # Fallback: create one generic finding per tool result
        fallback = []
        for tool_name, raw_result in tool_results:
            fallback.append(
                Finding(
                    key=f"{tool_name}_result",
                    value=str(raw_result)[:200],
                    type="fact",
                    source_tool=tool_name,
                )
            )
        return fallback

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_contents(
        self,
        messages: List[Dict[str, str]],
    ) -> tuple[list, Optional[str]]:
        """
        Convert standard messages to Gemini contents format.

        Returns (contents, system_instruction) tuple.
        Gemini uses system_instruction separately from contents.
        """
        system_instruction = None
        contents = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_instruction = content
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": content}]})
            elif role == "tool":
                # Tool results go as user messages in Gemini
                contents.append({"role": "user", "parts": [{"text": content}]})
            else:
                contents.append({"role": "user", "parts": [{"text": content}]})

        # Ensure at least one content message
        if not contents:
            contents.append({"role": "user", "parts": [{"text": "Hello"}]})

        return contents, system_instruction

    def _to_function_declaration(self, tool: Dict[str, Any]) -> protos.FunctionDeclaration:
        """Convert a tool dict to a Gemini FunctionDeclaration proto."""
        params = tool.get("parameters", {})

        # Build parameter schema
        properties = {}
        for pname, pschema in params.get("properties", {}).items():
            prop_type = self._map_type(pschema.get("type", "string"))
            prop = {"type_": prop_type, "description": pschema.get("description", "")}
            if "enum" in pschema:
                prop["enum"] = pschema["enum"]
            # Handle array items schema (required by Gemini for ARRAY types)
            if prop_type == protos.Type.ARRAY and "items" in pschema:
                items_type = self._map_type(pschema["items"].get("type", "string"))
                prop["items"] = protos.Schema(type_=items_type)
            properties[pname] = protos.Schema(**prop)

        schema = protos.Schema(
            type_=protos.Type.OBJECT,
            properties=properties,
            required=params.get("required", []),
        )

        return protos.FunctionDeclaration(
            name=tool["name"],
            description=tool.get("description", ""),
            parameters=schema,
        )

    @staticmethod
    def _map_type(type_str: str) -> protos.Type:
        """Map JSON Schema type strings to Gemini proto types."""
        mapping = {
            "string": protos.Type.STRING,
            "number": protos.Type.NUMBER,
            "integer": protos.Type.INTEGER,
            "boolean": protos.Type.BOOLEAN,
            "array": protos.Type.ARRAY,
            "object": protos.Type.OBJECT,
        }
        return mapping.get(type_str, protos.Type.STRING)
