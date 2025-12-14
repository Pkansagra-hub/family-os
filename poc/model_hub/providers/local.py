"""
Local provider implementation using HuggingFace Transformers.
"""

import asyncio
from typing import AsyncIterator

from ..exceptions import ModelNotFoundError, ProviderError
from ..model_types import (
    GenerateRequest,
    GenerateResponse,
    ProviderConfig,
    StreamChunk,
    Usage,
)
from .base import BaseProvider


class LocalProvider(BaseProvider):
    """Local HuggingFace model provider implementation."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._model = None
        self._tokenizer = None
        self._pipeline = None

    @property
    def provider_name(self) -> str:
        return "local"

    def get_default_model(self) -> str:
        return self.config.default_model or "microsoft/DialoGPT-medium"

    async def _ensure_model_loaded(self):
        """Lazy load the model and tokenizer."""
        if self._pipeline is not None:
            return

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
        except ImportError:
            raise ProviderError(
                self.provider_name,
                "transformers and torch are required for local models",
            )

        model_name = self.config.default_model or "microsoft/DialoGPT-medium"

        try:
            # Load tokenizer and model
            self._tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._model = AutoModelForCausalLM.from_pretrained(model_name)

            # Create pipeline
            self._pipeline = pipeline(
                "text-generation",
                model=self._model,
                tokenizer=self._tokenizer,
                device=0 if torch.cuda.is_available() else -1,
                torch_dtype=(
                    torch.float16 if torch.cuda.is_available() else torch.float32
                ),
            )

        except Exception as e:
            raise ModelNotFoundError(self.provider_name, model_name, {"error": str(e)})

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Generate text using local model."""
        await self._ensure_model_loaded()

        # Type assertions for mypy
        assert self._pipeline is not None
        assert self._tokenizer is not None

        try:
            # Prepare input
            if request.messages:
                # Convert messages to text
                prompt = self._messages_to_text(request.messages)
            else:
                prompt = request.prompt

            # Generate
            outputs = self._pipeline(
                prompt,
                max_length=request.max_tokens or 100,
                temperature=request.temperature or 1.0,
                top_p=request.top_p or 1.0,
                top_k=request.top_k,
                do_sample=request.temperature and request.temperature > 0,
                num_return_sequences=1,
                pad_token_id=self._tokenizer.eos_token_id,
                return_full_text=False,
            )

            generated_text = outputs[0]["generated_text"]

            # Estimate token usage (rough approximation)
            prompt_tokens = len(self._tokenizer.encode(prompt))
            completion_tokens = len(self._tokenizer.encode(generated_text))
            total_tokens = prompt_tokens + completion_tokens

            usage = Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )

            return GenerateResponse(
                text=generated_text,
                model=self.get_default_model(),
                provider=self.provider_name,
                usage=usage,
                finish_reason="stop",
            )

        except Exception as e:
            raise ProviderError(self.provider_name, f"Generation failed: {str(e)}")

    async def stream_generate(
        self, request: GenerateRequest
    ) -> AsyncIterator[StreamChunk]:
        """Stream text generation using local model."""
        # For local models, we'll generate the full response and simulate streaming
        try:
            response = await self.generate(request)

            # Split response into chunks for streaming simulation
            words = response.text.split()
            for i, word in enumerate(words):
                chunk_text = word + " "
                finish_reason = "stop" if i == len(words) - 1 else None

                yield StreamChunk(
                    text=chunk_text,
                    model=response.model,
                    provider=self.provider_name,
                    finish_reason=finish_reason,
                )

                # Small delay to simulate streaming
                await asyncio.sleep(0.01)

        except Exception as e:
            raise ProviderError(self.provider_name, f"Streaming failed: {str(e)}")

    def _messages_to_text(self, messages) -> str:
        """Convert chat messages to text format."""
        text_parts = []
        for msg in messages:
            role_prefix = "User: " if msg.role.value == "user" else "Assistant: "
            text_parts.append(f"{role_prefix}{msg.content}")

        return "\n".join(text_parts)

    async def close(self):
        """Clean up resources."""
        if self._model:
            del self._model
        if self._tokenizer:
            del self._tokenizer
        if self._pipeline:
            del self._pipeline

        self._model = None
        self._tokenizer = None
        self._pipeline = None
