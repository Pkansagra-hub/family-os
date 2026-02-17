"""TestFabricRetrievalAdapter -- in-memory IFabricRetrievalPort (SS16.2.3).

Implements the IFabricRetrievalPort Protocol (SS15.4) with:
- Constructor injection of preset capabilities and prompts
- Capture-mode recording of all discover/find calls
- Zero I/O, purely in-memory result construction
- Protocol-structural compliance with IFabricRetrievalPort

File location: tests/k1/planner/adapters/ (SS30.3)
Never importable from production code.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from k1.fabric.types import RetrievalResult, ScoredCapability


class TestFabricRetrievalAdapter:
    """In-memory IFabricRetrievalPort for deterministic testing (SS16.2.3).

    Constructor
    -----------
    preset_capabilities : List[ScoredCapability]
        Pre-configured capability results for discover_capabilities().
    preset_prompts : List[ScoredCapability]
        Pre-configured prompt results for find_relevant_prompts().

    Internal state
    --------------
    _discover_log : List[Dict]
        Capture list of all discover_capabilities() call arguments.
    _prompt_log : List[Dict]
        Capture list of all find_relevant_prompts() call arguments.
    """

    def __init__(
        self,
        preset_capabilities: Optional[List[ScoredCapability]] = None,
        preset_prompts: Optional[List[ScoredCapability]] = None,
    ) -> None:
        self._preset_capabilities: List[ScoredCapability] = list(preset_capabilities or [])
        self._preset_prompts: List[ScoredCapability] = list(preset_prompts or [])
        self._discover_log: List[Dict[str, Any]] = []
        self._prompt_log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # IFabricRetrievalPort Protocol methods
    # ------------------------------------------------------------------

    async def discover_capabilities(
        self,
        domain: Optional[List[str]] = None,
        intent: str = "",
        safety_band: str = "GREEN",
        session_context: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
    ) -> RetrievalResult:
        """Return preset capabilities sliced to top_k."""
        self._discover_log.append(
            {
                "domain": domain,
                "intent": intent,
                "safety_band": safety_band,
                "session_context": session_context,
                "top_k": top_k,
            }
        )
        sliced = self._preset_capabilities[:top_k]
        return RetrievalResult(
            capabilities=sliced,
            total_matched=len(self._preset_capabilities),
            query_latency_ms=0,
            query_intent=intent,
        )

    async def find_relevant_prompts(
        self,
        intent: str = "",
        domain: Optional[List[str]] = None,
        safety_band: str = "GREEN",
        top_k: int = 10,
    ) -> RetrievalResult:
        """Return preset prompts sliced to top_k."""
        self._prompt_log.append(
            {
                "intent": intent,
                "domain": domain,
                "safety_band": safety_band,
                "top_k": top_k,
            }
        )
        sliced = self._preset_prompts[:top_k]
        return RetrievalResult(
            capabilities=sliced,
            total_matched=len(self._preset_prompts),
            query_latency_ms=0,
            query_intent=intent,
        )

    # ------------------------------------------------------------------
    # Assertion / introspection helpers (test-only)
    # ------------------------------------------------------------------

    @property
    def discover_log(self) -> List[Dict[str, Any]]:
        """Read-only access to discover_capabilities() call log."""
        return list(self._discover_log)

    @property
    def prompt_log(self) -> List[Dict[str, Any]]:
        """Read-only access to find_relevant_prompts() call log."""
        return list(self._prompt_log)

    @property
    def discover_count(self) -> int:
        """Number of discover_capabilities() calls."""
        return len(self._discover_log)

    @property
    def prompt_count(self) -> int:
        """Number of find_relevant_prompts() calls."""
        return len(self._prompt_log)

    def assert_discover_count(self, n: int) -> None:
        """Assert discover_capabilities() was called exactly n times."""
        assert self.discover_count == n, f"Expected {n} discover calls, got {self.discover_count}"

    def assert_prompt_count(self, n: int) -> None:
        """Assert find_relevant_prompts() was called exactly n times."""
        assert self.prompt_count == n, f"Expected {n} prompt calls, got {self.prompt_count}"

    def assert_safety_band_in_discovers(self, expected: str) -> None:
        """Assert all discover_capabilities() calls used the given safety_band."""
        for i, call in enumerate(self._discover_log):
            actual = call["safety_band"]
            assert actual == expected, (
                f"discover call {i}: expected safety_band={expected!r}, " f"got {actual!r}"
            )

    def assert_safety_band_in_prompts(self, expected: str) -> None:
        """Assert all find_relevant_prompts() calls used the given safety_band."""
        for i, call in enumerate(self._prompt_log):
            actual = call["safety_band"]
            assert actual == expected, (
                f"prompt call {i}: expected safety_band={expected!r}, " f"got {actual!r}"
            )

    def assert_domain_in_discovers(self, expected: Optional[List[str]]) -> None:
        """Assert all discover_capabilities() calls used the given domain."""
        for i, call in enumerate(self._discover_log):
            actual = call["domain"]
            assert (
                actual == expected
            ), f"discover call {i}: expected domain={expected}, got {actual}"

    def get_discover_top_k_values(self) -> List[int]:
        """Return top_k arguments from all discover_capabilities() calls."""
        return [call["top_k"] for call in self._discover_log]

    def get_prompt_top_k_values(self) -> List[int]:
        """Return top_k arguments from all find_relevant_prompts() calls."""
        return [call["top_k"] for call in self._prompt_log]
