"""
Version Scanner for K0 Architecture Governance.

Scans and validates version consistency across:
- Config file versions (kernel.yaml, models.yaml, etc.)
- Contract versions (module contracts, pipeline contracts)
- Event topic versions (.v1, .v2 suffixes)
- Schema evolution (migrations vs documented versions)
- Contract artifact versions (VERSION file)

Part of Milestone 4: Version Control Tracking.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class ConfigVersionInfo:
    """Version info for a config file."""

    file_name: str
    version: str
    source_path: str
    status: str = "Active"


@dataclass
class ContractVersionInfo:
    """Version info for a contract file."""

    contract_id: str
    contract_type: str  # module, pipeline, capability, event
    version: str
    file_path: str
    status: str = "Active"


@dataclass
class EventTopicVersionInfo:
    """Version info for event topics."""

    topic: str
    version: str
    source_file: str
    status: str = "Active"


@dataclass
class ArtifactVersionInfo:
    """Version info for contract artifacts with checksums."""

    artifact_type: str
    file_path: str
    version: str
    sha256: str
    status: str = "Active"


def scan_config_versions(config_dir: Path | None = None) -> list[ConfigVersionInfo]:
    """
    Scan version fields in k0/config/*.yaml files.

    Returns list of ConfigVersionInfo with file versions.
    """
    if config_dir is None:
        config_dir = Path("k0/config")

    if not config_dir.exists():
        return []

    versions: list[ConfigVersionInfo] = []

    for config_file in list(config_dir.glob("*.yaml")) + list(config_dir.glob("*.yml")):
        try:
            content = config_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)

            if not data:
                continue

            # Check for top-level version field
            if "version" in data:
                versions.append(
                    ConfigVersionInfo(
                        file_name=config_file.name,
                        version=str(data["version"]),
                        source_path=str(config_file),
                        status="Active",
                    )
                )
        except Exception as e:
            print(f"Warning: Failed to parse {config_file.name}: {e}")

    return versions


def scan_contract_versions(contracts_dir: Path | None = None) -> list[ContractVersionInfo]:
    """
    Scan version fields in contract YAML files.

    Covers:
    - k0/contracts/modules/*.yaml
    - k0/contracts/pipelines/*.yaml
    - k0/contracts/capabilities/*.yaml

    Returns list of ContractVersionInfo.
    """
    if contracts_dir is None:
        contracts_dir = Path("k0/contracts")

    if not contracts_dir.exists():
        return []

    versions: list[ContractVersionInfo] = []

    # Scan module contracts
    modules_dir = contracts_dir / "modules"
    if modules_dir.exists():
        for contract_file in modules_dir.glob("*.yaml"):
            version_info = _extract_contract_version(contract_file, "module")
            if version_info:
                versions.append(version_info)

    # Scan pipeline contracts
    pipelines_dir = contracts_dir / "pipelines"
    if pipelines_dir.exists():
        for contract_file in pipelines_dir.glob("*.yaml"):
            version_info = _extract_contract_version(contract_file, "pipeline")
            if version_info:
                versions.append(version_info)

    # Scan capability contracts
    capabilities_dir = contracts_dir / "capabilities"
    if capabilities_dir.exists():
        for contract_file in capabilities_dir.glob("*.yaml"):
            version_info = _extract_contract_version(contract_file, "capability")
            if version_info:
                versions.append(version_info)

    return versions


def _extract_contract_version(
    contract_file: Path, contract_type: str
) -> ContractVersionInfo | None:
    """Extract version from a contract YAML file."""
    try:
        content = contract_file.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        if not data:
            return None

        # Get version from YAML or from filename pattern (e.g., module.v1.yaml)
        version = None

        if "version" in data:
            version = str(data["version"])
        else:
            # Try to extract from filename: name.v1.yaml -> v1
            match = re.search(r"\.v(\d+)\.yaml$", contract_file.name)
            if match:
                version = f"v{match.group(1)}"

        if version:
            # Extract contract ID from filename
            contract_id = contract_file.stem
            if contract_id.endswith(f".{version}"):
                contract_id = contract_id[: -len(f".{version}")]

            return ContractVersionInfo(
                contract_id=contract_id,
                contract_type=contract_type,
                version=version,
                file_path=str(contract_file),
                status="Active",
            )
    except Exception as e:
        print(f"Warning: Failed to parse contract {contract_file.name}: {e}")

    return None


def scan_event_topic_versions(contracts_dir: Path | None = None) -> list[EventTopicVersionInfo]:
    """
    Scan event topics for version suffixes (.v1, .v2).

    Looks in:
    - k0/contracts/asyncapi.events.yaml
    - Event topic definitions in module contracts

    Returns list of EventTopicVersionInfo.
    """
    if contracts_dir is None:
        contracts_dir = Path("k0/contracts")

    if not contracts_dir.exists():
        return []

    versions: list[EventTopicVersionInfo] = []

    # Scan asyncapi.events.yaml
    asyncapi_file = contracts_dir / "asyncapi.events.yaml"
    if asyncapi_file.exists():
        try:
            content = asyncapi_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)

            if data and "channels" in data:
                for channel_name, channel_data in data["channels"].items():
                    # Extract version from channel name (e.g., cognitive.memory.write.v1)
                    match = re.search(r"\.(v\d+)$", channel_name)
                    if match:
                        versions.append(
                            EventTopicVersionInfo(
                                topic=channel_name,
                                version=match.group(1),
                                source_file="asyncapi.events.yaml",
                                status="Active",
                            )
                        )
        except Exception as e:
            print(f"Warning: Failed to parse asyncapi.events.yaml: {e}")

    # Also scan module contracts for emits/subscribes
    modules_dir = contracts_dir / "modules"
    if modules_dir.exists():
        for contract_file in modules_dir.glob("*.yaml"):
            try:
                content = contract_file.read_text(encoding="utf-8")
                data = yaml.safe_load(content)

                if not data:
                    continue

                # Look for emits and subscribes
                for key in ["emits", "subscribes", "events"]:
                    events = data.get(key, [])
                    if isinstance(events, list):
                        for event in events:
                            if isinstance(event, str):
                                match = re.search(r"\.(v\d+)$", event)
                                if match:
                                    versions.append(
                                        EventTopicVersionInfo(
                                            topic=event,
                                            version=match.group(1),
                                            source_file=contract_file.name,
                                            status="Active",
                                        )
                                    )
                            elif isinstance(event, dict) and "topic" in event:
                                topic = event["topic"]
                                match = re.search(r"\.(v\d+)$", topic)
                                if match:
                                    versions.append(
                                        EventTopicVersionInfo(
                                            topic=topic,
                                            version=match.group(1),
                                            source_file=contract_file.name,
                                            status="Active",
                                        )
                                    )
            except Exception:
                pass

    # Deduplicate by topic
    seen_topics: set[str] = set()
    unique_versions: list[EventTopicVersionInfo] = []
    for v in versions:
        if v.topic not in seen_topics:
            seen_topics.add(v.topic)
            unique_versions.append(v)

    return unique_versions


def scan_artifact_versions(contracts_dir: Path | None = None) -> list[ArtifactVersionInfo]:
    """
    Scan VERSION file for artifact versions and checksums.

    Returns list of ArtifactVersionInfo with versions and checksums.
    Handles all artifact types:
    - openapi, asyncapi (root-level)
    - modules, pipelines, capabilities (versioned contracts)
    - policy, schemas, table_schemas, taxonomies (reference data)
    - jsonschema, jsonschema_examples (JSON schemas)
    """
    if contracts_dir is None:
        contracts_dir = Path("k0/contracts")

    version_file = contracts_dir / "VERSION"
    if not version_file.exists():
        return []

    artifacts: list[ArtifactVersionInfo] = []

    try:
        content = version_file.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        if not data or "artifacts" not in data:
            return []

        artifact_data = data["artifacts"]
        main_version = str(data.get("version", "1.0.0"))

        # OpenAPI artifact (single dict)
        if "openapi" in artifact_data:
            openapi = artifact_data["openapi"]
            artifacts.append(
                ArtifactVersionInfo(
                    artifact_type="openapi",
                    file_path=openapi.get("file", ""),
                    version=str(openapi.get("version", "")),
                    sha256=openapi.get("sha256", ""),
                    status="Active",
                )
            )

        # AsyncAPI artifact (single dict)
        if "asyncapi" in artifact_data:
            asyncapi = artifact_data["asyncapi"]
            artifacts.append(
                ArtifactVersionInfo(
                    artifact_type="asyncapi",
                    file_path=asyncapi.get("file", ""),
                    version=str(asyncapi.get("version", "")),
                    sha256=asyncapi.get("sha256", ""),
                    status="Active",
                )
            )

        # List-based artifact types with explicit versions
        versioned_types = ["modules", "pipelines", "capabilities"]
        for artifact_type in versioned_types:
            if artifact_type in artifact_data:
                for item in artifact_data[artifact_type]:
                    if isinstance(item, dict):
                        artifacts.append(
                            ArtifactVersionInfo(
                                artifact_type=(
                                    artifact_type[:-1]
                                    if artifact_type.endswith("s")
                                    else artifact_type
                                ),
                                file_path=item.get("file", ""),
                                version=str(item.get("version", main_version)),
                                sha256=item.get("sha256", ""),
                                status="Active",
                            )
                        )

        # List-based artifact types without versions (inherit main version)
        unversioned_types = ["policy", "schemas", "table_schemas", "taxonomies"]
        for artifact_type in unversioned_types:
            if artifact_type in artifact_data:
                for item in artifact_data[artifact_type]:
                    if isinstance(item, dict):
                        artifacts.append(
                            ArtifactVersionInfo(
                                artifact_type=(
                                    artifact_type[:-1]
                                    if artifact_type.endswith("s")
                                    else artifact_type
                                ),
                                file_path=item.get("file", ""),
                                version=main_version,
                                sha256=item.get("sha256", ""),
                                status="Active",
                            )
                        )

        # JSON schema artifacts (list)
        if "jsonschema" in artifact_data:
            for schema in artifact_data["jsonschema"]:
                if isinstance(schema, dict):
                    artifacts.append(
                        ArtifactVersionInfo(
                            artifact_type="jsonschema",
                            file_path=schema.get("file", ""),
                            version=main_version,
                            sha256=schema.get("sha256", ""),
                            status="Active",
                        )
                    )

        # JSON schema examples (list)
        if "jsonschema_examples" in artifact_data:
            for example in artifact_data["jsonschema_examples"]:
                if isinstance(example, dict):
                    artifacts.append(
                        ArtifactVersionInfo(
                            artifact_type="jsonschema_example",
                            file_path=example.get("file", ""),
                            version=main_version,
                            sha256=example.get("sha256", ""),
                            status="Active",
                        )
                    )

    except Exception as e:
        print(f"Warning: Failed to parse VERSION file: {e}")

    return artifacts


@dataclass
class ArtifactCheckResult:
    """Result of artifact checksum verification."""

    artifact_type: str
    file_path: str
    expected_sha256: str
    actual_sha256: str | None
    is_valid: bool
    error: str | None = None


def verify_artifact_checksums(contracts_dir: Path | None = None) -> list[ArtifactCheckResult]:
    """
    Verify artifact checksums match actual files.

    Returns list of ArtifactCheckResult with type, path, and validation status.
    """
    if contracts_dir is None:
        contracts_dir = Path("k0/contracts")

    artifacts = scan_artifact_versions(contracts_dir)
    results: list[ArtifactCheckResult] = []

    for artifact in artifacts:
        file_path = contracts_dir / artifact.file_path
        if not file_path.exists():
            results.append(
                ArtifactCheckResult(
                    artifact_type=artifact.artifact_type,
                    file_path=artifact.file_path,
                    expected_sha256=artifact.sha256,
                    actual_sha256=None,
                    is_valid=False,
                    error="File not found",
                )
            )
            continue

        try:
            content = file_path.read_bytes()
            actual_sha256 = hashlib.sha256(content).hexdigest()
            is_valid = actual_sha256 == artifact.sha256
            results.append(
                ArtifactCheckResult(
                    artifact_type=artifact.artifact_type,
                    file_path=artifact.file_path,
                    expected_sha256=artifact.sha256,
                    actual_sha256=actual_sha256,
                    is_valid=is_valid,
                    error=None if is_valid else "Checksum mismatch",
                )
            )
        except Exception as e:
            results.append(
                ArtifactCheckResult(
                    artifact_type=artifact.artifact_type,
                    file_path=artifact.file_path,
                    expected_sha256=artifact.sha256,
                    actual_sha256=None,
                    is_valid=False,
                    error=str(e),
                )
            )

    return results

    return results


def scan_config_versions_from_master(master_path: Path) -> list[ConfigVersionInfo]:
    """
    Extract documented config versions from Part 13 of master.

    Looks for:
    1. Version keys in the config key tables (13.1.x)
    2. Config File Versions table (13.5.1)
    """
    if not master_path.exists():
        return []

    content = master_path.read_text(encoding="utf-8")
    versions: list[ConfigVersionInfo] = []

    # Method 1: Find Part 13.1 section and look for version keys in tables
    section_match = re.search(
        r"## 13\.1 Configuration Keys Registry.*?(?=## 13\.2|# Part \d+:|\Z)",
        content,
        re.DOTALL,
    )

    if section_match:
        section = section_match.group(0)

        # Track current file from headers
        current_file = "unknown"
        file_pattern = re.compile(r"### 13\.1\.\d+\s+[^(]+\(`([^`]+)`\)")

        # Look for version rows: | `version` | string | `X.Y.Z` |
        version_pattern = re.compile(r"\|\s*`version`\s*\|\s*\w+\s*\|\s*`([^`]+)`")

        for line in section.split("\n"):
            # Check for file header
            file_match = file_pattern.search(line)
            if file_match:
                current_file = file_match.group(1)
                continue

            # Check for version row
            version_match = version_pattern.search(line)
            if version_match and current_file != "unknown":
                versions.append(
                    ConfigVersionInfo(
                        file_name=current_file,
                        version=version_match.group(1),
                        source_path=f"master/{current_file}",
                        status="Documented",
                    )
                )

    # Method 2: Find Part 13.5.1 Config File Versions table
    version_section_match = re.search(
        r"### 13\.5\.1 Config File Versions.*?(?=### 13\.5\.2|## 13\.6|# Part \d+:|\Z)",
        content,
        re.DOTALL,
    )

    if version_section_match:
        version_section = version_section_match.group(0)

        # Pattern: | `filename.yaml` | `X.Y.Z` | date | notes |
        file_version_pattern = re.compile(r"\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|")

        for line in version_section.split("\n"):
            match = file_version_pattern.search(line)
            if match:
                file_name = match.group(1)
                version = match.group(2)
                # Skip header row
                if file_name.lower() == "file" or version.lower() == "current version":
                    continue
                # Check if not already found via method 1
                existing_files = {v.file_name for v in versions}
                if file_name not in existing_files:
                    versions.append(
                        ConfigVersionInfo(
                            file_name=file_name,
                            version=version,
                            source_path=f"master/13.5.1/{file_name}",
                            status="Documented",
                        )
                    )

    return versions


def scan_contract_versions_from_master(master_path: Path) -> list[ContractVersionInfo]:
    """
    Extract documented contract versions from master registry tables.

    Looks in:
    - Part 2.1 Pipeline Master Registry (Version column)
    - Part 3.1 Module Master Registry (Version column)
    """
    if not master_path.exists():
        return []

    content = master_path.read_text(encoding="utf-8")
    versions: list[ContractVersionInfo] = []

    # Pipeline version pattern: | P## | Name | ... | v1 | date |
    # Module version pattern: | M## | Name | ... | v1 | date |

    # Pattern for table rows with version column
    # Format: | ID | Name | ... | Version | Last Updated |
    pipeline_pattern = re.compile(
        r"\|\s*(P\d+)\s*\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|\s*(v\d+(?:\.\d+)*)\s*\|"
    )

    module_pattern = re.compile(
        r"\|\s*(M\d+)\s*\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|\s*(v\d+(?:\.\d+)*)\s*\|"
    )

    for line in content.split("\n"):
        # Check for pipeline version
        pipeline_match = pipeline_pattern.search(line)
        if pipeline_match:
            versions.append(
                ContractVersionInfo(
                    contract_id=pipeline_match.group(1),
                    contract_type="pipeline",
                    version=pipeline_match.group(2),
                    file_path="master",
                    status="Documented",
                )
            )
            continue

        # Check for module version
        module_match = module_pattern.search(line)
        if module_match:
            versions.append(
                ContractVersionInfo(
                    contract_id=module_match.group(1),
                    contract_type="module",
                    version=module_match.group(2),
                    file_path="master",
                    status="Documented",
                )
            )

    return versions


def diff_config_versions(
    code_versions: list[ConfigVersionInfo],
    master_versions: list[ConfigVersionInfo],
) -> tuple[set[str], set[str], dict[str, tuple[str, str]]]:
    """
    Compare config versions between code and master.

    Returns:
        - missing_in_master: files in code but not documented
        - missing_in_code: files documented but not in code
        - version_mismatch: {file: (code_version, master_version)}
    """
    code_by_file = {v.file_name: v.version for v in code_versions}
    master_by_file = {v.file_name: v.version for v in master_versions}

    code_files = set(code_by_file.keys())
    master_files = set(master_by_file.keys())

    missing_in_master = code_files - master_files
    missing_in_code = master_files - code_files

    # Check version mismatches for files that exist in both
    version_mismatch: dict[str, tuple[str, str]] = {}
    for file_name in code_files & master_files:
        code_ver = code_by_file[file_name]
        master_ver = master_by_file[file_name]
        if code_ver != master_ver:
            version_mismatch[file_name] = (code_ver, master_ver)

    return missing_in_master, missing_in_code, version_mismatch


def diff_contract_versions(
    code_versions: list[ContractVersionInfo],
    master_versions: list[ContractVersionInfo],
) -> tuple[set[str], set[str], dict[str, tuple[str, str]]]:
    """
    Compare contract versions between code and master.

    Returns:
        - missing_in_master: contracts in code but not documented
        - missing_in_code: contracts documented but not in code
        - version_mismatch: {contract_id: (code_version, master_version)}
    """
    # Group by contract ID
    code_by_id = {v.contract_id: v.version for v in code_versions}
    master_by_id = {v.contract_id: v.version for v in master_versions}

    code_ids = set(code_by_id.keys())
    master_ids = set(master_by_id.keys())

    missing_in_master = code_ids - master_ids
    missing_in_code = master_ids - code_ids

    # Check version mismatches
    version_mismatch: dict[str, tuple[str, str]] = {}
    for contract_id in code_ids & master_ids:
        code_ver = code_by_id[contract_id]
        master_ver = master_by_id[contract_id]
        if code_ver != master_ver:
            version_mismatch[contract_id] = (code_ver, master_ver)

    return missing_in_master, missing_in_code, version_mismatch


# Main entry point for testing
if __name__ == "__main__":
    print("=== Config Versions ===")
    config_versions = scan_config_versions()
    for v in config_versions:
        print(f"  {v.file_name}: {v.version}")

    print("\n=== Contract Versions ===")
    contract_versions = scan_contract_versions()
    for v in contract_versions:
        print(f"  [{v.contract_type}] {v.contract_id}: {v.version}")

    print("\n=== Event Topic Versions ===")
    event_versions = scan_event_topic_versions()
    for v in event_versions:
        print(f"  {v.topic}: {v.version}")

    print("\n=== Artifact Versions ===")
    artifact_versions = scan_artifact_versions()
    for v in artifact_versions:
        print(f"  [{v.artifact_type}] {v.file_path}: {v.version}")

    print("\n=== Checksum Verification ===")
    checksums = verify_artifact_checksums()
    for result in checksums:
        status = "VALID" if result.is_valid else f"INVALID ({result.error})"
        print(f"  [{result.artifact_type}] {result.file_path}: {status}")
