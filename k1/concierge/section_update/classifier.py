"""Section-update classifier adapter contract and deterministic stub."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

from k1.concierge.section_update.types import (
    ClassifierMode,
    SectionUpdateInput,
    SectionUpdatePlan,
)


class ISectionUpdateClassifier(ABC):
    """Adapter protocol: produce plans only, never write SessionState."""

    @abstractmethod
    async def classify(self, input_data: SectionUpdateInput) -> SectionUpdatePlan:
        """Classify one completed turn into a SectionUpdatePlan."""


class DeterministicSectionUpdateClassifier(ISectionUpdateClassifier):
    """Fixture-driven offline classifier for tests and degraded local runs."""

    classifier_version = "offline_stub"

    def __init__(
        self,
        plans_by_turn: Mapping[str, SectionUpdatePlan | Mapping[str, object]] | None = None,
    ) -> None:
        self._plans_by_turn = dict(plans_by_turn or {})

    async def classify(self, input_data: SectionUpdateInput) -> SectionUpdatePlan:
        mode = str(input_data.constraints.get("classifier_mode", "") or "")
        if mode == ClassifierMode.DEGRADED_NOOP.value:
            return self._noop(input_data, "degraded_noop mode")
        configured = self._plans_by_turn.get(input_data.turn_id)
        if configured is None:
            return self._noop(input_data, "offline stub has no fixture for turn")
        plan = (
            configured
            if isinstance(configured, SectionUpdatePlan)
            else SectionUpdatePlan.from_dict(configured)
        )
        return plan

    def _noop(self, input_data: SectionUpdateInput, reason: str) -> SectionUpdatePlan:
        return SectionUpdatePlan.noop(
            plan_id=f"offline-stub:{input_data.turn_id}",
            turn_id=input_data.turn_id,
            session_id=input_data.session_id,
            classifier_version=self.classifier_version,
            reason=reason,
            cognitive_trace_id=input_data.cognitive_trace_id,
        )
