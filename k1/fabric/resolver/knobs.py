"""KnobConfig — experiment control for the resolver pipeline.

No heuristics.  Every knob is an independent variable with a finite set of
positions.  The benchmark script dials knobs via ``resolver.configure(knobs)``,
runs the 100-query corpus, and measures M0 (tool accuracy) and M3 (blocked rate).

Design authority: ``docs/whiteboard/capability_search_algorithm.md`` §Control Knobs Matrix.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KnobConfig:
    """Immutable knob positions for one experimental run.

    All fields default to the CURRENT production setting (the baseline
    we measured at 20% tool accuracy, 14% blocked rate).
    """

    # K1: Search method
    search_method: str = "graph-fts5-fallback"
    # Positions: "graph-only" | "graph-fts5-fallback" | "fts5-only" | "fts5-graph-refine"

    # K2: Domain handling
    domain_mode: str = "hard-filter"
    # Positions: "hard-filter" | "boost-2x" | "boost-1.5x" | "no-domain" | "domain-as-tiebreaker"

    # K3: Resource family handling
    rf_mode: str = "hard-filter"
    # Positions: "hard-filter" | "boost-2x" | "no-rf"

    # K4: Operation hint handling
    op_mode: str = "hard-filter"
    # Positions: "hard-filter" | "boost-1.5x" | "no-op"

    # K5: Return mode
    return_mode: str = "single-capability"
    # Positions: "single-capability" | "all-tools-for-connector" | "top-3-connectors" | "top-1-with-fallback"

    # K6: FTS5 index content
    index_content: str = "descriptions-only"
    # Positions: "descriptions-only" | "+action_names" | "+connector_meta" | "+concept_aliases" | "+all"

    # K7: FTS5 query construction
    query_mode: str = "action-text-only"
    # Positions: "action-text-only" | "action+op_terms" | "prefix-matching" | "weighted-fields"

    # K8: Fallback / safety net — DELETED (RES-023, 2026-06-17)
    # K9: Constitution & gate injection — DELETED (RES-023, 2026-06-17)

    # K10: Multi-intent strategy
    multi_intent_mode: str = "independent"
    # Positions: "independent" | "primary-only" | "union-connectors"

    # K11: Retrieval backend
    retrieval_backend: str = "fts5-bm25"
    # Positions: "fts5-bm25" | "fts5-trigram" | "minilm-l6-v2" | "gte-small" | "mpnet-base-v2" | "splade-v3" | "hybrid-bm25-minilm" | "hybrid-bm25-splade"


# ── Baseline (current production settings) ──
BASELINE = KnobConfig()
