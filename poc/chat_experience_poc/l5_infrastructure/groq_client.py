"""
Async Groq Client Wrapper (DEPRECATED - Use google_client.py)

This module is maintained for backward compatibility.
All new code should use GoogleClient from google_client.py.

For migration, update imports from:
    from l5_infrastructure.groq_client import GroqClient
To:
    from l5_infrastructure.google_client import GoogleClient as LLMClient

Or use the compatibility aliases exported from google_client.py.

References:
- config/llm_config.py (model, temperature, token limits)
- l5_infrastructure/google_client.py (new implementation)
"""

import os
import warnings

# Check which provider to use
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "google")

if LLM_PROVIDER in ("google", "vertex"):
    # Use Google/Vertex AI client
    from l5_infrastructure.google_client import GoogleClient as GroqClient
    from l5_infrastructure.google_client import LLMClientError as GroqClientError
    from l5_infrastructure.google_client import TokenBudgetExceeded

    # Emit deprecation warning on import
    warnings.warn(
        "GroqClient is deprecated. Use GoogleClient from google_client.py instead. "
        "Set LLM_PROVIDER='groq' in .env to continue using Groq.",
        DeprecationWarning,
        stacklevel=2,
    )
else:
    # Legacy Groq implementation
    import asyncio
    import time
    from datetime import datetime
    from typing import AsyncIterator, Optional

    import structlog
    from config.groq_config import (
        API_TIMEOUT_SECONDS,
        DEFAULT_MODEL,
        DEFAULT_TEMPERATURE,
        FALLBACK_MODELS,
        MAX_RETRIES,
        MAX_TOKENS,
        RETRY_BACKOFF_MULTIPLIER,
        RETRY_DELAY_SECONDS,
        TEMPERATURE_CONFIG,
    )
    from groq import APIConnectionError, APITimeoutError, AsyncGroq, RateLimitError

    class GroqClientError(Exception):
        """Base exception for Groq client errors."""

        pass

    class TokenBudgetExceeded(GroqClientError):
        """Raised when token budget limit exceeded."""

        pass

    class GroqClient:
        """
        Async wrapper for Groq API with retry logic, token tracking, and streaming support.

        Features:
        - Automatic retries with exponential backoff
        - Token counting for budget tracking
        - Structured logging with trace IDs
        - Rate limit handling
        - Graceful error recovery
        """

        def __init__(self, api_key: str, trace_id: Optional[str] = None):
            """
            Initialize Groq client.

            Args:
                api_key: Groq API key
                trace_id: Optional trace ID for request correlation
            """
            self.client = AsyncGroq(api_key=api_key)
            self.trace_id = trace_id or self._generate_trace_id()
            self.token_count = 0
            self.request_count = 0
            self.error_count = 0
            self.logger = structlog.get_logger(self.__class__.__name__)

        @staticmethod
        def _generate_trace_id() -> str:
            """Generate unique trace ID for request correlation."""
            return f"groq-{int(time.time() * 1000)}"

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
            Get LLM completion from Groq with automatic retries and fallback models.

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
                GroqClientError: On persistent failures after retries across all fallback models
                TokenBudgetExceeded: If token limit would be exceeded
            """
            trace_id = trace_id or self.trace_id
            requested_model = model or DEFAULT_MODEL
            temperature = temperature or TEMPERATURE_CONFIG.get(agent_type, DEFAULT_TEMPERATURE)

            # Build model list: start with requested model, then fallback list
            models_to_try = [requested_model]
            if requested_model in FALLBACK_MODELS:
                idx = FALLBACK_MODELS.index(requested_model)
                models_to_try.extend(FALLBACK_MODELS[idx + 1 :])
            else:
                models_to_try.extend(FALLBACK_MODELS)

            all_errors = []

            for model_idx, current_model in enumerate(models_to_try):
                attempt = 0

                self.logger.info(
                    "groq_model_attempt",
                    model=current_model,
                    model_position=model_idx + 1,
                    total_models=len(models_to_try),
                    trace_id=trace_id,
                )

                while attempt < MAX_RETRIES:
                    try:
                        attempt += 1

                        self.logger.info(
                            "groq_request",
                            attempt=attempt,
                            trace_id=trace_id,
                            model=current_model,
                            message_count=len(messages),
                        )

                        response = await asyncio.wait_for(
                            self.client.chat.completions.create(
                                model=current_model,
                                messages=messages,
                                temperature=temperature,
                                max_tokens=max_tokens,
                            ),
                            timeout=API_TIMEOUT_SECONDS,
                        )

                        tokens_used = (
                            response.usage.completion_tokens + response.usage.prompt_tokens
                        )
                        self.token_count += tokens_used
                        self.request_count += 1

                        content = response.choices[0].message.content
                        finish_reason = response.choices[0].finish_reason

                        self.logger.info(
                            "groq_success",
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

                    except RateLimitError:
                        self.error_count += 1
                        error_msg = f"Rate limit on {current_model} (attempt {attempt})"
                        all_errors.append(error_msg)

                        if attempt < MAX_RETRIES:
                            delay = RETRY_DELAY_SECONDS * (
                                RETRY_BACKOFF_MULTIPLIER ** (attempt - 1)
                            )
                            self.logger.warning(
                                "groq_rate_limit",
                                model=current_model,
                                attempt=attempt,
                                retry_delay=delay,
                                trace_id=trace_id,
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            self.logger.warning(
                                "groq_model_exhausted",
                                model=current_model,
                                reason="rate_limit",
                                trace_id=trace_id,
                            )
                            break

                    except (APIConnectionError, APITimeoutError) as e:
                        self.error_count += 1
                        error_msg = f"Timeout/connection error on {current_model} (attempt {attempt}): {str(e)}"
                        all_errors.append(error_msg)

                        if attempt < MAX_RETRIES:
                            delay = RETRY_DELAY_SECONDS * (
                                RETRY_BACKOFF_MULTIPLIER ** (attempt - 1)
                            )
                            self.logger.warning(
                                "groq_connection_error",
                                model=current_model,
                                attempt=attempt,
                                retry_delay=delay,
                                trace_id=trace_id,
                                error=str(e),
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            self.logger.warning(
                                "groq_model_exhausted",
                                model=current_model,
                                reason="timeout",
                                trace_id=trace_id,
                            )
                            break

                    except Exception as e:
                        self.error_count += 1
                        error_msg = f"Non-retryable error on {current_model}: {str(e)}"
                        all_errors.append(error_msg)

                        self.logger.error(
                            "groq_error",
                            model=current_model,
                            trace_id=trace_id,
                            error=str(e),
                            error_type=type(e).__name__,
                        )
                        break

            self.logger.error(
                "groq_all_models_exhausted",
                trace_id=trace_id,
                models_tried=len(models_to_try),
                total_attempts=len(all_errors),
            )

            error_summary = "\n".join(all_errors[-5:])
            raise GroqClientError(
                f"Groq API failed across {len(models_to_try)} models after multiple attempts.\n"
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
            Stream LLM completion from Groq.

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
                GroqClientError: On API failures
            """
            trace_id = trace_id or self.trace_id
            model = model or DEFAULT_MODEL
            temperature = temperature or TEMPERATURE_CONFIG.get(agent_type, DEFAULT_TEMPERATURE)

            self.logger.info(
                "groq_stream_start",
                trace_id=trace_id,
                model=model,
                message_count=len(messages),
            )

            try:
                stream = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )

                total_tokens = 0
                async for chunk in stream:
                    if chunk.choices[0].delta.content:
                        token = chunk.choices[0].delta.content
                        total_tokens += 1
                        yield token

                self.token_count += total_tokens
                self.request_count += 1

                self.logger.info(
                    "groq_stream_end",
                    trace_id=trace_id,
                    tokens_streamed=total_tokens,
                    total_tokens=self.token_count,
                )

            except Exception as e:
                self.error_count += 1
                self.logger.error(
                    "groq_stream_error",
                    trace_id=trace_id,
                    error=str(e),
                )
                raise GroqClientError(f"Groq stream error: {str(e)}") from e

        def get_stats(self) -> dict:
            """Return client statistics (tokens used, requests, errors)."""
            return {
                "token_count": self.token_count,
                "request_count": self.request_count,
                "error_count": self.error_count,
                "average_tokens_per_request": (
                    self.token_count / self.request_count if self.request_count > 0 else 0
                ),
            }

        async def close(self):
            """Close the client connection."""
            await self.client.close()

        async def __aenter__(self):
            """Async context manager entry."""
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            """Async context manager exit."""
            await self.close()
