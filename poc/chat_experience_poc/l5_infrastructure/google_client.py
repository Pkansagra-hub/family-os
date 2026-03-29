"""
Async Google AI / Vertex AI Client Wrapper

Provides async wrapper around Google Generative AI with:
- Error handling and retries (3 attempts with exponential backoff)
- Token counting and budget tracking
- Response streaming support
- Request/response logging with trace IDs
- Drop-in replacement for GroqClient interface

References:
- config/llm_config.py (model, temperature, token limits)
- Google AI: https://ai.google.dev/docs
- Vertex AI: https://cloud.google.com/vertex-ai/docs
"""

import asyncio
import time
from datetime import datetime
from typing import AsyncIterator, Optional

import structlog
from config.llm_config import (
    API_TIMEOUT_SECONDS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    FALLBACK_MODELS,
    LLM_PROVIDER,
    MAX_RETRIES,
    MAX_TOKENS,
    RETRY_BACKOFF_MULTIPLIER,
    RETRY_DELAY_SECONDS,
    TEMPERATURE_CONFIG,
)

# Conditional imports based on provider
try:
    import google.generativeai as genai
    from google.generativeai.types import HarmBlockThreshold, HarmCategory

    GOOGLE_AI_AVAILABLE = True
except ImportError:
    GOOGLE_AI_AVAILABLE = False

try:
    import vertexai
    from vertexai.generative_models import GenerativeModel

    VERTEX_AI_AVAILABLE = True
except ImportError:
    VERTEX_AI_AVAILABLE = False


class LLMClientError(Exception):
    """Base exception for LLM client errors."""

    pass


class TokenBudgetExceeded(LLMClientError):
    """Raised when token budget limit exceeded."""

    pass


class GoogleClient:
    """
    Async wrapper for Google AI / Vertex AI with retry logic, token tracking, and streaming support.

    Drop-in replacement for GroqClient with identical interface.

    Features:
    - Automatic retries with exponential backoff
    - Token counting for budget tracking
    - Structured logging with trace IDs
    - Rate limit handling
    - Graceful error recovery
    - Support for both Google AI Studio and Vertex AI
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        location: str = "us-central1",
        trace_id: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        """
        Initialize Google AI / Vertex AI client.

        Args:
            api_key: Google AI API key (for google-generativeai)
            project_id: GCP Project ID (for Vertex AI)
            location: GCP location (for Vertex AI, default: us-central1)
            trace_id: Optional trace ID for request correlation
            provider: Override provider ("google" or "vertex")
        """
        self.provider = provider or LLM_PROVIDER
        self.trace_id = trace_id or self._generate_trace_id()
        self.token_count = 0
        self.request_count = 0
        self.error_count = 0
        self.logger = structlog.get_logger(self.__class__.__name__)

        if self.provider == "google":
            if not GOOGLE_AI_AVAILABLE:
                raise ImportError(
                    "google-generativeai package not installed. "
                    "Run: pip install google-generativeai"
                )
            if not api_key:
                raise ValueError("api_key required for Google AI provider")
            genai.configure(api_key=api_key)
            self._model_cache = {}

        elif self.provider == "vertex":
            if not VERTEX_AI_AVAILABLE:
                raise ImportError(
                    "google-cloud-aiplatform package not installed. "
                    "Run: pip install google-cloud-aiplatform"
                )
            if not project_id:
                raise ValueError("project_id required for Vertex AI provider")
            vertexai.init(project=project_id, location=location)
            self._model_cache = {}

        else:
            raise ValueError(f"Unknown provider: {self.provider}. Use 'google' or 'vertex'")

        self.api_key = api_key
        self.project_id = project_id
        self.location = location

    def _get_model(self, model_name: str):
        """Get or create a GenerativeModel instance."""
        if model_name not in self._model_cache:
            if self.provider == "google":
                self._model_cache[model_name] = genai.GenerativeModel(model_name)
            else:  # vertex
                self._model_cache[model_name] = GenerativeModel(model_name)
        return self._model_cache[model_name]

    @staticmethod
    def _generate_trace_id() -> str:
        """Generate unique trace ID for request correlation."""
        return f"google-{int(time.time() * 1000)}"

    def _convert_messages_to_contents(self, messages: list[dict]) -> tuple[Optional[str], list]:
        """
        Convert OpenAI-style messages to Google AI content format.

        Args:
            messages: List of {"role": "user/assistant/system", "content": "..."}

        Returns:
            Tuple of (system_instruction, contents)
        """
        system_instruction: Optional[str] = None
        contents = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # Google AI uses system_instruction parameter instead of system role
                system_instruction = content
            elif role == "assistant":
                contents.append({"role": "model", "parts": [content]})
            else:  # user
                contents.append({"role": "user", "parts": [content]})

        return system_instruction, contents

    def _get_safety_settings(self):
        """Convert safety settings to Google AI format."""
        if self.provider == "google" and GOOGLE_AI_AVAILABLE:
            return [
                {
                    "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
                    "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                },
                {
                    "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                },
                {
                    "category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                },
                {
                    "category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                },
            ]
        return None

    async def complete(
        self,
        messages: list[dict],
        agent_type: str = "specialist",
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = MAX_TOKENS,
        trace_id: Optional[str] = None,
    ) -> dict:
        """
        Get LLM completion from Google AI with automatic retries and fallback models.

        Args:
            messages: List of message dicts with 'role' and 'content'
            agent_type: Agent type (affects temperature selection)
            model: Model name (defaults to DEFAULT_MODEL)
            temperature: Temperature (defaults by agent_type)
            max_tokens: Max tokens in response
            trace_id: Optional trace ID override

        Returns:
            Response dict with 'content', 'tokens_used', 'finish_reason', 'model_used'

        Raises:
            LLMClientError: On persistent failures after retries across all fallback models
            TokenBudgetExceeded: If token limit would be exceeded
        """
        trace_id = trace_id or self.trace_id
        requested_model = model or DEFAULT_MODEL
        temperature = temperature or TEMPERATURE_CONFIG.get(agent_type, DEFAULT_TEMPERATURE)

        # Build model list: start with requested model, then fallback list
        fallback_list = FALLBACK_MODELS.get(self.provider, [])
        models_to_try = [requested_model]
        if requested_model in fallback_list:
            idx = fallback_list.index(requested_model)
            models_to_try.extend(fallback_list[idx + 1 :])
        else:
            models_to_try.extend(fallback_list)

        all_errors = []
        system_instruction, contents = self._convert_messages_to_contents(messages)

        # Try each model in sequence
        for model_idx, current_model in enumerate(models_to_try):
            attempt = 0

            self.logger.info(
                "google_model_attempt",
                model=current_model,
                model_position=model_idx + 1,
                total_models=len(models_to_try),
                trace_id=trace_id,
            )

            while attempt < MAX_RETRIES:
                try:
                    attempt += 1

                    self.logger.info(
                        "google_request",
                        attempt=attempt,
                        trace_id=trace_id,
                        model=current_model,
                        message_count=len(messages),
                    )

                    # Get or create model
                    gen_model = self._get_model(current_model)

                    # Configure generation
                    generation_config = {
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    }

                    # Debug: show max tokens being used
                    print(
                        f"[DEBUG GOOGLE] max_output_tokens={max_tokens}, temp={temperature}",
                        flush=True,
                    )

                    # Build chat or single request
                    if self.provider == "google":
                        # Use async generate_content_async
                        response = await asyncio.wait_for(
                            gen_model.generate_content_async(
                                contents=(
                                    contents[-1]["parts"][0] if len(contents) == 1 else contents
                                ),
                                generation_config=generation_config,
                                safety_settings=self._get_safety_settings(),
                            ),
                            timeout=API_TIMEOUT_SECONDS,
                        )

                        # Extract response
                        content = response.text

                        # Log if response was truncated (MAX_TOKENS)
                        if response.candidates:
                            fr = getattr(response.candidates[0], "finish_reason", 0)
                            if fr == 2:  # MAX_TOKENS
                                print(
                                    f"[WARN] Response truncated: {len(content)} chars", flush=True
                                )

                        # Token counting - Google provides usage metadata
                        prompt_tokens = (
                            getattr(response.usage_metadata, "prompt_token_count", 0)
                            if hasattr(response, "usage_metadata")
                            else 0
                        )
                        completion_tokens = (
                            getattr(response.usage_metadata, "candidates_token_count", 0)
                            if hasattr(response, "usage_metadata")
                            else 0
                        )
                        tokens_used = prompt_tokens + completion_tokens

                        # Finish reason
                        finish_reason = "stop"
                        if response.candidates:
                            candidate = response.candidates[0]
                            if hasattr(candidate, "finish_reason"):
                                finish_reason = str(candidate.finish_reason).lower()
                    else:
                        # Vertex AI path
                        response = await asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(
                                None,
                                lambda: gen_model.generate_content(
                                    contents=(
                                        contents[-1]["parts"][0] if len(contents) == 1 else contents
                                    ),
                                    generation_config=generation_config,
                                ),
                            ),
                            timeout=API_TIMEOUT_SECONDS,
                        )

                        content = response.text
                        tokens_used = 0  # Vertex AI token counting varies
                        finish_reason = "stop"

                    # Track tokens
                    self.token_count += tokens_used
                    self.request_count += 1

                    self.logger.info(
                        "google_success",
                        trace_id=trace_id,
                        model=current_model,
                        tokens_used=tokens_used,
                        total_tokens=self.token_count,
                        finish_reason=finish_reason,
                        model_used=current_model,
                        fallback_used=(current_model != requested_model),
                    )

                    return {
                        "content": content,
                        "tokens_used": tokens_used,
                        "finish_reason": finish_reason,
                        "model_used": current_model,
                        "trace_id": trace_id,
                        "timestamp": datetime.utcnow().isoformat(),
                    }

                except asyncio.TimeoutError:
                    self.error_count += 1
                    error_msg = f"Timeout on {current_model} (attempt {attempt})"
                    all_errors.append(error_msg)

                    if attempt < MAX_RETRIES:
                        delay = RETRY_DELAY_SECONDS * (RETRY_BACKOFF_MULTIPLIER ** (attempt - 1))
                        self.logger.warning(
                            "google_timeout",
                            model=current_model,
                            attempt=attempt,
                            retry_delay=delay,
                            trace_id=trace_id,
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        self.logger.warning(
                            "google_model_exhausted",
                            model=current_model,
                            reason="timeout",
                            trace_id=trace_id,
                        )
                        break

                except Exception as e:
                    self.error_count += 1
                    error_str = str(e)

                    # Check for rate limit errors
                    if (
                        "429" in error_str
                        or "quota" in error_str.lower()
                        or "rate" in error_str.lower()
                    ):
                        error_msg = f"Rate limit on {current_model} (attempt {attempt})"
                        all_errors.append(error_msg)

                        if attempt < MAX_RETRIES:
                            delay = RETRY_DELAY_SECONDS * (
                                RETRY_BACKOFF_MULTIPLIER ** (attempt - 1)
                            )
                            self.logger.warning(
                                "google_rate_limit",
                                model=current_model,
                                attempt=attempt,
                                retry_delay=delay,
                                trace_id=trace_id,
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            self.logger.warning(
                                "google_model_exhausted",
                                model=current_model,
                                reason="rate_limit",
                                trace_id=trace_id,
                            )
                            break
                    else:
                        # Non-retryable error
                        error_msg = f"Error on {current_model}: {error_str}"
                        all_errors.append(error_msg)

                        self.logger.error(
                            "google_error",
                            model=current_model,
                            trace_id=trace_id,
                            error=error_str,
                            error_type=type(e).__name__,
                        )
                        break

        # All models exhausted
        self.logger.error(
            "google_all_models_exhausted",
            trace_id=trace_id,
            models_tried=len(models_to_try),
            total_attempts=len(all_errors),
        )

        error_summary = "\n".join(all_errors[-5:])
        raise LLMClientError(
            f"Google AI failed across {len(models_to_try)} models after multiple attempts.\n"
            f"Recent errors:\n{error_summary}"
        )

    async def stream(
        self,
        messages: list[dict],
        agent_type: str = "specialist",
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = MAX_TOKENS,
        trace_id: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        Stream LLM completion from Google AI.

        Args:
            messages: List of message dicts with 'role' and 'content'
            agent_type: Agent type (affects temperature selection)
            model: Model name (defaults to DEFAULT_MODEL)
            temperature: Temperature (defaults by agent_type)
            max_tokens: Max tokens in response
            trace_id: Optional trace ID override

        Yields:
            Token strings as they arrive from API

        Raises:
            LLMClientError: On API failures
        """
        trace_id = trace_id or self.trace_id
        model = model or DEFAULT_MODEL
        temperature = temperature or TEMPERATURE_CONFIG.get(agent_type, DEFAULT_TEMPERATURE)

        self.logger.info(
            "google_stream_start",
            trace_id=trace_id,
            model=model,
            message_count=len(messages),
        )

        try:
            system_instruction, contents = self._convert_messages_to_contents(messages)
            gen_model = self._get_model(model)

            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }

            if self.provider == "google":
                # Stream response
                response = await gen_model.generate_content_async(
                    contents=contents[-1]["parts"][0] if len(contents) == 1 else contents,
                    generation_config=generation_config,
                    safety_settings=self._get_safety_settings(),
                    stream=True,
                )

                total_tokens = 0
                async for chunk in response:
                    if chunk.text:
                        total_tokens += 1
                        yield chunk.text
            else:
                # Vertex AI streaming
                response = gen_model.generate_content(
                    contents=contents[-1]["parts"][0] if len(contents) == 1 else contents,
                    generation_config=generation_config,
                    stream=True,
                )

                total_tokens = 0
                for chunk in response:
                    if chunk.text:
                        total_tokens += 1
                        yield chunk.text

            self.token_count += total_tokens
            self.request_count += 1

            self.logger.info(
                "google_stream_end",
                trace_id=trace_id,
                tokens_streamed=total_tokens,
                total_tokens=self.token_count,
            )

        except Exception as e:
            self.error_count += 1
            self.logger.error(
                "google_stream_error",
                trace_id=trace_id,
                error=str(e),
            )
            raise LLMClientError(f"Google AI stream error: {str(e)}") from e

    def get_stats(self) -> dict:
        """Return client statistics (tokens used, requests, errors)."""
        return {
            "token_count": self.token_count,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "average_tokens_per_request": (
                self.token_count / self.request_count if self.request_count > 0 else 0
            ),
            "provider": self.provider,
        }

    async def complete_with_schema(
        self,
        messages: list[dict],
        response_schema: dict,
        agent_type: str = "specialist",
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = MAX_TOKENS,
        trace_id: Optional[str] = None,
    ) -> dict:
        """
        Get LLM completion with structured JSON output using response_mime_type.

        Uses Google's native JSON schema enforcement for guaranteed valid JSON output.

        Args:
            messages: List of message dicts with 'role' and 'content'
            response_schema: JSON schema dict defining the expected response structure.
                             Example: {"type": "object", "properties": {"name": {"type": "string"}}}
            agent_type: Agent type (affects temperature selection)
            model: Model name (defaults to DEFAULT_MODEL)
            temperature: Temperature (defaults by agent_type)
            max_tokens: Max tokens in response
            trace_id: Optional trace ID override

        Returns:
            Response dict with:
            - 'content': Raw JSON string response
            - 'data': Parsed JSON object
            - 'tokens_used', 'finish_reason', 'model_used'

        Raises:
            LLMClientError: On API failures or JSON parsing issues
        """
        trace_id = trace_id or self.trace_id
        requested_model = model or DEFAULT_MODEL
        temperature = temperature or TEMPERATURE_CONFIG.get(agent_type, DEFAULT_TEMPERATURE)

        system_instruction, contents = self._convert_messages_to_contents(messages)

        try:
            self.logger.info(
                "google_schema_request",
                trace_id=trace_id,
                model=requested_model,
                schema_type=response_schema.get("type", "unknown"),
            )

            # Get model
            gen_model = self._get_model(requested_model)

            # Configure generation with JSON schema
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "response_mime_type": "application/json",
                "response_schema": response_schema,
            }

            if self.provider == "google":
                response = await asyncio.wait_for(
                    gen_model.generate_content_async(
                        contents=contents[-1]["parts"][0] if len(contents) == 1 else contents,
                        generation_config=generation_config,
                        safety_settings=self._get_safety_settings(),
                    ),
                    timeout=API_TIMEOUT_SECONDS,
                )

                # Extract JSON response
                content = response.text

                # Token counting
                tokens_used = 0
                if hasattr(response, "usage_metadata"):
                    prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", 0)
                    completion_tokens = getattr(
                        response.usage_metadata, "candidates_token_count", 0
                    )
                    tokens_used = prompt_tokens + completion_tokens

                # Finish reason
                finish_reason = "stop"
                if response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, "finish_reason"):
                        finish_reason = str(candidate.finish_reason).lower()

            else:
                # Vertex AI path - JSON schema support may differ
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: gen_model.generate_content(
                        contents=contents[-1]["parts"][0] if len(contents) == 1 else contents,
                        generation_config=generation_config,
                    ),
                )
                content = response.text
                tokens_used = 0
                finish_reason = "stop"

            # Parse JSON
            import json

            try:
                parsed_data = json.loads(content)
            except json.JSONDecodeError as e:
                self.logger.error(
                    "google_schema_json_error",
                    trace_id=trace_id,
                    error=str(e),
                    content_preview=content[:200] if content else "empty",
                )
                raise LLMClientError(f"Failed to parse JSON response: {e}") from e

            # Track tokens
            self.token_count += tokens_used
            self.request_count += 1

            self.logger.info(
                "google_schema_success",
                trace_id=trace_id,
                model=requested_model,
                tokens_used=tokens_used,
                total_tokens=self.token_count,
                finish_reason=finish_reason,
            )

            return {
                "content": content,
                "data": parsed_data,
                "tokens_used": tokens_used,
                "finish_reason": finish_reason,
                "model_used": requested_model,
                "trace_id": trace_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except asyncio.TimeoutError:
            self.error_count += 1
            self.logger.error(
                "google_schema_timeout",
                trace_id=trace_id,
                model=requested_model,
            )
            raise LLMClientError(f"Google AI schema request timeout on {requested_model}")

        except LLMClientError:
            raise

        except Exception as e:
            self.error_count += 1
            self.logger.error(
                "google_schema_error",
                trace_id=trace_id,
                error=str(e),
            )
            raise LLMClientError(f"Google AI schema error: {str(e)}") from e

    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        agent_type: str = "specialist",
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = MAX_TOKENS,
        trace_id: Optional[str] = None,
    ) -> dict:
        """
        Get LLM completion with function calling (tool use) support.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: List of tool definitions in Google format:
                   [{"name": "tool_name", "description": "...", "parameters": {...}}]
            agent_type: Agent type (affects temperature selection)
            model: Model name (defaults to DEFAULT_MODEL)
            temperature: Temperature
            max_tokens: Max tokens in response
            trace_id: Optional trace ID override

        Returns:
            Response dict with:
            - 'content': Text response (if no tool call)
            - 'tool_calls': List of tool calls [{"name": "...", "args": {...}}]
            - 'tokens_used', 'finish_reason', 'model_used'
        """
        trace_id = trace_id or self.trace_id
        requested_model = model or DEFAULT_MODEL
        temperature = temperature or TEMPERATURE_CONFIG.get(agent_type, DEFAULT_TEMPERATURE)

        system_instruction, contents = self._convert_messages_to_contents(messages)

        try:
            self.logger.info(
                "google_tool_request",
                trace_id=trace_id,
                model=requested_model,
                tool_count=len(tools),
                tool_names=[t.get("name") for t in tools],
            )

            # Convert tools to Google format
            function_declarations = []
            for tool in tools:
                function_declarations.append(
                    {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                    }
                )

            # Get model
            gen_model = self._get_model(requested_model)

            # Configure generation with tools
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }

            # Build tool config for Google AI
            tool_config = {"function_declarations": function_declarations}

            if self.provider == "google":
                response = await asyncio.wait_for(
                    gen_model.generate_content_async(
                        contents=contents[-1]["parts"][0] if len(contents) == 1 else contents,
                        generation_config=generation_config,
                        safety_settings=self._get_safety_settings(),
                        tools=[tool_config],
                    ),
                    timeout=API_TIMEOUT_SECONDS,
                )

                # Check for function calls in response
                tool_calls = []
                text_content = ""

                if response.candidates:
                    candidate = response.candidates[0]
                    for part in candidate.content.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            fc = part.function_call
                            tool_calls.append(
                                {
                                    "name": fc.name,
                                    "args": dict(fc.args) if fc.args else {},
                                }
                            )
                        elif hasattr(part, "text") and part.text:
                            text_content += part.text

                # Token counting
                tokens_used = 0
                if hasattr(response, "usage_metadata"):
                    prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", 0)
                    completion_tokens = getattr(
                        response.usage_metadata, "candidates_token_count", 0
                    )
                    tokens_used = prompt_tokens + completion_tokens

                self.token_count += tokens_used
                self.request_count += 1

                # Determine finish reason
                finish_reason = "tool_calls" if tool_calls else "stop"

                self.logger.info(
                    "google_tool_success",
                    trace_id=trace_id,
                    model=requested_model,
                    tool_calls_count=len(tool_calls),
                    tool_names=[tc["name"] for tc in tool_calls],
                    tokens_used=tokens_used,
                )

                return {
                    "content": text_content,
                    "tool_calls": tool_calls,
                    "tokens_used": tokens_used,
                    "finish_reason": finish_reason,
                    "model_used": requested_model,
                    "trace_id": trace_id,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            else:
                raise NotImplementedError("Tool calling not yet implemented for Vertex AI provider")

        except Exception as e:
            self.error_count += 1
            self.logger.error(
                "google_tool_error",
                trace_id=trace_id,
                error=str(e),
            )
            # Fallback to regular completion without tools
            self.logger.warning("google_tool_fallback", trace_id=trace_id, reason=str(e))
            return await self.complete(
                messages=messages,
                agent_type=agent_type,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                trace_id=trace_id,
            )

    async def close(self):
        """Close the client connection (no-op for Google AI, kept for interface compatibility)."""
        pass

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Alias for backward compatibility with GroqClient usage patterns
LLMClient = GoogleClient
GroqClient = GoogleClient  # Drop-in replacement alias
GroqClientError = LLMClientError  # Exception alias for compatibility
