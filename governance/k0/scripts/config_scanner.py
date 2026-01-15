"""
Config Scanner for K0 Architecture Governance.

Scans configuration keys and feature flags from
Part 13 of k0_architecture_master.md and the config directory.

Scanner Categories:
- Config Keys: Part 13.1 keys across YAML/Python config files
- Feature Flags: Part 13.2 feature flag definitions

Usage:
    from governance.k0.scripts.config_scanner import (
        scan_config_keys_from_yaml,
        scan_feature_flags,
        diff_config_with_master,
    )
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def _get_repo_root() -> Path:
    """Get the repository root directory."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


@dataclass
class ConfigKeyInfo:
    """Information about a configuration key."""

    key_id: str  # e.g., "CFG-001"
    key_path: str  # e.g., "kernel.concurrency.max_workers"
    source_file: str  # e.g., "kernel.yaml"
    value_type: str  # e.g., "int", "str", "bool", "list"
    default_value: str = ""
    description: str = ""
    status: str = "Active"


@dataclass
class FeatureFlagInfo:
    """Information about a feature flag."""

    flag_id: str  # e.g., "FF-001"
    name: str  # e.g., "hippocampus.graph_storage"
    module: str  # e.g., "hippocampus"
    enabled_tier: str  # e.g., "dev", "staging", "prod"
    fallback_tier: str  # e.g., "off"
    rollout_percentage: int = 100
    status: str = "Active"


def scan_config_keys_from_yaml(config_dir: Path | None = None) -> list[ConfigKeyInfo]:
    """
    Scan configuration keys from YAML files in k0/config/.

    Returns list of ConfigKeyInfo with key details.
    """
    if config_dir is None:
        config_dir = _get_repo_root() / "k0" / "config"

    if not config_dir.exists():
        return []

    configs: list[ConfigKeyInfo] = []
    key_counter = 1

    for config_file in sorted(config_dir.glob("*.yaml")) + sorted(config_dir.glob("*.yml")):
        try:
            content = config_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)

            if not data:
                continue

            # Recursively extract keys
            keys = _extract_keys_recursive(data, prefix="", source=config_file.name)
            for key_path, value_type, default_value in keys:
                configs.append(
                    ConfigKeyInfo(
                        key_id=f"CFG-{key_counter:03d}",
                        key_path=key_path,
                        source_file=config_file.name,
                        value_type=value_type,
                        default_value=str(default_value)[:50],
                        status="Active",
                    )
                )
                key_counter += 1

        except Exception as e:
            print(f"Warning: Failed to parse {config_file.name}: {e}")

    return configs


def _extract_keys_recursive(
    data: dict | list | Any,
    prefix: str,
    source: str,
) -> list[tuple[str, str, Any]]:
    """Recursively extract configuration keys from nested structures."""
    keys: list[tuple[str, str, Any]] = []

    if isinstance(data, dict):
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                # Recurse into nested dicts
                keys.extend(_extract_keys_recursive(value, full_key, source))
            elif isinstance(value, list):
                # Record list itself and recurse if has dict items
                keys.append((full_key, "list", f"[{len(value)} items]"))
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        keys.extend(_extract_keys_recursive(item, f"{full_key}[{i}]", source))
            else:
                value_type = type(value).__name__
                keys.append((full_key, value_type, value))

    return keys


def scan_feature_flags(config_dir: Path | None = None) -> list[FeatureFlagInfo]:
    """
    Scan feature flag definitions from feature_flags.yaml.

    Returns list of FeatureFlagInfo with flag details.
    """
    if config_dir is None:
        config_dir = _get_repo_root() / "k0" / "config"

    flags_file = config_dir / "feature_flags.yaml"
    if not flags_file.exists():
        return []

    try:
        content = flags_file.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
    except Exception as e:
        print(f"Warning: Failed to parse feature_flags.yaml: {e}")
        return []

    if not data:
        return []

    flags: list[FeatureFlagInfo] = []
    flag_counter = 1

    # Handle different possible structures
    flags_section = data.get("feature_flags", data)

    if isinstance(flags_section, dict):
        for module_name, module_flags in flags_section.items():
            if not isinstance(module_flags, dict):
                continue

            for flag_name, flag_config in module_flags.items():
                if not isinstance(flag_config, dict):
                    continue

                flags.append(
                    FeatureFlagInfo(
                        flag_id=f"FF-{flag_counter:03d}",
                        name=f"{module_name}.{flag_name}",
                        module=module_name,
                        enabled_tier=str(flag_config.get("enabled_tier", "dev")),
                        fallback_tier=str(flag_config.get("fallback_tier", "off")),
                        rollout_percentage=int(flag_config.get("rollout_percentage", 100)),
                        status="Active",
                    )
                )
                flag_counter += 1

    return flags


def scan_config_from_master(master_path: Path) -> list[ConfigKeyInfo]:
    """
    Extract config keys from Part 13.1 of master document.

    Matches the existing master format: | Key | Type | Default | Description | Used By | Required? |
    """
    if not master_path.exists():
        return []

    content = master_path.read_text(encoding="utf-8")
    configs: list[ConfigKeyInfo] = []

    # Find Part 13.1 section only (Configuration Keys), stopping at 13.2 or Part 14
    section_match = re.search(
        r"## 13\.1 Configuration Keys Registry.*?(?=## 13\.2|# Part \d+:|\Z)",
        content,
        re.DOTALL,
    )

    if not section_match:
        return []

    section = section_match.group(0)
    config_counter = 1

    # Track current source file from headers
    # Pattern: ### 13.1.X Name Configuration (`filename`) or ### 13.1.X Name (`filename`)
    current_file = "unknown"
    file_pattern = re.compile(r"### 13\.1\.\d+\s+[^(]+\(`([^`]+)`\)")

    # Invalid "types" that indicate file reference rows, not config keys
    invalid_types = {"yaml", "yml", "python", "py", "dotenv", "env", "json", "toml"}

    for line in section.split("\n"):
        # Check for file header
        file_match = file_pattern.search(line)
        if file_match:
            current_file = file_match.group(1)
            continue

        # Pattern: | `key.path` | type | default | description | used_by | required |
        # Note: key pattern includes uppercase for env vars like NEO4J_AUTH
        config_pattern = re.compile(
            r"\|\s*`([a-zA-Z0-9_.\-]+)`\s*\|\s*(\w+)\s*\|\s*([^|]*)\s*\|\s*([^|]*)\s*\|"
        )

        match = config_pattern.search(line)
        if match:
            key_path = match.group(1).strip()
            value_type = match.group(2).strip()
            default_value = match.group(3).strip()

            # Skip header rows
            if key_path.lower() == "key" or value_type.lower() == "type":
                continue

            # Skip file reference rows (where "type" is actually a file format)
            if value_type.lower() in invalid_types:
                continue

            configs.append(
                ConfigKeyInfo(
                    key_id=f"CFG-{config_counter:03d}",
                    key_path=key_path,
                    source_file=current_file,
                    value_type=value_type,
                    default_value=default_value[:50],
                    status="Active",
                )
            )
            config_counter += 1

    return configs


def scan_feature_flags_from_master(master_path: Path) -> list[FeatureFlagInfo]:
    """
    Extract feature flag definitions from Part 13.2 of master document.

    Matches: | `flag.name` | `enabled_tier` | `fallback_tier` | 100% | 5 | description | status |
    """
    if not master_path.exists():
        return []

    content = master_path.read_text(encoding="utf-8")
    flags: list[FeatureFlagInfo] = []

    # Find section 13.2 - extends to 13.3 or Part 14
    section_match = re.search(
        r"## 13\.2 Feature Flags Registry.*?(?=## 13\.3|# Part |\Z)",
        content,
        re.DOTALL,
    )

    if not section_match:
        return []

    section = section_match.group(0)
    flag_counter = 1

    # Pattern: | `flag.name` | `tier` | `fallback` | 100% | ...
    # The format is: | `name` | `enabled` | `fallback` | percent% | failures | desc | status |
    flag_pattern = re.compile(
        r"\|\s*`([a-z0-9_.]+)`\s*\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|\s*(\d+)%"
    )

    for line in section.split("\n"):
        match = flag_pattern.search(line)
        if match:
            name = match.group(1).strip()
            enabled_tier = match.group(2).strip()
            fallback_tier = match.group(3).strip()
            rollout = int(match.group(4).strip())

            # Skip header rows
            if name.lower() in ("flag name", "flag"):
                continue

            # Extract module from name (e.g., "hippocampus.semantic_project" -> "hippocampus")
            module = name.split(".")[0] if "." in name else name

            flags.append(
                FeatureFlagInfo(
                    flag_id=f"FF-{flag_counter:03d}",
                    name=name,
                    module=module,
                    enabled_tier=enabled_tier,
                    fallback_tier=fallback_tier,
                    rollout_percentage=rollout,
                    status="Active",
                )
            )
            flag_counter += 1

    return flags


def diff_config_with_master(code_configs: list[ConfigKeyInfo], master_path: Path) -> dict[str, Any]:
    """
    Compare scanned config keys from code with Part 13.1 registry.

    Note: Master document has curated important keys, not exhaustive list.
    We compare the documented keys exist in code. Undocumented code keys
    are reported but marked as 'curated' (not strict drift).

    PostgreSQL keys from postgres.py are exempt from code-scan since they're
    documented in master but the Python file uses pydantic settings (not YAML).
    """
    master_configs = scan_config_from_master(master_path)

    # Get the key paths from code - use just the final key name for matching
    # since master uses short names and code uses full paths
    code_keys_full = {c.key_path for c in code_configs}
    code_keys_leaf = {c.key_path.split(".")[-1] for c in code_configs}

    # Get master keys - may use shorter paths
    master_keys = {c.key_path for c in master_configs}

    # Keys in master but not in code (potential documentation errors)
    # Match if either full path or leaf name matches
    # Also filter out file names, secrets, and postgres.py keys (pydantic, not YAML)
    false_positive_patterns = {".yaml", ".yml", ".py", ".env", "password", "secret"}

    # postgres.py config keys - these are pydantic settings, not YAML
    postgres_exempt_keys = {
        "host",
        "port",
        "database",
        "user",
        "min_pool_size",
        "max_pool_size",
        "ssl_mode",
        "ssl_root_cert",
        "vector_dimensions",
        "statement_cache_size",
        "command_timeout",
    }

    missing_in_code = set()
    for mk in master_keys:
        # Check if key exists in code (full match or leaf match)
        if mk in code_keys_full or mk in code_keys_leaf:
            continue
        # Check if it's a false positive
        if any(fp in mk.lower() for fp in false_positive_patterns):
            continue
        # Exempt postgres.py pydantic keys
        if mk in postgres_exempt_keys:
            continue
        missing_in_code.add(mk)

    # Calculate undocumented keys (in code but not in master)
    # This is informational - config keys are curated, not exhaustive
    documented_code_keys = set()
    for ck in code_keys_full:
        leaf = ck.split(".")[-1]
        if ck in master_keys or leaf in master_keys:
            documented_code_keys.add(ck)

    undocumented = code_keys_full - documented_code_keys

    return {
        "missing_in_master": undocumented,  # Informational (curated category)
        "missing_in_code": missing_in_code,
        "scanned_count": len(code_configs),
        "registered_count": len(master_configs),
        "planning_count": 0,
        "is_curated": True,  # Flag that this category is curated, not exhaustive
    }


def diff_feature_flags_with_master(
    code_flags: list[FeatureFlagInfo], master_path: Path
) -> dict[str, Any]:
    """
    Compare scanned feature flags from code with Part 13.2 registry.

    Handles prefix normalization (modules.hippocampus.x -> hippocampus.x).
    """
    master_flags = scan_feature_flags_from_master(master_path)

    # Normalize code flag names (remove "modules." prefix)
    def normalize(name: str) -> str:
        if name.startswith("modules."):
            return name[8:]
        if name.startswith("rollout_schedule."):
            return name  # Keep rollout schedules as-is
        return name

    code_names = {normalize(f.name) for f in code_flags}
    master_names = {f.name for f in master_flags}
    planning_names = {f.name for f in master_flags if f.status == "Planning"}

    # Filter out rollout_schedule flags (infrastructure, not module flags)
    code_module_flags = {n for n in code_names if not n.startswith("rollout_schedule.")}

    return {
        "missing_in_master": code_module_flags - master_names,
        "missing_in_code": master_names - code_names - planning_names,
        "scanned_count": len(code_module_flags),
        "registered_count": len(master_flags),
        "planning_count": len(planning_names),
    }


if __name__ == "__main__":
    # Quick test
    print("=" * 60)
    print("Config Scanner Test")
    print("=" * 60)

    master_path = _get_repo_root() / "governance" / "k0" / "k0_architecture_master.md"

    print("\n[1] Scanning config keys from YAML...")
    configs = scan_config_keys_from_yaml()
    print(f"Found {len(configs)} config keys:")
    for c in configs[:10]:
        print(f"  {c.key_id}: {c.key_path} ({c.value_type}) [{c.source_file}]")
    if len(configs) > 10:
        print(f"  ... and {len(configs) - 10} more")

    print("\n[2] Scanning feature flags...")
    flags = scan_feature_flags()
    print(f"Found {len(flags)} feature flags:")
    for f in flags[:10]:
        print(f"  {f.flag_id}: {f.name} ({f.enabled_tier}) [{f.module}]")
    if len(flags) > 10:
        print(f"  ... and {len(flags) - 10} more")

    print("\n[3] Scanning config keys from master...")
    master_configs = scan_config_from_master(master_path)
    print(f"Found {len(master_configs)} config keys in master:")
    for c in master_configs[:5]:
        print(f"  {c.key_id}: {c.key_path} ({c.status})")
    if len(master_configs) > 5:
        print(f"  ... and {len(master_configs) - 5} more")

    print("\n[4] Scanning feature flags from master...")
    master_flags = scan_feature_flags_from_master(master_path)
    print(f"Found {len(master_flags)} feature flags in master:")
    for f in master_flags[:5]:
        print(f"  {f.flag_id}: {f.name} ({f.status})")
    if len(master_flags) > 5:
        print(f"  ... and {len(master_flags) - 5} more")

    print("\n[5] Testing diff...")
    if configs:
        diff = diff_config_with_master(configs, master_path)
        print(f"Config Keys - Code: {diff['scanned_count']}, Master: {diff['registered_count']}")
        if diff["missing_in_master"]:
            print(f"  Missing in master: {len(diff['missing_in_master'])}")

    if flags:
        diff = diff_feature_flags_with_master(flags, master_path)
        print(f"Feature Flags - Code: {diff['scanned_count']}, Master: {diff['registered_count']}")
        if diff["missing_in_master"]:
            print(f"  Missing in master: {len(diff['missing_in_master'])}")
