"""
LLM Provider Module - Centralized LLM backend management

This module provides a clean abstraction for:
  1. Local LLM (Lemonade Server)
  2. OpenRouter API
  3. Mock responses for testing

All tests import from here instead of having LLM logic inside.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from enum import Enum

from openai import OpenAI


class LLMBackend(Enum):
    """Available LLM backends."""

    LOCAL = "local"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    MOCK = "mock"


class LLMProvider:
    """Unified LLM provider with automatic fallback chain."""

    def __init__(self, prefer_local: bool = True, max_workers: int = 5):
        """
        Initialize LLM provider with fallback chain.

        Priority: Local LLM -> Groq -> OpenRouter -> Mock

        Args:
            prefer_local: Try local LLM first
            max_workers: Thread pool size for blocking I/O
        """
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.client = None
        self.backend = LLMBackend.MOCK
        self.api_key = os.environ.get("OPENROUTER_API_KEY")
        self.groq_api_key = os.environ.get("GROQ_API_KEY")

        if prefer_local:
            self._init_local_llm()

        if self.backend == LLMBackend.MOCK and self.groq_api_key:
            self._init_groq()

        if self.backend == LLMBackend.MOCK and self.api_key:
            self._init_openrouter()

    def _init_local_llm(self) -> bool:
        """Try to connect to local LLM (Lemonade server)."""
        try:
            self.client = OpenAI(
                base_url="http://localhost:8000/api/v1",
                api_key="lemonade",
                timeout=30.0,
            )
            # Test connection
            _ = self.client.chat.completions.create(
                model="Qwen-2.5-1.5B-Instruct-NPU",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
                timeout=5.0,
            )
            self.backend = LLMBackend.LOCAL
            return True
        except Exception:
            self.client = None
            return False

    def _init_groq(self) -> bool:
        """Try to connect to Groq API."""
        try:
            self.client = OpenAI(
                api_key=self.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
                timeout=30.0,
            )
            self.backend = LLMBackend.GROQ
            return True
        except Exception:
            self.client = None
            return False

    def _init_openrouter(self) -> bool:
        """Try to connect to OpenRouter API."""
        try:
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.api_key,
                default_headers={
                    "HTTP-Referer": "http://localhost",
                    "X-Title": "FamilyOS-DAG-Tests",
                },
                timeout=30.0,
            )
            self.backend = LLMBackend.OPENROUTER
            return True
        except Exception:
            self.client = None
            return False

    def get_backend(self) -> str:
        """Get current backend name."""
        return self.backend.value

    def call_llm(self, prompt: str, max_tokens: int = 100, system_message: str = None) -> str:
        """
        Call LLM synchronously (for use in thread pool).

        Args:
            prompt: Question/prompt to send
            max_tokens: Max response tokens
            system_message: Optional system message for structured output

        Returns:
            Response text

        Raises:
            RuntimeError: If no backend available
        """
        if self.backend == LLMBackend.MOCK:
            return self._mock_response(prompt)

        if not self.client:
            raise RuntimeError("No LLM client available")

        if self.backend == LLMBackend.LOCAL:
            model = "Qwen-2.5-1.5B-Instruct-NPU"
        elif self.backend == LLMBackend.GROQ:
            model = "llama-3.3-70b-versatile"  # Current Groq model
        else:  # OPENROUTER
            model = "nvidia/nemotron-nano-12b-v2-vl:free"

        # Build messages
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
            timeout=30.0,
        )
        return response.choices[0].message.content or ""

    def _mock_response(self, prompt: str) -> str:
        """Return mock response for testing."""
        keywords = {
            "France": "Paris",
            "quantum": "Uses quantum superposition",
            "planets": "Eight planets",
            "percent": "50",
            "photosynthesis": "Plants convert light to energy",
            "speed": "40 mph",
            "apples": "35 apples",
            "fraction": "1/4",
        }

        for key, response in keywords.items():
            if key.lower() in prompt.lower():
                return response

        return "Mock response"

    def shutdown(self):
        """Clean up thread pool."""
        self.executor.shutdown(wait=True)


# Global provider instance
_provider = None


def get_provider(prefer_local: bool = True, max_workers: int = 5) -> LLMProvider:
    """Get or create global LLM provider."""
    global _provider
    if _provider is None:
        _provider = LLMProvider(prefer_local=prefer_local, max_workers=max_workers)
    return _provider


def reset_provider():
    """Reset global provider (for testing)."""
    global _provider
    if _provider:
        _provider.shutdown()
    _provider = None
