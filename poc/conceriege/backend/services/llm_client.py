"""LLM client for Groq API with caching and error handling."""

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from cachetools import TTLCache
from groq import AsyncGroq, Groq


@dataclass
class LLMMetrics:
    """Tracks LLM API call metrics."""

    total_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    latencies_ms: list[float] = field(default_factory=list)

    def record_call(
        self,
        latency_ms: float,
        tokens: int = 0,
        cost_usd: float = 0.0,
        from_cache: bool = False,
    ) -> None:
        """Record a single LLM API call.

        Args:
            latency_ms: Latency in milliseconds
            tokens: Number of tokens used
            cost_usd: Cost in USD
            from_cache: Whether response came from cache
        """
        if from_cache:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
            self.total_calls += 1
            self.total_tokens += tokens
            self.total_cost_usd += cost_usd

        self.latencies_ms.append(latency_ms)

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency."""
        if not self.latencies_ms:
            return 0.0
        return sum(self.latencies_ms) / len(self.latencies_ms)

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary.

        Returns:
            Dictionary with all metrics
        """
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "cache_hit_rate": round(self.cache_hit_rate, 2),
        }


class LLMClient:
    """LLM client for Groq API with caching and error handling."""

    # Groq pricing (approximate, as of 2024)
    # Llama 3.3 70B: $0.59/1M input tokens, $0.79/1M output tokens
    GROQ_PRICING = {
        "llama-3.3-70b-versatile": {"input": 0.59 / 1_000_000, "output": 0.79 / 1_000_000},
        "llama-3.1-70b-versatile": {"input": 0.59 / 1_000_000, "output": 0.79 / 1_000_000},
    }

    def __init__(self, settings):
        """Initialize LLM client with Groq API.

        Args:
            settings: Settings object with Groq configuration
        """
        self.settings = settings

        # Initialize Groq clients (sync and async)
        # Note: Groq SDK doesn't use base_url parameter, uses default endpoint
        self.client = Groq(api_key=settings.GROQ_API_KEY)
        self.async_client = AsyncGroq(api_key=settings.GROQ_API_KEY)

        # Initialize cache (1 hour TTL, max 1000 entries)
        self.cache: TTLCache = TTLCache(maxsize=1000, ttl=3600)

        # Initialize metrics
        self.metrics = LLMMetrics()

    def _cache_key(self, prompt: str, model: str, temperature: float) -> str:
        """Generate cache key for a prompt.

        Args:
            prompt: Input prompt
            model: Model name
            temperature: Temperature parameter

        Returns:
            Hash string for cache key
        """
        key_str = f"{prompt}|{model}|{temperature}"
        return hashlib.sha256(key_str.encode()).hexdigest()

    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD for API call.

        Args:
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        if model not in self.GROQ_PRICING:
            # Default to Llama 3.3 70B pricing
            model = "llama-3.3-70b-versatile"

        pricing = self.GROQ_PRICING[model]
        cost = (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])
        return cost

    def generate(self, prompt: str, model_profile: str = "fast", **kwargs) -> str:
        """Generate completion using Groq API (synchronous).

        Args:
            prompt: Input prompt
            model_profile: Profile name (fast, creative, synthesis)
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Generated text

        Raises:
            ValueError: If model profile not found
            Exception: If API call fails after retries
        """
        # Get profile config
        profile_config = self.settings.get_llm_config(model_profile)

        # Merge kwargs with profile config
        model = kwargs.get("model", profile_config["model"])
        temperature = kwargs.get("temperature", profile_config["temperature"])
        max_tokens = kwargs.get("max_tokens", profile_config["max_tokens"])

        # Check cache
        cache_key = self._cache_key(prompt, model, temperature)
        if cache_key in self.cache:
            cached_response = self.cache[cache_key]
            self.metrics.record_call(latency_ms=0.0, from_cache=True)
            return cached_response

        # Make API call
        start_time = time.time()
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # Extract response text
            text = response.choices[0].message.content

            # Calculate metrics
            latency_ms = (time.time() - start_time) * 1000
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            cost_usd = self._calculate_cost(model, input_tokens, output_tokens)

            # Record metrics
            self.metrics.record_call(
                latency_ms=latency_ms,
                tokens=input_tokens + output_tokens,
                cost_usd=cost_usd,
                from_cache=False,
            )

            # Cache response
            self.cache[cache_key] = text

            return text

        except Exception:
            # Record failed call
            latency_ms = (time.time() - start_time) * 1000
            self.metrics.record_call(latency_ms=latency_ms, from_cache=False)
            raise

    async def generate_async(self, prompt: str, model_profile: str = "fast", **kwargs) -> str:
        """Generate completion using Groq API (asynchronous).

        Args:
            prompt: Input prompt
            model_profile: Profile name (fast, creative, synthesis)
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Generated text

        Raises:
            ValueError: If model profile not found
            Exception: If API call fails after retries
        """
        # Get profile config
        profile_config = self.settings.get_llm_config(model_profile)

        # Merge kwargs with profile config
        model = kwargs.get("model", profile_config["model"])
        temperature = kwargs.get("temperature", profile_config["temperature"])
        max_tokens = kwargs.get("max_tokens", profile_config["max_tokens"])

        # Check cache
        cache_key = self._cache_key(prompt, model, temperature)
        if cache_key in self.cache:
            cached_response = self.cache[cache_key]
            self.metrics.record_call(latency_ms=0.0, from_cache=True)
            return cached_response

        # Make API call
        start_time = time.time()
        try:
            response = await self.async_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # Extract response text
            text = response.choices[0].message.content

            # Calculate metrics
            latency_ms = (time.time() - start_time) * 1000
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            cost_usd = self._calculate_cost(model, input_tokens, output_tokens)

            # Record metrics
            self.metrics.record_call(
                latency_ms=latency_ms,
                tokens=input_tokens + output_tokens,
                cost_usd=cost_usd,
                from_cache=False,
            )

            # Cache response
            self.cache[cache_key] = text

            return text

        except Exception:
            # Record failed call
            latency_ms = (time.time() - start_time) * 1000
            self.metrics.record_call(latency_ms=latency_ms, from_cache=False)
            raise

    async def generate_with_timeout(
        self, prompt: str, timeout_ms: int, model_profile: str = "fast", **kwargs
    ) -> str:
        """Generate completion with timeout enforcement.

        Args:
            prompt: Input prompt
            timeout_ms: Timeout in milliseconds
            model_profile: Profile name (fast, creative, synthesis)
            **kwargs: Additional parameters

        Returns:
            Generated text

        Raises:
            asyncio.TimeoutError: If call exceeds timeout
        """
        timeout_seconds = timeout_ms / 1000.0
        return await asyncio.wait_for(
            self.generate_async(prompt, model_profile, **kwargs),
            timeout=timeout_seconds,
        )

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics.

        Returns:
            Dictionary with all metrics
        """
        return self.metrics.to_dict()

    def reset_metrics(self) -> None:
        """Reset all metrics to zero."""
        self.metrics = LLMMetrics()

    def clear_cache(self) -> None:
        """Clear response cache."""
        self.cache.clear()
