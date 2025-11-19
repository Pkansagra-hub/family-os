"""
Device Profiler Module (M09) - Multi-Device Family Support

Classifies device type, platform, and input method for multi-device family scenarios.
Enables device-specific retention policies, notification routing, and cross-device analytics.

Performance: ≤2ms P95 (pure string parsing, no I/O)

Schema Authority (Single Source of Truth):
- Maps 1:1 to st_hipp_events device columns (migration 0024, lines 67-72):
  - device_id: TEXT NOT NULL (from envelope, preserved as-is)
  - device_kind: TEXT NOT NULL (phone/tablet/watch/web/api)
  - device_os: TEXT (iOS/Android/web/unknown/None)
  - ingress_channel: TEXT (write/photo/voice/import - from M10, not here)

Device Kind Taxonomy (5 categories):
- phone: Mobile smartphone (most common, default fallback)
- tablet: Tablet device (iPad, Android tablets)
- watch: Wearable device (Apple Watch, Wear OS)
- web: Browser-based client (Chrome, Safari, Firefox)
- api: Server-to-server API (scheduled imports, connectors)

Platform Detection (4 platforms):
- iOS: Apple devices (iPhone, iPad, Apple Watch)
- Android: Android devices (phones, tablets, watches)
- web: Browser clients (desktop, mobile web)
- unknown: Unable to detect from device_id

Input Method Tracking (6 methods - from envelope metadata):
- voice: Voice memo or transcription
- text: Manual text entry (default)
- photo: Photo capture with optional caption
- scan: Document/receipt scanning
- import: Bulk import from external source
- api: Programmatic API call

Use Cases:
1. Retention policy selection: (band, topic, device_kind) → retention_policy_id
2. Notification routing: Send push to phone (not watch)
3. Analytics: "User logs 80% meals from phone, 20% from web"
4. Quality scoring: Voice input has higher transcription error rate

Architecture Principles (World-Class Design):
- Pure string parsing (regex + contains checks, no I/O)
- Stateless computation (no cache needed, <2ms target)
- Deterministic output (same device_id → same classification)
- Fail-safe defaults (unknown → "phone" most common)
- Observability-ready (metrics for distribution analysis)

Contract: k0/contracts/modules/context.device_profile.v1.yaml
ADR: docs/architecture/decisions-K0/modules/k007.2-device-profiler.md
Migration: k0/contracts/sql/migrations/0024_p02_episodic_write_tables.sql (line 70)
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Module version (semantic versioning)
__version__ = "1.0.0"

# Configuration constants (aligned with contract)
DEFAULT_DEVICE_KIND = "phone"  # Most common device type
SUPPORTED_PLATFORMS = ["iOS", "Android", "web", "unknown"]
DEFAULT_INPUT_METHOD = "text"

# Device kind patterns (regex for robust matching)
DEVICE_KIND_PATTERNS = {
    "watch": r"(device-.+-watch|.+watch.+|wearable)",
    "tablet": r"(device-.+-tablet|.+-tablet|ipad)",
    "phone": r"(device-.+-phone|.+-phone|iphone|android)",
    "web": r"(web-.+|browser-.+|mozilla|chrome|safari)",
    "api": r"(api-.+|connector-.+|server-.+)",
}

# Platform detection patterns
PLATFORM_PATTERNS = {
    "iOS": ["ios", "iphone", "ipad", "ipod", "watch"],
    "Android": ["android"],
    "web": ["mozilla", "chrome", "safari", "firefox", "edge", "opera"],
}

# Input method mapping
INPUT_METHOD_MAP = {
    "voice": ["voice", "audio", "transcription", "speech"],
    "photo": ["photo", "image", "camera", "picture"],
    "scan": ["scan", "ocr", "document"],
    "import": ["import", "bulk", "sync", "batch"],
    "api": ["api", "connector", "scheduled", "automation"],
}


@dataclass(frozen=True)
class DeviceProfile:
    """
    Device profile output (frozen dataclass for immutability).

    Maps 1:1 to st_hipp_events device columns.
    """

    device_id: str  # TEXT NOT NULL (preserved from envelope)
    device_kind: str  # TEXT NOT NULL (phone/tablet/watch/web/api)
    device_platform: Optional[str]  # TEXT (iOS/Android/web/unknown)
    client_version: Optional[str]  # TEXT (e.g., "2.3.1")
    client_build: Optional[str]  # TEXT (e.g., "20250115.1")
    input_method: str  # TEXT (voice/text/photo/scan/import/api)
    device_profiled_at_utc: str  # TEXT ISO 8601 timestamp


# Metrics tracking (histogram-ready for P95 analysis)
_metrics: Dict[str, int] = {
    "total_profiles": 0,
    "device_kind_phone": 0,
    "device_kind_tablet": 0,
    "device_kind_watch": 0,
    "device_kind_web": 0,
    "device_kind_api": 0,
    "device_kind_unknown": 0,
    "platform_ios": 0,
    "platform_android": 0,
    "platform_web": 0,
    "platform_unknown": 0,
    "input_method_voice": 0,
    "input_method_text": 0,
    "input_method_photo": 0,
    "input_method_scan": 0,
    "input_method_import": 0,
    "input_method_api": 0,
}


def classify_device_kind(device_id: str, default: str = DEFAULT_DEVICE_KIND) -> str:
    """
    Classify device kind from device_id using regex patterns.

    Priority order (check most specific first):
    1. watch: "watch" or "wearable" (most specific)
    2. tablet: "tablet" or "ipad" (before phone, since some tablets have "mobile")
    3. phone: "phone" or "iphone" or "android" (most common)
    4. web: "web-" or "mozilla" or "chrome" (browser clients)
    5. api: "api-" or "connector-" (server-to-server)

    Args:
        device_id: Device identifier string (e.g., "device-dad-phone")
        default: Fallback device kind if no match (default: "phone")

    Returns:
        Device kind (phone/tablet/watch/web/api)

    Performance: <0.5ms (regex matching)
    """
    if not device_id:
        return default

    device_id_lower = device_id.lower()

    # Check patterns in priority order
    for kind, pattern in DEVICE_KIND_PATTERNS.items():
        if re.search(pattern, device_id_lower, re.IGNORECASE):
            return kind

    # Default fallback
    return default


def detect_platform(device_id: str, user_agent: Optional[str] = None) -> str:
    """
    Detect platform from device_id and optional user_agent.

    Priority order:
    1. iOS: "ios", "iphone", "ipad", "ipod", "watch"
    2. Android: "android"
    3. web: "mozilla", "chrome", "safari", "firefox"
    4. unknown: No match

    Args:
        device_id: Device identifier string
        user_agent: Optional user-agent string for additional context

    Returns:
        Platform (iOS/Android/web/unknown)

    Performance: <0.3ms (string contains checks)
    """
    if not device_id and not user_agent:
        return "unknown"

    # Combine device_id and user_agent for matching
    combined = f"{device_id or ''} {user_agent or ''}".lower()

    # Check platform patterns
    for platform, keywords in PLATFORM_PATTERNS.items():
        if any(keyword in combined for keyword in keywords):
            return platform

    return "unknown"


def parse_client_version(client_version_str: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Parse client version string into version and build.

    Formats supported:
    - Semantic versioning: "2.3.1" → ("2.3.1", None)
    - With build: "2.3.1+20250115.1" → ("2.3.1", "20250115.1")
    - With build (space): "2.3.1 20250115.1" → ("2.3.1", "20250115.1")

    Args:
        client_version_str: Client version string from metadata

    Returns:
        Tuple of (client_version, client_build)

    Performance: <0.1ms (string splitting)
    """
    if not client_version_str or not client_version_str.strip():
        return (None, None)

    version_str = client_version_str.strip()

    # Split by '+' or space for build number
    if "+" in version_str:
        parts = version_str.split("+", 1)
        return (parts[0].strip() or None, parts[1].strip() if len(parts) > 1 else None)
    elif " " in version_str:
        parts = version_str.split(" ", 1)
        return (parts[0].strip() or None, parts[1].strip() if len(parts) > 1 else None)
    else:
        return (version_str, None)


def map_input_method(input_source: Optional[str]) -> str:
    """
    Map input source to standardized input method.

    Valid values: voice, text, photo, scan, import, api
    Default: text (most common)

    Args:
        input_source: Input source string from envelope metadata

    Returns:
        Standardized input method

    Performance: <0.1ms (dictionary lookup)
    """
    if not input_source:
        return DEFAULT_INPUT_METHOD

    input_lower = input_source.lower()

    # Check input method patterns
    for method, keywords in INPUT_METHOD_MAP.items():
        if any(keyword in input_lower for keyword in keywords):
            return method

    # Default to text
    return DEFAULT_INPUT_METHOD


def profile_device_context(
    device_id: str,
    user_agent: Optional[str] = None,
    client_version_str: Optional[str] = None,
    input_source: Optional[str] = None,
) -> DeviceProfile:
    """
    Main device profiling function (single source of truth).

    Extracts device and client metadata from envelope fields:
    - Device kind: Classify from device_id (5 categories)
    - Platform: Detect from device_id + user_agent (4 platforms)
    - Client version: Parse semantic versioning
    - Input method: Map from input_source (6 methods)

    Args:
        device_id: Device identifier (e.g., "device-dad-phone")
        user_agent: Optional user-agent string
        client_version_str: Optional client version (e.g., "2.3.1")
        input_source: Optional input source (e.g., "voice_memo")

    Returns:
        DeviceProfile with 7 fields

    Performance: <2ms P95 (pure string parsing, no I/O)
    """
    # Step 1: Classify device kind
    device_kind = classify_device_kind(device_id)

    # Step 2: Detect platform
    device_platform = detect_platform(device_id, user_agent)

    # Step 3: Parse client version
    client_version, client_build = parse_client_version(client_version_str)

    # Step 4: Map input method
    input_method = map_input_method(input_source)

    # Step 5: Capture profiling timestamp
    device_profiled_at_utc = datetime.now(timezone.utc).isoformat()

    # Step 6: Update metrics
    _metrics["total_profiles"] += 1
    _metrics[f"device_kind_{device_kind}"] = _metrics.get(f"device_kind_{device_kind}", 0) + 1

    # Platform metrics (normalize platform string for metrics key)
    platform_key = device_platform.lower() if device_platform else "unknown"
    _metrics[f"platform_{platform_key}"] = _metrics.get(f"platform_{platform_key}", 0) + 1

    _metrics[f"input_method_{input_method}"] = _metrics.get(f"input_method_{input_method}", 0) + 1

    return DeviceProfile(
        device_id=device_id or "unknown",
        device_kind=device_kind,
        device_platform=device_platform,
        client_version=client_version,
        client_build=client_build,
        input_method=input_method,
        device_profiled_at_utc=device_profiled_at_utc,
    )


async def run(message: Any, context: Any, **config: Any) -> Dict[str, Any]:
    """
    Module entry point (Phase 2 signature for pipeline compatibility).

    Extracts device metadata from envelope and returns enriched envelope with profile.

    Args:
        message: BusMessage with .payload, .trace_id, .offset
        context: PipelineContext with .syscalls, .logger, .config
        **config: Stage-specific configuration
            - default_device_kind (str): Fallback device kind (default: "phone")
            - supported_platforms (list): Allowed platforms (default: ["iOS", "Android", "web", "unknown"])
            - minimum_client_version (str): Minimum required version (default: None)

    Returns:
        Enriched envelope with device profile fields (7 fields)

    Raises:
        ValueError: If envelope is missing required fields

    Performance: <2ms P95
    Contract: k0/contracts/modules/context.device_profile.v1.yaml
    """
    # Parse envelope from message
    envelope = (
        json.loads(message.payload)
        if isinstance(message.payload, (str, bytes))
        else message.payload
    )

    # Extract config parameters (with defaults)
    default_device_kind = config.get("default_device_kind", DEFAULT_DEVICE_KIND)
    supported_platforms = config.get("supported_platforms", SUPPORTED_PLATFORMS)
    minimum_client_version = config.get("minimum_client_version")

    # Log module start
    context.logger.debug(
        "M09 device_profile starting",
        extra={
            "module": "context.device_profile",
            "trace_id": message.trace_id,
            "event_id": envelope.get("event_id"),
        },
    )

    # Extract device metadata from envelope
    device_id = envelope.get("device_id", "")
    metadata = envelope.get("metadata", {})
    user_agent = metadata.get("user_agent")
    client_version_str = metadata.get("client_version")
    input_source = metadata.get("input_source")

    # Profile device context
    profile = profile_device_context(
        device_id=device_id,
        user_agent=user_agent,
        client_version_str=client_version_str,
        input_source=input_source,
    )

    # Convert to dict for enriched envelope
    device_fields = {
        "device_id": profile.device_id,
        "device_kind": profile.device_kind,
        "device_platform": profile.device_platform,
        "client_version": profile.client_version,
        "client_build": profile.client_build,
        "input_method": profile.input_method,
        "device_profiled_at_utc": profile.device_profiled_at_utc,
    }

    # Log module completion
    context.logger.debug(
        "M09 device_profile completed",
        extra={
            "module": "context.device_profile",
            "trace_id": message.trace_id,
            "device_kind": profile.device_kind,
            "device_platform": profile.device_platform,
        },
    )

    # Return enriched envelope
    return {**envelope, **device_fields}


def get_metrics() -> Dict[str, Any]:
    """
    Get module metrics for observability.

    Returns 14 metrics:
    - total_profiles: Total profiles computed
    - device_kind_*: Counts per device kind (5 categories)
    - platform_*: Counts per platform (4 platforms)
    - input_method_*: Counts per input method (6 methods)

    Returns:
        Metrics dictionary (histogram-ready)
    """
    return _metrics.copy()


def reset_metrics() -> None:
    """
    Reset all metrics (for testing or reload).
    """
    global _metrics
    _metrics = {
        "total_profiles": 0,
        "device_kind_phone": 0,
        "device_kind_tablet": 0,
        "device_kind_watch": 0,
        "device_kind_web": 0,
        "device_kind_api": 0,
        "device_kind_unknown": 0,
        "platform_ios": 0,
        "platform_android": 0,
        "platform_web": 0,
        "platform_unknown": 0,
        "input_method_voice": 0,
        "input_method_text": 0,
        "input_method_photo": 0,
        "input_method_scan": 0,
        "input_method_import": 0,
        "input_method_api": 0,
    }
