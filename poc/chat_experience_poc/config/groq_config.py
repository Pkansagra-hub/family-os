"""
Groq API Configuration

Defines default model, temperature, token limits, and timeouts for Groq API calls.
Referenced by l5_infrastructure/groq_client.py
"""

import os

# LLM Model Configuration
DEFAULT_MODEL = os.getenv(
    "GROQ_MODEL", "groq/compound"
)  # Using Groq's compound model for enhanced reasoning (configurable via .env)

# Fallback model priority list (iterative retry on timeout/rate-limit)
# Ordered by: capability, TPM (tokens per minute), and availability
FALLBACK_MODELS = [
    "groq/compound",  # Primary: Best reasoning (70K TPM)
    "llama-3.3-70b-versatile",  # Fast, high capability (12K TPM)
    "meta-llama/llama-4-scout-17b-16e-instruct",  # Good balance (30K TPM)
    "qwen/qwen3-32b",  # Reliable alternative (6K TPM, 60 RPM)
    "llama-3.1-8b-instant",  # Fast fallback (6K TPM)
    "openai/gpt-oss-120b",  # High capability (8K TPM)
    "meta-llama/llama-4-maverick-17b-128e-instruct",  # Extended context (6K TPM)
    "moonshotai/kimi-k2-instruct",  # Final fallback (10K TPM, 60 RPM)
]

# Temperature settings by agent type
TEMPERATURE_CONFIG = {
    "concierge": 0.7,  # Friendly, creative responses
    "healthcare": 0.7,  # Helpful but informative
    "finance": 0.3,  # Precise, conservative
    "planner": 0.3,  # Systematic, structured
    "writer": 0.5,  # Balanced creativity
    "specialist": 0.7,  # Expert but accessible
}

# Default temperature (fallback)
DEFAULT_TEMPERATURE = 0.7

# Token limits
MAX_TOKENS = 2048
MIN_TOKENS = 256

# Timeouts
API_TIMEOUT_SECONDS = 30
STREAM_TIMEOUT_SECONDS = 60

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1
RETRY_BACKOFF_MULTIPLIER = 2.0

# Rate limiting
REQUESTS_PER_MINUTE = 60
