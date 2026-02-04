"""
LLM API Configuration

Defines default model, temperature, token limits, and timeouts for LLM API calls.
Referenced by l5_infrastructure/groq_client.py and google_client.py
"""

import os

# LLM Model Configuration - Now uses Google AI (Gemini)
DEFAULT_MODEL = os.getenv(
    "GOOGLE_MODEL", "gemini-2.5-flash"
)  # Using Google's Gemini model (configurable via .env)

# Fallback model priority list (iterative retry on timeout/rate-limit)
# Ordered by: capability and availability
FALLBACK_MODELS = [
    "gemini-2.5-flash",  # Primary: Fast and capable
    "gemini-2.0-flash",  # Fallback: Previous generation
    "gemini-1.5-flash",  # Legacy fallback
    "gemini-1.5-pro",  # Pro tier fallback
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
