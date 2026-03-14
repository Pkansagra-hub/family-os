"""
TruthWriteAssembler — Issue 5.1.6

Assembles staged writes for all truth layers from phase outputs.
Converts R2-R5 phase outputs into StagedWrite operations for R7 commit.

Spec Reference:
    - Dossier §4.7.2 (R6 Staging — Truth Layer Assembly)
    - Dossier §6 (Truth Layer Schemas)
    - M5_EXECUTION.md Issue 5.1.6

Target Layers:
    - st_epi (R2 EpisodeCluster → episodic memory)
    - st_sem (R3 CREATE/EXTEND decisions → semantic patterns)
    - st_procedural (R4/R5 routines → procedural memory)
    - st_social (R4 social entities → social memory)
    - st_prospective (R5 ProspectiveMemory → future intentions)
    - st_learning_queue (R4 GapCandidate → P06 queue)

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from k0.modules.consolidation.algorithms.mcts import MCTSScenario

# Issue 7.6: Import ObservationContext for attaching to StagedWrite
from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.modules.consolidation.algorithms.routine_detector import RoutineCandidate
from k0.modules.consolidation.dream.intent_signals import (
    DecisionSignal,
    IntentSignal,
    IntentSignalType,
    ReminderSignal,
)
from k0.modules.consolidation.dream.models import (
    CounterfactualScenario,
    Insight,
    RoutineOptimization,
)
from k0.modules.context.temporal_profile import (
    convert_to_local_timezone,
    get_day_of_week,
    get_time_of_day_bucket,
)
from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction
from k0.pipelines.p03.phase_outputs import (
    EpisodeCluster,
    GapCandidate,
    ProspectiveMemory,
    SocialRelationship,
)
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_EPI,
    LAYER_ST_LEARNING_QUEUE,
    LAYER_ST_MCTS,
    LAYER_ST_PROCEDURAL,
    LAYER_ST_PROSPECTIVE,
    LAYER_ST_SEM,
    LAYER_ST_SOCIAL,
    StagedWrite,
)

from .idempotency import IdempotencyKeyGenerator

# =============================================================================
# Constants
# =============================================================================

# Actions that create new semantic records
CREATE_ACTIONS = frozenset({ReconciliationAction.CREATE})

# Actions that update existing semantic records
UPDATE_ACTIONS = frozenset(
    {
        ReconciliationAction.REINFORCE,
        ReconciliationAction.EXTEND,
    }
)

# Actions that archive/prune records
ARCHIVE_ACTIONS = frozenset({ReconciliationAction.PRUNE})


def _now_ms() -> int:
    """Return current time in milliseconds since epoch."""
    return int(time.time() * 1000)


def _generate_pattern_name(state: P03EventState, max_length: int = 200) -> str:
    """
    Generate a descriptive pattern name from event state.

    M10.8: Creates semantic names instead of raw event text truncation.

    Priority order for name generation:
    1. Activity type + key entities (e.g., "Dinner with Mom at Thai Palace")
    2. Activity type + location (e.g., "Work meeting at Office")
    3. Content type + entities (e.g., "Chat about vacation plans")
    4. Fallback to truncated text

    Args:
        state: P03EventState with NER entities, activity type, etc.
        max_length: Maximum length for pattern name

    Returns:
        Descriptive pattern name
    """
    # Parse NER entities from nested structure:
    # {"ner_family": {"entities": [{"text": "Emma", "label": "PERSON"}]}, "ner_general": {...}}
    # Only extract entities with labels indicating people/orgs (not events/actions)
    VALID_ENTITY_LABELS = {"PERSON", "PER", "KINSHIP", "ORG", "LOC", "PET"}
    entities: List[str] = []
    seen_texts: set = set()  # Avoid duplicates
    try:
        ner_json = getattr(state, "ner_entities_json", "{}") or "{}"
        ner_data = json.loads(ner_json) if ner_json else {}

        # Handle nested NER structure (ner_family, ner_general each have entities array)
        if isinstance(ner_data, dict):
            # Prefer ner_family entities over ner_general (more specific)
            for ner_source in ["ner_family", "ner_general"]:
                if ner_source in ner_data:
                    source_data = ner_data[ner_source]
                    if isinstance(source_data, dict) and "entities" in source_data:
                        for ent in source_data["entities"]:
                            if isinstance(ent, dict) and "text" in ent:
                                # Filter by entity label - only use people/orgs/locations
                                label = ent.get("label", "")
                                if label not in VALID_ENTITY_LABELS:
                                    continue
                                text = ent["text"].strip()
                                # Skip possessive forms, normalize
                                if text.endswith("'s"):
                                    text = text[:-2]
                                # Skip garbage like "and Jake", "with Emma"
                                if text.lower().startswith(("and ", "with ", "the ")):
                                    text = text.split(" ", 1)[1] if " " in text else text
                                # Skip duplicates and very short entities
                                if text and len(text) > 1 and text.lower() not in seen_texts:
                                    entities.append(text)
                                    seen_texts.add(text.lower())
        # Handle legacy flat list format: [{"text": "Mom", "label": "KINSHIP"}]
        elif isinstance(ner_data, list):
            for ent in ner_data:
                if isinstance(ent, dict) and "text" in ent:
                    label = ent.get("label", "")
                    if label and label not in VALID_ENTITY_LABELS:
                        continue
                    text = ent["text"].strip()
                    if text and len(text) > 1 and text.lower() not in seen_texts:
                        entities.append(text)
                        seen_texts.add(text.lower())
                elif isinstance(ent, str) and ent:
                    if ent.lower() not in seen_texts:
                        entities.append(ent)
                        seen_texts.add(ent.lower())
    except (json.JSONDecodeError, TypeError):
        pass

    # Get activity type (prefer UltraBERT classification)
    activity = getattr(state, "activity_type_ultrabert", "") or ""
    if not activity:
        activity = getattr(state, "activity_type", "") or ""
    if not activity:
        activity = getattr(state, "content_type", "") or ""

    # Normalize activity type for display
    activity_display = activity.replace("_", " ").title() if activity else ""

    # Get location
    location = getattr(state, "location_name", "") or ""

    # Build pattern name based on available data
    pattern_name = ""

    # Priority 1: Activity + entities (e.g., "Dinner with Mom, Dad")
    if activity_display and entities:
        entity_str = ", ".join(entities[:3])  # Max 3 entities
        pattern_name = f"{activity_display} with {entity_str}"
        if location:
            pattern_name += f" at {location}"

    # Priority 2: Activity + location
    elif activity_display and location:
        pattern_name = f"{activity_display} at {location}"

    # Priority 3: Activity + first part of text
    elif activity_display:
        text = getattr(state, "content_text", "") or ""
        if text:
            # Take first sentence or 50 chars
            first_sentence = text.split(".")[0][:50].strip()
            if first_sentence:
                pattern_name = f"{activity_display}: {first_sentence}"
            else:
                pattern_name = activity_display
        else:
            pattern_name = activity_display

    # Priority 4: Just entities
    elif entities:
        pattern_name = f"Memory about {', '.join(entities[:3])}"

    # Fallback: Use text content
    if not pattern_name:
        text = getattr(state, "content_text", "") or ""
        if text:
            pattern_name = text
        else:
            event_id = getattr(state, "event_id", "unknown")
            pattern_name = f"Pattern from {event_id}"

    # Truncate to max length
    if len(pattern_name) > max_length:
        pattern_name = pattern_name[: max_length - 3] + "..."

    return pattern_name


# =============================================================================
# AssembledWrite Helper
# =============================================================================


@dataclass
class AssembledWrite:
    """
    Metadata about an assembled write for tracking.

    Attributes:
        write: The StagedWrite object
        layer: Target layer name
        record_id: Primary key
        source: Description of source phase/data
    """

    write: StagedWrite
    layer: str
    record_id: str
    source: str


# =============================================================================
# TruthWriteAssembler Class
# =============================================================================


class TruthWriteAssembler:
    """
    Assembles staged writes for truth layers from phase outputs.

    Converts R2-R5 outputs into StagedWrite operations ready for R7 commit.
    Each layer has specific schema requirements from Dossier §6.

    Attributes:
        idempotency: Key generator for deterministic idempotency keys
        source_phase: Phase name for provenance (default "R6")
        tenant_id: Tenant identifier for multi-tenant isolation
        space_id: Space identifier for family/user isolation
    """

    def __init__(
        self,
        idempotency_gen: IdempotencyKeyGenerator,
        source_phase: str = "R6",
        tenant_id: str = "default",
        space_id: str = "default",
        consolidation_cycle_id: Optional[str] = None,
    ) -> None:
        """
        Initialize assembler with idempotency generator.

        Args:
            idempotency_gen: Generator for idempotency keys
            source_phase: Phase name for provenance tracking
            tenant_id: Tenant identifier for multi-tenant isolation
            space_id: Space identifier for family/user isolation
        """
        self.idempotency = idempotency_gen
        self.source_phase = source_phase
        self.tenant_id = tenant_id
        self.space_id = space_id
        self.consolidation_cycle_id = consolidation_cycle_id

    # =========================================================================
    # st_epi — Episodic Memory (from R2 EpisodeCluster)
    # =========================================================================

    def assemble_epi_writes(
        self,
        clusters: List[EpisodeCluster],
        event_states: Dict[str, P03EventState],
    ) -> List[StagedWrite]:
        """
        Assemble st_epi writes from R2 episode clusters.

        Each cluster becomes an episodic memory record. Events in the
        cluster contribute to the episode's provenance.

        Issue 2 Fix: Also generates UPDATE writes for events that matched
        existing episodes (reconciliation_action=REINFORCE).

        Args:
            clusters: R2 episode clusters
            event_states: Event states for provenance lookup

        Returns:
            List of StagedWrite for st_epi inserts AND updates
        """
        writes: List[StagedWrite] = []

        # === ISSUE 2 FIX: Generate UPDATE writes for matched events ===
        # Events with episode_match_id should UPDATE existing episodes
        episode_updates = self._assemble_epi_update_writes(event_states)
        writes.extend(episode_updates)

        # === Original logic: Generate INSERT writes for new clusters ===
        if not clusters:
            return writes

        for cluster in clusters:
            # Extract source event IDs from cluster members
            source_ids = cluster.member_event_ids.copy()

            # Build episode record_data per Dossier §6.1
            record_data = self._build_epi_record_data(cluster, event_states)

            # Generate idempotency key
            idem_key = self.idempotency.for_truth_write(
                LAYER_ST_EPI,
                cluster.cluster_id,
            )

            # Issue 7.6: Get observation context from cluster
            # Use first member_context or create from episode cluster
            obs_context = None
            if cluster.member_contexts:
                obs_context = cluster.member_contexts[0]
            elif cluster.member_event_ids:
                # Fallback: create from first event state
                first_event_id = cluster.member_event_ids[0]
                if first_event_id in event_states:
                    obs_context = ObservationContext.from_event(event_states[first_event_id])
            if obs_context and self.consolidation_cycle_id:
                obs_context.consolidation_cycle_id = self.consolidation_cycle_id

            # Create INSERT write
            write = StagedWrite.insert(
                layer=LAYER_ST_EPI,
                record_id=cluster.cluster_id,
                data=record_data,
                phase=self.source_phase,
                event_ids=source_ids,
            )
            # Override idempotency key with proper format
            write.idempotency_key = idem_key
            # Issue 7.6: Attach observation context for st_observations recording
            write.observation_context = obs_context

            writes.append(write)

        return writes

    def _assemble_epi_update_writes(
        self,
        event_states: Dict[str, P03EventState],
    ) -> List[StagedWrite]:
        """
        Assemble st_epi UPDATE writes for events matching existing episodes.

        Issue 2 Fix: Events with episode_match_id and reconciliation_action=REINFORCE
        should UPDATE the existing episode instead of creating a new one.

        The UPDATE increments source_event_count and extends temporal bounds.

        Args:
            event_states: Event states with episode match info from R2

        Returns:
            List of StagedWrite for st_epi updates (one per unique episode)
        """
        from collections import Counter, defaultdict

        # Group events by matched episode_id
        episode_events: Dict[str, List[P03EventState]] = defaultdict(list)

        for state in event_states.values():
            if state.reconciliation_action == ReconciliationAction.REINFORCE and getattr(
                state, "episode_match_id", None
            ):
                episode_events[state.episode_match_id].append(state)

        if not episode_events:
            return []

        writes: List[StagedWrite] = []
        now_ms = _now_ms()

        for episode_id, events in episode_events.items():
            # Build UPDATE payload
            # Get the version from the first event (all should have same version)
            expected_version = (
                events[0].episode_match_version
                if hasattr(events[0], "episode_match_version")
                else 1
            )

            # Collect event IDs to add to source_events_json
            new_event_ids = [e.event_id for e in events]

            # Compute new temporal bounds (will be merged with existing in writer)
            event_timestamps = [e.timestamp for e in events if e.timestamp > 0]
            min_timestamp = min(event_timestamps) if event_timestamps else 0
            max_timestamp = max(event_timestamps) if event_timestamps else 0

            update_data = {
                "episode_id": episode_id,
                "tenant_id": self.tenant_id,
                "space_id": self.space_id,
                # Fields to UPDATE:
                "additional_event_ids": new_event_ids,  # Will be appended to source_events_json
                "additional_event_count": len(new_event_ids),
                "new_start_time_utc": min_timestamp,  # Will use MIN(existing, new)
                "new_end_time_utc": max_timestamp,  # Will use MAX(existing, new)
                "consolidation_cycle_id": self.consolidation_cycle_id,
                "updated_at": now_ms,
            }

            # Epic 5.1: Collect narrative thread_ids from reinforcing events
            reinforce_threads = [e.narrative_thread_id for e in events if e.narrative_thread_id]
            if reinforce_threads:
                update_data["narrative_thread_ids_json"] = json.dumps(
                    sorted(set(reinforce_threads))
                )
                update_data["narrative_thread_id"] = Counter(reinforce_threads).most_common(1)[0][0]

            # Generate idempotency key
            idem_key = self.idempotency.for_truth_write(
                LAYER_ST_EPI,
                f"{episode_id}:update",
            )

            # Create UPDATE write with optimistic locking
            write = StagedWrite.update(
                layer=LAYER_ST_EPI,
                record_id=episode_id,
                data=update_data,
                expected_version=expected_version,
                phase=self.source_phase,
                event_ids=new_event_ids,
            )
            write.idempotency_key = idem_key
            if events:
                obs_context = ObservationContext.from_event(events[0])
                if self.consolidation_cycle_id:
                    obs_context.consolidation_cycle_id = self.consolidation_cycle_id
                write.observation_context = obs_context

            writes.append(write)

        return writes

    def _build_epi_record_data(
        self, cluster: EpisodeCluster, event_states: Dict[str, P03EventState]
    ) -> Dict[str, Any]:
        """
        Build st_epi record_data from EpisodeCluster.

        Schema (actual st_epi table columns):
            episode_id, tenant_id, space_id, version, episode_summary,
            episode_type, start_time_utc, end_time_utc, primary_location,
            location_type, participants_json, participant_count,
            embedding_id, cluster_id, cluster_confidence, source_events_json,
            source_event_count, archival_status, created_at, updated_at, valid_from,
            narrative_thread_id, narrative_thread_ids_json, narrative_arc_position,
            continuation_of_episode_id
        """
        from collections import Counter

        now_ms = _now_ms()
        member_ids = list(cluster.member_event_ids)

        first_event: Optional[P03EventState] = None
        for event_id in member_ids:
            if event_id in event_states:
                first_event = event_states[event_id]
                break

        location_type = cluster.location_type
        if not location_type and first_event:
            location_type = getattr(first_event, "location_type", None) or None

        temporal_bucket = None
        day_of_week = None
        if first_event:
            bucket = getattr(first_event, "time_of_day_bucket", None) or ""
            day = getattr(first_event, "day_of_week", None) or ""
            temporal_bucket = bucket.upper() if bucket else None
            day_of_week = day.upper() if day else None

        if (not temporal_bucket or not day_of_week) and cluster.temporal_start > 0:
            derived_bucket, derived_day = self._derive_temporal_fields(cluster.temporal_start)
            temporal_bucket = temporal_bucket or derived_bucket
            day_of_week = day_of_week or derived_day

        duration_minutes = None
        if cluster.temporal_start > 0 and cluster.temporal_end > 0:
            if cluster.temporal_end >= cluster.temporal_start:
                duration_minutes = int((cluster.temporal_end - cluster.temporal_start) / 60000)

        last_observed_at = cluster.temporal_end if cluster.temporal_end > 0 else now_ms

        # Get embedding_id from cluster centroid or first member event
        embedding_id = cluster.centroid_embedding_id
        if embedding_id is None and member_ids and event_states:
            first_event = event_states.get(member_ids[0])
            if first_event:
                embedding_id = first_event.embedding_id

        # Epic 5.1: Compute narrative columns from source events
        thread_ids = [
            event_states[eid].narrative_thread_id
            for eid in member_ids
            if eid in event_states and event_states[eid].narrative_thread_id
        ]
        dominant_thread_id = Counter(thread_ids).most_common(1)[0][0] if thread_ids else None
        all_thread_ids_json = json.dumps(sorted(set(thread_ids))) if thread_ids else None
        arc_positions = [
            event_states[eid].narrative_arc_position
            for eid in member_ids
            if eid in event_states and event_states[eid].narrative_arc_position
        ]
        dominant_arc = Counter(arc_positions).most_common(1)[0][0] if arc_positions else None

        return {
            "episode_id": cluster.cluster_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "version": 1,
            "episode_summary": cluster.summary or cluster.title or "Untitled episode",
            "episode_type": cluster.activity_type or "GENERAL",
            "start_time_utc": cluster.temporal_start,
            "end_time_utc": cluster.temporal_end,
            "duration_minutes": duration_minutes,
            "temporal_bucket": temporal_bucket,
            "day_of_week": day_of_week,
            "is_recurring": None,
            "recurrence_pattern": None,
            "primary_location": cluster.location_hint,
            "location_type": location_type,  # GAP-002: location category
            "participants_json": cluster.participants_json,
            "participant_count": len(json.loads(cluster.participants_json or "[]")),
            "embedding_id": embedding_id,
            "cluster_id": cluster.cluster_id,
            "cluster_confidence": cluster.cohesion_score or 0.5,
            "consolidation_cycle_id": self.consolidation_cycle_id,
            "source_events_json": json.dumps(member_ids),
            "source_event_count": len(member_ids),
            "archival_status": "ACTIVE",
            "last_observed_at": last_observed_at,
            "created_at": now_ms,
            "updated_at": now_ms,
            "valid_from": now_ms,
            # Epic 5.1: Narrative thread columns
            "narrative_thread_id": dominant_thread_id,
            "narrative_thread_ids_json": all_thread_ids_json,
            "narrative_arc_position": dominant_arc,
            "continuation_of_episode_id": None,  # Set by R2 thread matching
            # Epic 5.2: Goal completion
            "narrative_thread_completed": False,  # Set by R2 detect_arc_completion
            # === Epic 6.5: Metadata Preservation ===
            "centroid_metadata_json": (
                json.dumps(cluster.centroid_metadata) if cluster.centroid_metadata else None
            ),
            "ambiguity_score": cluster.ambiguity_score or None,
            "entity_ids_json": (
                json.dumps(sorted(cluster.entity_ids)) if cluster.entity_ids else None
            ),
            "dominant_sentiment": cluster.dominant_sentiment or None,
            "dominant_emotion": cluster.dominant_emotion or None,
            "aggregated_sentiment": cluster.aggregated_sentiment,
            "aggregated_salience": cluster.aggregated_salience,
            "dominant_social_context": cluster.dominant_social_context,
            "activity_type_ultrabert": cluster.activity_type_ultrabert or None,
        }

    def _derive_temporal_fields(
        self,
        timestamp_ms: int,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Derive temporal_bucket and day_of_week from a UTC timestamp in ms.

        Returns uppercase bucket/day strings or (None, None) if derivation fails.
        """
        if timestamp_ms <= 0:
            return None, None

        try:
            dt_local, _ = convert_to_local_timezone(int(timestamp_ms / 1000), self.tenant_id)
        except Exception:
            return None, None

        bucket = get_time_of_day_bucket(dt_local).upper()
        day = get_day_of_week(dt_local).upper()
        return bucket, day

    def _format_recurrence_pattern(self, candidate: RoutineCandidate) -> Optional[str]:
        """Format recurrence_pattern from RoutineCandidate fields."""
        parts: List[str] = []

        frequency = getattr(candidate, "frequency", None)
        if frequency is not None:
            freq_value = getattr(frequency, "value", None) or str(frequency)
            if freq_value:
                parts.append(freq_value)

        day_pattern = getattr(candidate, "day_pattern", None)
        if day_pattern:
            parts.append(str(day_pattern).upper())

        temporal_anchor = getattr(candidate, "temporal_anchor", None)
        if temporal_anchor:
            parts.append(str(temporal_anchor))

        return ":".join(parts) if parts else None

    def _merge_epi_recurrence_updates(
        self,
        epi_writes: List[StagedWrite],
        routine_candidates: List[RoutineCandidate],
    ) -> None:
        """
        Merge recurrence signals into existing st_epi writes or add updates.

        This avoids duplicate writes for the same episode_id while allowing
        recurrence fields to be populated when RoutineDetector emits candidates.
        """
        if not routine_candidates:
            return

        now_ms = _now_ms()
        write_by_id: Dict[str, StagedWrite] = {
            w.record_id: w for w in epi_writes if w.layer == LAYER_ST_EPI
        }

        for candidate in routine_candidates:
            source_json = getattr(candidate, "source_episodes_json", "[]") or "[]"
            try:
                episode_ids = json.loads(source_json)
                if not isinstance(episode_ids, list):
                    episode_ids = []
            except (json.JSONDecodeError, TypeError):
                episode_ids = []

            recurrence_pattern = self._format_recurrence_pattern(candidate)

            for episode_id in episode_ids:
                if not episode_id:
                    continue

                if episode_id in write_by_id:
                    write = write_by_id[episode_id]
                    write.record_data["is_recurring"] = True
                    if recurrence_pattern:
                        write.record_data["recurrence_pattern"] = recurrence_pattern
                    write.record_data["updated_at"] = now_ms
                    continue

                record_data = {
                    "is_recurring": True,
                    "updated_at": now_ms,
                }
                if recurrence_pattern:
                    record_data["recurrence_pattern"] = recurrence_pattern

                idem_key = self.idempotency.for_truth_write(
                    LAYER_ST_EPI,
                    f"{episode_id}:recurrence",
                )

                write = StagedWrite.update(
                    layer=LAYER_ST_EPI,
                    record_id=episode_id,
                    data=record_data,
                    phase=self.source_phase,
                    expected_version=None,
                    event_ids=[],
                )
                write.idempotency_key = idem_key
                epi_writes.append(write)
                write_by_id[episode_id] = write

    # =========================================================================
    # st_sem — Semantic Memory (from R3 reconciliation decisions)
    # =========================================================================

    def assemble_sem_writes(
        self,
        event_states: Dict[str, P03EventState],
    ) -> List[StagedWrite]:
        """
        Assemble st_sem writes from R3 CREATE/EXTEND/REINFORCE decisions.

        Events with CREATE action → INSERT new pattern
        Events with EXTEND/EVOLVE/REINFORCE → UPDATE existing pattern

        Args:
            event_states: Event states with reconciliation decisions

        Returns:
            List of StagedWrite for st_sem operations
        """
        if not event_states:
            return []

        writes: List[StagedWrite] = []

        for event_id, state in event_states.items():
            action = state.reconciliation_action
            if action is None:
                continue

            if action in CREATE_ACTIONS:
                write = self._create_sem_insert(event_id, state)
                if write:
                    writes.append(write)

            elif action == ReconciliationAction.EVOLVE:
                writes.extend(self._create_sem_evolve_writes(event_id, state))

            elif action in UPDATE_ACTIONS:
                write = self._create_sem_update(event_id, state)
                if write:
                    writes.append(write)

            elif action in ARCHIVE_ACTIONS:
                write = self._create_sem_archive(event_id, state)
                if write:
                    writes.append(write)

        return writes

    def _create_sem_insert(
        self,
        event_id: str,
        state: P03EventState,
    ) -> Optional[StagedWrite]:
        """
        Create st_sem INSERT for CREATE action.

        GAP-006: actor_id is intentionally NULL for semantic patterns.
        Semantic memory represents generalized, actor-independent knowledge
        extracted from episodic memories. Unlike episodic memories which are
        tied to specific actors, semantic patterns (routines, preferences,
        themes) are abstractions that can apply across actors.

        Actor-specific idiosyncratic patterns should use st_epi (episodic)
        or st_procedural (habits) where actor_id is populated.

        Reference: Tulving's Memory Systems (1972, 1985)
        """
        import json

        from k0.modules.consolidation.algorithms.subtype_classifier import get_subtype_classifier

        # Pattern ID comes from event being promoted to pattern
        pattern_id = f"sem_{event_id}"
        now = _now_ms()

        # Extract pattern info from event state
        pattern_type = getattr(state, "content_type", "general").upper()
        if pattern_type not in ("ROUTINE", "PREFERENCE", "THEME", "RELATIONSHIP", "GOAL", "VALUE"):
            pattern_type = "THEME"  # Default valid type

        # M10.8: Generate descriptive pattern name from NER entities and activity type
        pattern_name = _generate_pattern_name(state, max_length=200)

        # GAP-005: Classify pattern_subtype
        classifier = get_subtype_classifier()
        pattern_subtype = classifier.classify_pattern(
            pattern_type=pattern_type,
            pattern_name=pattern_name,
            source_texts=[state.content_text] if state.content_text else None,
        )

        description = self._build_sem_description(state, pattern_name, pattern_type)
        attributes_json = self._build_sem_attributes(state, pattern_type)
        temporal_regularity, temporal_pattern_json = self._build_sem_temporal_fields(state)

        record_data = {
            "pattern_id": pattern_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "actor_id": getattr(state, "actor_id", None) or None,
            "pattern_type": pattern_type,
            "pattern_subtype": pattern_subtype,  # GAP-005
            "pattern_name": pattern_name,
            "pattern_description": description,
            "pattern_attributes_json": attributes_json,
            "temporal_regularity": temporal_regularity,
            "temporal_pattern_json": temporal_pattern_json,
            "embedding_id": state.embedding_id,
            "source_episodes_json": json.dumps([event_id]),
            "source_episode_count": 1,
            "confidence_score": state.confidence or 0.5,
            "observation_count": 1,
            "first_observed_at": now,
            "last_observed_at": now,
            "created_at": now,
            "updated_at": now,
            "valid_from": now,
            "archival_status": "ACTIVE",
        }

        idem_key = self.idempotency.for_truth_write(LAYER_ST_SEM, pattern_id)

        write = StagedWrite.insert(
            layer=LAYER_ST_SEM,
            record_id=pattern_id,
            data=record_data,
            phase=self.source_phase,
            event_ids=[event_id],
        )
        write.idempotency_key = idem_key
        # Issue 7.6: Attach observation context for st_observations recording
        write.observation_context = ObservationContext.from_event(state)

        return write

    def _create_sem_evolve_writes(
        self,
        event_id: str,
        state: P03EventState,
    ) -> List[StagedWrite]:
        """
        Create EVOLVE writes for st_sem.

        EVOLVE creates a new canonical pattern that supersedes the old one,
        and marks the old pattern non-canonical with a valid_to timestamp.
        """
        writes: List[StagedWrite] = []

        old_pattern_id = state.best_match_id
        if not old_pattern_id:
            return writes

        now = _now_ms()
        new_pattern_id = f"sem_{event_id}"

        pattern_type = getattr(state, "content_type", "general").upper()
        if pattern_type not in ("ROUTINE", "PREFERENCE", "THEME", "RELATIONSHIP", "GOAL", "VALUE"):
            pattern_type = "THEME"

        pattern_name = _generate_pattern_name(state, max_length=200)
        description = self._build_sem_description(state, pattern_name, pattern_type)
        attributes_json = self._build_sem_attributes(state, pattern_type)
        temporal_regularity, temporal_pattern_json = self._build_sem_temporal_fields(state)

        record_data = {
            "pattern_id": new_pattern_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "actor_id": getattr(state, "actor_id", None) or None,
            "pattern_type": pattern_type,
            "pattern_subtype": None,
            "pattern_name": pattern_name,
            "pattern_description": description,
            "pattern_attributes_json": attributes_json,
            "temporal_regularity": temporal_regularity,
            "temporal_pattern_json": temporal_pattern_json,
            "embedding_id": state.embedding_id,
            "source_episodes_json": json.dumps([event_id]),
            "source_episode_count": 1,
            "confidence_score": state.confidence or 0.5,
            "observation_count": 1,
            "first_observed_at": now,
            "last_observed_at": now,
            "created_at": now,
            "updated_at": now,
            "valid_from": now,
            "archival_status": "ACTIVE",
            "supersedes_id": old_pattern_id,
        }

        idem_key = self.idempotency.for_truth_write(LAYER_ST_SEM, new_pattern_id)
        insert_write = StagedWrite.insert(
            layer=LAYER_ST_SEM,
            record_id=new_pattern_id,
            data=record_data,
            phase=self.source_phase,
            event_ids=[event_id],
        )
        insert_write.idempotency_key = idem_key
        insert_write.observation_context = ObservationContext.from_event(state)
        writes.append(insert_write)

        update_data = {
            "_action": "EVOLVE",
            "updated_at": now,
            "valid_to": now,
        }

        update_idem = self.idempotency.for_truth_write(
            LAYER_ST_SEM,
            f"{old_pattern_id}:evolve",
        )
        update_write = StagedWrite.update(
            layer=LAYER_ST_SEM,
            record_id=old_pattern_id,
            data=update_data,
            phase=self.source_phase,
            expected_version=None,
            event_ids=[event_id],
        )
        update_write.idempotency_key = update_idem
        update_write.observation_context = ObservationContext.from_event(state)
        writes.append(update_write)

        return writes

    def _build_sem_description(
        self,
        state: P03EventState,
        pattern_name: str,
        pattern_type: str,
    ) -> Optional[str]:
        """Build a lightweight semantic pattern description."""
        location = getattr(state, "location_name", "") or ""
        activity = getattr(state, "activity_type_ultrabert", "") or getattr(
            state, "activity_type", ""
        )
        activity = activity.replace("_", " ") if activity else ""

        parts = [pattern_name]
        if pattern_type:
            parts.append(f"Type: {pattern_type}")
        if activity:
            parts.append(f"Activity: {activity}")
        if location:
            parts.append(f"Location: {location}")

        description = "; ".join(parts).strip()
        return description if description else None

    def _build_sem_attributes(self, state: P03EventState, pattern_type: str) -> str:
        """Build JSON attributes for semantic pattern."""
        attributes: Dict[str, Any] = {
            "pattern_type": pattern_type,
            "activity_type": getattr(state, "activity_type_ultrabert", None)
            or getattr(state, "activity_type", None),
            "location_name": getattr(state, "location_name", None),
            "location_type": getattr(state, "location_type", None),
            "intent": getattr(state, "intent_label", None),
            "sentiment_label": getattr(state, "sentiment_label", None),
            "sentiment_score": getattr(state, "sentiment_score", None),
            "source_event_id": state.event_id,
        }

        entities: List[str] = []
        try:
            ner_json = getattr(state, "ner_entities_json", "[]") or "[]"
            ner_data = json.loads(ner_json)
            if isinstance(ner_data, list):
                for ent in ner_data:
                    if isinstance(ent, dict) and ent.get("text"):
                        entities.append(ent["text"])
            elif isinstance(ner_data, dict):
                for source in ("ner_family", "ner_general"):
                    source_data = ner_data.get(source, {})
                    if isinstance(source_data, dict):
                        for ent in source_data.get("entities", []):
                            if isinstance(ent, dict) and ent.get("text"):
                                entities.append(ent["text"])
        except (json.JSONDecodeError, TypeError):
            pass

        if entities:
            attributes["entities"] = entities

        return json.dumps(attributes)

    def _build_sem_temporal_fields(
        self,
        state: P03EventState,
    ) -> tuple[Optional[float], Optional[str]]:
        """
        Build temporal_regularity and temporal_pattern_json.

        Uses explicit temporal expressions when present; otherwise
        falls back to day_of_week/time_of_day_bucket context.
        """
        temporal_pattern: Dict[str, Any] = {}
        temporal_regularity: Optional[float] = None

        day_of_week = getattr(state, "day_of_week", "") or ""
        time_bucket = getattr(state, "time_of_day_bucket", "") or ""

        if day_of_week:
            temporal_pattern["day_of_week"] = day_of_week.upper()
        if time_bucket:
            temporal_pattern["time_of_day_bucket"] = time_bucket.upper()

        try:
            temporal_json = getattr(state, "temporal_expressions_json", "[]") or "[]"
            expressions = json.loads(temporal_json)
        except (json.JSONDecodeError, TypeError):
            expressions = []

        if isinstance(expressions, list) and expressions:
            texts: List[str] = []
            for exp in expressions:
                if isinstance(exp, dict) and exp.get("text"):
                    texts.append(str(exp["text"]).lower())
                elif isinstance(exp, str):
                    texts.append(exp.lower())

            frequency = None
            if any("daily" in text or "every day" in text for text in texts):
                frequency = "DAILY"
            elif any("weekly" in text or "every week" in text for text in texts):
                frequency = "WEEKLY"
            elif any("monthly" in text or "every month" in text for text in texts):
                frequency = "MONTHLY"

            if frequency:
                temporal_pattern["frequency"] = frequency
                temporal_regularity = 0.7

        if not temporal_pattern:
            return None, None

        return temporal_regularity, json.dumps(temporal_pattern)

    def _create_sem_update(
        self,
        event_id: str,
        state: P03EventState,
    ) -> Optional[StagedWrite]:
        """Create st_sem UPDATE for REINFORCE/EXTEND/EVOLVE actions."""
        # Target pattern is the best match
        pattern_id = state.best_match_id
        if not pattern_id:
            return None

        now = _now_ms()
        # Partial update: increment observation count, update timestamp
        # st_sem uses observation_count, confidence_score, last_observed_at
        record_data = {
            "observation_count": 1,  # Will be incremented by R7 (or use SQL expression)
            "last_observed_at": now,
            "updated_at": now,
        }

        # Use expected version None for REINFORCE/EXTEND - these are idempotent
        # operations and don't need strict version control
        idem_key = self.idempotency.for_truth_write(LAYER_ST_SEM, pattern_id)

        write = StagedWrite.update(
            layer=LAYER_ST_SEM,
            record_id=pattern_id,
            data=record_data,
            phase=self.source_phase,
            expected_version=None,  # Idempotent operation - no version check
            event_ids=[event_id],
        )
        write.idempotency_key = idem_key
        # Issue 7.6: Attach observation context for st_observations recording
        write.observation_context = ObservationContext.from_event(state)

        return write

    def _create_sem_archive(
        self,
        event_id: str,
        state: P03EventState,
    ) -> Optional[StagedWrite]:
        """Create st_sem ARCHIVE for PRUNE action."""
        pattern_id = state.best_match_id
        if not pattern_id:
            return None

        reason = state.reconciliation_reason or "decay"

        write = StagedWrite.archive(
            layer=LAYER_ST_SEM,
            record_id=pattern_id,
            phase=self.source_phase,
            reason=reason,
            event_ids=[event_id],
        )

        return write

    # =========================================================================
    # st_procedural — Procedural Memory (from R5 routines)
    # =========================================================================

    def assemble_procedural_writes(
        self,
        routines: List[Dict[str, Any]],
    ) -> List[StagedWrite]:
        """
        Assemble st_procedural writes from R5 routine optimizations.

        Args:
            routines: List of routine dicts with routine_id and data

        Returns:
            List of StagedWrite for st_procedural
        """
        if not routines:
            return []

        writes: List[StagedWrite] = []

        for routine in routines:
            routine_id = routine.get("routine_id")
            if not routine_id:
                continue

            is_new = routine.get("is_new", True)

            if is_new:
                record_data = {
                    "routine_id": routine_id,
                    "routine_name": routine.get("routine_name", ""),
                    "steps_json": routine.get("steps_json", "[]"),
                    "frequency": routine.get("frequency", 0),
                    "avg_duration_ms": routine.get("avg_duration_ms", 0),
                    "created_at_ms": _now_ms(),
                }

                idem_key = self.idempotency.for_truth_write(
                    LAYER_ST_PROCEDURAL,
                    routine_id,
                )

                write = StagedWrite.insert(
                    layer=LAYER_ST_PROCEDURAL,
                    record_id=routine_id,
                    data=record_data,
                    phase=self.source_phase,
                    event_ids=routine.get("source_event_ids", []),
                )
                write.idempotency_key = idem_key
                writes.append(write)

        return writes

    def assemble_routine_candidate_writes(
        self,
        candidates: List[RoutineCandidate],
    ) -> List[StagedWrite]:
        """
        Assemble st_procedural writes from RoutineDetector candidates (GAP-003).

        Maps RoutineCandidate dataclass fields to st_procedural table columns.
        This is the primary routine detection path - RoutineDetector analyzes
        episodic memory to detect recurring behavioral patterns.

        Args:
            candidates: List of RoutineCandidate from RoutineDetector.detect()

        Returns:
            List of StagedWrite for st_procedural
        """
        if not candidates:
            return []

        writes: List[StagedWrite] = []
        now_ms = _now_ms()

        for candidate in candidates:
            if not candidate.routine_id:
                continue

            # Map RoutineCandidate to st_procedural columns
            record_data = {
                # Identity
                "routine_id": candidate.routine_id,
                "tenant_id": self.tenant_id,
                "space_id": self.space_id,
                "actor_id": self.tenant_id,  # Default actor
                "version": 1,
                "is_canonical": True,
                # Routine metadata
                "routine_name": candidate.routine_name,
                "routine_category": candidate.routine_category,
                "temporal_anchor": candidate.temporal_anchor,
                "day_pattern": candidate.day_pattern,
                "frequency": candidate.frequency.value if candidate.frequency else "IRREGULAR",
                "regularity_score": candidate.regularity_score,
                "action_sequence_json": candidate.action_sequence_json,
                "typical_duration_minutes": candidate.typical_duration_minutes,
                # Source tracking
                "source_episodes_json": candidate.source_episodes_json,
                "source_episode_count": candidate.source_episode_count,
                # Scoring
                "observation_count": candidate.source_episode_count,
                "confidence_score": candidate.confidence_score,
                "streak_count": candidate.streak_count,
                # Timestamps
                "archival_status": "ACTIVE",
                "created_at": now_ms,
                "updated_at": now_ms,
                "valid_from": now_ms,
            }

            idem_key = self.idempotency.for_truth_write(
                LAYER_ST_PROCEDURAL,
                candidate.routine_id,
            )

            write = StagedWrite.insert(
                layer=LAYER_ST_PROCEDURAL,
                record_id=candidate.routine_id,
                data=record_data,
                phase=self.source_phase,
                event_ids=[],  # Source episodes tracked in source_episodes_json
            )
            write.idempotency_key = idem_key
            writes.append(write)

        return writes

    # =========================================================================
    # st_social — Social Memory (from R4 SocialRelationship)
    # =========================================================================

    def assemble_social_writes(
        self,
        social_relationships: List[SocialRelationship],
    ) -> List[StagedWrite]:
        """
        Assemble st_social writes from R4 SocialRelationship objects.

        Maps SocialRelationship dataclass fields to st_social table columns
        as defined in migration 0030_st_social and enriched by 0054.

        Args:
            social_relationships: List of SocialRelationship from R4

        Returns:
            List of StagedWrite for st_social
        """
        if not social_relationships:
            return []

        writes: List[StagedWrite] = []
        now_ms = _now_ms()

        for rel in social_relationships:
            # Use relationship_id as the primary key
            if not rel.relationship_id:
                continue

            if rel.is_new:
                # Map SocialRelationship fields to st_social columns
                record_data = {
                    # Identity (primary key)
                    "relationship_id": rel.relationship_id,
                    "tenant_id": self.tenant_id,
                    "space_id": self.space_id,
                    # Relationship endpoints
                    "actor_a_id": rel.actor_a_id,
                    "actor_b_id": rel.actor_b_id,
                    # Versioning
                    "version": 1,
                    "is_canonical": True,
                    # Relationship type
                    "relationship_type": rel.relationship_type or "ACQUAINTANCE",
                    "relationship_subtype": rel.relationship_subtype or None,
                    "relationship_label": rel.actor_b_name or None,
                    # Relationship strength
                    "interaction_count": rel.interaction_count,
                    "avg_sentiment": rel.emotional_valence_avg,
                    "relationship_strength": rel.confidence,
                    "intimacy_level": rel.intimacy_level or "ACQUAINTANCE",
                    # Temporal
                    "first_interaction_at": now_ms,
                    "last_interaction_at": now_ms,
                    "interaction_frequency": None,
                    # Source episodes
                    "source_episodes_json": json.dumps(rel.source_event_ids),
                    # Truth tracking
                    "observation_count": 1,
                    "confidence_score": rel.confidence,
                    "decay_factor": 1.0,
                    # Lifecycle
                    "archival_status": "ACTIVE",
                    # Timestamps
                    "created_at": now_ms,
                    "updated_at": now_ms,
                    "valid_from": now_ms,
                    # UltraBERT enrichment (migration 0054)
                    "ultrabert_relation_types": json.dumps(rel.ultrabert_relation_types),
                    "emotional_role": rel.emotional_role or None,
                    "emotional_valence_avg": rel.emotional_valence_avg,
                    "emotional_valence_trend": rel.emotional_valence_trend,
                    "relationship_phase": rel.relationship_phase or "FORMING",
                    "interaction_modalities_json": json.dumps(rel.interaction_modalities),
                    "typical_activities_json": json.dumps(rel.typical_activities),
                    "sentiment_trajectory_json": json.dumps(rel.sentiment_trajectory),
                    "emotions_json": json.dumps(rel.emotions),
                    "dominant_emotion": rel.dominant_emotion or None,
                    "canonical_entity_id": rel.canonical_entity_id or None,
                }

                idem_key = self.idempotency.for_truth_write(
                    LAYER_ST_SOCIAL,
                    rel.relationship_id,
                )

                write = StagedWrite.insert(
                    layer=LAYER_ST_SOCIAL,
                    record_id=rel.relationship_id,
                    data=record_data,
                    phase=self.source_phase,
                    event_ids=rel.source_event_ids,
                )
                write.idempotency_key = idem_key
                # Issue 7.6: Create minimal observation context from timestamp
                write.observation_context = ObservationContext.from_timestamp(now_ms)
                writes.append(write)

        return writes

    # =========================================================================
    # st_prospective — Prospective Memory (from R5 ProspectiveMemory)
    # =========================================================================

    def assemble_prospective_writes(
        self,
        intentions: List[ProspectiveMemory],
    ) -> List[StagedWrite]:
        """
        Assemble st_prospective writes from R5 prospective memories.

        Args:
            intentions: List of ProspectiveMemory objects

        Returns:
            List of StagedWrite for st_prospective inserts
        """
        if not intentions:
            return []

        writes: List[StagedWrite] = []

        for intention in intentions:
            record_data = {
                "prosp_id": intention.prosp_id,
                "intention_type": intention.intention_type,
                "description": intention.description,
                "trigger_condition": intention.trigger_condition,
                "action_to_take": intention.action_to_take,
                "deadline_ts": intention.deadline_ts,
                "importance": intention.importance,
                "source_episode_id": intention.source_episode_id,
                "created_at_ms": _now_ms(),
                # Issue 7.7: Temporal anchor context
                "anchor_time_utc": getattr(intention, "anchor_time_utc", None),
                "original_temporal_expr": getattr(intention, "original_temporal_expr", None),
            }

            idem_key = self.idempotency.for_truth_write(
                LAYER_ST_PROSPECTIVE,
                intention.prosp_id,
            )

            source_ids = [intention.source_episode_id] if intention.source_episode_id else []

            write = StagedWrite.insert(
                layer=LAYER_ST_PROSPECTIVE,
                record_id=intention.prosp_id,
                data=record_data,
                phase=self.source_phase,
                event_ids=source_ids,
            )
            write.idempotency_key = idem_key
            # Issue 7.6/7.7: Create observation context with anchor time if available
            anchor_ts = getattr(intention, "anchor_time_utc", None) or _now_ms()
            write.observation_context = ObservationContext.from_timestamp(anchor_ts)
            # Issue 7.7: Set original temporal expression if available
            if getattr(intention, "original_temporal_expr", None):
                write.observation_context.original_temporal_expr = intention.original_temporal_expr
            writes.append(write)

        return writes

    # =========================================================================
    # st_sem — R5 Insight Writes (from BGT-SM)
    # Issue 8.1.16 — TruthWriteAssembler R5 Output Assembly
    # =========================================================================

    def assemble_insight_writes(
        self,
        insights: List[Insight],
    ) -> List[StagedWrite]:
        """
        Assemble st_sem writes from R5 insights.

        Insights from BGT-SM (Bisociative Graph Traversal) are written
        to st_sem with pattern_type='INSIGHT'.

        Args:
            insights: List of Insight objects from R5

        Returns:
            List of StagedWrite for st_sem inserts
        """
        if not insights:
            return []

        writes: List[StagedWrite] = []
        now_ms = _now_ms()

        for insight in insights:
            # Pattern ID is derived from insight_id
            pattern_id = f"insight_{insight.insight_id}"

            # Build st_sem record per Issue 8.1.16 spec
            record_data = {
                "pattern_id": pattern_id,
                "tenant_id": self.tenant_id,
                "space_id": self.space_id,
                "pattern_type": "INSIGHT",  # R5 insight type
                "pattern_name": (
                    insight.description[:200] if insight.description else "Untitled insight"
                ),
                "embedding_id": None,  # Insights don't have embeddings yet
                "source_episodes_json": json.dumps(list(insight.supporting_evidence)),
                "source_episode_count": len(insight.supporting_evidence),
                "confidence_score": insight.confidence,
                "novelty_score": insight.novelty_score,
                "pmi_score": insight.pmi_score,
                "semantic_distance": insight.semantic_distance,
                "concept_a_id": insight.concept_a_id,
                "concept_b_id": insight.concept_b_id,
                "insight_type": insight.insight_type,
                "relevance_score": insight.relevance_score,
                "serendipity_score": insight.serendipity_score,
                "observation_count": 1,
                "first_observed_at": now_ms,
                "last_observed_at": now_ms,
                "created_at": now_ms,
                "updated_at": now_ms,
                "valid_from": now_ms,
                "archival_status": "ACTIVE",
            }

            idem_key = self.idempotency.for_truth_write(LAYER_ST_SEM, pattern_id)

            write = StagedWrite.insert(
                layer=LAYER_ST_SEM,
                record_id=pattern_id,
                data=record_data,
                phase="R5",
                event_ids=list(insight.supporting_evidence),
            )
            write.idempotency_key = idem_key
            writes.append(write)

        return writes

    # =========================================================================
    # st_prospective — R5 Counterfactual Writes (from CPN)
    # Issue 8.1.16 — TruthWriteAssembler R5 Output Assembly
    # =========================================================================

    def assemble_counterfactual_writes(
        self,
        counterfactuals: List[CounterfactualScenario],
    ) -> List[StagedWrite]:
        """
        Assemble st_prospective writes from R5 counterfactual scenarios.

        Counterfactuals from CPN are written to st_prospective with
        type='COUNTERFACTUAL'.

        Args:
            counterfactuals: List of CounterfactualScenario from R5

        Returns:
            List of StagedWrite for st_prospective inserts
        """
        if not counterfactuals:
            return []

        writes: List[StagedWrite] = []
        now_ms = _now_ms()

        for scenario in counterfactuals:
            record_data = {
                "intention_id": scenario.scenario_id,  # Primary key for st_prospective
                "tenant_id": self.tenant_id,
                "space_id": self.space_id,
                "intention_type": "COUNTERFACTUAL",  # Type for counterfactual scenarios
                "description": (
                    scenario.counterfactual_outcome[:500] if scenario.counterfactual_outcome else ""
                ),
                "trigger_condition": f"If: {scenario.perturbation_target}",
                "action_to_take": scenario.counterfactual_outcome,
                "original_outcome": scenario.original_outcome,
                "scenario_type": scenario.scenario_type,  # UPWARD, DOWNWARD, SEMIFACTUAL
                "base_episode_id": scenario.base_episode_id,
                "perturbation_target": scenario.perturbation_target,
                "plausibility": scenario.plausibility,
                "success_probability": scenario.success_probability,
                "utility_delta": scenario.utility_delta,
                "importance": scenario.plausibility * scenario.success_probability,  # Derived
                "confidence": scenario.plausibility,
                "source_episode_id": scenario.base_episode_id,
                "deadline_ts": None,
                "status": "ACTIVE",
                "created_at_ms": now_ms,
            }

            idem_key = self.idempotency.for_truth_write(
                LAYER_ST_PROSPECTIVE,
                scenario.scenario_id,
            )

            write = StagedWrite.insert(
                layer=LAYER_ST_PROSPECTIVE,
                record_id=scenario.scenario_id,
                data=record_data,
                phase="R5",
                event_ids=[scenario.base_episode_id] if scenario.base_episode_id else [],
            )
            write.idempotency_key = idem_key
            writes.append(write)

        return writes

    # =========================================================================
    # st_procedural — R5 Routine Optimization Writes (from TDL-HCO)
    # Issue 8.1.16 — TruthWriteAssembler R5 Output Assembly
    # =========================================================================

    def assemble_routine_optimization_writes(
        self,
        optimizations: List[RoutineOptimization],
    ) -> List[StagedWrite]:
        """
        Assemble st_procedural writes from R5 routine optimizations.

        Routine optimizations from TDL-HCO identify bottlenecks in
        procedural patterns and suggest improvements.

        Args:
            optimizations: List of RoutineOptimization from R5

        Returns:
            List of StagedWrite for st_procedural updates
        """
        if not optimizations:
            return []

        writes: List[StagedWrite] = []
        now_ms = _now_ms()

        for opt in optimizations:
            # Routine optimizations create update records
            # They target existing routines with improvement suggestions
            record_data = {
                "routine_id": opt.routine_id,
                "tenant_id": self.tenant_id,
                "space_id": self.space_id,
                "routine_name": opt.routine_name,
                "bottleneck_step": opt.bottleneck_step,
                "bottleneck_position": opt.bottleneck_position,
                "value_drop": opt.value_drop,
                "suggested_action": opt.suggested_action,
                "expected_improvement": opt.expected_improvement,
                "optimization_confidence": opt.confidence,
                "optimization_status": "PENDING",  # User hasn't acted yet
                "updated_at": now_ms,
            }

            # Use INSERT for new optimization records
            # (Each optimization is a new suggestion, not an update to existing)
            optimization_id = f"opt_{opt.routine_id}_{opt.bottleneck_position}"

            idem_key = self.idempotency.for_truth_write(
                LAYER_ST_PROCEDURAL,
                optimization_id,
            )

            write = StagedWrite.insert(
                layer=LAYER_ST_PROCEDURAL,
                record_id=optimization_id,
                data=record_data,
                phase="R5",
                event_ids=[],
            )
            write.idempotency_key = idem_key
            writes.append(write)

        return writes

    # =========================================================================
    # st_mcts_decisions — MCTS Scenario Writes (R5 Forward Simulation)
    # =========================================================================

    def assemble_mcts_writes(
        self,
        scenarios: List[MCTSScenario],
    ) -> List[StagedWrite]:
        """
        Assemble st_mcts_decisions writes from R5 MCTS scenarios.

        MCTS scenarios are forward simulations from the MCTS algorithm
        that predict future outcomes based on action sequences.

        Args:
            scenarios: List of MCTSScenario from R5

        Returns:
            List of StagedWrite for st_mcts_decisions
        """
        if not scenarios:
            return []

        writes: List[StagedWrite] = []
        now_ms = _now_ms()

        for scenario in scenarios:
            # Build action sequence JSON
            action_sequence_json = json.dumps(list(scenario.action_sequence))

            # Store extended scenario data in context_json
            # Table schema has fixed columns; extra fields go in context
            context_data = {
                "predicted_outcome": scenario.predicted_outcome,
                "action_sequence": list(scenario.action_sequence),
                "success_probability": scenario.success_probability,
                "plausibility": scenario.plausibility,
                "depth": scenario.depth,
                "tenant_id": self.tenant_id,
                "space_id": self.space_id,
            }

            record_data = {
                "decision_id": scenario.scenario_id,
                "cycle_id": self.consolidation_cycle_id,
                "decision_type": "forward_simulation",
                "context_json": json.dumps(context_data),
                "rollouts_allocated": scenario.visit_count,
                "rollouts_executed": scenario.visit_count,
                "early_termination": False,
                "termination_reason": None,
                "chosen_action": action_sequence_json,
                "value_estimate": scenario.expected_reward,
                "confidence_interval_width": 1.0 - scenario.plausibility,
                "compute_ms": 0,  # Not tracked per-scenario
                "created_at": now_ms,
            }

            idem_key = self.idempotency.for_truth_write(
                LAYER_ST_MCTS,
                scenario.scenario_id,
            )

            write = StagedWrite.insert(
                layer=LAYER_ST_MCTS,
                record_id=scenario.scenario_id,
                data=record_data,
                phase="R5",
                event_ids=[],
            )
            write.idempotency_key = idem_key
            writes.append(write)

        return writes

    # =========================================================================
    # st_prospective — Intent Signal Writes (GAP-001 Milestone 7)
    # Routes ReminderSignal, DecisionSignal to st_prospective
    # =========================================================================

    def assemble_intent_signal_writes(
        self,
        intent_signals: List[IntentSignal],
    ) -> List[StagedWrite]:
        """
        Assemble st_prospective writes from R5 intent signals.

        Routes intent signals to appropriate layers:
        - ReminderSignal → st_prospective with intention_type='REMINDER'
        - DecisionSignal → st_prospective with intention_type='DECISION'

        GAP Reference: GAP_001 Milestone 7 (Intent-Aware Prospective Writer)

        Args:
            intent_signals: List of IntentSignal objects from R5

        Returns:
            List of StagedWrite for st_prospective inserts
        """
        if not intent_signals:
            return []

        writes: List[StagedWrite] = []
        now_ms = _now_ms()

        for signal in intent_signals:
            if signal.signal_type == IntentSignalType.REMINDER:
                write = self._assemble_reminder_write(signal, now_ms)
                if write:
                    writes.append(write)
            elif signal.signal_type == IntentSignalType.DECISION:
                write = self._assemble_decision_write(signal, now_ms)
                if write:
                    writes.append(write)
            # Other signal types (LESSON, EMOTIONAL_TREND, etc.) go to different layers
            # and will be handled by separate methods if needed

        return writes

    def _assemble_reminder_write(
        self,
        signal: IntentSignal,
        now_ms: int,
    ) -> Optional[StagedWrite]:
        """
        Create st_prospective write from ReminderSignal.

        Args:
            signal: ReminderSignal from IntentSignalDetector
            now_ms: Current timestamp in milliseconds

        Returns:
            StagedWrite for st_prospective INSERT
        """
        if not isinstance(signal, ReminderSignal):
            return None

        # Generate intention_id from event_id
        intention_id = f"reminder_{signal.event_id}"

        record_data = {
            "intention_id": intention_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "intention_type": "REMINDER",
            "description": signal.action_description or signal.source_text,
            "trigger_time_ms": signal.target_date,
            "trigger_context_json": json.dumps({"source_text": signal.source_text}),
            "goal_inference_json": "{}",
            "confidence": signal.confidence,
            "status": "pending",
            "source_episodes_json": json.dumps([signal.event_id]),
            "counterfactual_json": None,
        }

        idem_key = self.idempotency.for_truth_write(
            LAYER_ST_PROSPECTIVE,
            intention_id,
        )

        write = StagedWrite.insert(
            layer=LAYER_ST_PROSPECTIVE,
            record_id=intention_id,
            data=record_data,
            phase="R5",
            event_ids=[signal.event_id],
        )
        write.idempotency_key = idem_key

        return write

    def _assemble_decision_write(
        self,
        signal: IntentSignal,
        now_ms: int,
    ) -> Optional[StagedWrite]:
        """
        Create st_prospective write from DecisionSignal.

        Args:
            signal: DecisionSignal from IntentSignalDetector
            now_ms: Current timestamp in milliseconds

        Returns:
            StagedWrite for st_prospective INSERT
        """
        if not isinstance(signal, DecisionSignal):
            return None

        # Generate intention_id from event_id
        intention_id = f"decision_{signal.event_id}"

        # Build decision context from options
        decision_context = {
            "source_text": signal.source_text,
            "options": signal.options if hasattr(signal, "options") else [],
            "domain": signal.decision_domain if hasattr(signal, "decision_domain") else None,
        }

        record_data = {
            "intention_id": intention_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "intention_type": "GOAL",  # Decision uses GOAL type per schema constraint
            "description": signal.source_text,
            "trigger_time_ms": None,  # Decisions don't have target dates
            "trigger_context_json": json.dumps(decision_context),
            "goal_inference_json": "{}",
            "confidence": signal.confidence,
            "status": "pending",
            "source_episodes_json": json.dumps([signal.event_id]),
            "counterfactual_json": None,
        }

        idem_key = self.idempotency.for_truth_write(
            LAYER_ST_PROSPECTIVE,
            intention_id,
        )

        write = StagedWrite.insert(
            layer=LAYER_ST_PROSPECTIVE,
            record_id=intention_id,
            data=record_data,
            phase="R5",
            event_ids=[signal.event_id],
        )
        write.idempotency_key = idem_key

        return write

    # =========================================================================
    # st_learning_queue — P06 Gap Queue (from R4 GapCandidate)
    # =========================================================================

    def assemble_learning_queue_writes(
        self,
        gaps: List[GapCandidate],
    ) -> List[StagedWrite]:
        """
        Assemble st_learning_queue writes for P06 active learning.

        Args:
            gaps: List of GapCandidate objects from R4

        Returns:
            List of StagedWrite for st_learning_queue inserts
        """
        if not gaps:
            return []

        writes: List[StagedWrite] = []

        for gap in gaps:
            record_data = {
                "gap_id": gap.gap_id,
                "gap_type": gap.gap_type,
                "related_entity_id": gap.related_entity_id,
                "entropy_score": gap.entropy_score,
                "priority": gap.priority,
                "context_json": gap.context_json,
                "candidate_values_json": json.dumps(gap.candidate_values),
                "status": "PENDING",
                "created_at_ms": _now_ms(),
            }

            idem_key = self.idempotency.for_truth_write(
                LAYER_ST_LEARNING_QUEUE,
                gap.gap_id,
            )

            write = StagedWrite.insert(
                layer=LAYER_ST_LEARNING_QUEUE,
                record_id=gap.gap_id,
                data=record_data,
                phase=self.source_phase,
                event_ids=[gap.related_entity_id] if gap.related_entity_id else [],
            )
            write.idempotency_key = idem_key
            writes.append(write)

        return writes

    # =========================================================================
    # Aggregate Assembly
    # =========================================================================

    def assemble_all(
        self,
        clusters: Optional[List[EpisodeCluster]] = None,
        event_states: Optional[Dict[str, P03EventState]] = None,
        routines: Optional[List[Dict[str, Any]]] = None,
        social_relationships: Optional[List[SocialRelationship]] = None,
        intentions: Optional[List[ProspectiveMemory]] = None,
        gaps: Optional[List[GapCandidate]] = None,
        # R5 outputs (Issue 8.1.16)
        insights: Optional[List[Insight]] = None,
        counterfactuals: Optional[List[CounterfactualScenario]] = None,
        routine_optimizations: Optional[List[RoutineOptimization]] = None,
        # GAP-001 Milestone 7: Intent signals
        intent_signals: Optional[List[IntentSignal]] = None,
        # GAP-003: Routine candidates from RoutineDetector
        routine_candidates: Optional[List[RoutineCandidate]] = None,
        # MCTS scenarios for st_mcts_decisions
        mcts_scenarios: Optional[List[MCTSScenario]] = None,
    ) -> Dict[str, List[StagedWrite]]:
        """
        Assemble all truth layer writes from phase outputs.

        Returns writes grouped by layer for easy routing to P03StagedWrites.

        Args:
            clusters: R2 episode clusters
            event_states: Event states with R3 reconciliation
            routines: R5 routine data (legacy format)
            social_relationships: R4 social relationships (SocialRelationship objects)
            intentions: R5 prospective memories
            gaps: R4 gap candidates
            insights: R5 insights from BGT-SM (Issue 8.1.16)
            counterfactuals: R5 counterfactual scenarios from CPN (Issue 8.1.16)
            routine_optimizations: R5 routine optimizations from TDL-HCO (Issue 8.1.16)
            intent_signals: R5 intent signals (GAP-001 Milestone 7)
            routine_candidates: GAP-003 routine candidates from RoutineDetector
            mcts_scenarios: R5 MCTS forward simulation scenarios

        Returns:
            Dict mapping layer name to list of StagedWrite
        """
        result: Dict[str, List[StagedWrite]] = {}

        # st_epi from R2 clusters
        epi_writes = self.assemble_epi_writes(clusters or [], event_states or {})
        self._merge_epi_recurrence_updates(epi_writes, routine_candidates or [])
        if epi_writes:
            result[LAYER_ST_EPI] = epi_writes

        # st_sem from R3 decisions
        sem_writes = self.assemble_sem_writes(event_states or {})
        if sem_writes:
            result[LAYER_ST_SEM] = sem_writes

        # st_sem from R5 insights (Issue 8.1.16)
        insight_writes = self.assemble_insight_writes(insights or [])
        if insight_writes:
            # Merge with existing st_sem writes
            if LAYER_ST_SEM in result:
                result[LAYER_ST_SEM].extend(insight_writes)
            else:
                result[LAYER_ST_SEM] = insight_writes

        # st_procedural from R5 routines (legacy)
        proc_writes = self.assemble_procedural_writes(routines or [])
        if proc_writes:
            result[LAYER_ST_PROCEDURAL] = proc_writes

        # st_procedural from R5 routine optimizations (Issue 8.1.16)
        opt_writes = self.assemble_routine_optimization_writes(routine_optimizations or [])
        if opt_writes:
            # Merge with existing st_procedural writes
            if LAYER_ST_PROCEDURAL in result:
                result[LAYER_ST_PROCEDURAL].extend(opt_writes)
            else:
                result[LAYER_ST_PROCEDURAL] = opt_writes

        # st_procedural from GAP-003 routine candidates (RoutineDetector)
        candidate_writes = self.assemble_routine_candidate_writes(routine_candidates or [])
        if candidate_writes:
            # Merge with existing st_procedural writes
            if LAYER_ST_PROCEDURAL in result:
                result[LAYER_ST_PROCEDURAL].extend(candidate_writes)
            else:
                result[LAYER_ST_PROCEDURAL] = candidate_writes

        # st_social from R4 relationships
        social_writes = self.assemble_social_writes(social_relationships or [])
        if social_writes:
            result[LAYER_ST_SOCIAL] = social_writes

        # st_prospective from R5 intentions
        prosp_writes = self.assemble_prospective_writes(intentions or [])
        if prosp_writes:
            result[LAYER_ST_PROSPECTIVE] = prosp_writes

        # st_prospective from R5 counterfactuals (Issue 8.1.16)
        cf_writes = self.assemble_counterfactual_writes(counterfactuals or [])
        if cf_writes:
            # Merge with existing st_prospective writes
            if LAYER_ST_PROSPECTIVE in result:
                result[LAYER_ST_PROSPECTIVE].extend(cf_writes)
            else:
                result[LAYER_ST_PROSPECTIVE] = cf_writes

        # st_prospective from R5 intent signals (GAP-001 Milestone 7)
        intent_writes = self.assemble_intent_signal_writes(intent_signals or [])
        if intent_writes:
            # Merge with existing st_prospective writes
            if LAYER_ST_PROSPECTIVE in result:
                result[LAYER_ST_PROSPECTIVE].extend(intent_writes)
            else:
                result[LAYER_ST_PROSPECTIVE] = intent_writes

        # st_learning_queue from R4 gaps
        queue_writes = self.assemble_learning_queue_writes(gaps or [])
        if queue_writes:
            result[LAYER_ST_LEARNING_QUEUE] = queue_writes

        # st_mcts_decisions from R5 MCTS scenarios
        mcts_writes = self.assemble_mcts_writes(mcts_scenarios or [])
        if mcts_writes:
            result[LAYER_ST_MCTS] = mcts_writes

        return result

    def count_writes(
        self,
        assembled: Dict[str, List[StagedWrite]],
    ) -> Dict[str, int]:
        """
        Count writes per layer.

        Args:
            assembled: Dict from assemble_all()

        Returns:
            Dict mapping layer to write count
        """
        return {layer: len(writes) for layer, writes in assembled.items()}


# =============================================================================
# Utility Functions
# =============================================================================


def flatten_writes(assembled: Dict[str, List[StagedWrite]]) -> List[StagedWrite]:
    """
    Flatten assembled writes dict to single list.

    Note: Does NOT respect dependency order. Use
    P03StagedWrites.get_all_writes_ordered() for commit order.

    Args:
        assembled: Dict from TruthWriteAssembler.assemble_all()

    Returns:
        Flat list of all StagedWrite objects
    """
    result: List[StagedWrite] = []
    for writes in assembled.values():
        result.extend(writes)
    return result


def summarize_assembly(assembled: Dict[str, List[StagedWrite]]) -> str:
    """
    Generate human-readable summary of assembled writes.

    Args:
        assembled: Dict from TruthWriteAssembler.assemble_all()

    Returns:
        Multi-line summary string
    """
    lines = ["Truth Write Assembly Summary:"]
    total = 0
    for layer, writes in sorted(assembled.items()):
        count = len(writes)
        total += count
        lines.append(f"  {layer}: {count} writes")
    lines.append(f"  Total: {total} writes")
    return "\n".join(lines)
