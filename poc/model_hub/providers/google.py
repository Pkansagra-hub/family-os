"""
Google provider implementation.
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


class GoogleProvider(BaseProvider):
    """Google AI (Gemini) provider implementation."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        if not config.api_key:
            raise ValueError("API key is required for Google provider")

        self.client = httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com/v1beta",
            timeout=config.timeout,
        )

    @property
    def provider_name(self) -> str:
        return "google"

    def get_default_model(self) -> str:
        return self.config.default_model or "gemini-pro"

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Generate text using Google AI API."""
        try:
            url = f"/models/{request.model}:generateContent?key={self.config.api_key}"
            payload = self._build_payload(request)

            response = await self.client.post(url, json=payload)
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
        """Stream text generation using Google AI API."""
        # Google AI doesn't support streaming in the same way
        # We'll simulate streaming by yielding the full response
        try:
            response = await self.generate(request)
            yield StreamChunk(
                text=response.text,
                model=request.model,
                provider=self.provider_name,
                finish_reason=response.finish_reason,
            )
        except Exception as e:
            raise ProviderError(self.provider_name, f"Streaming failed: {str(e)}")

    def _build_payload(self, request: GenerateRequest) -> Dict[str, Any]:
        """Build the API payload."""
        contents: Dict[str, Any] = {
            "contents": [],
        }

        # Build contents array
        if request.messages:
            for msg in request.messages:
                contents["contents"].append(
                    {
                        "role": "user" if msg.role.value == "user" else "model",
                        "parts": [{"text": msg.content}],
                    }
                )
        else:
            # Simple prompt case
            contents["contents"].append(
                {
                    "role": "user",
                    "parts": [{"text": request.prompt}],
                }
            )

        payload: Dict[str, Any] = {
            "contents": contents["contents"],
        }

        # Add generation config
        generation_config = {}
        if request.max_tokens:
            generation_config["maxOutputTokens"] = request.max_tokens
        if request.temperature is not None:
            generation_config["temperature"] = request.temperature
        if request.top_p is not None:
            generation_config["topP"] = request.top_p
        if request.top_k is not None:
            generation_config["topK"] = request.top_k
        if request.stop:
            generation_config["stopSequences"] = (
                request.stop if isinstance(request.stop, list) else [request.stop]
            )

        if generation_config:
            payload["generationConfig"] = generation_config

        # Add system instruction if provided
        if request.system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": request.system_prompt}],
            }

        # Add any extra parameters
        if request.extra_params:
            payload.update(request.extra_params)

        return payload

    def _parse_response(self, data: Dict[str, Any], model: str) -> GenerateResponse:
        """Parse the API response."""
        candidates = data.get("candidates", [])
        if not candidates:
            raise ProviderError(self.provider_name, "No response candidates returned")

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        text = parts[0].get("text", "") if parts else ""

        # Google doesn't provide detailed token usage
        usage = Usage(
            prompt_tokens=0,  # Not provided by Google AI API
            completion_tokens=0,
            total_tokens=0,
        )

        finish_reason = candidates[0].get("finishReason")

        return GenerateResponse(
            text=text,
            model=model,
            provider=self.provider_name,
            usage=usage,
            finish_reason=finish_reason,
        )

    def _handle_http_error(self, error: httpx.HTTPStatusError):
        """Handle HTTP errors from the API."""
        status_code = error.response.status_code

        if status_code == 401 or status_code == 403:
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
