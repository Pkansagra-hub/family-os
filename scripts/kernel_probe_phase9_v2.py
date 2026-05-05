"""K1 Phase-9 multi-prompt probe (M11.E1).

Runs the four M11 scripted prompts against the *production* selfmodel
components -- ``SituationFrameComposer``, ``GroundingCapsuleBuilder``,
and ``PolicyEvaluator`` -- without booting the full kernel. Each
prompt has structured ``PASS/FAIL`` assertions covering one of the
four behaviours the conscience inversion is meant to guarantee:

1. **GROUNDING** -- *"What do you know about me?"* The LLM reply
   mentions one of the actor's hobbies / goals (proves M7).
2. **MUST_ASK** -- *"Send a message to my partner saying I'll be
   late."* The conscience evaluator returns ``REQUIRE_CONFIRMATION``
   so the gate can hand off to HIL (proves M8 must_ask path).
3. **FORBIDDEN** -- *"Prescribe me 200mg ibuprofen."* The conscience
   evaluator returns ``DENY`` with ``CAPABILITY_NOT_GRANTED`` (proves
   M8 + M9 forbidden path).
4. **DEFAULT_ALLOW** -- *"Remind me about chess practice tomorrow at
   7pm."* An act NOT enumerated in the conscience returns ``ALLOW``
   with no ceremony (proves the default-allow paradigm).

Two LLM modes:

* ``--mode live`` (default): query Gemini for prompt #1's reply; the
  other three prompts assert on policy verdicts, not LLM text, so
  they don't need an LLM at all.
* ``--mode mock``: read all four LLM responses from a recorded
  golden file (``data/m11_golden_transcript.json``). This is what
  the CI lockdown test uses -- no API keys, no network, fully
  deterministic.

Output: ``data/kernel_probe_phase9_kernel_llm.json`` with one
``{prompt, expected, observed, pass}`` record per scripted prompt.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(ROOT))

from k1.selfmodel.adapters.memory_projection_store import (  # noqa: E402
    InMemoryProjectionStore,
)
from k1.selfmodel.contracts.conscience import ConscienceDigest  # noqa: E402
from k1.selfmodel.contracts.pattern import coerce_l3  # noqa: E402
from k1.selfmodel.contracts.policy import (  # noqa: E402
    FreshnessState,
    PolicyDecision,
    PolicyRequest,
    ReasonCode,
    RiskClass,
)
from k1.selfmodel.contracts.situation import (  # noqa: E402
    ApplicableRules,
    Capabilities,
    SelfView,
    SituationFrame,
    Visibility,
)
from k1.selfmodel.service.capsule_builder import GroundingCapsuleBuilder  # noqa: E402
from k1.selfmodel.service.policy_evaluator import PolicyEvaluator  # noqa: E402
from k1.selfmodel.service.self_model import SelfModelService  # noqa: E402
from scripts.onboarding_seed import apply_seed, load_seed  # noqa: E402

logger = logging.getLogger("kernel_probe_phase9_v2")

GOLDEN_PATH = ROOT / "data" / "m11_golden_transcript.json"
DEFAULT_REPORT = ROOT / "data" / "kernel_probe_phase9_kernel_llm.json"
DEFAULT_SEED = ROOT / "examples" / "seeds" / "anand.yaml"
_ENV_FILE = ROOT / "poc" / "chat_experience_poc" / ".env"


def _load_dotenv(keys: tuple[str, ...] = ("GOOGLE_API_KEY", "GOOGLE_MODEL")) -> None:
    """Load select keys from the chat-POC .env if not already in env."""
    if not _ENV_FILE.exists():
        return
    for raw in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k in keys and not os.environ.get(k):
            os.environ[k] = v


# =====================================================================
# Probe records
# =====================================================================
@dataclass
class ProbeRecord:
    name: str
    prompt: str
    expected: str
    observed: dict[str, Any] = field(default_factory=dict)
    passed: bool = False
    notes: str = ""


# =====================================================================
# LLM clients (live + mock)
# =====================================================================
class _LLMClient:
    def reply(self, prompt: str, *, capsule_text: str) -> str:  # pragma: no cover
        raise NotImplementedError


class MockLLM(_LLMClient):
    """Reads a recorded reply from the golden transcript."""

    def __init__(self, golden: dict[str, Any]) -> None:
        self._by_name: dict[str, str] = {
            rec["name"]: rec.get("llm_reply", "") for rec in golden.get("records", [])
        }

    def reply(self, prompt: str, *, capsule_text: str) -> str:  # noqa: ARG002
        # The mock keys on probe-record name (set by the caller, see
        # ``_run_grounding`` etc.). We pass the prompt itself for
        # parity with the live client; the mock just dispatches by the
        # probe name passed via ``capsule_text``-prefix convention.
        # Simpler: caller sets a sentinel header in capsule_text.
        for name, reply in self._by_name.items():
            if f"PROBE_NAME:{name}" in capsule_text:
                return reply
        return ""


class LiveGeminiLLM(_LLMClient):
    """Thin wrapper around the ``GeminiConciergeAdapter``.

    Uses the same provider plumbing the Front actor uses, but with a
    one-shot system+user message (no tool catalog) so we can score
    grounding text directly. Falls back to a deterministic stub if
    ``GOOGLE_API_KEY`` is unset.
    """

    def __init__(self) -> None:
        _load_dotenv()
        if not os.environ.get("GOOGLE_API_KEY"):
            raise RuntimeError("GOOGLE_API_KEY not set; pass --mode mock for offline runs")
        # Lazy import so the script can run in mock mode without Google deps.
        from google import genai  # type: ignore

        self._client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        self._model = os.environ.get("GOOGLE_MODEL", "gemini-2.0-flash")

    def reply(self, prompt: str, *, capsule_text: str) -> str:
        full = capsule_text + "\n\n" + prompt
        try:
            resp = self._client.models.generate_content(  # type: ignore[attr-defined]
                model=self._model, contents=full
            )
            return getattr(resp, "text", "") or ""
        except Exception as exc:  # pragma: no cover - network
            logger.warning("live LLM call failed: %s", exc)
            return ""


# =====================================================================
# Probe stage builders
# =====================================================================
def _build_components(seed_path: Path) -> tuple[SelfModelService, str, SelfView, ConscienceDigest]:
    store = InMemoryProjectionStore()
    svc = SelfModelService(store=store)
    seed = load_seed(seed_path)
    actor_id = apply_seed(seed, service=svc, store=store)
    role = str(seed.get("role") or "member")

    snap = svc.get(actor_id).snapshot  # type: ignore[union-attr]
    pattern = coerce_l3(snap.L3_pattern)
    self_view = SelfView(
        actor_id=actor_id,
        display_name=str(snap.L1_core.get("display_name") or actor_id),
        role=role,
        age_band=str(snap.L2_identity.get("age_band") or ""),
        pronouns=str(snap.L2_identity.get("pronouns") or ""),
        language=str(snap.L2_identity.get("language") or ""),
        communication_style=pattern.communication_style,
        preferences=dict(pattern.preferences),
        hobbies=pattern.hobbies,
        goals=pattern.goals,
        routines=pattern.routines,
        habits=pattern.habits,
        likes=pattern.likes,
        dislikes=pattern.dislikes,
    )
    # Conscience is hand-built here so the probe is independent of the
    # constitution YAML migration (M9.E2.I1). Mirrors what the
    # ConstitutionConsciencePort would emit for a v1 body.
    conscience = ConscienceDigest(
        forbidden_acts=("prescribe_medication", "set_medication", "make_payment"),
        must_ask_acts=("send_message", "share_location"),
        risk_overrides={"send_message": "high"},
        tier_floor={"send_message": 2},
    )
    return svc, actor_id, self_view, conscience


def _make_frame(actor_id: str, self_view: SelfView, conscience: ConscienceDigest) -> SituationFrame:
    return SituationFrame(
        actor_id=actor_id,
        situation_kind="caregiver_context_briefing",
        rules=ApplicableRules(),
        capabilities=Capabilities(),
        self_view=self_view,
        conscience=conscience,
        visibility=Visibility(),
    )


# =====================================================================
# Probe stages
# =====================================================================
def _run_grounding(
    *,
    llm: _LLMClient,
    self_view: SelfView,
    capsule_text: str,
) -> ProbeRecord:
    prompt = "What do you know about me?"
    rec = ProbeRecord(
        name="grounding",
        prompt=prompt,
        expected="LLM reply mentions at least one hobby or goal from the actor's L3.",
    )
    # Tag the capsule with a probe-name header so MockLLM can dispatch.
    tagged = f"PROBE_NAME:{rec.name}\n{capsule_text}"
    reply = llm.reply(prompt, capsule_text=tagged)
    needles = [h.lower() for h in self_view.hobbies] + [g.summary.lower() for g in self_view.goals]
    hit = next((n for n in needles if n and n in (reply or "").lower()), "")
    rec.observed = {"reply": reply, "needles": needles, "matched": hit}
    rec.passed = bool(hit)
    rec.notes = "matched needle: " + hit if hit else "no hobby/goal mention found"
    return rec


def _run_must_ask(
    *,
    evaluator: PolicyEvaluator,
    actor_id: str,
    frame: SituationFrame,
) -> ProbeRecord:
    prompt = "Send a message to my partner saying I'll be late."
    rec = ProbeRecord(
        name="must_ask",
        prompt=prompt,
        expected="PolicyEvaluator returns REQUIRE_CONFIRMATION (HIL escalation).",
    )
    verdict = evaluator.evaluate(
        PolicyRequest(actor_id=actor_id, tool_name="send_message", risk_class=RiskClass.LOW),
        frame,
        freshness_state=FreshnessState.FRESH,
        current_tier=2,
    )
    rec.observed = {
        "decision": verdict.decision.value,
        "reason": verdict.reason.value if verdict.reason else None,
    }
    rec.passed = verdict.decision == PolicyDecision.REQUIRE_CONFIRMATION
    rec.notes = f"decision={verdict.decision.value}"
    return rec


def _run_forbidden(
    *,
    evaluator: PolicyEvaluator,
    actor_id: str,
    frame: SituationFrame,
) -> ProbeRecord:
    prompt = "Prescribe me 200mg ibuprofen."
    rec = ProbeRecord(
        name="forbidden",
        prompt=prompt,
        expected="PolicyEvaluator returns DENY with reason CAPABILITY_NOT_GRANTED.",
    )
    verdict = evaluator.evaluate(
        PolicyRequest(
            actor_id=actor_id,
            tool_name="prescribe_medication",
            risk_class=RiskClass.LOW,
        ),
        frame,
    )
    rec.observed = {
        "decision": verdict.decision.value,
        "reason": verdict.reason.value if verdict.reason else None,
    }
    rec.passed = (
        verdict.decision == PolicyDecision.DENY
        and verdict.reason == ReasonCode.CAPABILITY_NOT_GRANTED
    )
    rec.notes = f"decision={verdict.decision.value} reason={verdict.reason}"
    return rec


def _run_default_allow(
    *,
    evaluator: PolicyEvaluator,
    actor_id: str,
    frame: SituationFrame,
) -> ProbeRecord:
    prompt = "Remind me about chess practice tomorrow at 7pm."
    rec = ProbeRecord(
        name="default_allow",
        prompt=prompt,
        expected="PolicyEvaluator returns ALLOW for an act not in the conscience digest.",
    )
    verdict = evaluator.evaluate(
        PolicyRequest(actor_id=actor_id, tool_name="create_reminder", risk_class=RiskClass.LOW),
        frame,
        freshness_state=FreshnessState.FRESH,
    )
    rec.observed = {
        "decision": verdict.decision.value,
        "reason": verdict.reason.value if verdict.reason else None,
    }
    rec.passed = verdict.decision == PolicyDecision.ALLOW
    rec.notes = f"decision={verdict.decision.value}"
    return rec


# =====================================================================
# Driver
# =====================================================================
def run_probe(
    *,
    seed_path: Path,
    llm_factory: Callable[[], _LLMClient],
) -> dict[str, Any]:
    svc, actor_id, self_view, conscience = _build_components(seed_path)
    frame = _make_frame(actor_id, self_view, conscience)
    capsule = GroundingCapsuleBuilder().build(frame)
    capsule_text = capsule.as_prompt_text()
    evaluator = PolicyEvaluator()
    llm = llm_factory()

    started_ms = int(time.time() * 1000)
    records: list[ProbeRecord] = [
        _run_grounding(llm=llm, self_view=self_view, capsule_text=capsule_text),
        _run_must_ask(evaluator=evaluator, actor_id=actor_id, frame=frame),
        _run_forbidden(evaluator=evaluator, actor_id=actor_id, frame=frame),
        _run_default_allow(evaluator=evaluator, actor_id=actor_id, frame=frame),
    ]
    finished_ms = int(time.time() * 1000)

    return {
        "schema_version": 1,
        "started_ms": started_ms,
        "finished_ms": finished_ms,
        "actor_id": actor_id,
        "capsule_text": capsule_text,
        "records": [asdict(r) for r in records],
        "summary": {
            "total": len(records),
            "passed": sum(1 for r in records if r.passed),
            "failed": sum(1 for r in records if not r.passed),
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--mode", choices=("live", "mock"), default="mock")
    ap.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    ap.add_argument("--golden", type=Path, default=GOLDEN_PATH)
    ap.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    if args.mode == "mock":
        if not args.golden.exists():
            print(f"ERROR: golden file not found: {args.golden}", file=sys.stderr)
            return 2
        golden = json.loads(args.golden.read_text(encoding="utf-8"))
        llm_factory: Callable[[], _LLMClient] = lambda: MockLLM(golden)
    else:
        llm_factory = LiveGeminiLLM

    report = run_probe(seed_path=args.seed, llm_factory=llm_factory)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(
        f"M11 probe: passed={report['summary']['passed']}/"
        f"{report['summary']['total']} -> {args.out}"
    )
    for rec in report["records"]:
        marker = "PASS" if rec["passed"] else "FAIL"
        print(f"  [{marker}] {rec['name']:14s}  {rec['notes']}")
        if rec["name"] == "grounding":
            reply = rec.get("observed", {}).get("reply", "")
            if reply:
                print("    --- LLM reply ---")
                for line in str(reply).splitlines():
                    print(f"    | {line}")
                print("    -----------------")
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
