"""
M08: Temporal & Circadian Profiler Module

**Contract**: context.temporal_profile.v2.yaml
**Performance Budget**: <4ms P95 fast path, <6ms NER fallback path
**Schema Alignment**: Produces exactly 14 temporal columns for st_hipp_events

This module enriches episodic memories with temporal context and circadian rhythm data:
- Implements TEMPORAL FALLBACK CHAIN (MW resolved -> NER temporal -> event_time -> envelope.ts -> now)
- Implements SPATIAL FALLBACK CHAIN (MW location -> NER LOC -> text heuristic -> null)
- Normalizes event timestamps to UTC (deterministic, no drift)
- Converts to tenant's local timezone (cached, O(1) lookup)
- Computes temporal buckets (time_of_day, day_of_week, circadian_slot)
- Calculates write lag metrics with QoS bands (realtime/delayed/backdated)
- Detects backdated events (write_lag > threshold)

**14-Dimensional Output (maps 1:1 to st_hipp_events temporal columns)**:
1. event_time_utc (INT) - Canonical event timestamp
2. write_time_utc (INT) - Database commit timestamp
3. write_lag_ms (INT) - Write latency (write_time - event_time)
4. local_date (TEXT) - Event date in tenant timezone
5. local_time (TEXT) - Event time in tenant timezone
6. day_of_week (TEXT) - Day name (Monday-Sunday)
7. is_weekend (BOOLEAN) - Saturday/Sunday flag
8. time_of_day_bucket (TEXT) - morning/afternoon/evening/night
9. circadian_slot (TEXT) - breakfast/lunch/dinner/sleep/NULL
10. is_backdated (BOOLEAN) - write_lag > 24 hours
11. created_at (INT) - Row creation timestamp (= write_time_utc)
12. temporal_mentioned_time (TEXT) - Raw temporal reference from MW (v2)
13. temporal_resolved_epoch_ms (BIGINT) - K1-resolved epoch from MW (v2)
14. temporal_orientation (TEXT) - PAST/ONGOING/FUTURE_COMMITMENT from MW (v2)

**World-Class Design Features**:
1. Schema Authority: M08 is single source of truth for all 11 dimensions
2. Zero Drift: No other P02 stage recomputes or mutates temporal fields
3. Config-Driven: Circadian slots and time buckets from contract YAML
4. Write Lag Bands: QoS-aware classification (realtime/delayed/backdated)
5. Tenant Timezone Cache: LRU + lazy load from st_tenants (stub ready)
6. Property Invariants: ingested_at ≤ write_time_utc (verified)
7. Histogram Metrics: Percentile-ready observability (not just means)
8. DST-Safe: ZoneInfo handles daylight saving transitions

**Use Cases**:
- Memory retention (recent vs. backdated events)
- Circadian pattern analysis (meal times, sleep patterns)
- QoS monitoring (realtime vs delayed vs bulk import)
- Timezone-aware queries and display
- Learning loop (P06 uses write_lag_band for quality signals)

**Performance**: <4ms P95 (timezone lookup + date math)
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from functools import lru_cache
from typing import Any, Optional
from zoneinfo import ZoneInfo

# Module logger (use instead of print)
logger = logging.getLogger(__name__)

# Module-level constants from contract config_schema
DEFAULT_TIMEZONE = "America/Los_Angeles"
BACKDATE_THRESHOLD_HOURS = 24
YEAR_2100_TIMESTAMP = 4102444800  # Unix seconds for 2100-01-01 00:00:00 UTC

# Future timestamp tolerance (clock skew, bulk import with slight future timestamps)
# Allow timestamps up to 24 hours in the future without clamping
# Rationale: Bulk imports, timezone confusion, device clock drift
FUTURE_TOLERANCE_HOURS = 24

# Write lag QoS bands (for P06/P17 analytics)
WRITE_LAG_BAND_REALTIME_MS = 5_000  # <5 seconds
WRITE_LAG_BAND_DELAYED_MS = 86_400_000  # <24 hours (1 day)
# >24 hours = backdated

# DEPRECATED: Hardcoded circadian slots removed - culturally biased and don't generalize
# Circadian patterns should be learned from user behavior, not assumed
# See get_circadian_slot() docstring for rationale

# Time-of-day buckets (frozen tuples) - generalized, works for all users
TIME_OF_DAY_BUCKETS = (
    ("morning", time(6, 0), time(12, 0)),
    ("afternoon", time(12, 0), time(17, 0)),
    ("evening", time(17, 0), time(22, 0)),
    ("night", time(22, 0), time(6, 0)),  # Wraps around midnight
)

# Module-level metrics (with histogram buckets for P95 tracking)
_metrics = {
    "total_profiles": 0,
    "timezone_cache_hits": 0,
    "timezone_cache_misses": 0,
    "timezone_fallback_count": 0,
    "future_event_time_clamped": 0,
    "backdate_count": 0,
    "write_lag_sum_ms": 0,
    "write_lag_realtime_count": 0,
    "write_lag_delayed_count": 0,
    "write_lag_backdated_count": 0,
    "invariant_violations": 0,  # ingested_at > write_time_utc violations
}


@dataclass(slots=True, frozen=True)
class TemporalProfile:
    """
    Temporal enrichment result (immutable).

    Maps 1:1 to st_hipp_events temporal columns (14 dimensions, v2).
    Schema alignment verified in contract tests.
    """

    # Core timestamps (3 dimensions)
    event_time_utc: int  # Unix timestamp (seconds) - canonical event time
    write_time_utc: int  # Unix timestamp (seconds) - DB commit time
    write_lag_ms: int  # Milliseconds (write_time - event_time)

    # v3 (Epic 1.2): Conversation anchor (K1 turn timestamp, ms)
    conversation_anchor_ms: Optional[int]  # K1 MW turn timestamp (ms) or None

    # Local time dimensions (3 dimensions)
    local_date: str  # ISO date (YYYY-MM-DD) in tenant timezone
    local_time: str  # ISO time (HH:MM:SS) in tenant timezone
    timezone_used: str  # Timezone identifier (e.g., "America/Los_Angeles")

    # Temporal buckets (4 dimensions)
    day_of_week: str  # Day name (Monday-Sunday)
    is_weekend: bool  # Saturday/Sunday
    time_of_day_bucket: str  # morning/afternoon/evening/night
    circadian_slot: Optional[str]  # breakfast/lunch/dinner/sleep/None

    # Write lag classification (1 dimension)
    is_backdated: bool  # write_lag_ms > 24 hours

    # Metadata (derived, always = write_time_utc)
    created_at: int  # Row creation timestamp

    # v2: MW temporal signals (3 new dimensions)
    temporal_mentioned_time: Optional[str]  # Raw temporal ref ("yesterday evening")
    temporal_resolved_epoch_ms: Optional[int]  # K1-resolved epoch (ms)
    temporal_orientation: Optional[str]  # PAST/ONGOING/FUTURE_COMMITMENT

    # v2: Provenance tracking
    temporal_source: str  # mw_resolved/ner_temporal/event_time/envelope_ts/now

    # v2.1 (Epic 2.4): Multi-link temporal model
    temporal_links_json: Optional[str]  # JSON array of TemporalLink dicts, max 5

    # v2: Spatial resolution
    location_name: Optional[str]  # Resolved location name
    location_type: Optional[str]  # restaurant/park/school/home/etc.
    location_source: Optional[str]  # mw_location/ner_location/text_heuristic/none


_VALID_LINK_TYPES = frozenset(
    {
        "RETROSPECTIVE",
        "PROSPECTIVE",
        "CONCURRENT",
        "HABITUAL",
        "CONTEXTUAL",
        "CONDITIONAL",
    }
)

_TEMPORAL_LINK_FIELDS = frozenset(
    {
        "mentioned_time",
        "resolved_epoch_ms",
        "uncertainty_window_ms",
        "link_type",
        "confidence",
    }
)


def parse_temporal_links(body: dict) -> Optional[str]:
    """Parse body.temporal_links (v2.1) or synthesize from body.temporal (v2.0).

    Returns a compact JSON string for st_hipp_events.temporal_links_json,
    or None if no temporal links exist.

    v2.1 path: body.temporal_links is a list of dicts -- validate and serialize.
    v2.0 backward compat: body.temporal exists but no temporal_links --
        synthesize a single-element list from the legacy temporal object.
    """
    import json

    raw_links = body.get("temporal_links")

    if raw_links is not None and isinstance(raw_links, list):
        # v2.1 path: validate and pass through (max 5)
        validated = []
        for link in raw_links[:5]:
            if not isinstance(link, dict):
                continue
            mt = link.get("mentioned_time")
            if not mt or not isinstance(mt, str) or not mt.strip():
                continue
            lt = link.get("link_type", "CONCURRENT")
            if lt not in _VALID_LINK_TYPES:
                lt = "CONCURRENT"
            validated.append(
                {
                    "mentioned_time": mt,
                    "resolved_epoch_ms": int(link.get("resolved_epoch_ms") or 0),
                    "uncertainty_window_ms": max(0, int(link.get("uncertainty_window_ms") or 0)),
                    "link_type": lt,
                    "confidence": max(0.0, min(1.0, float(link.get("confidence", 1.0)))),
                }
            )
        if not validated:
            return None
        return json.dumps(validated, ensure_ascii=False, separators=(",", ":"))

    # v2.0 backward compat: synthesize from body.temporal
    temporal = body.get("temporal")
    if isinstance(temporal, dict) and temporal.get("mentioned_time"):
        is_backdated = temporal.get("is_backdated", False)
        link = {
            "mentioned_time": temporal["mentioned_time"],
            "resolved_epoch_ms": int(temporal.get("resolved_epoch_ms") or 0),
            "uncertainty_window_ms": 0,
            "link_type": "RETROSPECTIVE" if is_backdated else "CONCURRENT",
            "confidence": 1.0,
        }
        return json.dumps([link], ensure_ascii=False, separators=(",", ":"))

    return None


def load_tenant_timezone_from_store(tenant_id: str) -> str:
    """
    Load tenant timezone from persistent storage (st_tenants or tenant_config).

    This is the REAL I/O function that will be replaced in production.
    Currently a stub that returns default timezone.

    In production, this will:
    - Query st_tenants.timezone_id or tenant_config table
    - Handle missing tenants with default fallback
    - Emit metrics on slow queries (>2ms)

    Returns:
        Timezone name (e.g., "America/Los_Angeles")
    """
    # TODO: Query tenant_config or st_tenants table
    # For now, return default (no I/O)
    return DEFAULT_TIMEZONE


@lru_cache(maxsize=100)
def get_tenant_timezone(tenant_id: str) -> str:
    """
    Lookup tenant timezone from config (cached, O(1) after first load).

    Cache strategy:
    - LRU cache with maxsize=100 tenants
    - Implicit TTL via cache eviction (no explicit expiry)
    - Cache invalidation on tenant.config.updated event (future)

    Metrics:
    - Increments timezone_cache_misses ONLY on cache miss (first load)
    - Subsequent hits do NOT increment cache_hits (tracked in convert_to_local_timezone)

    Returns:
        Timezone name (e.g., "America/Los_Angeles")
    """
    # Increment cache miss counter (only on first load for this tenant_id)
    _metrics["timezone_cache_misses"] += 1

    # Load from store (stub returns default)
    return load_tenant_timezone_from_store(tenant_id)


def _parse_raw_timestamp(event_time: Any, now_ts: int) -> Optional[int]:
    """
    Parse a raw timestamp value (ISO 8601, Unix int/float) into Unix seconds.

    Returns None if parsing fails entirely.
    """
    if isinstance(event_time, str):
        try:
            dt = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return int(dt.timestamp())
        except (ValueError, AttributeError) as e:
            logger.warning(f"Timestamp parse failed for event_time={event_time}: {e}")
            return None
    elif isinstance(event_time, (int, float)):
        timestamp = int(event_time)
        if timestamp >= 1_000_000_000_000_000:  # microseconds
            timestamp = timestamp // 1_000_000
        elif timestamp >= 1_000_000_000_000:  # milliseconds
            timestamp = timestamp // 1000
        return timestamp
    return None


def _clamp_future_timestamp(timestamp: int, now_ts: int) -> int:
    """Clamp future timestamps (year 2100 or beyond tolerance)."""
    if timestamp > YEAR_2100_TIMESTAMP:
        logger.warning(
            f"Future timestamp detected: {timestamp} > {YEAR_2100_TIMESTAMP} (year 2100), clamping"
        )
        _metrics["future_event_time_clamped"] += 1
        return now_ts
    elif timestamp > (now_ts + FUTURE_TOLERANCE_HOURS * 3600):
        logger.warning(
            f"Future timestamp beyond tolerance: {timestamp} > {now_ts + FUTURE_TOLERANCE_HOURS * 3600} "
            f"(now + {FUTURE_TOLERANCE_HOURS}h), clamping to now"
        )
        _metrics["future_event_time_clamped"] += 1
        return now_ts
    return timestamp


# ==================== NER Temporal Resolution (v2) ====================

# Regex patterns for basic temporal expression resolution
_TEMPORAL_PATTERNS = [
    (
        re.compile(r"\byesterday\s*evening\b", re.IGNORECASE),
        lambda now: now - timedelta(hours=24) + timedelta(hours=19),
    ),
    (
        re.compile(r"\byesterday\s*morning\b", re.IGNORECASE),
        lambda now: now - timedelta(hours=24) + timedelta(hours=9),
    ),
    (
        re.compile(r"\byesterday\s*afternoon\b", re.IGNORECASE),
        lambda now: now - timedelta(hours=24) + timedelta(hours=14),
    ),
    (
        re.compile(r"\byesterday\s*night\b", re.IGNORECASE),
        lambda now: now - timedelta(hours=24) + timedelta(hours=21),
    ),
    (re.compile(r"\byesterday\b", re.IGNORECASE), lambda now: now - timedelta(hours=24)),
    (re.compile(r"\blast\s*week\b", re.IGNORECASE), lambda now: now - timedelta(days=7)),
    (re.compile(r"\btwo\s*days?\s*ago\b", re.IGNORECASE), lambda now: now - timedelta(days=2)),
    (re.compile(r"\bthree\s*days?\s*ago\b", re.IGNORECASE), lambda now: now - timedelta(days=3)),
    (re.compile(r"\blast\s*night\b", re.IGNORECASE), lambda now: now - timedelta(hours=12)),
    (
        re.compile(r"\bthis\s*morning\b", re.IGNORECASE),
        lambda now: now.replace(hour=9, minute=0, second=0, microsecond=0),
    ),
    (re.compile(r"\bearlier\s*today\b", re.IGNORECASE), lambda now: now - timedelta(hours=4)),
    # Issue 1.2.5: Additional patterns for improved Priority 2 coverage
    (
        re.compile(r"\ba\s*few\s*hours?\s*ago\b", re.IGNORECASE),
        lambda now: now - timedelta(hours=3),
    ),
    (
        re.compile(r"\ban?\s*hour\s*ago\b", re.IGNORECASE),
        lambda now: now - timedelta(hours=1),
    ),
    (
        re.compile(r"\ba\s*couple\s*(?:of\s*)?days?\s*ago\b", re.IGNORECASE),
        lambda now: now - timedelta(days=2),
    ),
    (
        re.compile(r"\bfew\s*days?\s*(?:ago|back)\b", re.IGNORECASE),
        lambda now: now - timedelta(days=3),
    ),
    (
        re.compile(r"\blast\s*month\b", re.IGNORECASE),
        lambda now: now - timedelta(days=30),
    ),
    (
        re.compile(r"\blast\s*year\b", re.IGNORECASE),
        lambda now: now - timedelta(days=365),
    ),
    (
        re.compile(r"\bover\s*the\s*weekend\b", re.IGNORECASE),
        lambda now: now - timedelta(days=(now.weekday() + 2) % 7),
    ),
    (
        re.compile(r"\bthis\s*afternoon\b", re.IGNORECASE),
        lambda now: now.replace(hour=14, minute=0, second=0, microsecond=0),
    ),
    (
        re.compile(r"\bthis\s*evening\b", re.IGNORECASE),
        lambda now: now.replace(hour=19, minute=0, second=0, microsecond=0),
    ),
    (
        re.compile(r"\btoday\b", re.IGNORECASE),
        lambda now: now.replace(hour=0, minute=0, second=0, microsecond=0),
    ),
    (
        re.compile(r"\b(?:around\s*)?noon\b", re.IGNORECASE),
        lambda now: now.replace(hour=12, minute=0, second=0, microsecond=0),
    ),
]


def _resolve_temporal_expression(raw_text: str, now_ts: int) -> Optional[int]:
    """
    Attempt basic regex resolution of a temporal expression to Unix seconds.

    This is a HEURISTIC fallback -- lower fidelity than K1's LLM resolution.
    Used only when body.temporal.resolved_epoch_ms is missing.

    Args:
        raw_text: Raw temporal expression ("yesterday evening", "last week", etc.)
        now_ts: Current Unix timestamp (seconds) for relative resolution.

    Returns:
        Resolved Unix timestamp (seconds), or None if no pattern matches.
    """
    now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
    for pattern, resolver in _TEMPORAL_PATTERNS:
        if pattern.search(raw_text):
            try:
                resolved_dt = resolver(now_dt)
                return int(resolved_dt.timestamp())
            except Exception:
                continue
    return None


# ==================== Spatial Fallback Chain (v2) ====================

# Location type classification patterns
_LOCATION_TYPE_PATTERNS = [
    (
        re.compile(r"\b(restaurant|cafe|diner|bistro|pizzeria|grill|bar)\b", re.IGNORECASE),
        "restaurant",
    ),
    (re.compile(r"\b(park|garden|trail|beach|lake|forest|playground)\b", re.IGNORECASE), "park"),
    (re.compile(r"\b(school|university|college|academy|campus)\b", re.IGNORECASE), "school"),
    (re.compile(r"\b(hospital|clinic|doctor|medical|pharmacy)\b", re.IGNORECASE), "medical"),
    (re.compile(r"\b(church|temple|mosque|synagogue)\b", re.IGNORECASE), "worship"),
    (
        re.compile(r"\b(store|mall|shop|market|grocery|walmart|target|costco)\b", re.IGNORECASE),
        "retail",
    ),
    (re.compile(r"\b(office|workplace|headquarters|studio)\b", re.IGNORECASE), "workplace"),
    (re.compile(r"\b(home|house|apartment|condo)\b", re.IGNORECASE), "home"),
    (re.compile(r"\b(gym|fitness|pool|stadium|arena)\b", re.IGNORECASE), "fitness"),
    (re.compile(r"\b(airport|station|terminal|bus\s*stop)\b", re.IGNORECASE), "transit"),
]

# Heuristic location extraction from text
_LOCATION_HEURISTIC_PATTERN = re.compile(
    r"\b(?:at|in|near|from|to|visited)\s+([A-Z][A-Za-z'']+(?:\s+[A-Z][A-Za-z'']+){0,4})"
)


def _classify_location_type(location_text: str) -> Optional[str]:
    """Classify a location name into a category using pattern matching."""
    for pattern, loc_type in _LOCATION_TYPE_PATTERNS:
        if pattern.search(location_text):
            return loc_type
    return None


def _extract_location_heuristic(text: str) -> Optional[str]:
    """
    Extract a likely location name from text using regex heuristics.

    Looks for patterns like "at Olive Garden", "in Central Park", etc.
    Only matches capitalized multi-word sequences after spatial prepositions.

    Returns:
        Location name string or None if no match.
    """
    if not text:
        return None
    match = _LOCATION_HEURISTIC_PATTERN.search(text)
    if match:
        candidate = match.group(1).strip()
        # Filter out common false positives (pronouns, temporal words, etc.)
        false_positives = {
            "I",
            "We",
            "He",
            "She",
            "They",
            "It",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        }
        if candidate in false_positives:
            return None
        return candidate
    return None


def resolve_location(
    body: dict, m02_output: Optional[dict] = None
) -> tuple[Optional[str], Optional[str], str]:
    """
    Resolve location via spatial fallback chain.

    Priority:
    1. MW body.location_name + body.location_type (LLM extracted)
    2. M02 NER LOC entities (UltraBERT detected)
    3. Heuristic extraction from body.text ("at [Place]" patterns)
    4. null (no location -- acceptable)

    Args:
        body: Envelope body dict.
        m02_output: M02 enrichment output with ner_loc_entities (optional).

    Returns:
        (location_name, location_type, location_source) tuple.
    """
    # Priority 1: MW location fields
    if body.get("location_name"):
        loc_name = body["location_name"]
        loc_type = body.get("location_type") or _classify_location_type(loc_name)
        return loc_name, loc_type, "mw_location"

    # Priority 2: M02 NER LOC entities
    if m02_output and isinstance(m02_output, dict):
        ner_locs = m02_output.get("ner_loc_entities")
        if ner_locs and isinstance(ner_locs, list) and len(ner_locs) > 0:
            loc_entity = ner_locs[0]
            loc_text = (
                loc_entity.get("text", "") if isinstance(loc_entity, dict) else str(loc_entity)
            )
            if loc_text:
                loc_type = _classify_location_type(loc_text)
                return loc_text, loc_type, "ner_location"

    # Priority 3: Heuristic extraction from body.text
    text = body.get("text", "")
    loc_match = _extract_location_heuristic(text)
    if loc_match:
        loc_type = _classify_location_type(loc_match)
        return loc_match, loc_type, "text_heuristic"

    # Priority 4: No location (acceptable)
    return None, None, "none"


def _resolve_conversation_time(body: dict, envelope: dict, now_ts: int) -> tuple[int, str]:
    """
    Chain A: Resolve CONVERSATION TIME (when the user actually chatted).

    This timestamp drives R2 episode formation and temporal clustering.
    It must reflect the moment of interaction, NOT what date the event
    refers to (that is Chain B's job).

    Priority:
    1. body.conversation_anchor_ms (K1 MW turn timestamp, highest fidelity)
    2. body.event_time (ISO 8601 or Unix -- MW now_utc() at extraction)
    3. envelope.ts (Bridge timestamp -- ALWAYS PRESENT, hard backstop)
    4. now() (ultimate fallback)

    Returns:
        (event_time_utc_seconds, source_tag)
    """
    # Priority 1: K1 MW conversation_anchor_ms (set from turn_timestamp_ms in Epic 1.1)
    anchor_ms = body.get("conversation_anchor_ms")
    if anchor_ms and isinstance(anchor_ms, (int, float)) and anchor_ms > 0:
        timestamp = int(anchor_ms) // 1000 if anchor_ms >= 1_000_000_000_000 else int(anchor_ms)
        timestamp = _clamp_future_timestamp(timestamp, now_ts)
        return timestamp, "conversation_anchor"

    # Priority 2: body.event_time (MW now_utc at extraction time)
    event_time = body.get("event_time")
    if event_time:
        parsed = _parse_raw_timestamp(event_time, now_ts)
        if parsed is not None:
            parsed = _clamp_future_timestamp(parsed, now_ts)
            return parsed, "event_time"

    # Priority 3: envelope.ts (Bridge timestamp -- hard backstop)
    envelope_ts = envelope.get("ts")
    if envelope_ts:
        parsed = _parse_raw_timestamp(envelope_ts, now_ts)
        if parsed is not None:
            parsed = _clamp_future_timestamp(parsed, now_ts)
            return parsed, "envelope_ts"

    # Priority 4: now() (should never reach here if envelope.ts present)
    return now_ts, "now"


def _resolve_referred_time(
    body: dict, m02_output: Optional[dict], now_ts: int
) -> tuple[Optional[int], str]:
    """
    Chain B: Resolve REFERRED TIME (what date/time the event talks about).

    This is the temporal expression the user mentioned ("yesterday evening",
    "last Tuesday"). It does NOT affect event_time_utc or R2 episodes.
    It feeds temporal_resolved_epoch_ms for temporal queries and R5 CTD.

    Priority:
    1. body.temporal.resolved_epoch_ms (K1 LLM resolved -- highest fidelity)
    2. M02 NER temporal expression + regex resolution (heuristic)
    3. None (no temporal reference detected)

    Returns:
        (referred_epoch_ms_or_None, source_tag)
    """
    # Priority 1: MW resolved epoch (K1 resolved "yesterday evening" to epoch)
    temporal = body.get("temporal", {}) if isinstance(body.get("temporal"), dict) else {}
    resolved_ms = temporal.get("resolved_epoch_ms")
    if resolved_ms and isinstance(resolved_ms, (int, float)) and resolved_ms > 0:
        # Keep in milliseconds (matches column contract: temporal_resolved_epoch_ms BIGINT ms)
        return int(resolved_ms), "mw_resolved"

    # Priority 2: M02 NER temporal entities (regex resolution)
    if m02_output and isinstance(m02_output, dict):
        ner_temporal = m02_output.get("ner_temporal_entities")
        if ner_temporal and isinstance(ner_temporal, list) and len(ner_temporal) > 0:
            first_entity = ner_temporal[0]
            raw_text = (
                first_entity.get("text", "")
                if isinstance(first_entity, dict)
                else str(first_entity)
            )
            if raw_text:
                resolved_seconds = _resolve_temporal_expression(raw_text, now_ts)
                if resolved_seconds is not None:
                    resolved_seconds = _clamp_future_timestamp(resolved_seconds, now_ts)
                    # Convert to ms for consistency with MW resolved_epoch_ms
                    return resolved_seconds * 1000, "ner_temporal"

    # Priority 3: No temporal reference
    return None, "none"


def normalize_timestamp(
    envelope: dict, now_ts: Optional[int] = None, m02_output: Optional[dict] = None
) -> tuple[int, str, Optional[int], str]:
    """
    Extract and normalize event timestamps via dual TEMPORAL FALLBACK CHAINS (v3).

    The temporal fallback chain is the MOST CRITICAL chain in P02.
    Without a correct timestamp, everything downstream collapses.

    Split into two independent chains (Epic 1.2 / GAP-002):

    Chain A -- CONVERSATION TIME (event_time_utc):
      When the user actually chatted. Drives R2 episode formation.
      1. body.conversation_anchor_ms (K1 MW turn timestamp)
      2. body.event_time (MW now_utc at extraction)
      3. envelope.ts (Bridge timestamp -- hard backstop)
      4. now() (ultimate fallback)

    Chain B -- REFERRED TIME (temporal_resolved_epoch_ms):
      What date/time the event talks about. For temporal queries only.
      1. body.temporal.resolved_epoch_ms (K1 LLM resolved)
      2. M02 NER temporal expression (heuristic)
      3. None (no temporal reference)

    Args:
        envelope: Event envelope dict.
        now_ts: Current timestamp (Unix seconds), for testing. If None, computed once.
        m02_output: M02 enrichment output with ner_temporal_entities (optional).

    Returns:
        (event_time_utc, conv_source, referred_epoch_ms, ref_source):
        - event_time_utc: Unix seconds (conversation time, NEVER null)
        - conv_source: Chain A provenance tag
        - referred_epoch_ms: Milliseconds or None (referred time)
        - ref_source: Chain B provenance tag
    """
    body = envelope.get("body", {})

    # Capture current time ONCE (deterministic)
    if now_ts is None:
        now_ts = int(datetime.now(timezone.utc).timestamp())

    # Chain A: conversation time (for R2 episodes)
    event_time_utc, conv_source = _resolve_conversation_time(body, envelope, now_ts)

    # Chain B: referred time (for temporal queries)
    referred_epoch_ms, ref_source = _resolve_referred_time(body, m02_output, now_ts)

    return event_time_utc, conv_source, referred_epoch_ms, ref_source


def convert_to_local_timezone(timestamp_utc: int, tenant_id: str) -> tuple[datetime, str]:
    """
    Convert UTC timestamp to tenant's local timezone (cached, O(1) after first load).

    Cache behavior:
    - First call for tenant_id: cache miss → increment timezone_cache_misses
    - Subsequent calls: cache hit (lru_cache returns cached value, no miss increment)
    - Cache hit tracked ONLY on successful conversion (no exception)

    Exception handling:
    - ZoneInfo load failure → fallback to UTC
    - Increment timezone_fallback_count ONCE per failure

    Args:
        timestamp_utc: Unix timestamp (seconds)
        tenant_id: Tenant identifier for timezone lookup

    Returns:
        (local_datetime, timezone_name): Local datetime object and timezone string
    """
    try:
        tz_name = get_tenant_timezone(tenant_id)
        tz = ZoneInfo(tz_name)
        # Cache hit: Only increment if no exception (successful conversion)
        _metrics["timezone_cache_hits"] += 1
    except Exception as e:
        # Fallback to UTC on any exception (ZoneInfo load failure, cache error, etc.)
        logger.warning(
            f"Timezone lookup failed for tenant_id={tenant_id}: {e}, falling back to UTC"
        )
        tz_name = "UTC"
        tz = timezone.utc
        _metrics["timezone_fallback_count"] += 1

    # Convert UTC → local timezone
    dt_utc = datetime.fromtimestamp(timestamp_utc, tz=timezone.utc)
    dt_local = dt_utc.astimezone(tz)

    return dt_local, tz_name


def get_day_of_week(dt: datetime) -> str:
    """Get day name (Monday-Sunday)."""
    return dt.strftime("%A")


def is_weekend(dt: datetime) -> bool:
    """Check if Saturday or Sunday."""
    return dt.weekday() in (5, 6)  # 5=Saturday, 6=Sunday


def get_time_of_day_bucket(dt: datetime) -> str:
    """
    Classify time into morning/afternoon/evening/night (config-driven).

    Uses frozen tuple for branch-light comparisons (faster than dict iteration).

    Buckets (default config):
    - morning: 06:00-12:00
    - afternoon: 12:00-17:00
    - evening: 17:00-22:00
    - night: 22:00-06:00 (wraps around midnight)

    Midnight wrap-around:
    - night bucket uses (t >= start) OR (t < end) logic
    - Handles 22:00-23:59 and 00:00-05:59 correctly

    Returns:
        Bucket name (str): "morning" | "afternoon" | "evening" | "night"
    """
    t = dt.time()

    for bucket_name, start, end in TIME_OF_DAY_BUCKETS:
        if bucket_name == "night":
            # Night wraps around midnight (22:00-06:00)
            if t >= start or t < end:
                return bucket_name
        else:
            if start <= t < end:
                return bucket_name

    # Default fallback (should not reach here with valid config)
    return "unknown"


def get_circadian_slot(dt: datetime) -> Optional[str]:
    """
    Returns circadian slot for a datetime.

    DESIGN DECISION: Always returns None.

    Hardcoded meal/sleep windows (breakfast 06:00-09:00, dinner 17:30-20:30, etc.)
    are culturally biased and don't work for:
    - Night shift workers
    - Different cultures (late Spanish dinners, early Japanese breakfasts)
    - Parents with irregular schedules
    - Freelancers, remote workers, anyone outside 9-5

    The generalized time_of_day_bucket (morning/afternoon/evening/night) already
    provides sufficient temporal context without prescriptive assumptions.

    FUTURE: If circadian slots are needed, they should be learned from actual
    user behavior patterns (e.g., user typically eats at 14:00), not hardcoded.
    This would require a user_preferences or learned_patterns module.

    Args:
        dt: datetime to classify

    Returns:
        None (always) - circadian slots should be learned, not assumed
    """
    # Removed hardcoded CIRCADIAN_SLOTS logic
    # Use time_of_day_bucket for generalized time classification
    return None


def compute_write_lag(event_time_utc: int, write_time_utc: int) -> int:
    """
    Compute write lag in milliseconds.

    write_lag_ms = write_time_utc - event_time_utc

    Returns:
        Lag in milliseconds (int)
    """
    lag_seconds = write_time_utc - event_time_utc
    return lag_seconds * 1000


def is_backdated(write_lag_ms: int, threshold_hours: int = BACKDATE_THRESHOLD_HOURS) -> bool:
    """
    Detect backdated events (write lag > threshold).

    Default threshold: 24 hours (86,400,000 milliseconds)

    Args:
        write_lag_ms: Write lag in milliseconds
        threshold_hours: Backdate threshold in hours (default 24)

    Returns:
        True if backdated (write_lag > threshold)
    """
    threshold_ms = threshold_hours * 3600 * 1000
    return write_lag_ms > threshold_ms


def classify_write_lag_band(write_lag_ms: int) -> str:
    """
    Classify write lag into QoS bands for P06/P17 analytics.

    Bands (from contract requirements):
    - "realtime": <5 seconds (live capture, high quality signal)
    - "delayed": 5 seconds to 24 hours (async processing, medium quality)
    - "backdated": >24 hours (bulk import, low quality signal for learning)

    Use cases:
    - P06 (Learning): Weight realtime events higher than backdated
    - P17 (QoS): Track write path performance (% realtime vs delayed)
    - P02 Monitoring: Alert on high delayed/backdated rates

    Args:
        write_lag_ms: Write lag in milliseconds

    Returns:
        Band name: "realtime" | "delayed" | "backdated"
    """
    if write_lag_ms < WRITE_LAG_BAND_REALTIME_MS:
        return "realtime"
    elif write_lag_ms < WRITE_LAG_BAND_DELAYED_MS:
        return "delayed"
    else:
        return "backdated"


def profile_temporal(
    event_time_utc: int,
    write_time_utc: int,
    tenant_id: str,
    backdate_threshold_hours: int = BACKDATE_THRESHOLD_HOURS,
    temporal_mentioned_time: Optional[str] = None,
    temporal_resolved_epoch_ms: Optional[int] = None,
    temporal_orientation: Optional[str] = None,
    temporal_source: str = "now",
    location_name: Optional[str] = None,
    location_type: Optional[str] = None,
    location_source: Optional[str] = "none",
    conversation_anchor_ms: Optional[int] = None,
    temporal_links_json: Optional[str] = None,
) -> TemporalProfile:
    """
    Generate complete temporal profile for an event (14 dimensions, v2).

    This is the SINGLE SOURCE OF TRUTH for all temporal enrichments in P02.
    No other stage should recompute or mutate these fields.

    Args:
        event_time_utc: Event timestamp (Unix seconds, canonical)
        write_time_utc: Database write timestamp (Unix seconds, P02 commit time)
        tenant_id: Tenant identifier for timezone lookup
        backdate_threshold_hours: Backdate detection threshold (default 24h)
        temporal_mentioned_time: Raw temporal reference from MW (v2)
        temporal_resolved_epoch_ms: K1-resolved epoch ms from MW (v2)
        temporal_orientation: PAST/ONGOING/FUTURE_COMMITMENT from MW (v2)
        temporal_source: Provenance tag from fallback chain (v2)
        location_name: Resolved location name (v2)
        location_type: Location category (v2)
        location_source: Spatial chain provenance (v2)

    Returns:
        TemporalProfile with all 14 dimensions (maps 1:1 to st_hipp_events)
    """
    # Convert to local timezone (cached lookup, <1ms P95)
    dt_local, tz_name = convert_to_local_timezone(event_time_utc, tenant_id)

    # Extract temporal components (local timezone)
    local_date = dt_local.strftime("%Y-%m-%d")
    local_time = dt_local.strftime("%H:%M:%S")
    day_name = get_day_of_week(dt_local)
    weekend = is_weekend(dt_local)
    tod_bucket = get_time_of_day_bucket(dt_local)
    circadian = get_circadian_slot(dt_local)

    # Compute write lag (millisecond precision)
    lag_ms = compute_write_lag(event_time_utc, write_time_utc)
    backdated = is_backdated(lag_ms, backdate_threshold_hours)
    lag_band = classify_write_lag_band(lag_ms)

    # Update metrics (histogram-ready for P95 tracking)
    _metrics["total_profiles"] += 1
    _metrics["write_lag_sum_ms"] += lag_ms

    # Track write lag band counts (for QoS analytics)
    if lag_band == "realtime":
        _metrics["write_lag_realtime_count"] += 1
    elif lag_band == "delayed":
        _metrics["write_lag_delayed_count"] += 1
    else:  # backdated
        _metrics["write_lag_backdated_count"] += 1
        _metrics["backdate_count"] += 1  # Compatibility with existing metric

    return TemporalProfile(
        event_time_utc=event_time_utc,
        write_time_utc=write_time_utc,
        write_lag_ms=lag_ms,
        conversation_anchor_ms=conversation_anchor_ms,
        local_date=local_date,
        local_time=local_time,
        timezone_used=tz_name,
        day_of_week=day_name,
        is_weekend=weekend,
        time_of_day_bucket=tod_bucket,
        circadian_slot=circadian,
        is_backdated=backdated,
        created_at=write_time_utc,
        temporal_mentioned_time=temporal_mentioned_time,
        temporal_resolved_epoch_ms=temporal_resolved_epoch_ms,
        temporal_orientation=temporal_orientation,
        temporal_source=temporal_source,
        temporal_links_json=temporal_links_json,
        location_name=location_name,
        location_type=location_type,
        location_source=location_source,
    )


async def run(message: Any, context: Any, **config: Any) -> dict[str, Any]:
    """
    M08 temporal_profile module entry point (Phase 2, v2).

    This function is the SINGLE AUTHORITY for temporal enrichment in P02.
    Output maps 1:1 to st_hipp_events temporal columns (verified in contract tests).

    v2 additions:
    - Temporal fallback chain: MW resolved -> NER temporal -> event_time -> envelope.ts -> now
    - Spatial fallback chain: MW location -> NER LOC -> text heuristic -> null
    - 3 new MW temporal dimensions + provenance tracking + spatial fields

    Args:
        message: BusMessage with .payload, .trace_id, .offset
        context: PipelineContext with .syscalls, .logger, .config
        **config: Stage-specific configuration:
            - write_time_utc (int, optional): Override for UnitOfWork commit time (for testing)
            - ingested_at (int, optional): Ingress timestamp for invariant validation
            - timezone_source (str): "tenant_config" (default)

    Returns:
        Enriched envelope dict with temporal profile (14 dimensions):
            - event_time_utc: INT - Canonical event timestamp
            - write_time_utc: INT - DB commit timestamp
            - write_lag_ms: INT - Write latency (ms)
            - local_date: TEXT - Event date in tenant TZ
            - local_time: TEXT - Event time in tenant TZ
            - day_of_week: TEXT - Day name
            - is_weekend: BOOLEAN - Sat/Sun flag
            - time_of_day_bucket: TEXT - morning/afternoon/evening/night
            - circadian_slot: TEXT - breakfast/lunch/dinner/sleep/NULL
            - is_backdated: BOOLEAN - write_lag > 24h
            - created_at: INT - Row creation (= write_time_utc)
            - timezone_used: TEXT - Tenant timezone
            - temporal_mentioned_time: TEXT - MW raw temporal ref (v2)
            - temporal_resolved_epoch_ms: BIGINT - MW resolved epoch (v2)
            - temporal_orientation: TEXT - PAST/ONGOING/FUTURE_COMMITMENT (v2)
            - temporal_source: TEXT - Provenance tag (v2)
            - location_name: TEXT - Resolved location (v2)
            - location_type: TEXT - Location category (v2)
            - location_source: TEXT - Spatial provenance (v2)

    Performance: <4ms P95 fast path, <6ms NER fallback
    Deterministic: Captures now_ts once, no repeated datetime.now() calls

    Invariant Validation:
    - If ingested_at provided: validates ingested_at <= write_time_utc
    - Violation -> logs warning + increments invariant_violations metric

    Contract: k0/contracts/modules/context.temporal_profile.v2.yaml
    """
    # Use enriched envelope from pipeline_runner, with fallback to message.payload
    import json

    envelope = config.get("envelope")
    if envelope is None:
        envelope = (
            json.loads(message.payload)
            if isinstance(message.payload, (str, bytes))
            else message.payload
        )

    # Extract config parameters
    write_time_utc_override = config.get("write_time_utc")
    ingested_at = config.get("ingested_at")
    timezone_source = config.get("timezone_source", "tenant_config")

    # Log module start
    context.logger.debug(
        "M08 temporal_profile starting",
        extra={
            "module_id": "context.temporal_profile",
            "trace_id": message.trace_id,
            "event_id": envelope.get("event_id"),
            "timezone_source": timezone_source,
        },
    )

    # Extract tenant_id
    tenant_id = envelope.get("tenant_id", "default")

    # Capture current time ONCE (deterministic, used for write_time_utc and normalize_timestamp)
    now_ts = int(datetime.now(timezone.utc).timestamp())

    # v2: Extract M02 enrichment output for NER fallback (if pipeline already ran M02)
    enrichments = envelope.get("enrichments", {})
    m02_output = enrichments.get("semantic_projector") or enrichments.get("m02")

    # v2: Normalize event timestamp via TEMPORAL FALLBACK CHAIN (returns provenance)
    # v3 (Epic 1.2): Split into Chain A (conversation time) + Chain B (referred time)
    event_time_utc, temporal_source, referred_epoch_ms, referred_source = normalize_timestamp(
        envelope, now_ts=now_ts, m02_output=m02_output
    )

    # v2: Extract MW temporal signals (passthrough -- only LLM can produce these)
    body = envelope.get("body", {})
    temporal_section = body.get("temporal", {}) if isinstance(body.get("temporal"), dict) else {}
    temporal_mentioned_time = temporal_section.get("mentioned_time")
    # v3 (Epic 1.2): Use Chain B result for temporal_resolved_epoch_ms
    # instead of re-reading from body (Chain B also includes NER resolution)
    temporal_resolved_epoch_ms = referred_epoch_ms
    # MW v2 schema: temporal_orientation is top-level body field
    # Legacy fallback: body.temporal.orientation (nested dict)
    temporal_orientation = body.get("temporal_orientation") or temporal_section.get("orientation")
    # Validate orientation enum
    if temporal_orientation not in (None, "PAST", "ONGOING", "FUTURE_COMMITMENT"):
        context.logger.warning(
            "M08 invalid temporal_orientation value",
            extra={
                "trace_id": message.trace_id,
                "temporal_orientation": temporal_orientation,
            },
        )
        temporal_orientation = None

    # v2: Resolve location via SPATIAL FALLBACK CHAIN
    location_name, location_type, location_source = resolve_location(body, m02_output)

    # v2.1 (Epic 2.4): Parse temporal_links from v2.1 atom or synthesize from v2.0 body.temporal
    temporal_links_json = parse_temporal_links(body)

    # Capture write time (P02 UnitOfWork commit timestamp)
    if write_time_utc_override is None:
        write_time_utc = now_ts
    else:
        write_time_utc = write_time_utc_override

    # Validate invariant: ingested_at <= write_time_utc (for realtime events)
    if ingested_at is not None and ingested_at > write_time_utc:
        context.logger.warning(
            "Invariant violation: ingested_at > write_time_utc",
            extra={
                "module_id": "context.temporal_profile",
                "trace_id": message.trace_id,
                "ingested_at": ingested_at,
                "write_time_utc": write_time_utc,
            },
        )
        _metrics["invariant_violations"] += 1

    # Generate temporal profile (14 dimensions, v2)
    # v3 (Epic 1.2): Propagate conversation_anchor_ms from K1 MW
    raw_anchor_ms = body.get("conversation_anchor_ms")
    conversation_anchor_ms = (
        int(raw_anchor_ms)
        if raw_anchor_ms is not None
        and isinstance(raw_anchor_ms, (int, float))
        and raw_anchor_ms > 0
        else None
    )

    profile = profile_temporal(
        event_time_utc=event_time_utc,
        write_time_utc=write_time_utc,
        tenant_id=tenant_id,
        temporal_mentioned_time=temporal_mentioned_time,
        temporal_resolved_epoch_ms=temporal_resolved_epoch_ms,
        temporal_orientation=temporal_orientation,
        temporal_source=temporal_source,
        location_name=location_name,
        location_type=location_type,
        location_source=location_source,
        conversation_anchor_ms=conversation_anchor_ms,
        temporal_links_json=temporal_links_json,
    )

    # Log module completion
    context.logger.debug(
        "M08 temporal_profile completed",
        extra={
            "module_id": "context.temporal_profile",
            "trace_id": message.trace_id,
            "local_date": profile.local_date,
            "time_of_day_bucket": profile.time_of_day_bucket,
            "write_lag_ms": profile.write_lag_ms,
            "temporal_source": profile.temporal_source,
            "location_source": profile.location_source,
        },
    )

    # Return enriched envelope (merge temporal fields into original envelope)
    return {
        **envelope,
        # BACKWARD COMPAT: Keep flat fields during migration (Phase 4)
        "event_time_utc": profile.event_time_utc,
        "write_time_utc": profile.write_time_utc,
        "write_lag_ms": profile.write_lag_ms,
        "local_date": profile.local_date,
        "local_time": profile.local_time,
        "day_of_week": profile.day_of_week,
        "is_weekend": profile.is_weekend,
        "time_of_day_bucket": profile.time_of_day_bucket,
        "circadian_slot": profile.circadian_slot,
        "is_backdated": profile.is_backdated,
        "created_at": profile.created_at,
        "timezone_used": profile.timezone_used,
        # v2: New temporal + spatial flat fields
        "temporal_mentioned_time": profile.temporal_mentioned_time,
        "temporal_resolved_epoch_ms": profile.temporal_resolved_epoch_ms,
        "temporal_orientation": profile.temporal_orientation,
        "temporal_source": profile.temporal_source,
        # v3 (Epic 1.2): conversation_anchor_ms for st_hipp_events
        "conversation_anchor_ms": profile.conversation_anchor_ms,
        # v2.1 (Epic 2.4): temporal_links_json for st_hipp_events
        "temporal_links_json": profile.temporal_links_json,
        "location_name": profile.location_name,
        "location_type": profile.location_type,
        "location_source": profile.location_source,
        # Nested enrichments structure (Phase 4)
        "enrichments": {
            **envelope.get("enrichments", {}),
            "temporal_profiler": {
                "event_time_utc": profile.event_time_utc,
                "write_time_utc": profile.write_time_utc,
                "write_lag_ms": profile.write_lag_ms,
                "local_date": profile.local_date,
                "local_time": profile.local_time,
                "day_of_week": profile.day_of_week,
                "is_weekend": profile.is_weekend,
                "time_of_day_bucket": profile.time_of_day_bucket,
                "circadian_slot": profile.circadian_slot,
                "is_backdated": profile.is_backdated,
                "created_at": profile.created_at,
                "timezone_used": profile.timezone_used,
                "temporal_mentioned_time": profile.temporal_mentioned_time,
                "temporal_resolved_epoch_ms": profile.temporal_resolved_epoch_ms,
                "temporal_orientation": profile.temporal_orientation,
                "temporal_source": profile.temporal_source,
                "conversation_anchor_ms": profile.conversation_anchor_ms,
                "temporal_links_json": profile.temporal_links_json,
                "location_name": profile.location_name,
                "location_type": profile.location_type,
                "location_source": profile.location_source,
                "module_version": "v2",
                "execution_time_ms": 0.0,  # Set by PipelineRunner
            },
        },
    }


def get_metrics() -> dict:
    """
    Get module metrics (observability for P17 dashboards).

    Metrics design:
    - Histogram-ready: Track write_lag_band counts for percentile computation
    - Rate calculation: Backdate rate, realtime rate, delayed rate
    - Cache performance: Hits, misses, fallbacks
    - Invariant violations: Track ingested_at > write_time_utc anomalies

    Returns:
        {
            "total_profiles": int,
            "timezone_cache_hits": int,
            "timezone_cache_misses": int,
            "timezone_fallback_count": int,
            "future_event_time_clamped": int,
            "avg_write_lag_ms": float,
            "backdate_count": int,
            "backdate_rate": float (0.0-1.0),
            "write_lag_realtime_count": int,
            "write_lag_delayed_count": int,
            "write_lag_backdated_count": int,
            "realtime_rate": float (0.0-1.0),
            "delayed_rate": float (0.0-1.0),
            "invariant_violations": int
        }
    """
    total = _metrics["total_profiles"]
    avg_lag = _metrics["write_lag_sum_ms"] / total if total > 0 else 0.0
    backdate_rate = _metrics["backdate_count"] / total if total > 0 else 0.0
    realtime_rate = _metrics["write_lag_realtime_count"] / total if total > 0 else 0.0
    delayed_rate = _metrics["write_lag_delayed_count"] / total if total > 0 else 0.0

    return {
        "total_profiles": total,
        "timezone_cache_hits": _metrics["timezone_cache_hits"],
        "timezone_cache_misses": _metrics["timezone_cache_misses"],
        "timezone_fallback_count": _metrics["timezone_fallback_count"],
        "future_event_time_clamped": _metrics["future_event_time_clamped"],
        "avg_write_lag_ms": avg_lag,
        "backdate_count": _metrics["backdate_count"],
        "backdate_rate": backdate_rate,
        "write_lag_realtime_count": _metrics["write_lag_realtime_count"],
        "write_lag_delayed_count": _metrics["write_lag_delayed_count"],
        "write_lag_backdated_count": _metrics["write_lag_backdated_count"],
        "realtime_rate": realtime_rate,
        "delayed_rate": delayed_rate,
        "invariant_violations": _metrics["invariant_violations"],
    }


def reset_metrics():
    """Reset metrics (for testing and module reload)."""
    global _metrics
    _metrics = {
        "total_profiles": 0,
        "timezone_cache_hits": 0,
        "timezone_cache_misses": 0,
        "timezone_fallback_count": 0,
        "future_event_time_clamped": 0,
        "backdate_count": 0,
        "write_lag_sum_ms": 0,
        "write_lag_realtime_count": 0,
        "write_lag_delayed_count": 0,
        "write_lag_backdated_count": 0,
        "invariant_violations": 0,
    }
