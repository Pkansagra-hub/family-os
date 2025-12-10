"""
Ingress Classification Module (M10) - Channel and Activity Attribution

Classifies episodic memory input type and activity context for provenance tracking,
retention policy selection, and analytics.

Performance: ≤3ms P95 (rule-based classification, no ML)

Schema Authority (Single Source of Truth):
- Maps to st_hipp_events ingress/activity columns (migration 0024):
  - ingress_topic: TEXT (cognitive.memory.write/photo/voice/import)
  - activity_type: TEXT (meal/conversation/routine/milestone/social/work/unknown)
  - content_type: TEXT (episodic/semantic/procedural)
  - ingress_source: TEXT (mobile_app/web_app/api/connector)

Classification Categories:

1. Ingress Topics (4 channels):
   - write: Manual text entry (cognitive.memory.write)
   - photo: Photo capture (cognitive.memory.photo)
   - voice: Voice memo (cognitive.memory.voice)
   - import: Bulk import (cognitive.memory.import)

2. Activity Types (7 categories, priority ordered):
   - meal: Food-related events (highest specificity)
   - milestone: Significant life events (graduation, birthday)
   - work: Professional activities (meetings, projects)
   - social: Group gatherings (parties, reunions)
   - conversation: Social interactions (chats, calls)
   - routine: Daily activities (shower, bedtime)
   - unknown: Default fallback (lowest priority)

3. Content Types (3 memory systems per Schacter & Tulving):
   - episodic: Time-bound personal experiences (95% of P02)
   - semantic: Facts and knowledge (P09 focus)
   - procedural: How-to skills (rare in P02)

4. Ingress Sources (4 sources):
   - mobile_app: FamilyOS mobile client (most common)
   - web_app: FamilyOS web browser
   - api: Programmatic API call
   - connector: External data sync (Google Calendar, Fitbit)

Use Cases:
1. Retention policy: (band, topic, device_kind) → retention_policy_id
2. Provenance tracking: Know where memory originated
3. Analytics: Channel usage trends, activity distribution
4. Query optimization: "Show me meals last week"

Architecture Principles (World-Class Design):
- Rule-based keywords (no ML, <3ms latency)
- Priority-ordered classification (high-specificity first)
- Deterministic output (same text → same classification)
- Fail-safe defaults (unknown → routine → episodic)
- Observability-ready (distribution metrics for analytics)

Contract: k0/contracts/modules/context.ingress_classify.v1.yaml
ADR: docs/architecture/decisions-K0/modules/k007.3-ingress-classifier.md
Migration: k0/contracts/sql/migrations/0024_p02_episodic_write_tables.sql
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Module version (semantic versioning)
__version__ = "1.1.0"  # Updated for Issue 5.1.1 zero-shot classification

# Feature flag for enhanced classification (default: disabled)
# Set to True to use new ZeroShotActivityClassifier
FEATURE_ENHANCED_CLASSIFICATION = True

# Configuration constants (aligned with contract)
DEFAULT_ACTIVITY_TYPE = "routine"  # Fallback for unclassifiable activities
DEFAULT_CONTENT_TYPE = "episodic"  # P02 assumption: time-bound personal experiences
DEFAULT_INGRESS_SOURCE = "mobile_app"  # Most common source

# Ingress topic mapping (topic → channel)
INGRESS_TOPIC_MAP = {
    "cognitive.memory.write": "write",
    "cognitive.memory.write.v1": "write",
    "cognitive.memory.write.committed.v1": "write",
    "cognitive.memory.photo": "photo",
    "cognitive.memory.photo.v1": "photo",
    "cognitive.memory.voice": "voice",
    "cognitive.memory.voice.v1": "voice",
    "cognitive.memory.import": "import",
    "cognitive.memory.import.v1": "import",
}

# Activity type keywords (priority ordered: high-specificity first)
ACTIVITY_KEYWORDS = {
    "meal": [
        "breakfast",
        "lunch",
        "dinner",
        "ate",
        "food",
        "meal",
        "snack",
        "restaurant",
        "eating",
        "brunch",
        "supper",
        "hungry",
        "cook",
        "recipe",
    ],
    "milestone": [
        "birthday",
        "anniversary",
        "graduation",
        "wedding",
        "first time",
        "milestone",
        "achievement",
        "promotion",
        "award",
        "engagement",
        "birth",
        "death",
        "funeral",
        "baptism",
        "confirmation",
    ],
    "work": [
        "meeting",
        "project",
        "deadline",
        "presentation",
        "client",
        "work",
        "office",
        "boss",
        "colleague",
        "email",
        "report",
        "interview",
        "conference",
        "training",
        "business",
    ],
    "social": [
        "party",
        "gathering",
        "reunion",
        "event",
        "celebration",
        "picnic",
        "barbeque",
        "bbq",
        "get-together",
        "hangout",
        "vacation",
        "trip",
        "outing",
        "festival",
    ],
    "conversation": [
        "chat",
        "talked",
        "discussed",
        "conversation",
        "call",
        "phone",
        "text",
        "message",
        "video call",
        "zoom",
        "facetime",
        "whatsapp",
        "discuss",
    ],
    "routine": [
        "shower",
        "brushed",
        "bedtime",
        "woke up",
        "commute",
        "routine",
        "morning",
        "evening",
        "exercise",
        "walk",
        "run",
        "sleep",
        "wake",
        "dress",
        "breakfast routine",
        "nap",
    ],
}

# Content type markers (semantic/procedural detection)
CONTENT_TYPE_MARKERS = {
    "semantic": ["fact", "definition", "knowledge", "learn", "information", "note"],
    "procedural": ["recipe", "how to", "instructions", "steps", "guide", "tutorial"],
}

# Ingress source patterns
INGRESS_SOURCE_PATTERNS = {
    "connector": ["connector", "sync", "import", "integration", "fitbit", "gcal", "calendar"],
    "api": ["api", "automation", "scheduled", "batch", "bulk"],
    "mobile_app": ["iphone", "android", "mobile", "ios"],
    "web_app": ["mozilla", "chrome", "safari", "firefox", "edge", "opera", "browser"],
}


@dataclass(frozen=True)
class IngressClassification:
    """
    Ingress classification output (frozen dataclass for immutability).

    Maps to st_hipp_events ingress/activity columns.
    """

    ingress_topic: str  # TEXT (write/photo/voice/import)
    activity_type: str  # TEXT (meal/conversation/routine/milestone/social/work/unknown)
    content_type: str  # TEXT (episodic/semantic/procedural)
    ingress_source: str  # TEXT (mobile_app/web_app/api/connector)
    is_structured: bool  # BOOLEAN (true for API imports with schema)
    is_user_initiated: bool  # BOOLEAN (false for automated imports)
    ingress_classified_at_utc: str  # TEXT ISO 8601 timestamp


# Metrics tracking (histogram-ready for P95 analysis)
_metrics: Dict[str, int] = {
    "total_classifications": 0,
    "ingress_write": 0,
    "ingress_photo": 0,
    "ingress_voice": 0,
    "ingress_import": 0,
    "activity_meal": 0,
    "activity_milestone": 0,
    "activity_work": 0,
    "activity_social": 0,
    "activity_conversation": 0,
    "activity_routine": 0,
    "activity_unknown": 0,
    "content_episodic": 0,
    "content_semantic": 0,
    "content_procedural": 0,
    "source_mobile_app": 0,
    "source_web_app": 0,
    "source_api": 0,
    "source_connector": 0,
}


def classify_ingress_topic(topic: str) -> str:
    """
    Map ingress topic to channel (write/photo/voice/import).

    Handles versioned topics (e.g., cognitive.memory.write.v1 → write).

    Args:
        topic: Event topic string

    Returns:
        Channel (write/photo/voice/import)

    Performance: <0.1ms (dictionary lookup)
    """
    if not topic:
        return "write"  # Default

    # Direct lookup
    if topic in INGRESS_TOPIC_MAP:
        return INGRESS_TOPIC_MAP[topic]

    # Fuzzy match (handles versioned topics)
    topic_lower = topic.lower()
    if "photo" in topic_lower:
        return "photo"
    elif "voice" in topic_lower:
        return "voice"
    elif "import" in topic_lower:
        return "import"
    else:
        return "write"  # Default


def classify_activity_type(text: Optional[str]) -> str:
    """
    Rule-based activity classification from keywords.

    Priority order (high-specificity first):
    1. meal (most specific: breakfast/lunch/dinner)
    2. milestone (significant events: birthday/graduation)
    3. work (professional: meeting/project)
    4. social (gatherings: party/reunion)
    5. conversation (interactions: chat/call)
    6. routine (daily: shower/bedtime)
    7. unknown (default fallback)

    Args:
        text: Event text content

    Returns:
        Activity type (meal/conversation/routine/milestone/social/work/unknown)

    Performance: <2ms (keyword matching, worst case ~100 comparisons)
    """
    if not text:
        return "unknown"

    text_lower = text.lower()

    # Check activity types in priority order
    # Use word boundary matching to avoid false positives (e.g., "celebrated" containing "ate")
    for activity_type, keywords in ACTIVITY_KEYWORDS.items():
        for keyword in keywords:
            # Match whole words or phrases (with word boundaries)
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, text_lower):
                return activity_type

    # Default: unknown
    return "unknown"


def classify_activity_type_enhanced(text: Optional[str]) -> Dict[str, Any]:
    """
    Enhanced activity classification using ZeroShotActivityClassifier.

    Research Foundation:
    - Yin et al. (2019) - Benchmarking Zero-shot Text Classification
    - Lewis et al. (2020) - BART: Denoising Sequence-to-Sequence Pre-training

    Features vs legacy classify_activity_type():
    - 20+ activity types (vs 7)
    - Multi-label support (e.g., "birthday dinner" = celebration + meal)
    - Confidence scores
    - Hierarchy path (e.g., "sustenance.meal.dinner")
    - ML-ready interface (BART-MNLI zero-shot)

    Args:
        text: Event text content

    Returns:
        Dict with activity_type, confidence, secondary_activities, hierarchy_path

    Performance: <5ms P95 (rule-based), <50ms P95 (ML)
    """
    if not text:
        return {
            "activity_type": "routine",
            "confidence": 0.3,
            "secondary_activities": [],
            "is_multi_activity": False,
            "hierarchy_path": "routine",
            "parent_category": "routine",
        }

    try:
        from k0.modules.activity.zero_shot_classifier import ClassificationTier, classify_activity

        # Use HYBRID tier - rule-based with ML fallback for better accuracy
        # This allows fast classification with ML improvement for ambiguous cases
        result = classify_activity(text, tier=ClassificationTier.HYBRID)

        # Map to legacy activity type for backward compatibility
        legacy_activity = _map_to_legacy_activity(result.primary_activity)

        return {
            "activity_type": legacy_activity,
            "activity_type_enhanced": result.primary_activity,
            "confidence": result.confidence,
            "secondary_activities": list(result.secondary_activities),
            "is_multi_activity": result.is_multi_activity,
            "hierarchy_path": result.hierarchy_path,
            "parent_category": result.parent_category,
        }
    except ImportError:
        # Fallback to legacy if activity module not available
        activity_type = classify_activity_type(text)
        return {
            "activity_type": activity_type,
            "confidence": 0.7 if activity_type != "unknown" else 0.3,
            "secondary_activities": [],
            "is_multi_activity": False,
            "hierarchy_path": activity_type,
            "parent_category": None,
        }


def _map_to_legacy_activity(enhanced_activity: str) -> str:
    """
    Map enhanced activity type to legacy 7-type system.

    Maintains backward compatibility with existing code expecting:
    meal, milestone, work, social, conversation, routine, unknown

    Args:
        enhanced_activity: Activity from enhanced classifier

    Returns:
        Legacy activity type
    """
    legacy_map = {
        # Sustenance
        "meal": "meal",
        "cooking": "meal",
        "dining_out": "meal",
        # Celebration/Milestone
        "celebration": "milestone",
        "birthday": "milestone",
        "anniversary": "milestone",
        "graduation": "milestone",
        "wedding": "milestone",
        "religious_activity": "milestone",
        # Work
        "work_meeting": "work",
        "project_work": "work",
        "commute": "work",
        "networking": "work",
        # Social
        "family_gathering": "social",
        "social_event": "social",
        "party": "social",
        "hangout": "social",
        "date": "social",
        # Conversation
        "conversation": "conversation",
        "phone_call": "conversation",
        "video_call": "conversation",
        # Wellness
        "exercise": "routine",
        "medical_appointment": "routine",
        "personal_care": "routine",
        # Other
        "entertainment": "social",
        "outdoor_recreation": "routine",
        "travel": "social",
        "shopping": "routine",
        "household_chore": "routine",
        "education": "routine",
        "creative_activity": "routine",
        "sports": "routine",
        "pet_care": "routine",
        "routine": "routine",
        "reading": "routine",
        "relaxation": "routine",
    }
    return legacy_map.get(enhanced_activity, "unknown")


def determine_content_type(body: Dict[str, Any]) -> str:
    """
    Determine content type (episodic/semantic/procedural).

    P02 assumption: Default to episodic (time-bound personal experiences).
    Semantic/procedural rare in P02, mainly handled by P09.

    Args:
        body: Event body dict with potential markers

    Returns:
        Content type (episodic/semantic/procedural)

    Performance: <0.1ms (dict lookups + keyword matching)
    """
    # Check explicit markers
    if body.get("is_fact") or body.get("is_knowledge_base_entry"):
        return "semantic"

    if body.get("is_recipe") or body.get("is_how_to"):
        return "procedural"

    # Check text for content type markers
    text = body.get("text", "").lower()

    for content_type, markers in CONTENT_TYPE_MARKERS.items():
        if any(marker in text for marker in markers):
            return content_type

    # Default: episodic (95% of P02 events)
    return DEFAULT_CONTENT_TYPE


def infer_ingress_source(metadata: Dict[str, Any], device_id: Optional[str] = None) -> str:
    """
    Infer ingress source from metadata and device_id.

    Sources (priority ordered):
    1. connector: External data sync (highest specificity)
    2. api: Programmatic API call
    3. mobile_app: FamilyOS mobile client (most common)
    4. web_app: FamilyOS web browser

    Args:
        metadata: Event metadata dict
        device_id: Optional device identifier

    Returns:
        Ingress source (mobile_app/web_app/api/connector)

    Performance: <0.3ms (keyword matching)
    """
    user_agent = metadata.get("user_agent", "").lower()
    source_hint = metadata.get("source", "").lower()
    combined = f"{user_agent} {source_hint} {device_id or ''}".lower()

    # Check source patterns in priority order
    for source, patterns in INGRESS_SOURCE_PATTERNS.items():
        if any(pattern in combined for pattern in patterns):
            return source

    # Default: mobile_app (most common)
    return DEFAULT_INGRESS_SOURCE


def classify_ingress(
    topic: str,
    body: Dict[str, Any],
    metadata: Dict[str, Any],
    device_id: Optional[str] = None,
) -> IngressClassification:
    """
    Main ingress classification function (single source of truth).

    Classifies:
    1. Ingress topic (write/photo/voice/import)
    2. Activity type (meal/conversation/routine/milestone/social/work/unknown)
    3. Content type (episodic/semantic/procedural)
    4. Ingress source (mobile_app/web_app/api/connector)

    Args:
        topic: Event topic string
        body: Event body dict
        metadata: Event metadata dict
        device_id: Optional device identifier

    Returns:
        IngressClassification with 7 fields

    Performance: <3ms P95 (rule-based, no ML)
    """
    # Step 1: Classify ingress topic
    ingress_topic = classify_ingress_topic(topic)

    # Step 2: Classify activity type
    text = body.get("text", "")

    # Use enhanced classifier if feature flag enabled
    if FEATURE_ENHANCED_CLASSIFICATION:
        enhanced = classify_activity_type_enhanced(text)
        activity_type = enhanced["activity_type"]
    else:
        activity_type = classify_activity_type(text)

    # Step 3: Determine content type
    content_type = determine_content_type(body)

    # Step 4: Infer ingress source
    ingress_source = infer_ingress_source(metadata, device_id)

    # Step 5: Determine structured flag
    is_structured = metadata.get("is_structured", False) or body.get("schema_version") is not None

    # Step 6: Determine user-initiated flag
    is_user_initiated = ingress_topic not in ["import"] and ingress_source not in [
        "api",
        "connector",
    ]

    # Step 7: Capture classification timestamp
    ingress_classified_at_utc = datetime.now(timezone.utc).isoformat()

    # Step 8: Update metrics
    _metrics["total_classifications"] += 1
    _metrics[f"ingress_{ingress_topic}"] = _metrics.get(f"ingress_{ingress_topic}", 0) + 1
    _metrics[f"activity_{activity_type}"] = _metrics.get(f"activity_{activity_type}", 0) + 1
    _metrics[f"content_{content_type}"] = _metrics.get(f"content_{content_type}", 0) + 1
    _metrics[f"source_{ingress_source}"] = _metrics.get(f"source_{ingress_source}", 0) + 1

    return IngressClassification(
        ingress_topic=ingress_topic,
        activity_type=activity_type,
        content_type=content_type,
        ingress_source=ingress_source,
        is_structured=is_structured,
        is_user_initiated=is_user_initiated,
        ingress_classified_at_utc=ingress_classified_at_utc,
    )


def classify_ingress_enhanced(
    topic: str,
    body: Dict[str, Any],
    metadata: Dict[str, Any],
    device_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Enhanced ingress classification with multi-label activity support.

    Same as classify_ingress() but returns enhanced activity metadata:
    - 20+ activity types (vs 7)
    - Multi-label support
    - Confidence scores
    - Hierarchy path

    Args:
        topic: Event topic string
        body: Event body dict
        metadata: Event metadata dict
        device_id: Optional device identifier

    Returns:
        Dict with all IngressClassification fields plus enhanced activity metadata

    Performance: <5ms P95 (rule-based), <50ms P95 (ML)
    """
    # Get base classification
    base = classify_ingress(topic, body, metadata, device_id)

    # Get enhanced activity classification
    text = body.get("text", "")
    enhanced_activity = classify_activity_type_enhanced(text)

    return {
        # Base classification fields
        "ingress_topic": base.ingress_topic,
        "activity_type": base.activity_type,
        "content_type": base.content_type,
        "ingress_source": base.ingress_source,
        "is_structured": base.is_structured,
        "is_user_initiated": base.is_user_initiated,
        "ingress_classified_at_utc": base.ingress_classified_at_utc,
        # Enhanced activity fields
        "activity_type_enhanced": enhanced_activity.get(
            "activity_type_enhanced", base.activity_type
        ),
        "activity_confidence": enhanced_activity.get("confidence", 0.7),
        "secondary_activities": enhanced_activity.get("secondary_activities", []),
        "is_multi_activity": enhanced_activity.get("is_multi_activity", False),
        "activity_hierarchy_path": enhanced_activity.get("hierarchy_path"),
        "activity_parent_category": enhanced_activity.get("parent_category"),
    }


async def run(message: Any, context: Any, **config: Any) -> Dict[str, Any]:
    """
    Module entry point (Phase 2 signature for pipeline compatibility).

    Extracts ingress metadata from envelope and returns enriched envelope with classification.

    Args:
        message: BusMessage with .payload, .trace_id, .offset
        context: PipelineContext with .syscalls, .logger, .config
        **config: Stage-specific configuration
            - default_activity_type (str): Fallback activity type (default: "routine")
            - default_content_type (str): Fallback content type (default: "episodic")
            - supported_ingress_topics (list): Allowed ingress topics (default: all)

    Returns:
        Enriched envelope with ingress classification fields (7 fields)

    Raises:
        ValueError: If envelope is missing required fields

    Performance: <3ms P95
    Contract: k0/contracts/modules/context.ingress_classify.v1.yaml
    """
    # Use enriched envelope from pipeline runner if available, otherwise parse from message
    envelope = config.get("envelope")
    if envelope is None:
        envelope = (
            json.loads(message.payload)
            if isinstance(message.payload, (str, bytes))
            else message.payload
        )

    # Extract config parameters (with defaults)
    default_activity_type = config.get("default_activity_type", DEFAULT_ACTIVITY_TYPE)
    default_content_type = config.get("default_content_type", DEFAULT_CONTENT_TYPE)
    supported_ingress_topics = config.get(
        "supported_ingress_topics", list(INGRESS_TOPIC_MAP.keys())
    )

    # Log module start
    context.logger.debug(
        "M10 ingress_classify starting",
        extra={
            "module_id": "context.ingress_classify",
            "trace_id": message.trace_id,
            "event_id": envelope.get("event_id"),
        },
    )

    # Extract ingress metadata from envelope
    topic = envelope.get("topic", "")
    body = envelope.get("body", {})
    metadata = envelope.get("metadata", {})
    device_id = envelope.get("device_id")

    # Classify ingress
    classification = classify_ingress(
        topic=topic,
        body=body,
        metadata=metadata,
        device_id=device_id,
    )

    # Convert to dict for enriched envelope
    ingress_fields = {
        "ingress_topic": classification.ingress_topic,
        "activity_type": classification.activity_type,
        "content_type": classification.content_type,
        "ingress_source": classification.ingress_source,
        "is_structured": classification.is_structured,
        "is_user_initiated": classification.is_user_initiated,
        "ingress_classified_at_utc": classification.ingress_classified_at_utc,
    }

    # Log module completion
    context.logger.debug(
        "M10 ingress_classify completed",
        extra={
            "module_id": "context.ingress_classify",
            "trace_id": message.trace_id,
            "activity_type": classification.activity_type,
            "ingress_topic": classification.ingress_topic,
        },
    )

    # Check if enhanced classification is requested
    use_enhanced = config.get("use_enhanced_classification", FEATURE_ENHANCED_CLASSIFICATION)

    if use_enhanced:
        # Add enhanced activity fields
        text = body.get("text", "")
        enhanced = classify_activity_type_enhanced(text)
        ingress_fields.update(
            {
                "activity_type_enhanced": enhanced.get(
                    "activity_type_enhanced", classification.activity_type
                ),
                "activity_confidence": enhanced.get("confidence", 0.7),
                "secondary_activities": enhanced.get("secondary_activities", []),
                "is_multi_activity": enhanced.get("is_multi_activity", False),
                "activity_hierarchy_path": enhanced.get("hierarchy_path"),
                "activity_parent_category": enhanced.get("parent_category"),
            }
        )

    # Return enriched envelope
    return {**envelope, **ingress_fields}


def get_metrics() -> Dict[str, Any]:
    """
    Get module metrics for observability.

    Returns 18 metrics:
    - total_classifications: Total classifications computed
    - ingress_*: Counts per ingress topic (4 channels)
    - activity_*: Counts per activity type (7 types)
    - content_*: Counts per content type (3 types)
    - source_*: Counts per ingress source (4 sources)

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
        "total_classifications": 0,
        "ingress_write": 0,
        "ingress_photo": 0,
        "ingress_voice": 0,
        "ingress_import": 0,
        "activity_meal": 0,
        "activity_milestone": 0,
        "activity_work": 0,
        "activity_social": 0,
        "activity_conversation": 0,
        "activity_routine": 0,
        "activity_unknown": 0,
        "content_episodic": 0,
        "content_semantic": 0,
        "content_procedural": 0,
        "source_mobile_app": 0,
        "source_web_app": 0,
        "source_api": 0,
        "source_connector": 0,
    }
