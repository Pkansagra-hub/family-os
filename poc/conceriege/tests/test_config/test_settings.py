"""Unit tests for Settings configuration class."""

import os
from unittest.mock import patch

import pytest
from backend.config.settings import Settings


class TestSettings:
    """Test Settings configuration loading."""

    def test_settings_loads_defaults(self):
        """Test Settings loads default values when env vars not set."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

            assert settings.GROQ_API_KEY == ""
            assert settings.GROQ_BASE_URL == "https://api.groq.com/openai/v1"
            assert settings.GROQ_MODEL_FAST == "llama-3.3-70b-versatile"
            assert settings.GROQ_MODEL_SYNTHESIS == "llama-3.3-70b-versatile"
            assert settings.GROQ_TIMEOUT_MS == 1000
            assert settings.K0_API_URL == "http://localhost:8000"
            assert settings.MAX_CONVERSATION_HISTORY == 10
            assert settings.PROACTIVE_COOLDOWN_SECONDS == 5
            assert settings.MIN_BACKGROUND_DURATION_MS == 300
            assert settings.LOG_LEVEL == "INFO"

    def test_settings_loads_from_env(self):
        """Test Settings loads from environment variables."""
        env_vars = {
            "GROQ_API_KEY": "test_key_12345",
            "GROQ_BASE_URL": "https://custom.api.url",
            "GROQ_MODEL_FAST": "custom-model",
            "GROQ_TIMEOUT_MS": "2000",
            "MAX_CONVERSATION_HISTORY": "20",
            "LOG_LEVEL": "DEBUG",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()

            assert settings.GROQ_API_KEY == "test_key_12345"
            assert settings.GROQ_BASE_URL == "https://custom.api.url"
            assert settings.GROQ_MODEL_FAST == "custom-model"
            assert settings.GROQ_TIMEOUT_MS == 2000
            assert settings.MAX_CONVERSATION_HISTORY == 20
            assert settings.LOG_LEVEL == "DEBUG"

    def test_get_llm_config_fast_profile(self):
        """Test get_llm_config returns fast profile configuration."""
        settings = Settings()
        config = settings.get_llm_config("fast")

        assert config["temperature"] == 0.0
        assert config["max_tokens"] == 100
        assert config["timeout_ms"] == 50
        assert "intent_classification" in config["use_case"]
        assert "emotion_detection" in config["use_case"]

    def test_get_llm_config_creative_profile(self):
        """Test get_llm_config returns creative profile configuration."""
        settings = Settings()
        config = settings.get_llm_config("creative")

        assert config["temperature"] == 0.8
        assert config["max_tokens"] == 50
        assert config["timeout_ms"] == 150
        assert "empathy_generation" in config["use_case"]
        assert "proactive_prompts" in config["use_case"]

    def test_get_llm_config_synthesis_profile(self):
        """Test get_llm_config returns synthesis profile configuration."""
        settings = Settings()
        config = settings.get_llm_config("synthesis")

        assert config["model"] == "llama-3.3-70b-versatile"
        assert config["temperature"] == 0.7
        assert config["max_tokens"] == 100
        assert config["timeout_ms"] == 300
        assert "result_synthesis" in config["use_case"]

    def test_get_llm_config_invalid_profile(self):
        """Test get_llm_config raises error for invalid profile."""
        settings = Settings()

        with pytest.raises(ValueError, match="LLM profile 'invalid' not found"):
            settings.get_llm_config("invalid")

    def test_validate_success(self):
        """Test validate returns True for valid settings."""
        env_vars = {"GROQ_API_KEY": "test_key_12345"}

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            is_valid, errors = settings.validate()

            assert is_valid is True
            assert len(errors) == 0

    def test_validate_missing_api_key(self):
        """Test validate detects missing GROQ_API_KEY."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            is_valid, errors = settings.validate()

            assert is_valid is False
            assert "GROQ_API_KEY is required" in errors

    def test_validate_invalid_timeout(self):
        """Test validate detects invalid GROQ_TIMEOUT_MS."""
        env_vars = {"GROQ_API_KEY": "test_key", "GROQ_TIMEOUT_MS": "0"}

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            is_valid, errors = settings.validate()

            assert is_valid is False
            assert "GROQ_TIMEOUT_MS must be positive" in errors

    def test_validate_invalid_history_size(self):
        """Test validate detects invalid MAX_CONVERSATION_HISTORY."""
        env_vars = {"GROQ_API_KEY": "test_key", "MAX_CONVERSATION_HISTORY": "-1"}

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            is_valid, errors = settings.validate()

            assert is_valid is False
            assert "MAX_CONVERSATION_HISTORY must be positive" in errors

    def test_to_dict_masks_api_key(self):
        """Test to_dict masks GROQ_API_KEY in output."""
        env_vars = {"GROQ_API_KEY": "test_key_12345"}

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            config_dict = settings.to_dict()

            assert "GROQ_API_KEY" in config_dict
            assert config_dict["GROQ_API_KEY"] == "***2345"
            assert "test_key" not in config_dict["GROQ_API_KEY"]

    def test_to_dict_handles_missing_api_key(self):
        """Test to_dict handles missing GROQ_API_KEY."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            config_dict = settings.to_dict()

            assert config_dict["GROQ_API_KEY"] == "NOT SET"

    def test_to_dict_includes_all_settings(self):
        """Test to_dict includes all configuration fields."""
        settings = Settings()
        config_dict = settings.to_dict()

        expected_keys = [
            "GROQ_API_KEY",
            "GROQ_BASE_URL",
            "GROQ_MODEL_FAST",
            "GROQ_MODEL_SYNTHESIS",
            "GROQ_TIMEOUT_MS",
            "K0_API_URL",
            "MAX_CONVERSATION_HISTORY",
            "PROACTIVE_COOLDOWN_SECONDS",
            "MIN_BACKGROUND_DURATION_MS",
            "LOG_LEVEL",
            "llm_profiles",
        ]

        for key in expected_keys:
            assert key in config_dict

    def test_llm_profiles_loaded(self):
        """Test LLM profiles are loaded from YAML."""
        settings = Settings()

        assert "fast" in settings._llm_config
        assert "creative" in settings._llm_config
        assert "synthesis" in settings._llm_config
