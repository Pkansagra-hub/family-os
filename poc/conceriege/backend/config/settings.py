"""Configuration settings for Concierge PoC."""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


class Settings:
    """Application settings loaded from environment and YAML."""

    def __init__(self):
        """Initialize settings from environment and YAML config."""
        # Load environment variables
        load_dotenv()

        # Groq API settings
        self.GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
        self.GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com")
        self.GROQ_MODEL_FAST: str = os.getenv("GROQ_MODEL_FAST", "llama-3.3-70b-versatile")
        self.GROQ_MODEL_SYNTHESIS: str = os.getenv(
            "GROQ_MODEL_SYNTHESIS", "llama-3.3-70b-versatile"
        )
        self.GROQ_TIMEOUT_MS: int = int(os.getenv("GROQ_TIMEOUT_MS", "1000"))

        # K0 API settings
        self.K0_API_URL: str = os.getenv("K0_API_URL", "http://localhost:8000")

        # Conversation settings
        self.MAX_CONVERSATION_HISTORY: int = int(os.getenv("MAX_CONVERSATION_HISTORY", "10"))
        self.PROACTIVE_COOLDOWN_SECONDS: int = int(os.getenv("PROACTIVE_COOLDOWN_SECONDS", "5"))
        self.MIN_BACKGROUND_DURATION_MS: int = int(os.getenv("MIN_BACKGROUND_DURATION_MS", "300"))

        # Logging
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

        # Load LLM config from YAML
        self._llm_config: dict[str, Any] = self._load_llm_config()

    def _load_llm_config(self) -> dict[str, Any]:
        """Load LLM configuration from YAML file.

        Returns:
            Dictionary with LLM client configurations
        """
        config_path = Path(__file__).parent / "llm_config.yaml"

        if not config_path.exists():
            return {}

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        return config.get("llm_clients", {})

    def get_llm_config(self, profile: str = "fast") -> dict[str, Any]:
        """Get LLM configuration for a specific profile.

        Args:
            profile: Profile name (fast, creative, synthesis)

        Returns:
            Dictionary with model, temperature, max_tokens, timeout_ms, use_case

        Raises:
            ValueError: If profile not found
        """
        if profile not in self._llm_config:
            raise ValueError(f"LLM profile '{profile}' not found in llm_config.yaml")

        return self._llm_config[profile]

    def validate(self) -> tuple[bool, list[str]]:
        """Validate settings for completeness.

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        if not self.GROQ_API_KEY:
            errors.append("GROQ_API_KEY is required")

        if self.GROQ_TIMEOUT_MS <= 0:
            errors.append("GROQ_TIMEOUT_MS must be positive")

        if self.MAX_CONVERSATION_HISTORY <= 0:
            errors.append("MAX_CONVERSATION_HISTORY must be positive")

        if self.PROACTIVE_COOLDOWN_SECONDS < 0:
            errors.append("PROACTIVE_COOLDOWN_SECONDS must be non-negative")

        if self.MIN_BACKGROUND_DURATION_MS < 0:
            errors.append("MIN_BACKGROUND_DURATION_MS must be non-negative")

        # Validate LLM profiles exist
        required_profiles = ["fast", "creative", "synthesis"]
        for profile in required_profiles:
            if profile not in self._llm_config:
                errors.append(f"LLM profile '{profile}' missing from llm_config.yaml")

        return len(errors) == 0, errors

    def to_dict(self) -> dict[str, Any]:
        """Convert settings to dictionary (for logging/debugging).

        Returns:
            Dictionary of all settings (API key masked)
        """
        return {
            "GROQ_API_KEY": "***" + self.GROQ_API_KEY[-4:] if self.GROQ_API_KEY else "NOT SET",
            "GROQ_BASE_URL": self.GROQ_BASE_URL,
            "GROQ_MODEL_FAST": self.GROQ_MODEL_FAST,
            "GROQ_MODEL_SYNTHESIS": self.GROQ_MODEL_SYNTHESIS,
            "GROQ_TIMEOUT_MS": self.GROQ_TIMEOUT_MS,
            "K0_API_URL": self.K0_API_URL,
            "MAX_CONVERSATION_HISTORY": self.MAX_CONVERSATION_HISTORY,
            "PROACTIVE_COOLDOWN_SECONDS": self.PROACTIVE_COOLDOWN_SECONDS,
            "MIN_BACKGROUND_DURATION_MS": self.MIN_BACKGROUND_DURATION_MS,
            "LOG_LEVEL": self.LOG_LEVEL,
            "llm_profiles": list(self._llm_config.keys()),
        }
