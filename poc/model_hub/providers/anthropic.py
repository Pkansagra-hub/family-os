"""
Anthropic provider implementation.
"""

import json
from typing import Any, AsyncIterator, Dict, Optional

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


class AnthropicProvider(BaseProvider):
    """Anthropic API provider implementation."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        if not config.api_key:
            raise ValueError("API key is required for Anthropic provider")

        self.client = httpx.AsyncClient(
            base_url="https://api.anthropic.com/v1",
            headers={
                "x-api-key": config.api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            timeout=config.timeout,
        )

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def get_default_model(self) -> str:
        return self.config.default_model or "claude-3-sonnet-20240229"

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Generate text using Anthropic API."""
        try:
            payload = self._build_payload(request)

            response = await self.client.post("/messages", json=payload)
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
        """Stream text generation using Anthropic API."""
        try:
            payload = self._build_payload(request, stream=True)

            async with self.client.stream(
                "POST", "/messages", json=payload
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.strip():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break

                            try:
                                chunk_data = json.loads(data)
                                chunk = self._parse_stream_chunk(
                                    chunk_data, request.model
                                )
                                if chunk:
                                    yield chunk
                            except json.JSONDecodeError:
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

        # Anthropic expects messages in a specific format
        if request.messages:
            for msg in request.messages:
                messages.append(
                    {
                        "role": (
                            msg.role.value
                            if msg.role.value != "assistant"
                            else "assistant"
                        ),
                        "content": msg.content,
                    }
                )
        else:
            # Simple prompt case
            if request.system_prompt:
                messages.append(
                    {
                        "role": "user",
                        "content": f"{request.system_prompt}\n\n{request.prompt}",
                    }
                )
            else:
                messages.append({"role": "user", "content": request.prompt})

        payload = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
            "stream": stream,
        }

        # Add optional parameters
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.top_k is not None:
            payload["top_k"] = request.top_k
        if request.stop:
            payload["stop_sequences"] = (
                request.stop if isinstance(request.stop, list) else [request.stop]
            )

        # Add system prompt separately for Anthropic
        if request.system_prompt and not request.messages:
            payload["system"] = request.system_prompt

        # Add any extra parameters
        if request.extra_params:
            payload.update(request.extra_params)

        return payload

    def _parse_response(self, data: Dict[str, Any], model: str) -> GenerateResponse:
        """Parse the API response."""
        content = data["content"][0]["text"] if data["content"] else ""

        # Anthropic doesn't provide token usage in the same way
        usage = Usage(
            prompt_tokens=data.get("usage", {}).get("input_tokens", 0),
            completion_tokens=data.get("usage", {}).get("output_tokens", 0),
            total_tokens=data.get("usage", {}).get("input_tokens", 0)
            + data.get("usage", {}).get("output_tokens", 0),
        )

        return GenerateResponse(
            text=content,
            model=model,
            provider=self.provider_name,
            usage=usage,
            finish_reason=data.get("stop_reason"),
        )

    def _parse_stream_chunk(
        self, data: Dict[str, Any], model: str
    ) -> Optional[StreamChunk]:
        """Parse a streaming response chunk."""
        if data.get("type") == "content_block_delta":
            text = data.get("delta", {}).get("text", "")
            if text:
                return StreamChunk(
                    text=text,
                    model=model,
                    provider=self.provider_name,
                )
        elif data.get("type") == "message_stop":
            return StreamChunk(
                text="",
                model=model,
                provider=self.provider_name,
                finish_reason=data.get("stop_reason"),
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
