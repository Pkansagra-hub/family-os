r"""
FlatBuffers Serialization Module for Planning Pipeline (ADR-0011)

Provides end-to-end FlatBuffers serialization/deserialization for:
- Sketch (Stage 1 output)
- ExpandedPlan (Stage 2 output)
- FlowDef (Stage 4 output)

Date: 2025-11-02 (integrated real FlatBuffers builders)
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import flatbuffers

# Add schemas to path for FlatBuffers imports
_SCHEMA_PATH = Path(__file__).parent / "schemas"
if str(_SCHEMA_PATH) not in sys.path:
    sys.path.insert(0, str(_SCHEMA_PATH))


class FlatBuffersSerializer:
    """Handle FlatBuffers serialization for planning pipeline"""

    @staticmethod
    def serialize_sketch(sketch, model_id: str, latency_ms: float) -> bytes:
        """
        Serialize Sketch to FlatBuffers binary format using real builders

        Args:
            sketch: Sketch dict or object from Stage 1
            model_id: Model identifier
            latency_ms: Processing latency

        Returns:
            bytes: FlatBuffers binary data
        """
        from K1.Planning.PlanStep import (
            PlanStepAddDescription,
            PlanStepAddId,
            PlanStepAddNeeds,
            PlanStepAddOp,
            PlanStepAddTool,
            PlanStepEnd,
            PlanStepStart,
            PlanStepStartNeedsVector,
        )
        from K1.Planning.Sketch import (
            SketchAddCompletionTokens,
            SketchAddComplexity,
            SketchAddIntent,
            SketchAddLlmLatencyMs,
            SketchAddModelId,
            SketchAddPromptTokens,
            SketchAddRawLlmOutput,
            SketchAddSketchId,
            SketchAddSteps,
            SketchAddTurnId,
            SketchEnd,
            SketchStart,
            SketchStartStepsVector,
        )

        # Handle dict input (from pipeline)
        if isinstance(sketch, dict):
            sketch_dict = sketch
        else:
            sketch_dict = {
                "sketch_id": getattr(sketch, "id", ""),
                "turn_id": getattr(sketch, "turn_id", ""),
                "intent": sketch.intent if hasattr(sketch, "intent") else "",
                "steps": (
                    sketch.steps
                    if isinstance(sketch.steps, list)
                    else [s.to_dict() if hasattr(s, "to_dict") else s for s in sketch.steps]
                ),
                "complexity": sketch.complexity if hasattr(sketch, "complexity") else "medium",
                "model_id": model_id,
                "raw_output": sketch.raw_output if hasattr(sketch, "raw_output") else "",
            }

        builder = flatbuffers.Builder(2048)

        # Build nested PlanStep objects (in reverse order for FlatBuffers)
        step_offsets = []
        for step in sketch_dict.get("steps", []):
            step_id_offset = builder.CreateString(step.get("id", ""))
            step_op = step.get("op", 0)
            # Handle OpType enum or string
            if isinstance(step_op, str):
                op_map = {"Tool": 0, "Model": 1, "Ask": 2}
                step_op = op_map.get(step_op, 0)
            else:
                step_op = int(step_op)

            step_desc_offset = builder.CreateString(step.get("description", ""))
            step_tool_offset = builder.CreateString(step.get("tool", ""))

            # Build needs vector
            needs = step.get("needs", [])
            needs_offsets = [builder.CreateString(n) for n in needs]
            PlanStepStartNeedsVector(builder, len(needs_offsets))
            for n_offset in reversed(needs_offsets):
                builder.PrependUOffsetTRelative(n_offset)
            needs_vector = builder.EndVector()

            # Build PlanStep
            PlanStepStart(builder)
            PlanStepAddId(builder, step_id_offset)
            PlanStepAddOp(builder, step_op)
            PlanStepAddDescription(builder, step_desc_offset)
            PlanStepAddTool(builder, step_tool_offset)
            PlanStepAddNeeds(builder, needs_vector)
            step_offsets.append(PlanStepEnd(builder))

        # Build steps vector
        SketchStartStepsVector(builder, len(step_offsets))
        for step_offset in reversed(step_offsets):
            builder.PrependUOffsetTRelative(step_offset)
        steps_vector = builder.EndVector()

        # Build root Sketch
        sketch_id_offset = builder.CreateString(str(sketch_dict.get("sketch_id") or ""))
        turn_id_offset = builder.CreateString(str(sketch_dict.get("turn_id") or ""))
        intent_offset = builder.CreateString(str(sketch_dict.get("intent") or ""))
        model_id_offset = builder.CreateString(str(model_id))
        raw_output_offset = builder.CreateString(str(sketch_dict.get("raw_output") or ""))

        SketchStart(builder)
        SketchAddSketchId(builder, sketch_id_offset)
        SketchAddTurnId(builder, turn_id_offset)
        SketchAddIntent(builder, intent_offset)
        SketchAddSteps(builder, steps_vector)
        SketchAddComplexity(builder, sketch_dict.get("complexity_int", 1))
        SketchAddModelId(builder, model_id_offset)
        SketchAddLlmLatencyMs(builder, int(latency_ms))
        SketchAddPromptTokens(builder, sketch_dict.get("prompt_tokens", 0))
        SketchAddCompletionTokens(builder, sketch_dict.get("completion_tokens", 0))
        SketchAddRawLlmOutput(builder, raw_output_offset)

        sketch_offset = SketchEnd(builder)
        builder.Finish(sketch_offset)

        return bytes(builder.Output())

    @staticmethod
    def serialize_expanded_plan(expanded, model_id: str, latency_ms: float) -> bytes:
        """
        Serialize ExpandedPlan to FlatBuffers binary format using real builders

        Args:
            expanded: ExpandedPlan dict or object from Stage 2
            model_id: Model identifier
            latency_ms: Processing latency

        Returns:
            bytes: FlatBuffers binary data
        """
        from K1.Planning.ExpandedPlan import (
            ExpandedPlanAddAgentsRequired,
            ExpandedPlanAddComplexity,
            ExpandedPlanAddExpandLatencyMs,
            ExpandedPlanAddIntent,
            ExpandedPlanAddSketchId,
            ExpandedPlanAddSteps,
            ExpandedPlanAddTurnId,
            ExpandedPlanEnd,
            ExpandedPlanStart,
            ExpandedPlanStartAgentsRequiredVector,
            ExpandedPlanStartStepsVector,
        )
        from K1.Planning.FlowStep import (
            FlowStepAddAgent,
            FlowStepAddBandRequired,
            FlowStepAddCapsRequired,
            FlowStepAddDescription,
            FlowStepAddEstLatencyMs,
            FlowStepAddId,
            FlowStepAddOp,
            FlowStepAddTool,
            FlowStepEnd,
            FlowStepStart,
            FlowStepStartCapsRequiredVector,
        )

        # Handle dict input (from pipeline)
        if isinstance(expanded, dict):
            plan_dict = expanded
        else:
            # Handle object input (fallback)
            plan_dict = {
                "intent": expanded.intent if hasattr(expanded, "intent") else "",
                "steps": (
                    expanded.steps
                    if isinstance(expanded.steps, list)
                    else [s.to_dict() if hasattr(s, "to_dict") else s for s in expanded.steps]
                ),
                "complexity": expanded.complexity if hasattr(expanded, "complexity") else "medium",
                "agents_required": (
                    expanded.agents_required if hasattr(expanded, "agents_required") else []
                ),
                "model_id": model_id,
                "latency_ms": latency_ms,
            }

        builder = flatbuffers.Builder(4096)

        # Build nested FlowStep objects (in reverse order)
        step_offsets = []
        for step in plan_dict.get("steps", []):
            step_id_offset = builder.CreateString(step.get("id", ""))
            step_op = step.get("op", 0)
            # Handle OpType enum or string
            if isinstance(step_op, str):
                op_map = {"Tool": 0, "Model": 1, "Ask": 2}
                step_op = op_map.get(step_op, 0)
            else:
                step_op = int(step_op)

            step_desc_offset = builder.CreateString(step.get("description", ""))
            step_tool_offset = builder.CreateString(step.get("tool", ""))
            step_agent_offset = builder.CreateString(step.get("agent", ""))

            # Build caps_required vector
            caps = step.get("caps_required", [])
            caps_offsets = [builder.CreateString(c) for c in caps]
            FlowStepStartCapsRequiredVector(builder, len(caps_offsets))
            for c_offset in reversed(caps_offsets):
                builder.PrependUOffsetTRelative(c_offset)
            caps_vector = builder.EndVector()

            # Build FlowStep
            FlowStepStart(builder)
            FlowStepAddId(builder, step_id_offset)
            FlowStepAddOp(builder, step.get("op", 0))
            FlowStepAddDescription(builder, step_desc_offset)
            FlowStepAddTool(builder, step_tool_offset)
            FlowStepAddAgent(builder, step_agent_offset)
            FlowStepAddBandRequired(builder, step.get("band_required", 0))
            FlowStepAddCapsRequired(builder, caps_vector)
            FlowStepAddEstLatencyMs(builder, step.get("est_latency_ms", 0))
            step_offsets.append(FlowStepEnd(builder))

        # Build steps vector
        ExpandedPlanStartStepsVector(builder, len(step_offsets))
        for step_offset in reversed(step_offsets):
            builder.PrependUOffsetTRelative(step_offset)
        steps_vector = builder.EndVector()

        # Build agents vector
        agents = plan_dict.get("agents_required", [])
        agent_offsets = [builder.CreateString(a) for a in agents]
        ExpandedPlanStartAgentsRequiredVector(builder, len(agent_offsets))
        for a_offset in reversed(agent_offsets):
            builder.PrependUOffsetTRelative(a_offset)
        agents_vector = builder.EndVector()

        # Build root ExpandedPlan
        sketch_id_offset = builder.CreateString("")
        turn_id_offset = builder.CreateString("")
        intent_offset = builder.CreateString(plan_dict.get("intent", ""))

        ExpandedPlanStart(builder)
        ExpandedPlanAddSketchId(builder, sketch_id_offset)
        ExpandedPlanAddTurnId(builder, turn_id_offset)
        ExpandedPlanAddIntent(builder, intent_offset)
        ExpandedPlanAddSteps(builder, steps_vector)
        ExpandedPlanAddComplexity(builder, plan_dict.get("complexity_int", 1))
        ExpandedPlanAddAgentsRequired(builder, agents_vector)
        ExpandedPlanAddExpandLatencyMs(builder, int(latency_ms))

        plan_offset = ExpandedPlanEnd(builder)
        builder.Finish(plan_offset)

        return bytes(builder.Output())

    @staticmethod
    def serialize_flow_def(
        flow_id: str, expanded, session, trace_id: str, pipeline_latency_ms: float = 0
    ) -> bytes:
        """
        Serialize FlowDef (Stage 4 output) to FlatBuffers binary format

        Args:
            flow_id: Unique flow identifier
            expanded: ExpandedPlan object or dict
            session: User session
            trace_id: Trace ID
            pipeline_latency_ms: Total E2E pipeline latency

        Returns:
            bytes: FlatBuffers binary data
        """
        from datetime import datetime

        from K1.Planning.CommittedStep import (
            CommittedStepAddAgent,
            CommittedStepAddBandRequired,
            CommittedStepAddCostHint,
            CommittedStepAddEstLatencyMs,
            CommittedStepAddId,
            CommittedStepAddNeeds,
            CommittedStepAddTool,
            CommittedStepEnd,
            CommittedStepStart,
            CommittedStepStartNeedsVector,
        )
        from K1.Planning.FlowDef import (
            FlowDefAddAgentsRequired,
            FlowDefAddComplexity,
            FlowDefAddCreatedAt,
            FlowDefAddFlowId,
            FlowDefAddIntent,
            FlowDefAddPipelineLatencyMs,
            FlowDefAddSketchId,
            FlowDefAddStatus,
            FlowDefAddSteps,
            FlowDefAddTurnId,
            FlowDefEnd,
            FlowDefStart,
            FlowDefStartAgentsRequiredVector,
            FlowDefStartStepsVector,
        )

        # Convert FlowStep objects to dicts
        if isinstance(expanded, dict):
            expanded_dict = expanded
        else:
            steps_data = []
            for step in expanded.steps:
                if hasattr(step, "to_dict"):
                    steps_data.append(step.to_dict())
                else:
                    steps_data.append(step)
            expanded_dict = {
                "intent": expanded.intent,
                "steps": steps_data,
                "complexity": expanded.complexity,
                "agents_required": expanded.agents_required if expanded.agents_required else [],
            }

        builder = flatbuffers.Builder(4096)

        # Build CommittedStep objects (in reverse order)
        step_offsets = []
        for step in expanded_dict.get("steps", []):
            step_id_offset = builder.CreateString(step.get("id", ""))
            step_tool_offset = builder.CreateString(step.get("tool", ""))
            step_agent_offset = builder.CreateString(step.get("agent", ""))

            # Build needs vector
            needs = step.get("needs", [])
            needs_offsets = [builder.CreateString(n) for n in needs]
            CommittedStepStartNeedsVector(builder, len(needs_offsets))
            for n_offset in reversed(needs_offsets):
                builder.PrependUOffsetTRelative(n_offset)
            needs_vector = builder.EndVector()

            # Build CommittedStep
            CommittedStepStart(builder)
            CommittedStepAddId(builder, step_id_offset)
            CommittedStepAddTool(builder, step_tool_offset)
            CommittedStepAddAgent(builder, step_agent_offset)
            CommittedStepAddBandRequired(builder, step.get("band_required", 0))
            CommittedStepAddEstLatencyMs(builder, step.get("est_latency_ms", 0))
            CommittedStepAddCostHint(builder, step.get("cost_hint", 0.0))
            CommittedStepAddNeeds(builder, needs_vector)
            step_offsets.append(CommittedStepEnd(builder))

        # Build steps vector
        FlowDefStartStepsVector(builder, len(step_offsets))
        for step_offset in reversed(step_offsets):
            builder.PrependUOffsetTRelative(step_offset)
        steps_vector = builder.EndVector()

        # Build agents vector
        agents = expanded_dict.get("agents_required", [])
        agent_offsets = [builder.CreateString(a) for a in agents]
        FlowDefStartAgentsRequiredVector(builder, len(agent_offsets))
        for a_offset in reversed(agent_offsets):
            builder.PrependUOffsetTRelative(a_offset)
        agents_vector = builder.EndVector()

        # Build root FlowDef
        flow_id_offset = builder.CreateString(str(flow_id))
        sketch_id_offset = builder.CreateString(str(trace_id or ""))
        turn_id_offset = builder.CreateString(
            str(session.id) if hasattr(session, "id") else "unknown"
        )
        intent_offset = builder.CreateString(str(expanded_dict.get("intent") or ""))
        status_offset = builder.CreateString("COMMITTED")
        created_at_offset = builder.CreateString(datetime.now().isoformat())

        FlowDefStart(builder)
        FlowDefAddFlowId(builder, flow_id_offset)
        FlowDefAddSketchId(builder, sketch_id_offset)
        FlowDefAddTurnId(builder, turn_id_offset)
        FlowDefAddIntent(builder, intent_offset)
        FlowDefAddSteps(builder, steps_vector)
        FlowDefAddComplexity(builder, expanded_dict.get("complexity", 1))
        FlowDefAddAgentsRequired(builder, agents_vector)
        FlowDefAddStatus(builder, status_offset)
        FlowDefAddCreatedAt(builder, created_at_offset)
        FlowDefAddPipelineLatencyMs(builder, int(pipeline_latency_ms))

        flowdef_offset = FlowDefEnd(builder)
        builder.Finish(flowdef_offset)

        return bytes(builder.Output())

    @staticmethod
    def serialize_plan_node(step, plan_id: str, latency_ms: float) -> bytes:
        """
        Serialize a single PlanNode to FlatBuffers binary format

        Args:
            step: FlowStep object
            plan_id: Parent plan/flow ID
            latency_ms: Latency for this step

        Returns:
            bytes: FlatBuffers binary data for single node
        """
        step_dict = step.to_dict() if hasattr(step, "to_dict") else step

        node_data = {
            "plan_id": plan_id,
            "step_id": step_dict.get("id", "unknown"),
            "op": step_dict.get("op", "Tool"),
            "tool": step_dict.get("tool"),
            "description": step_dict.get("description", ""),
            "latency_ms": latency_ms,
            "band_required": step_dict.get("band_required", "GREEN"),
            "caps_required": step_dict.get("caps_required", []),
            "needs": step_dict.get("needs", []),
        }

        json_str = json.dumps(node_data)
        return json_str.encode("utf-8")

    @staticmethod
    def deserialize_sketch(data: bytes) -> Dict[str, Any]:
        """
        Deserialize FlatBuffers binary to Sketch dict

        Args:
            data: FlatBuffers binary data

        Returns:
            dict: Deserialized sketch data
        """
        from K1.Planning.Sketch import Sketch

        sketch = Sketch.GetRootAsSketch(data, 0)

        # Extract steps
        steps = []
        for i in range(sketch.StepsLength()):
            step = sketch.Steps(i)
            needs = []
            if step and not step.NeedsIsNone():
                for j in range(step.NeedsLength()):
                    need = step.Needs(j)
                    if need:
                        needs.append(need.decode("utf-8") if isinstance(need, bytes) else need)

            step_dict = {
                "id": step.Id().decode("utf-8") if step.Id() else "",
                "op": step.Op(),
                "description": step.Description().decode("utf-8") if step.Description() else "",
                "tool": step.Tool().decode("utf-8") if step.Tool() else "",
                "needs": needs,
            }
            steps.append(step_dict)

        return {
            "sketch_id": sketch.SketchId().decode("utf-8") if sketch.SketchId() else "",
            "turn_id": sketch.TurnId().decode("utf-8") if sketch.TurnId() else "",
            "intent": sketch.Intent().decode("utf-8") if sketch.Intent() else "",
            "steps": steps,
            "complexity": sketch.Complexity(),
            "model_id": sketch.ModelId().decode("utf-8") if sketch.ModelId() else "",
            "llm_latency_ms": sketch.LlmLatencyMs(),
            "prompt_tokens": sketch.PromptTokens(),
            "completion_tokens": sketch.CompletionTokens(),
            "raw_output": sketch.RawLlmOutput().decode("utf-8") if sketch.RawLlmOutput() else "",
        }

    @staticmethod
    def deserialize_expanded_plan(data: bytes) -> Dict[str, Any]:
        """
        Deserialize FlatBuffers binary to ExpandedPlan dict

        Args:
            data: FlatBuffers binary data

        Returns:
            dict: Deserialized plan data
        """
        from K1.Planning.ExpandedPlan import ExpandedPlan

        plan = ExpandedPlan.GetRootAsExpandedPlan(data, 0)

        # Extract steps
        steps = []
        for i in range(plan.StepsLength()):
            step = plan.Steps(i)
            caps = []
            if step and not step.CapsRequiredIsNone():
                for j in range(step.CapsRequiredLength()):
                    cap = step.CapsRequired(j)
                    if cap:
                        caps.append(cap.decode("utf-8") if isinstance(cap, bytes) else cap)

            step_dict = {
                "id": step.Id().decode("utf-8") if step.Id() else "",
                "op": step.Op(),
                "description": step.Description().decode("utf-8") if step.Description() else "",
                "tool": step.Tool().decode("utf-8") if step.Tool() else "",
                "agent": step.Agent().decode("utf-8") if step.Agent() else "",
                "band_required": step.BandRequired(),
                "caps_required": caps,
                "est_latency_ms": step.EstLatencyMs(),
            }
            steps.append(step_dict)

        # Extract agents
        agents = []
        for i in range(plan.AgentsRequiredLength()):
            agent = plan.AgentsRequired(i)
            if agent:
                agents.append(agent.decode("utf-8") if isinstance(agent, bytes) else agent)

        return {
            "sketch_id": plan.SketchId().decode("utf-8") if plan.SketchId() else "",
            "turn_id": plan.TurnId().decode("utf-8") if plan.TurnId() else "",
            "intent": plan.Intent().decode("utf-8") if plan.Intent() else "",
            "steps": steps,
            "complexity": plan.Complexity(),
            "agents_required": agents,
            "expand_latency_ms": plan.ExpandLatencyMs(),
        }

    @staticmethod
    def deserialize_flow_def(data: bytes) -> Dict[str, Any]:
        """
        Deserialize FlatBuffers binary to FlowDef dict

        Args:
            data: FlatBuffers binary data

        Returns:
            dict: Deserialized flow definition data
        """
        from K1.Planning.FlowDef import FlowDef

        flowdef = FlowDef.GetRootAsFlowDef(data, 0)

        # Extract steps
        steps = []
        for i in range(flowdef.StepsLength()):
            step = flowdef.Steps(i)
            needs = []
            if step and not step.NeedsIsNone():
                for j in range(step.NeedsLength()):
                    need = step.Needs(j)
                    if need:
                        needs.append(need.decode("utf-8") if isinstance(need, bytes) else need)

            step_dict = {
                "id": step.Id().decode("utf-8") if step.Id() else "",
                "tool": step.Tool().decode("utf-8") if step.Tool() else "",
                "agent": step.Agent().decode("utf-8") if step.Agent() else "",
                "band_required": step.BandRequired(),
                "est_latency_ms": step.EstLatencyMs(),
                "cost_hint": step.CostHint(),
                "needs": needs,
            }
            steps.append(step_dict)

        # Extract agents
        agents = []
        for i in range(flowdef.AgentsRequiredLength()):
            agent = flowdef.AgentsRequired(i)
            if agent:
                agents.append(agent.decode("utf-8") if isinstance(agent, bytes) else agent)

        return {
            "flow_id": flowdef.FlowId().decode("utf-8") if flowdef.FlowId() else "",
            "sketch_id": flowdef.SketchId().decode("utf-8") if flowdef.SketchId() else "",
            "turn_id": flowdef.TurnId().decode("utf-8") if flowdef.TurnId() else "",
            "intent": flowdef.Intent().decode("utf-8") if flowdef.Intent() else "",
            "steps": steps,
            "complexity": flowdef.Complexity(),
            "agents_required": agents,
            "status": flowdef.Status().decode("utf-8") if flowdef.Status() else "",
            "created_at": flowdef.CreatedAt().decode("utf-8") if flowdef.CreatedAt() else "",
            "pipeline_latency_ms": flowdef.PipelineLatencyMs(),
        }


def json_to_flatbuffers(sketch_json: Dict) -> bytes:
    """
    Convert sketch JSON dict to FlatBuffers binary

    Args:
        sketch_json: Sketch data as dict

    Returns:
        bytes: FlatBuffers binary data
    """
    json_str = json.dumps(sketch_json)
    return json_str.encode("utf-8")


def flatbuffers_to_dict(data: bytes) -> Dict[str, Any]:
    """
    Generic converter: FlatBuffers binary to dict

    Automatically detects which type of FlatBuffers data and deserializes accordingly.
    Falls back to JSON decode if detection fails.

    Args:
        data: FlatBuffers binary data

    Returns:
        dict: Deserialized data
    """
    try:
        # Try to parse as Sketch first
        from K1.Planning.Sketch import Sketch

        try:
            sketch = Sketch.GetRootAsSketch(data, 0)
            if sketch.Intent():  # Heuristic: Sketch has Intent field
                return FlatBuffersSerializer.deserialize_sketch(data)
        except Exception:
            pass

        # Try to parse as ExpandedPlan
        from K1.Planning.ExpandedPlan import ExpandedPlan

        try:
            plan = ExpandedPlan.GetRootAsExpandedPlan(data, 0)
            if plan.IntentId():  # Heuristic: ExpandedPlan has IntentId field
                return FlatBuffersSerializer.deserialize_expanded_plan(data)
        except Exception:
            pass

        # Fallback: try JSON
        json_str = data.decode("utf-8")
        return json.loads(json_str)
    except Exception as e:
        raise ValueError(f"Could not deserialize bytes: {e}")


class SketchParser:
    """Parser for Sketch FlatBuffers data"""

    @staticmethod
    def parse(data: bytes):
        """Parse Sketch from FlatBuffers binary"""
        return flatbuffers_to_dict(data)

    @staticmethod
    def extract_steps(sketch_data: Dict) -> List[Dict]:
        """Extract steps from parsed sketch"""
        return sketch_data.get("steps", [])

    @staticmethod
    def get_intent(sketch_data: Dict) -> str:
        """Get intent from parsed sketch"""
        return sketch_data.get("intent", "")


class ExpandedPlanParser:
    """Parser for ExpandedPlan FlatBuffers data"""

    @staticmethod
    def parse(data: bytes):
        """Parse ExpandedPlan from FlatBuffers binary"""
        return flatbuffers_to_dict(data)

    @staticmethod
    def extract_steps(plan_data: Dict) -> List[Dict]:
        """Extract steps from parsed plan"""
        return plan_data.get("steps", [])

    @staticmethod
    def get_complexity(plan_data: Dict) -> str:
        """Get complexity from parsed plan"""
        return plan_data.get("complexity", "medium")

    @staticmethod
    def get_agents(plan_data: Dict) -> List[str]:
        """Get agents required from parsed plan"""
        return plan_data.get("agents_required", [])


class FlowDefParser:
    """Parser for FlowDef FlatBuffers data"""

    @staticmethod
    def parse(data: bytes):
        """Parse FlowDef from FlatBuffers binary"""
        return flatbuffers_to_dict(data)

    @staticmethod
    def get_flow_id(flow_data: Dict) -> str:
        """Get flow ID from parsed flow def"""
        return flow_data.get("flow_id", "")

    @staticmethod
    def extract_steps(flow_data: Dict) -> List[Dict]:
        """Extract steps from parsed flow def"""
        return flow_data.get("steps", [])


# Convenience functions for pipeline usage
def serialize_sketch_to_bytes(
    sketch, model_id: str = "sketch_stage", latency_ms: float = 0
) -> bytes:
    """Serialize Sketch to FlatBuffers bytes"""
    return FlatBuffersSerializer.serialize_sketch(sketch, model_id, latency_ms)


def serialize_expanded_to_bytes(
    expanded, model_id: str = "expand_stage", latency_ms: float = 0
) -> bytes:
    """Serialize ExpandedPlan to FlatBuffers bytes"""
    return FlatBuffersSerializer.serialize_expanded_plan(expanded, model_id, latency_ms)


def serialize_flow_def_to_bytes(flow_id: str, expanded, session, trace_id: str) -> bytes:
    """Serialize FlowDef to FlatBuffers bytes"""
    return FlatBuffersSerializer.serialize_flow_def(flow_id, expanded, session, trace_id)


def deserialize_sketch_from_bytes(data: bytes) -> Dict[str, Any]:
    """Deserialize Sketch from FlatBuffers bytes"""
    return FlatBuffersSerializer.deserialize_sketch(data)


def deserialize_expanded_from_bytes(data: bytes) -> Dict[str, Any]:
    """Deserialize ExpandedPlan from FlatBuffers bytes"""
    return FlatBuffersSerializer.deserialize_expanded_plan(data)


def deserialize_flow_def_from_bytes(data: bytes) -> Dict[str, Any]:
    """Deserialize FlowDef from FlatBuffers bytes"""
    return FlatBuffersSerializer.deserialize_flow_def(data)
    return FlatBuffersSerializer.deserialize_flow_def(data)


def deserialize_sketch_from_bytes(data: bytes) -> Dict[str, Any]:
    """Deserialize Sketch from FlatBuffers bytes"""
    return FlatBuffersSerializer.deserialize_sketch(data)


def deserialize_expanded_from_bytes(data: bytes) -> Dict[str, Any]:
    """Deserialize ExpandedPlan from FlatBuffers bytes"""
    return FlatBuffersSerializer.deserialize_expanded_plan(data)


def deserialize_flow_def_from_bytes(data: bytes) -> Dict[str, Any]:
    """Deserialize FlowDef from FlatBuffers bytes"""
    return FlatBuffersSerializer.deserialize_flow_def(data)
    return FlatBuffersSerializer.deserialize_flow_def(data)
