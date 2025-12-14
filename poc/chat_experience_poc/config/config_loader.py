"""
Configuration Loader

Loads YAML config files, merges with environment variables, and provides singleton access.
Validates all configuration using Pydantic models.

Usage:
    config = ConfigLoader.load("config/poc_config.yml")
    session_config = config.session
    agent_config = config.agent
"""

import os
from pathlib import Path
from typing import Optional

import structlog
import yaml
from models.config_models import POCConfig

logger = structlog.get_logger(__name__)


class ConfigLoader:
    """Load and manage PoC configuration."""

    _instance: Optional["ConfigLoader"] = None
    _config: Optional[POCConfig] = None

    def __new__(cls):
        """Implement singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @staticmethod
    def load(config_path: str = "config/poc_config.yml") -> POCConfig:
        """
        Load configuration from YAML file with environment variable overrides.

        Args:
            config_path: Path to YAML config file (relative to cwd)

        Returns:
            POCConfig instance with all settings

        Raises:
            FileNotFoundError: If config file not found
            ValueError: If configuration is invalid
        """
        # Convert to absolute path if needed
        if not os.path.isabs(config_path):
            config_path = os.path.join(os.getcwd(), config_path)

        config_file = Path(config_path)

        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        logger.info("loading_config", config_path=config_path)

        # Load YAML
        with open(config_file, "r") as f:
            yaml_config = yaml.safe_load(f) or {}

        # Merge environment variables
        config_dict = ConfigLoader._merge_env_vars(yaml_config)

        # Validate and create POCConfig
        try:
            config = POCConfig(**config_dict)
            logger.info(
                "config_loaded",
                environment=config.environment,
                debug=config.debug,
            )
            return config
        except Exception as e:
            logger.error("config_validation_failed", error=str(e))
            raise ValueError(f"Invalid configuration: {str(e)}") from e

    @staticmethod
    def _merge_env_vars(yaml_config: dict) -> dict:
        """
        Merge environment variables into YAML config.

        Environment variables take precedence over YAML.
        Naming convention: K1_POC_<SECTION>_<KEY>
        Example: K1_POC_SESSION_TIMEOUT_SECONDS=900

        Args:
            yaml_config: Configuration dict from YAML

        Returns:
            Merged configuration dict
        """
        config = yaml_config.copy()

        # Define mapping of env vars to config paths
        env_mappings = {
            "K1_POC_ENVIRONMENT": ("environment",),
            "K1_POC_DEBUG": ("debug",),
            "K1_POC_SESSION_TIMEOUT": ("session", "session_timeout_seconds"),
            "K1_POC_SESSION_MAX_TURNS": ("session", "max_turns"),
            "K1_POC_AGENT_POOL_SIZE": ("agent", "agent_pool_size"),
            "K1_POC_K0_API_URL": ("k0_bridge", "k0_api_url"),
            "K1_POC_TICK_INTERVAL": ("temporal", "tick_interval_seconds"),
        }

        for env_var, path in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                # Navigate to nested location
                target = config
                for key in path[:-1]:
                    if key not in target:
                        target[key] = {}
                    target = target[key]

                # Parse value (try int/float/bool first, then string)
                final_key = path[-1]
                if value.lower() in ("true", "false"):
                    target[final_key] = value.lower() == "true"
                elif value.isdigit():
                    target[final_key] = int(value)
                else:
                    try:
                        target[final_key] = float(value)
                    except ValueError:
                        target[final_key] = value

                logger.debug("env_override", env_var=env_var, value=value)

        return config

    @staticmethod
    def get_instance() -> "ConfigLoader":
        """Get singleton instance."""
        return ConfigLoader()


def get_config(config_path: str = "config/poc_config.yml") -> POCConfig:
    """
    Convenience function to load config (singleton-aware).

    Args:
        config_path: Path to YAML config file

    Returns:
        POCConfig instance
    """
    loader = ConfigLoader.get_instance()
    if loader._config is None:
        loader._config = ConfigLoader.load(config_path)
    return loader._config
