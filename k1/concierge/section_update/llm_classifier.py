"""Production LLM-backed section-update classifier.

This is the real (non-fixture) implementation of
``ISectionUpdateClassifier``. It runs the full prompt + tool-schema
defined in :mod:`k1.concierge.section_update.prompt` through the K1
Model Hub (``IModelHubPort.execute``) and parses the single batched
``submit_section_update_batch`` tool call into a ``SectionUpdatePlan``.

Failures (no tool call, malformed JSON, schema rejection, provider
errors) are translated into a ``SectionUpdatePlan.noop(...)`` with a
diagnostic-bearing rejected candidate. Hard transport / provider
exceptions propagate so that
:func:`k1.concierge.section_update.lifecycle.classify_section_update_blocking`
can map them to ``SectionUpdateCompletionStatus.PROVIDER_FAILED``.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from k1.concierge.section_update.classifier import ISectionUpdateClassifier
from k1.concierge.section_update.prompt import (
    SECTION_UPDATE_BATCH_TOOL_NAME,
    build_section_update_system_prompt,
    build_section_update_tool_schema,
)
from k1.concierge.section_update.types import (
    SectionUpdateContractError,
    SectionUpdateInput,
    SectionUpdatePlan,
)
from k1.model_hub.ports.hub_port import IModelHubPort
from k1.model_hub.types import (
    CapabilityType,
    HubRequest,
    Message,
    ModelPreference,
    Priority,
    RequestConstraints,
    ToolCallPayload,
    ToolCallResultSet,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


class LLMSectionUpdateClassifier(ISectionUpdateClassifier):
    """Real LLM-backed classifier using K1 ModelHub TOOL_CALL capability."""

    classifier_version = "section-update-v0"

    def __init__(
        self,
        *,
        model_hub: IModelHubPort,
        provider_id: str = "vertex",
        model_id: str = "gemini-2.5-flash-lite",
        timeout_ms: int = 75_000,
        max_tokens: int = 8_192,
        temperature: float = 0.2,
        consumer_id: str = "section_update_classifier",
    ) -> None:
        if model_hub is None:
            raise ValueError("LLMSectionUpdateClassifier requires a model_hub")
        self._hub = model_hub
        self._provider_id = (provider_id or "").strip()
        self._model_id = (model_id or "").strip()
        self._timeout_ms = max(int(timeout_ms or 0), 1_000)
        self._max_tokens = max(int(max_tokens or 0), 1_024)
        self._temperature = float(temperature)
        self._consumer_id = consumer_id or "section_update_classifier"
        self._system_prompt = build_section_update_system_prompt()
        schema = build_section_update_tool_schema()
        self._tool = ToolDefinition(
            name=schema.name,
            description=schema.description,
            parameters=dict(schema.parameters or {}),
        )

    # ------------------------------------------------------------------
    # ISectionUpdateClassifier
    # ------------------------------------------------------------------

    async def classify(self, input_data: SectionUpdateInput) -> SectionUpdatePlan:
        trace_id = input_data.cognitive_trace_id or f"section-update:{input_data.turn_id}"
        user_text = _render_user_message(input_data)
        payload = ToolCallPayload(
            messages=[Message(role="user", content=user_text)],
            tools=[self._tool],
            tool_choice="required",
            parallel_tool_calls=False,
            system_prompt=self._system_prompt,
        )
        constraints = RequestConstraints(
            max_tokens=self._max_tokens,
            timeout_ms=self._timeout_ms,
            priority=Priority.BACKGROUND,
            temperature=self._temperature,
            model_preference=(
                ModelPreference(
                    preferred_provider=self._provider_id or None,
                    preferred_model=self._model_id or None,
                )
                if (self._provider_id or self._model_id)
                else None
            ),
            provider_preference=self._provider_id or None,
            consumer_id=self._consumer_id,
        )
        request = HubRequest(
            capability=CapabilityType.TOOL_CALL,
            payload=payload,
            constraints=constraints,
            trace_id=trace_id,
            session_id=input_data.session_id,
        )

        response = await self._hub.execute(request)
        result = response.result
        if not isinstance(result, ToolCallResultSet) or not result.tool_calls:
            logger.warning(
                "section_update classifier received no tool call session=%s turn=%s",
                input_data.session_id,
                input_data.turn_id,
            )
            return self._noop(input_data, "llm returned no tool call")

        call = result.tool_calls[0]
        if call.name != SECTION_UPDATE_BATCH_TOOL_NAME:
            logger.warning(
                "section_update classifier received unexpected tool=%s session=%s turn=%s",
                call.name,
                input_data.session_id,
                input_data.turn_id,
            )
            return self._noop(input_data, f"unexpected tool call: {call.name}")

        try:
            args = json.loads(call.arguments) if isinstance(call.arguments, str) else dict(
                call.arguments
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning(
                "section_update classifier tool args JSON parse failed session=%s turn=%s err=%s",
                input_data.session_id,
                input_data.turn_id,
                exc,
            )
            return self._noop(input_data, f"tool args parse error: {exc}")

        if not isinstance(args, dict):
            return self._noop(input_data, "tool args must be a JSON object")

        plan_dict = dict(args)
        plan_dict.setdefault("plan_id", f"llm:{input_data.turn_id}:{uuid.uuid4().hex[:8]}")
        plan_dict.setdefault("turn_id", input_data.turn_id)
        plan_dict.setdefault("session_id", input_data.session_id)
        plan_dict.setdefault("classifier_version", self.classifier_version)
        plan_dict.setdefault("cognitive_trace_id", input_data.cognitive_trace_id)
        if not plan_dict.get("snapshot_version"):
            plan_dict["snapshot_version"] = str(
                input_data.session_snapshot.get("snapshot_version", "") or ""
            )
        if not plan_dict.get("snapshot_source_epoch"):
            plan_dict["snapshot_source_epoch"] = str(
                input_data.session_snapshot.get("snapshot_source_epoch", "") or ""
            )

        try:
            return SectionUpdatePlan.from_dict(plan_dict)
        except (SectionUpdateContractError, ValueError, TypeError) as exc:
            logger.warning(
                "section_update plan contract rejected session=%s turn=%s err=%s",
                input_data.session_id,
                input_data.turn_id,
                exc,
            )
            return self._noop(input_data, f"plan contract rejected: {exc}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _noop(self, input_data: SectionUpdateInput, reason: str) -> SectionUpdatePlan:
        return SectionUpdatePlan.noop(
            plan_id=f"llm-noop:{input_data.turn_id}:{uuid.uuid4().hex[:8]}",
            turn_id=input_data.turn_id,
            session_id=input_data.session_id,
            classifier_version=self.classifier_version,
            reason=reason,
            cognitive_trace_id=input_data.cognitive_trace_id,
        )


def _render_user_message(input_data: SectionUpdateInput) -> str:
    """Render the section-update classifier user payload as compact JSON.

    The system prompt enumerates the schema; the user message simply
    delivers the full turn context so the model can pattern-match
    sections to update. Speaker identity is surfaced as a top-level
    field so the classifier can normalize first-person pronouns
    ("I", "me", "my") into the active member's real name when emitting
    belief subjects.
    """

    speaker_identity = (
        input_data.session_snapshot.get("speaker_identity", {})
        if isinstance(input_data.session_snapshot, dict)
        else {}
    )
    payload: dict[str, Any] = {
        "speaker_identity": speaker_identity,
        "turn_id": input_data.turn_id,
        "session_id": input_data.session_id,
        "cognitive_trace_id": input_data.cognitive_trace_id,
        "prompt_mode": input_data.prompt_mode,
        "fsm_state": input_data.fsm_state,
        "bus_topic": input_data.bus_topic,
        "admission_context": input_data.admission_context,
        "user_turn": input_data.user_turn,
        "assistant_turn": input_data.assistant_turn,
        "arbiter_context": input_data.arbiter_context,
        "prompt_context": input_data.prompt_context,
        "session_snapshot": input_data.session_snapshot,
        "history_context": input_data.history_context,
        "scenario_context": input_data.scenario_context,
        "constraints": input_data.constraints,
    }
    return json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)


__all__ = ["LLMSectionUpdateClassifier"]
