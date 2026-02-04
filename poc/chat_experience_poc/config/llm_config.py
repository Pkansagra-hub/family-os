"""
LLM API Configuration

Unified LLM configuration supporting multiple providers:
- Google AI (Gemini via google-generativeai)
- Vertex AI (Gemini via google-cloud-aiplatform)
- Groq (legacy, for migration path)

Referenced by l5_infrastructure/llm_client.py
"""

import os

# Provider selection: "google", "vertex", "groq"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "google")

# Google AI Configuration (google-generativeai SDK)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")

# Vertex AI Configuration (google-cloud-aiplatform SDK)
VERTEX_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID", "")
VERTEX_LOCATION = os.getenv("GOOGLE_LOCATION", "us-central1")
VERTEX_MODEL = os.getenv("VERTEX_MODEL", "gemini-2.5-flash")

# Legacy Groq Configuration (for migration)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "groq/compound")


# Default model based on provider
def get_default_model() -> str:
    """Get the default model based on configured provider."""
    if LLM_PROVIDER == "google":
        return GOOGLE_MODEL
    elif LLM_PROVIDER == "vertex":
        return VERTEX_MODEL
    elif LLM_PROVIDER == "groq":
        return GROQ_MODEL
    return GOOGLE_MODEL


DEFAULT_MODEL = get_default_model()

# Fallback model priority list by provider
FALLBACK_MODELS = {
    "google": [
        "gemini-2.5-flash",  # Primary: Latest fast model
        "gemini-2.5-pro",  # High capability
        "gemini-2.0-flash",  # Next-gen fast model
        "gemini-1.5-flash",  # Stable fallback
        "gemini-1.5-pro",  # Legacy high capability
    ],
    "vertex": [
        "gemini-2.5-flash",  # Primary
        "gemini-2.5-pro",  # High capability
        "gemini-1.5-flash-002",  # Latest flash
        "gemini-1.5-pro-002",  # Latest pro
    ],
    "groq": [
        "groq/compound",
        "llama-3.3-70b-versatile",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "qwen/qwen3-32b",
        "llama-3.1-8b-instant",
    ],
}

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

# Safety settings for Google/Vertex AI
SAFETY_SETTINGS = {
    "HARM_CATEGORY_HARASSMENT": "BLOCK_MEDIUM_AND_ABOVE",
    "HARM_CATEGORY_HATE_SPEECH": "BLOCK_MEDIUM_AND_ABOVE",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_MEDIUM_AND_ABOVE",
    "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_MEDIUM_AND_ABOVE",
}
