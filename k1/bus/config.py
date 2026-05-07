"""
k1.bus.config -- Bus configuration loader.

Loads bus timing rules and default delivery mode from ``k1/config/bus.yaml``.
Falls back to the hardcoded defaults in ``k1.bus.timing.defaults`` when the
YAML file is missing or unparseable.

Usage::

    from k1.bus.config import load_bus_config

    config = load_bus_config()           # auto-discover bus.yaml
    config = load_bus_config(path)       # explicit path

    # Use directly with TimingConfig
    from k1.bus.timing.timing_config import TimingConfig
    tc = TimingConfig(rules=config.timing_rules, default=config.default_mode)

V2 Design Ref: Bus ARCHITECTURE.md §3.5
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from k1.bus.envelope import DeliveryMode

logger = logging.getLogger(__name__)

# Default YAML location relative to repo root
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "bus.yaml"

_MODE_MAP: dict[str, DeliveryMode] = {
    "STRICT": DeliveryMode.STRICT,
    "RELAXED": DeliveryMode.RELAXED,
    "BEST_EFFORT": DeliveryMode.BEST_EFFORT,
}


@dataclass(frozen=True)
class BusConfig:
    """Parsed bus configuration.

    Attributes:
        default_mode: Fallback delivery mode for unmatched topics.
        timing_rules: Mapping of topic prefix → DeliveryMode.
        source: Where the config was loaded from ("yaml", "defaults").
    """

    default_mode: DeliveryMode = DeliveryMode.RELAXED
    timing_rules: dict[str, DeliveryMode] = field(default_factory=dict)
    source: str = "defaults"


def load_bus_config(
    path: Optional[Path | str] = None,
) -> BusConfig:
    """Load bus configuration from YAML, falling back to hardcoded defaults.

    Args:
        path: Explicit path to ``bus.yaml``.  If None, uses the default
              location ``k1/config/bus.yaml``.

    Returns:
        BusConfig with timing rules and default mode.

    The function never raises — any parse/IO error falls back to defaults
    with a logged warning.
    """
    config_path = Path(path) if path is not None else _DEFAULT_CONFIG_PATH

    if not config_path.is_file():
        logger.debug("Bus config not found at %s, using hardcoded defaults", config_path)
        return _from_defaults()

    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not installed, using hardcoded defaults")
        return _from_defaults()

    try:
        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except Exception:
        logger.warning("Failed to parse %s, using hardcoded defaults", config_path, exc_info=True)
        return _from_defaults()

    if not isinstance(data, dict):
        logger.warning("Bus config is not a mapping, using hardcoded defaults")
        return _from_defaults()

    return _parse_config(data)


def _parse_config(data: dict) -> BusConfig:
    """Parse a raw YAML dict into BusConfig."""
    # Default mode
    raw_default = str(data.get("default_mode", "RELAXED")).upper()
    default_mode = _MODE_MAP.get(raw_default, DeliveryMode.RELAXED)
    if raw_default not in _MODE_MAP:
        logger.warning(
            "Unknown default_mode %r in bus.yaml, falling back to RELAXED",
            raw_default,
        )

    # Timing rules
    raw_rules = data.get("timing_rules", {})
    if not isinstance(raw_rules, dict):
        logger.warning("timing_rules is not a mapping, ignoring")
        raw_rules = {}

    timing_rules: dict[str, DeliveryMode] = {}
    for prefix, mode_str in raw_rules.items():
        mode_upper = str(mode_str).upper()
        mode = _MODE_MAP.get(mode_upper)
        if mode is None:
            logger.warning(
                "Unknown mode %r for prefix %r in bus.yaml, skipping",
                mode_str,
                prefix,
            )
            continue
        timing_rules[str(prefix)] = mode

    return BusConfig(
        default_mode=default_mode,
        timing_rules=timing_rules,
        source="yaml",
    )


def _from_defaults() -> BusConfig:
    """Create BusConfig from the hardcoded defaults."""
    from k1.bus.timing.defaults import DEFAULT_MODE, DEFAULT_RULES

    return BusConfig(
        default_mode=DEFAULT_MODE,
        timing_rules=dict(DEFAULT_RULES),
        source="defaults",
    )
