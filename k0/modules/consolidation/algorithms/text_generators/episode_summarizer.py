"""Structured-semantic episode summarizer (production).

Winner of the 9-technique benchmark (composite 0.930, semantic 0.810).
Produces WHO -- WHAT at WHERE: MMR-selected detail sentence.

Adapted from poc/summary_generator/benchmark.py technique_structured_semantic.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import TYPE_CHECKING, List, Optional, Protocol, Sequence

import numpy as np

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol for event objects accepted by the summarizer
# ---------------------------------------------------------------------------
class SummarizableEvent(Protocol):
    """Minimal interface an event must satisfy for summarization."""

    @property
    def text(self) -> str: ...

    @property
    def activity_type(self) -> str: ...

    @property
    def location_name(self) -> str: ...

    @property
    def participants_json(self) -> str: ...

    @property
    def embedding_768(self) -> Optional[np.ndarray]: ...


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def generate_episode_summary(
    events: Sequence[SummarizableEvent],
    episode_location: str = "",
    episode_participants_json: str = "[]",
) -> str:
    """Generate a structured-semantic episode summary.

    Structure: "{who} -- {what} at {where}: {mmr_detail}"

    Args:
        events: Member events with text, embeddings, metadata.
        episode_location: Episode-level location hint (fallback).
        episode_participants_json: Episode-level participants JSON (primary).

    Returns:
        Summary string, or empty string if no text content.
    """
    texts = [_get_text(e) for e in events]
    texts_valid = [t for t in texts if t]
    if not texts_valid:
        return ""
    if len(texts_valid) == 1:
        return texts_valid[0]

    who = _extract_who(events, episode_participants_json)
    what = _extract_what(events)
    where = _extract_where(events, episode_location)
    detail = _select_detail_mmr(events, texts)

    header = f"{who} -- {what} at {where}"
    if detail:
        return f"{header}: {detail}"
    return header


# ---------------------------------------------------------------------------
# WHO: merge episode-level + event-level participants
# ---------------------------------------------------------------------------
def _extract_who(
    events: Sequence[SummarizableEvent],
    episode_participants_json: str,
) -> str:
    counts: Counter[str] = Counter()

    # Episode-level participants (from st_epi.participants_json)
    try:
        plist = json.loads(episode_participants_json or "[]")
    except (json.JSONDecodeError, TypeError):
        plist = []

    for p in plist:
        name = _participant_name(p)
        if name:
            counts[name] += 1

    # Fallback to event-level if no episode-level participants
    if not counts:
        for ev in events:
            try:
                ev_plist = json.loads(getattr(ev, "participants_json", "[]") or "[]")
            except (json.JSONDecodeError, TypeError):
                ev_plist = []
            for p in ev_plist:
                name = _participant_name(p)
                if name:
                    counts[name] += 1

    top = [p for p, _ in counts.most_common(3)]
    return ", ".join(top) if top else "Solo"


def _participant_name(p: object) -> str:
    if isinstance(p, dict):
        name = p.get("name") or p.get("participant_name") or ""
    else:
        name = str(p).strip()
    # Skip raw person_ IDs
    if name and not name.startswith("person_"):
        return name
    return ""


# ---------------------------------------------------------------------------
# WHAT: most common non-trivial activity type
# ---------------------------------------------------------------------------
def _extract_what(events: Sequence[SummarizableEvent]) -> str:
    activities: Counter[str] = Counter()
    for e in events:
        act = getattr(e, "activity_type", "") or ""
        if act and act != "unknown":
            activities[act] += 1
    return activities.most_common(1)[0][0] if activities else "activity"


# ---------------------------------------------------------------------------
# WHERE: most common location across events
# ---------------------------------------------------------------------------
def _extract_where(
    events: Sequence[SummarizableEvent],
    episode_location: str,
) -> str:
    locations: Counter[str] = Counter()
    for e in events:
        loc = getattr(e, "location_name", "") or ""
        if loc:
            locations[loc] += 1
    if locations:
        return locations.most_common(1)[0][0]
    return episode_location or "unknown location"


# ---------------------------------------------------------------------------
# DETAIL: MMR-selected representative sentence
# ---------------------------------------------------------------------------
def _select_detail_mmr(
    events: Sequence[SummarizableEvent],
    texts: List[str],
    top_k: int = 1,
    relevance_weight: float = 0.7,
) -> str:
    """Select the most representative sentence via Maximal Marginal Relevance.

    Uses pre-computed event embeddings (no model loading at runtime).
    """
    embs = []
    for i, e in enumerate(events):
        vec = getattr(e, "embedding_768", None)
        text = texts[i] if i < len(texts) else ""
        if vec is not None and text and len(text.split()) >= 5:
            embs.append((i, np.asarray(vec, dtype=np.float32)))

    if not embs:
        # Fallback: longest sentence with content words
        scored = [(len(t.split()), i) for i, t in enumerate(texts) if t and len(t.split()) >= 5]
        if scored:
            scored.sort(reverse=True)
            return _truncate(texts[scored[0][1]], 120)
        return ""

    indices, vectors = zip(*embs)
    mat = np.stack(vectors)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1
    mat = mat / norms

    centroid = mat.mean(axis=0)
    c_norm = np.linalg.norm(centroid)
    if c_norm > 0:
        centroid /= c_norm

    relevance = mat @ centroid
    diversity_weight = 1.0 - relevance_weight

    selected: List[int] = []
    for _ in range(min(top_k, len(indices))):
        best_score = -999.0
        best_j = 0
        for j in range(len(indices)):
            if j in selected:
                continue
            if selected:
                sim_to_sel = max(float(mat[j] @ mat[k]) for k in selected)
            else:
                sim_to_sel = 0.0
            score = relevance_weight * relevance[j] - diversity_weight * sim_to_sel
            if score > best_score:
                best_score = score
                best_j = j
        selected.append(best_j)

    orig_indices = sorted(indices[j] for j in selected)
    parts = [_truncate(texts[i], 120) for i in orig_indices if i < len(texts)]
    return " ".join(parts)


def _truncate(text: str, max_len: int = 120) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "..."


def _get_text(event: SummarizableEvent) -> str:
    # P03EventState uses content_text; POC/test objects may use text
    text = getattr(event, "content_text", "") or getattr(event, "text", "") or ""
    return text.strip()
