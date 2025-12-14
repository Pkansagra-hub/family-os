"""
Configuration management for the Model Hub.
"""

import os
from typing import Dict, Optional

from .exceptions import ConfigurationError
from .model_types import ProviderConfig


class Config:
    """Configuration manager for providers."""

    def __init__(self, env_file: Optional[str] = None):
        self._configs: Dict[str, ProviderConfig] = {}
        self._load_from_env()

        if env_file:
            self._load_from_file(env_file)

    def _load_from_env(self):
        """Load configuration from environment variables."""
        # OpenAI
        if os.getenv("OPENAI_API_KEY"):
            self._configs["openai"] = ProviderConfig(
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("OPENAI_BASE_URL"),
                timeout=float(os.getenv("OPENAI_TIMEOUT", "30.0")),
                max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "3")),
                default_model=os.getenv("OPENAI_DEFAULT_MODEL", "gpt-3.5-turbo"),
            )

        # Anthropic
        if os.getenv("ANTHROPIC_API_KEY"):
            self._configs["anthropic"] = ProviderConfig(
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                base_url=os.getenv("ANTHROPIC_BASE_URL"),
                timeout=float(os.getenv("ANTHROPIC_TIMEOUT", "30.0")),
                max_retries=int(os.getenv("ANTHROPIC_MAX_RETRIES", "3")),
                default_model=os.getenv(
                    "ANTHROPIC_DEFAULT_MODEL", "claude-3-sonnet-20240229"
                ),
            )

        # Google
        if os.getenv("GOOGLE_API_KEY"):
            self._configs["google"] = ProviderConfig(
                api_key=os.getenv("GOOGLE_API_KEY"),
                base_url=os.getenv("GOOGLE_BASE_URL"),
                timeout=float(os.getenv("GOOGLE_TIMEOUT", "30.0")),
                max_retries=int(os.getenv("GOOGLE_MAX_RETRIES", "3")),
                default_model=os.getenv("GOOGLE_DEFAULT_MODEL", "gemini-pro"),
            )

        # Groq
        if os.getenv("GROQ_API_KEY"):
            self._configs["groq"] = ProviderConfig(
                api_key=os.getenv("GROQ_API_KEY"),
                base_url=os.getenv("GROQ_BASE_URL"),
                timeout=float(os.getenv("GROQ_TIMEOUT", "30.0")),
                max_retries=int(os.getenv("GROQ_MAX_RETRIES", "3")),
                default_model=os.getenv("GROQ_DEFAULT_MODEL", "llama-3.1-8b-instant"),
            )

        # Local models
        if os.getenv("LOCAL_MODEL_PATH"):
            self._configs["local"] = ProviderConfig(
                base_url=os.getenv("LOCAL_MODEL_PATH"),
                timeout=float(os.getenv("LOCAL_TIMEOUT", "60.0")),
                max_retries=int(os.getenv("LOCAL_MAX_RETRIES", "1")),
                default_model=os.getenv(
                    "LOCAL_DEFAULT_MODEL", "microsoft/DialoGPT-medium"
                ),
            )

    def _load_from_file(self, file_path: str):
        """Load configuration from a file (future enhancement)."""
        # TODO: Implement file-based configuration loading
        pass

    def get_provider_config(self, provider: str) -> ProviderConfig:
        """Get configuration for a specific provider."""
        if provider not in self._configs:
            raise ConfigurationError(
                f"No configuration found for provider '{provider}'"
            )
        return self._configs[provider]

    def set_provider_config(self, provider: str, config: ProviderConfig):
        """Set configuration for a provider."""
        self._configs[provider] = config

    def list_configured_providers(self) -> list[str]:
        """List all configured providers."""
        return list(self._configs.keys())

    def validate_config(self):
        """Validate all provider configurations."""
        errors = []

        for provider_name, config in self._configs.items():
            if not config.api_key and provider_name in [
                "openai",
                "anthropic",
                "google",
                "groq",
            ]:
                errors.append(f"Missing API key for provider '{provider_name}'")

            if config.timeout <= 0:
                errors.append(
                    f"Invalid timeout for provider '{provider_name}': {config.timeout}"
                )

            if config.max_retries < 0:
                errors.append(
                    f"Invalid max_retries for provider '{provider_name}': {config.max_retries}"
                )

        if errors:
            raise ConfigurationError(
                f"Configuration validation failed: {', '.join(errors)}"
            )

    def get_default_model(self, provider: str) -> str:
        """Get the default model for a provider."""
        config = self.get_provider_config(provider)
        if not config.default_model:
            raise ConfigurationError(
                f"No default model configured for provider '{provider}'"
            )
        return config.default_model


# Global config instance
config = Config()
