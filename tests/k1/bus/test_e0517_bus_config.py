"""
Tests for E-0.5.17 -- Bus Configuration Gaps.

I-0.5.17.1: K1_BUS_BACKEND env var overrides programmatic backend= param.
I-0.5.17.2: k1/bus/config.py loads bus.yaml, falls back to hardcoded defaults.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from k1.bus.envelope import DeliveryMode
from k1.bus.timing.defaults import DEFAULT_MODE, DEFAULT_RULES

# =====================================================================
# I-0.5.17.1 -- K1_BUS_BACKEND env var support
# =====================================================================


class TestBusBackendEnvVar:
    """K1_BUS_BACKEND env var overrides the backend= parameter."""

    def test_env_python_overrides_auto(self):
        from k1.bus.factory import _resolve_backend

        with patch.dict(os.environ, {"K1_BUS_BACKEND": "python"}):
            assert _resolve_backend("auto") == "python"

    def test_env_auto_overrides_python(self):
        """env=auto with no Rust available resolves to python."""
        from k1.bus.factory import _resolve_backend

        with patch.dict(os.environ, {"K1_BUS_BACKEND": "auto"}):
            # auto resolves based on _RUST_AVAILABLE
            result = _resolve_backend("python")
            assert result in ("python", "rust")

    def test_env_invalid_value_ignored(self):
        from k1.bus.factory import _resolve_backend

        with patch.dict(os.environ, {"K1_BUS_BACKEND": "invalid_backend"}):
            # Invalid env var is ignored; programmatic param used
            result = _resolve_backend("python")
            assert result == "python"

    def test_env_empty_string_ignored(self):
        from k1.bus.factory import _resolve_backend

        with patch.dict(os.environ, {"K1_BUS_BACKEND": ""}):
            result = _resolve_backend("python")
            assert result == "python"

    def test_env_whitespace_only_ignored(self):
        from k1.bus.factory import _resolve_backend

        with patch.dict(os.environ, {"K1_BUS_BACKEND": "   "}):
            result = _resolve_backend("python")
            assert result == "python"

    def test_env_case_insensitive(self):
        from k1.bus.factory import _resolve_backend

        with patch.dict(os.environ, {"K1_BUS_BACKEND": "Python"}):
            assert _resolve_backend("auto") == "python"

    def test_env_unset_uses_param(self):
        from k1.bus.factory import _resolve_backend

        with patch.dict(os.environ, {}, clear=False):
            # Remove the key if it exists
            os.environ.pop("K1_BUS_BACKEND", None)
            result = _resolve_backend("python")
            assert result == "python"

    def test_env_rust_without_rust_available_raises(self):
        from k1.bus import factory as fmod

        with (
            patch.dict(os.environ, {"K1_BUS_BACKEND": "rust"}),
            patch.object(fmod, "_RUST_AVAILABLE", False),
        ):
            with pytest.raises(ImportError, match="Rust backend requested"):
                fmod._resolve_backend("python")

    def test_factory_create_local_respects_env(self):
        """BusFactory.create_local() passes through the env var override."""
        from k1.bus.factory import BusFactory

        with patch.dict(os.environ, {"K1_BUS_BACKEND": "python"}):
            bus = BusFactory.create_local(backend="auto")
            # Should get LocalBus (python backend) even though auto was requested
            from k1.bus.impl.local_bus import LocalBus

            assert isinstance(bus, LocalBus)

    def test_factory_create_for_testing_respects_env(self):
        from k1.bus.factory import BusFactory

        with patch.dict(os.environ, {"K1_BUS_BACKEND": "python"}):
            bus = BusFactory.create_for_testing(backend="auto")
            from k1.bus.impl.local_bus import LocalBus

            assert isinstance(bus, LocalBus)


# =====================================================================
# I-0.5.17.2 -- BusConfig + YAML loading
# =====================================================================


class TestBusConfigDataclass:
    """BusConfig is a frozen dataclass with correct defaults."""

    def test_default_construction(self):
        from k1.bus.config import BusConfig

        cfg = BusConfig()
        assert cfg.default_mode == DeliveryMode.RELAXED
        assert cfg.timing_rules == {}
        assert cfg.source == "defaults"

    def test_frozen(self):
        from k1.bus.config import BusConfig

        cfg = BusConfig()
        with pytest.raises(AttributeError):
            cfg.source = "modified"  # type: ignore[misc]

    def test_custom_construction(self):
        from k1.bus.config import BusConfig

        rules = {"k1.test": DeliveryMode.STRICT}
        cfg = BusConfig(
            default_mode=DeliveryMode.BEST_EFFORT,
            timing_rules=rules,
            source="yaml",
        )
        assert cfg.default_mode == DeliveryMode.BEST_EFFORT
        assert cfg.timing_rules == {"k1.test": DeliveryMode.STRICT}
        assert cfg.source == "yaml"


class TestLoadBusConfigFromYaml:
    """load_bus_config() parses a YAML file into BusConfig."""

    def test_load_default_yaml(self):
        """Loading the shipped bus.yaml should match hardcoded defaults."""
        from k1.bus.config import load_bus_config

        cfg = load_bus_config()
        assert cfg.source == "yaml"
        assert cfg.default_mode == DEFAULT_MODE
        assert cfg.timing_rules == DEFAULT_RULES

    def test_load_custom_yaml(self, tmp_path: Path):
        from k1.bus.config import load_bus_config

        yaml_content = textwrap.dedent(
            """\
            default_mode: STRICT
            timing_rules:
              k1.custom: BEST_EFFORT
              k1.other: RELAXED
        """
        )
        yaml_file = tmp_path / "bus.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        cfg = load_bus_config(yaml_file)
        assert cfg.source == "yaml"
        assert cfg.default_mode == DeliveryMode.STRICT
        assert cfg.timing_rules == {
            "k1.custom": DeliveryMode.BEST_EFFORT,
            "k1.other": DeliveryMode.RELAXED,
        }

    def test_load_empty_yaml(self, tmp_path: Path):
        from k1.bus.config import load_bus_config

        yaml_file = tmp_path / "bus.yaml"
        yaml_file.write_text("", encoding="utf-8")

        # empty YAML → safe_load returns None → not a dict → fallback
        cfg = load_bus_config(yaml_file)
        assert cfg.source == "defaults"

    def test_load_yaml_with_unknown_mode(self, tmp_path: Path):
        from k1.bus.config import load_bus_config

        yaml_content = textwrap.dedent(
            """\
            default_mode: RELAXED
            timing_rules:
              k1.valid: STRICT
              k1.bad: INVALID_MODE
        """
        )
        yaml_file = tmp_path / "bus.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        cfg = load_bus_config(yaml_file)
        assert cfg.source == "yaml"
        # Valid rule kept, invalid rule skipped
        assert "k1.valid" in cfg.timing_rules
        assert "k1.bad" not in cfg.timing_rules

    def test_load_yaml_with_unknown_default_mode(self, tmp_path: Path):
        from k1.bus.config import load_bus_config

        yaml_content = textwrap.dedent(
            """\
            default_mode: GARBAGE
            timing_rules:
              k1.test: STRICT
        """
        )
        yaml_file = tmp_path / "bus.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        cfg = load_bus_config(yaml_file)
        # Unknown default → falls back to RELAXED
        assert cfg.default_mode == DeliveryMode.RELAXED
        assert cfg.timing_rules == {"k1.test": DeliveryMode.STRICT}


class TestLoadBusConfigFallback:
    """load_bus_config() falls back to defaults on missing/broken YAML."""

    def test_missing_file_returns_defaults(self, tmp_path: Path):
        from k1.bus.config import load_bus_config

        cfg = load_bus_config(tmp_path / "nonexistent.yaml")
        assert cfg.source == "defaults"
        assert cfg.default_mode == DEFAULT_MODE
        assert cfg.timing_rules == DEFAULT_RULES

    def test_invalid_yaml_returns_defaults(self, tmp_path: Path):
        from k1.bus.config import load_bus_config

        yaml_file = tmp_path / "bus.yaml"
        yaml_file.write_text("{{{{not valid yaml", encoding="utf-8")

        cfg = load_bus_config(yaml_file)
        assert cfg.source == "defaults"

    def test_non_mapping_yaml_returns_defaults(self, tmp_path: Path):
        from k1.bus.config import load_bus_config

        yaml_file = tmp_path / "bus.yaml"
        yaml_file.write_text("- just\n- a\n- list\n", encoding="utf-8")

        cfg = load_bus_config(yaml_file)
        assert cfg.source == "defaults"

    def test_no_pyyaml_returns_defaults(self, tmp_path: Path):
        """If PyYAML is not installed, falls back to defaults."""
        from k1.bus.config import load_bus_config

        yaml_file = tmp_path / "bus.yaml"
        yaml_file.write_text("default_mode: STRICT\n", encoding="utf-8")

        # Simulate yaml import failure
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("No module named 'yaml'")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            cfg = load_bus_config(yaml_file)
            assert cfg.source == "defaults"


class TestBusConfigWithTimingConfig:
    """BusConfig integrates with TimingConfig for end-to-end wiring."""

    def test_config_to_timing_config(self):
        from k1.bus.config import load_bus_config
        from k1.bus.timing.timing_config import TimingConfig

        cfg = load_bus_config()
        tc = TimingConfig(rules=cfg.timing_rules, default=cfg.default_mode)

        # STRICT prefix resolves correctly
        assert tc.resolve("k1.capability.completed.v1") == DeliveryMode.STRICT
        # BEST_EFFORT prefix resolves correctly
        assert tc.resolve("k1.k0.sse.heartbeat") == DeliveryMode.BEST_EFFORT
        # Unknown prefix falls back to default
        assert tc.resolve("k1.unknown.topic") == cfg.default_mode


class TestPackageExports:
    """BusConfig and load_bus_config are exported from k1.bus."""

    def test_bus_config_exported(self):
        from k1.bus import BusConfig

        assert BusConfig is not None

    def test_load_bus_config_exported(self):
        from k1.bus import load_bus_config

        assert callable(load_bus_config)

    def test_in_all(self):
        import k1.bus as bus_mod

        assert "BusConfig" in bus_mod.__all__
        assert "load_bus_config" in bus_mod.__all__
