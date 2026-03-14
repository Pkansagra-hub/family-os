"""
Memory Writer v2 Invariants -- Machine-checkable assertion helpers.

Runtime and compile-time assertion helpers for MW-01 through MW-11.
These are called by pipeline stages and validators to enforce the
11 hard invariants defined in the module contract.

Each function:
  - Has a clear invariant ID prefix (MW-XX)
  - Raises InvariantViolation with the invariant ID on failure
  - Is designed to be called inline during processing

Source of truth:
  - k1/contracts/modules/memory_writer/module.contract.yaml (invariants section)
  - k1/contracts/modules/memory_writer/policies.contract.yaml

Import graph:
  - k1.memory_writer.invariants -> k1.memory_writer.config (for limits)
  - NEVER import from service or adapter modules
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Sequence

from k1.memory_writer.config import MWConfig


class InvariantViolation(Exception):
    """Raised when a Memory Writer invariant is violated.

    Attributes:
        invariant_id: The MW-XX identifier (e.g. "MW-04")
        message: Human-readable description of the violation
    """

    def __init__(self, invariant_id: str, message: str) -> None:
        self.invariant_id = invariant_id
        super().__init__(f"[{invariant_id}] {message}")


# ---------------------------------------------------------------------------
# MW-01: NEVER writes SessionState
# Enforcement: compile-time -- no IStateWritePort dependency exists.
# This helper validates at init time that no write port was injected.
# ---------------------------------------------------------------------------


def assert_mw01_no_write_port(dependencies: Dict[str, Any]) -> None:
    """MW-01: Assert no SessionState write port exists in dependencies.

    Called during MemoryWriterPipeline initialization.

    Args:
        dependencies: Dict of injected port instances keyed by name.

    Raises:
        InvariantViolation: If any write port is found.
    """
    forbidden = {"IStateWritePort", "state_write_port", "session_write"}
    found = forbidden & set(dependencies.keys())
    if found:
        raise InvariantViolation(
            "MW-01",
            f"SessionState write port(s) found in dependencies: {found}. "
            "Memory Writer NEVER writes SessionState.",
        )


# ---------------------------------------------------------------------------
# MW-02: Reads SessionState lock-free <1ms
# Enforcement: runtime timing assertion on snapshot call.
# ---------------------------------------------------------------------------


def assert_mw02_read_latency(latency_ms: float, threshold_ms: float = 1.0) -> None:
    """MW-02: Assert SessionState read completed within latency budget.

    Called after ISessionReadPort.snapshot() returns.

    Args:
        latency_ms: Measured read latency in milliseconds.
        threshold_ms: Maximum allowed latency (default 1.0ms).

    Raises:
        InvariantViolation: If latency exceeds threshold.
    """
    if latency_ms > threshold_ms:
        raise InvariantViolation(
            "MW-02",
            f"SessionState read took {latency_ms:.2f}ms, " f"exceeding {threshold_ms}ms budget.",
        )


# ---------------------------------------------------------------------------
# MW-03: All K0 writes via Bridge
# Enforcement: compile-time -- only IBridgeCommandPort as output path.
# This helper validates at init time.
# ---------------------------------------------------------------------------


def assert_mw03_bridge_only(dependencies: Dict[str, Any]) -> None:
    """MW-03: Assert no direct DB or HTTP output ports exist.

    Called during MemoryWriterPipeline initialization.

    Args:
        dependencies: Dict of injected port instances keyed by name.

    Raises:
        InvariantViolation: If any direct output port is found.
    """
    forbidden = {"db_port", "http_port", "direct_write_port", "database"}
    found = forbidden & set(dependencies.keys())
    if found:
        raise InvariantViolation(
            "MW-03",
            f"Direct output port(s) found: {found}. "
            "All K0 writes must go through IBridgeCommandPort.",
        )


# ---------------------------------------------------------------------------
# MW-04: Body text <= 50 words
# Enforcement: runtime assertion in ExtractionValidator.
# ---------------------------------------------------------------------------


def assert_mw04_text_length(text: str, config: Optional[MWConfig] = None) -> None:
    """MW-04: Assert atom text does not exceed word limit.

    Called by ExtractionValidator on each extracted MemoryAtom.

    Args:
        text: The memory atom text field.
        config: MWConfig for max_text_words (default 50).

    Raises:
        InvariantViolation: If text exceeds word limit.
    """
    max_words = config.max_text_words if config else 50
    word_count = len(text.split())
    if word_count > max_words:
        raise InvariantViolation(
            "MW-04",
            f"Atom text has {word_count} words, exceeding limit of {max_words}.",
        )


# ---------------------------------------------------------------------------
# MW-05: 0-6 atoms per turn max
# Enforcement: runtime assertion in pipeline output.
# ---------------------------------------------------------------------------


def assert_mw05_atom_count(count: int, config: Optional[MWConfig] = None) -> None:
    """MW-05: Assert atom count does not exceed per-turn limit.

    Called after WriterAgent extraction before envelope building.

    Args:
        count: Number of atoms extracted for this turn.
        config: MWConfig for max_atoms_per_turn (default 6).

    Raises:
        InvariantViolation: If count exceeds limit.
    """
    max_atoms = config.max_atoms_per_turn if config else 6
    if count > max_atoms:
        raise InvariantViolation(
            "MW-05",
            f"Extracted {count} atoms, exceeding limit of {max_atoms} per turn.",
        )


# ---------------------------------------------------------------------------
# MW-06: LLM budget: 2000 tokens
# Enforcement: runtime assertion in IModelHubPort call.
# ---------------------------------------------------------------------------


def assert_mw06_token_budget(budget_tokens: int, config: Optional[MWConfig] = None) -> None:
    """MW-06: Assert LLM call does not exceed token budget.

    Called before IModelHubPort.chat() invocation.

    Args:
        budget_tokens: Token budget being passed to Model Hub.
        config: MWConfig for llm_token_budget (default 2000).

    Raises:
        InvariantViolation: If budget exceeds configured limit.
    """
    max_budget = config.llm_token_budget if config else 2000
    if budget_tokens > max_budget:
        raise InvariantViolation(
            "MW-06",
            f"LLM budget {budget_tokens} tokens exceeds limit of {max_budget}.",
        )


# ---------------------------------------------------------------------------
# MW-07: Filter is rule-based (no LLM)
# Enforcement: compile-time -- no IModelHubPort in filter package.
# This is a static check, not a runtime assertion.
# ---------------------------------------------------------------------------


def assert_mw07_filter_no_llm(filter_dependencies: Dict[str, Any]) -> None:
    """MW-07: Assert RelevanceFilter has no LLM port dependency.

    Called during RelevanceFilter initialization.

    Args:
        filter_dependencies: Dict of injected dependencies for the filter.

    Raises:
        InvariantViolation: If any LLM-related port is found.
    """
    forbidden = {"IModelHubPort", "model_hub_port", "model_hub", "llm_port"}
    found = forbidden & set(filter_dependencies.keys())
    if found:
        raise InvariantViolation(
            "MW-07",
            f"LLM port(s) found in filter dependencies: {found}. "
            "Filter must be rule-based only.",
        )


# ---------------------------------------------------------------------------
# MW-08: Batch window: 250ms
# Enforcement: runtime config validation.
# ---------------------------------------------------------------------------


def assert_mw08_batch_window(config: MWConfig) -> None:
    """MW-08: Assert batch window matches configured value.

    Called during DeltaAggregator initialization.

    Args:
        config: MWConfig with batch_window_ms.

    Raises:
        InvariantViolation: If batch window is misconfigured.
    """
    if config.batch_window_ms <= 0:
        raise InvariantViolation(
            "MW-08",
            f"Batch window {config.batch_window_ms}ms is invalid. Must be > 0.",
        )


# ---------------------------------------------------------------------------
# MW-09: Offline-safe (LocalOutbox)
# Enforcement: runtime adapter guarantee. This is validated at adapter level.
# Placeholder assertion for init-time adapter capability check.
# ---------------------------------------------------------------------------


def assert_mw09_offline_capable(adapter: Any) -> None:
    """MW-09: Assert Bridge adapter supports offline queueing.

    Called during MemoryWriterPipeline initialization to verify
    the IBridgeCommandPort adapter has outbox capability.

    Args:
        adapter: The IBridgeCommandPort adapter instance.

    Raises:
        InvariantViolation: If adapter lacks offline support.
    """
    if hasattr(adapter, "supports_offline") and not adapter.supports_offline:
        raise InvariantViolation(
            "MW-09",
            "IBridgeCommandPort adapter does not support offline queueing. "
            "Memory Writer requires LocalOutbox capability.",
        )


# ---------------------------------------------------------------------------
# MW-10: All envelopes carry cognitive_trace_id
# Enforcement: runtime assertion in EnvelopeBuilder.
# ---------------------------------------------------------------------------


def assert_mw10_trace_id(trace_id: Optional[str]) -> None:
    """MW-10: Assert envelope carries a non-empty cognitive_trace_id.

    Called by EnvelopeBuilder on every envelope construction.

    Args:
        trace_id: The cognitive_trace_id from the envelope.

    Raises:
        InvariantViolation: If trace_id is missing or empty.
    """
    if not trace_id or not trace_id.strip():
        raise InvariantViolation(
            "MW-10",
            "Envelope missing cognitive_trace_id. " "All envelopes MUST carry a trace ID.",
        )


# ---------------------------------------------------------------------------
# MW-11: UltraBERT validates in K0 P02 (not K1)
# Enforcement: compile-time -- no UltraBERT import in memory_writer.
# This is a static check helper for CI/contract validation.
# ---------------------------------------------------------------------------


def assert_mw11_no_ultrabert_import() -> None:
    """MW-11: Assert no UltraBERT imports exist in memory_writer package.

    This is a compile-time / CI check. At runtime, it verifies that
    the ultrabert module is not loaded in the memory_writer namespace.

    Raises:
        InvariantViolation: If UltraBERT is imported.
    """
    import sys

    mw_modules = [name for name in sys.modules if name.startswith("k1.memory_writer")]
    for mod_name in mw_modules:
        mod = sys.modules.get(mod_name)
        if mod and hasattr(mod, "__dict__"):
            for attr_name in mod.__dict__:
                if "ultrabert" in attr_name.lower():
                    raise InvariantViolation(
                        "MW-11",
                        f"UltraBERT reference found in {mod_name}.{attr_name}. "
                        "UltraBERT validation belongs in K0 P02, not K1.",
                    )


# ---------------------------------------------------------------------------
# MW-12: temporal_links validation (0-5 TemporalLinks per atom)
# Enforcement: runtime assertion in ExtractionValidator.
# ---------------------------------------------------------------------------

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


def assert_mw12_temporal_links(
    temporal_links: Sequence,
    config: Optional[MWConfig] = None,
) -> None:
    """MW-12: Assert temporal_links conform to TemporalLink contract.

    Validation rules:
      1. Must be a list or tuple.
      2. Maximum items = config.max_temporal_links_per_atom (default 5).
      3. Each link must have a non-empty ``mentioned_time``.
      4. Each link must have a valid ``link_type`` (one of 6 enum values).
      5. ``confidence`` must be in [0.0, 1.0].
      6. ``uncertainty_window_ms`` must be >= 0.

    Args:
        temporal_links: The temporal_links sequence from a MemoryAtom.
        config: MWConfig for max_temporal_links_per_atom.

    Raises:
        InvariantViolation: On first violation found.
    """
    if not isinstance(temporal_links, (list, tuple)):
        raise InvariantViolation(
            "MW-12",
            f"temporal_links must be list or tuple, got {type(temporal_links).__name__}.",
        )

    max_links = config.max_temporal_links_per_atom if config else 5
    if len(temporal_links) > max_links:
        raise InvariantViolation(
            "MW-12",
            f"temporal_links has {len(temporal_links)} items, exceeding limit of {max_links}.",
        )

    for i, link in enumerate(temporal_links):
        # mentioned_time: non-empty string
        mt = getattr(link, "mentioned_time", None)
        if not mt or not isinstance(mt, str) or not mt.strip():
            raise InvariantViolation(
                "MW-12",
                f"temporal_links[{i}].mentioned_time is missing or empty.",
            )

        # link_type: valid enum value
        lt = getattr(link, "link_type", None)
        if lt not in _VALID_LINK_TYPES:
            raise InvariantViolation(
                "MW-12",
                f"temporal_links[{i}].link_type '{lt}' is not a valid TemporalLinkType.",
            )

        # confidence: [0.0, 1.0]
        conf = getattr(link, "confidence", None)
        if conf is None or not isinstance(conf, (int, float)) or conf < 0.0 or conf > 1.0:
            raise InvariantViolation(
                "MW-12",
                f"temporal_links[{i}].confidence={conf} is not in [0.0, 1.0].",
            )

        # uncertainty_window_ms: >= 0
        uw = getattr(link, "uncertainty_window_ms", None)
        if uw is None or not isinstance(uw, (int, float)) or uw < 0:
            raise InvariantViolation(
                "MW-12",
                f"temporal_links[{i}].uncertainty_window_ms={uw} is negative or missing.",
            )


_PLACE_ID_RE = re.compile(r"^place_[a-z0-9_]+$")


def assert_mw13_place_id(place_id: Optional[str]) -> None:
    """MW-13: place_id must be None or match pattern place_<slug>.

    Rules:
      - None is valid (location not resolved)
      - Non-empty string must match ^place_[a-z0-9_]+$
      - Empty string is invalid (use None instead)

    Raises:
        InvariantViolation: If place_id is malformed.
    """
    if place_id is None:
        return
    if not isinstance(place_id, str) or not place_id:
        raise InvariantViolation(
            "MW-13",
            f"place_id must be None or a non-empty string, got {type(place_id).__name__}={place_id!r}.",
        )
    if not _PLACE_ID_RE.match(place_id):
        raise InvariantViolation(
            "MW-13",
            f"place_id '{place_id}' does not match pattern ^place_[a-z0-9_]+$.",
        )


# ---------------------------------------------------------------------------
# Convenience: run all init-time invariant checks
# ---------------------------------------------------------------------------


def validate_init_invariants(
    dependencies: Dict[str, Any],
    filter_dependencies: Dict[str, Any],
    bridge_adapter: Any,
    config: MWConfig,
) -> None:
    """Run all init-time invariant checks (MW-01, MW-03, MW-07, MW-08, MW-09, MW-11).

    Called by MemoryWriterPipeline.__init__() after dependency injection.

    Args:
        dependencies: All injected port instances.
        filter_dependencies: Dependencies injected into RelevanceFilter.
        bridge_adapter: The IBridgeCommandPort adapter instance.
        config: MWConfig instance.

    Raises:
        InvariantViolation: On first violation found.
    """
    assert_mw01_no_write_port(dependencies)
    assert_mw03_bridge_only(dependencies)
    assert_mw07_filter_no_llm(filter_dependencies)
    assert_mw08_batch_window(config)
    assert_mw09_offline_capable(bridge_adapter)
    assert_mw11_no_ultrabert_import()
