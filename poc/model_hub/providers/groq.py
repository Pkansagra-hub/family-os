"""
Groq provider implementation.
"""

from typing import Any, AsyncIterator, Dict

import httpx

from ..exceptions import (
    AuthenticationError,
    ModelNotFoundError,
    ProviderError,
    RateLimitError,
)
from ..model_types import (
    GenerateRequest,
    GenerateResponse,
    ProviderConfig,
    StreamChunk,
    Usage,
)
from .base import BaseProvider


class GroqProvider(BaseProvider):
    """Groq API provider implementation."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        if not config.api_key:
            raise ValueError("API key is required for Groq provider")

        self.client = httpx.AsyncClient(
            base_url="https://api.groq.com/openai/v1",
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=config.timeout,
        )

    @property
    def provider_name(self) -> str:
        return "groq"

    def get_default_model(self) -> str:
        return self.config.default_model or "mixtral-8x7b-32768"

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Generate text using Groq API."""
        try:
            payload = self._build_payload(request)

            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()

            data = response.json()
            return self._parse_response(data, request.model)

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
        except Exception as e:
            raise ProviderError(self.provider_name, f"Generation failed: {str(e)}")

    async def stream_generate(
        self, request: GenerateRequest
    ) -> AsyncIterator[StreamChunk]:
        """Stream text generation using Groq API."""
        try:
            payload = self._build_payload(request, stream=True)

            async with self.client.stream(
                "POST", "/chat/completions", json=payload
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.strip():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break

                            try:
                                import json

                                chunk_data = json.loads(data)
                                chunk = self._parse_stream_chunk(
                                    chunk_data, request.model
                                )
                                if chunk:
                                    yield chunk
                            except Exception:
                                continue

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
        except Exception as e:
            raise ProviderError(self.provider_name, f"Streaming failed: {str(e)}")

    def _build_payload(
        self, request: GenerateRequest, stream: bool = False
    ) -> Dict[str, Any]:
        """Build the API payload."""
        messages = []

        # Add system message if provided
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})

        # Add user message
        if request.messages:
            # Convert our Message objects to Groq format (compatible with OpenAI)
            for msg in request.messages:
                messages.append(
                    {
                        "role": msg.role.value,
                        "content": msg.content,
                        "name": msg.name,
                    }
                )
        else:
            messages.append({"role": "user", "content": request.prompt})

        payload = {
            "model": request.model,
            "messages": messages,
            "stream": stream,
        }

        # Add optional parameters
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop:
            payload["stop"] = request.stop

        # Add any extra parameters
        if request.extra_params:
            payload.update(request.extra_params)

        return payload

    def _parse_response(self, data: Dict[str, Any], model: str) -> GenerateResponse:
        """Parse the API response."""
        choice = data["choices"][0]
        message = choice["message"]

        usage = Usage(
            prompt_tokens=data["usage"]["prompt_tokens"],
            completion_tokens=data["usage"]["completion_tokens"],
            total_tokens=data["usage"]["total_tokens"],
        )

        return GenerateResponse(
            text=message["content"],
            model=model,
            provider=self.provider_name,
            usage=usage,
            finish_reason=choice.get("finish_reason"),
        )

    def _parse_stream_chunk(
        self, data: Dict[str, Any], model: str
    ) -> StreamChunk | None:
        """Parse a streaming response chunk."""
        choice = data["choices"][0]
        delta = choice.get("delta", {})

        text = delta.get("content", "")
        finish_reason = choice.get("finish_reason")

        if text or finish_reason:
            return StreamChunk(
                text=text,
                model=model,
                provider=self.provider_name,
                finish_reason=finish_reason,
            )

        return None

    def _handle_http_error(self, error: httpx.HTTPStatusError):
        """Handle HTTP errors from the API."""
        status_code = error.response.status_code

        if status_code == 401:
            raise AuthenticationError(self.provider_name, "Invalid API key")
        elif status_code == 429:
            raise RateLimitError(self.provider_name)
        elif status_code == 404:
            raise ModelNotFoundError(
                self.provider_name, "model", {"message": "Model not found"}
            )
        else:
            try:
                error_data = error.response.json()
                message = error_data.get("error", {}).get("message", str(error))
            except Exception:
                message = str(error)
            raise ProviderError(
                self.provider_name, f"API error ({status_code}): {message}"
            )

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
