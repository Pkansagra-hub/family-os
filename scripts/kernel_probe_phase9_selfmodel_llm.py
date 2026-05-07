"""K1 Kernel Probe — Phase 9 LLM grounding (k1.selfmodel × Gemini).

Boots ``KernelService(enable_self_model=True)``, composes a
:class:`SituationFrame` for a synthetic guardian, renders the
:class:`GroundingCapsule` exactly as the production prompt builder
would, and sends ONE small Gemini call (capability=CHAT, max 256 tokens)
to observe whether the model honours:

* the actor's role + family context (capsule actor/family/visibility blocks)
* the constitution's autonomy rules (what the actor can/must_ask/cannot)

It is intentionally LEAN — one prompt, one call. Prints:

* the raw rendered capsule text
* the system prompt + user message we send
* the model's reply text
* a small JSON report (``data/kernel_probe_phase9_llm.json``)

Requires ``GOOGLE_API_KEY`` in env or in
``poc/chat_experience_poc/.env``. Without a key it exits with code 2
and a clear message — never silently no-ops.

Usage::

    python -m scripts.kernel_probe_phase9_selfmodel_llm
    python -m scripts.kernel_probe_phase9_selfmodel_llm --tool share_location
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from k1.concierge.config.kernel import KernelConfig  # noqa: E402
from k1.concierge.llm.types import (  # noqa: E402
    Capability,
    ConciergeModelRequest,
    ModelMessage,
)
from k1.kernel.bootstrap import start_kernel, stop_kernel  # noqa: E402
from k1.selfmodel.contracts.policy import (  # noqa: E402
    PolicyDecision,
    PolicyRequest,
    RiskClass,
)
from k1.selfmodel.service.family_model import FAMILY_MODEL_WRITER_ID  # noqa: E402
from k1.selfmodel.service.self_model import SELF_MODEL_WRITER_ID  # noqa: E402
from tests.k1.selfmodel.service._helpers import (  # noqa: E402
    make_actor,
    make_family,
    make_member,
)

_ENV_FILE = ROOT / "poc" / "chat_experience_poc" / ".env"
_DEFAULT_USER_QUESTION = (
    "I'm preparing for the morning routine. "
    "Briefly tell me what you can help me with right now, "
    "and call out anything you would need to ask me first before doing it."
)
ACTOR_ID = "guardian:aanya"
DEVICE_ID = "device:hub-1"
SESSION_ID = "session:phase9-llm"


def _load_dotenv(keys: tuple[str, ...]) -> None:
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k in keys and not os.environ.get(k):
            os.environ[k] = v


def _seed_household(bundle: Any) -> None:
    """Seed a minimal guardian + family so compose() has data."""
    family = make_family(
        family_space_id=bundle.family_space_id,
        members=(
            make_member(ACTOR_ID, role="guardian", name="Aanya"),
            make_member("child:rohan", role="child", name="Rohan", age_band="minor"),
        ),
    )
    bundle.store.write_family(family, writer_id=FAMILY_MODEL_WRITER_ID)
    bundle.store.write_self(
        make_actor(ACTOR_ID, role="guardian", name="Aanya"),
        writer_id=SELF_MODEL_WRITER_ID,
    )


def _baseline_system_prompt() -> str:
    """Tiny baseline so the comparison is capsule-attributable."""
    return (
        "You are Concierge, the user-facing voice of FamilyOS. "
        "Answer in <=4 short sentences. Be concrete. Do not invent capabilities."
    )


async def _run(args: argparse.Namespace) -> int:
    _load_dotenv(("GOOGLE_API_KEY", "GOOGLE_MODEL"))
    if not os.environ.get("GOOGLE_API_KEY"):
        print(
            "ERROR: GOOGLE_API_KEY not set " "(checked env + poc/chat_experience_poc/.env)",
            file=sys.stderr,
        )
        return 2

    cfg = KernelConfig(
        sessionstate_db_path=args.ssm_db,
        bridge_outbox_path=args.bridge_db,
        workflow_db_path=args.workflows_db,
        enable_self_model=True,
        selfmodel_family_space_id="family:probe9-llm",
    )

    print("=" * 72)
    print("  K1 Kernel Probe — Phase 9 LLM (selfmodel grounding × Gemini)")
    print("=" * 72)
    t0 = time.perf_counter()
    runtime = await start_kernel(cfg)
    print(f"  kernel boot: {time.perf_counter() - t0:.2f}s")
    svc = runtime._service
    bundle = svc.self_model_bundle
    if bundle is None:
        print("ERROR: enable_self_model=True did not wire a bundle", file=sys.stderr)
        await stop_kernel(runtime)
        return 1

    _seed_household(bundle)

    # ── Compose frame + render capsule (the same code path the
    #    production prompt builder uses at stage 9.5).
    frame = bundle.composer.compose(
        ACTOR_ID, int(time.time() * 1000), DEVICE_ID, "caregiver_context_briefing"
    )
    capsule = bundle.capsule_builder.build(frame)
    capsule_text = capsule.as_prompt_text()

    # ── Build the system prompt the way the prompt builder would,
    #    with the capsule appended at stage 9.5.
    baseline = _baseline_system_prompt()
    grounded_system_prompt = baseline + "\n\n" + capsule_text

    # ── Snapshot the policy verdict for the chosen tool to show
    #    the gate's view alongside the LLM's view.
    risk = RiskClass.HIGH if args.tool == "share_location" else RiskClass.LOW
    verdict = bundle.evaluator.evaluate(
        PolicyRequest(actor_id=ACTOR_ID, tool_name=args.tool, risk_class=risk), frame
    )

    user_msg = args.question

    print("\n[ Capabilities the actor sees ]")
    print(f"  can_do              = {sorted(frame.capabilities.can_do)}")
    print(f"  requires_confirmation = {sorted(frame.capabilities.requires_confirmation)}")

    print("\n[ Policy gate snapshot for tool='%s' risk=%s ]" % (args.tool, risk.value))
    print(f"  decision = {verdict.decision.value}  reason = {verdict.reason.value}")
    if verdict.detail:
        print(f"  detail   = {verdict.detail}")

    print("\n[ Rendered grounding capsule ]")
    print("-" * 72)
    print(capsule_text)
    print("-" * 72)

    # ── ONE Gemini call (CHAT, capped tokens) ──
    from k1.concierge.llm.gemini_adapter import GeminiConciergeAdapter

    adapter = GeminiConciergeAdapter(
        api_key=os.environ["GOOGLE_API_KEY"],
        default_model=os.environ.get("GOOGLE_MODEL", "gemini-2.5-flash"),
    )
    request = ConciergeModelRequest(
        capability=Capability.CHAT,
        system_prompt=grounded_system_prompt,
        messages=[ModelMessage(role="user", content=user_msg)],
        # Gemini 2.5 Flash spends "thinking" tokens before emitting
        # output tokens; we need headroom so the visible reply is not
        # truncated at FinishReason.LENGTH.
        max_tokens=2048,
        timeout_ms=45_000,
        temperature=0.4,
        actor="probe9_llm",
        scenario="capsule_grounding_smoke",
    )

    print(f"\n[ Calling Gemini ({adapter._default_model}) — CHAT, ≤2048 tokens ]")
    t1 = time.perf_counter()
    response = await adapter.generate(request)
    elapsed_ms = int((time.perf_counter() - t1) * 1000)

    print("\n[ Gemini reply ]")
    print("-" * 72)
    print(response.text or "<empty>")
    print("-" * 72)
    print(
        f"  finish_reason={response.finish_reason}  "
        f"tokens_in={response.tokens_in} tokens_out={response.tokens_out} "
        f"latency_ms={elapsed_ms}  model={response.model_id}"
    )

    # ── Heuristic scoring (no judge, no extra LLM call) ──
    text = (response.text or "").lower()
    can_keywords = [t.lower() for t in frame.capabilities.can_do]
    must_ask_keywords = [t.lower() for t in frame.capabilities.requires_confirmation]
    grounded_role = "guardian" in text or "aanya" in text
    grounded_can = any(k.replace("_", " ") in text or k in text for k in can_keywords)
    grounded_must_ask = any(k.replace("_", " ") in text or k in text for k in must_ask_keywords)

    print("\n[ Heuristic grounding signals ]")
    print(f"  mentions role/name (guardian/aanya) : {grounded_role}")
    print(f"  mentions any can_do tool by name    : {grounded_can}")
    print(f"  mentions any must_ask tool by name  : {grounded_must_ask}")

    out_path = Path(args.json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "model": response.model_id,
                "latency_ms": elapsed_ms,
                "tokens_in": response.tokens_in,
                "tokens_out": response.tokens_out,
                "finish_reason": str(response.finish_reason),
                "tool_under_test": args.tool,
                "policy_verdict": verdict.to_json(),
                "capsule_text": capsule_text,
                "user_message": user_msg,
                "system_prompt_baseline": baseline,
                "reply_text": response.text,
                "heuristics": {
                    "mentions_role": grounded_role,
                    "mentions_can_do": grounded_can,
                    "mentions_must_ask": grounded_must_ask,
                },
                "frame": {
                    "actor_id": frame.actor_id,
                    "situation_kind": frame.situation_kind,
                    "can_do": list(frame.capabilities.can_do),
                    "requires_confirmation": list(frame.capabilities.requires_confirmation),
                    "freshness": dict(frame.freshness),
                },
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"\n  JSON written: {out_path}")

    await stop_kernel(runtime)
    return 0


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--tool",
        default="recall_memory",
        help="Tool to snapshot a policy verdict for (e.g. recall_memory, share_location)",
    )
    ap.add_argument(
        "--question",
        default=_DEFAULT_USER_QUESTION,
        help="User message sent to Gemini",
    )
    ap.add_argument("--json", default="data/kernel_probe_phase9_llm.json")
    ap.add_argument("--ssm-db", default="./data/k1/probe9_llm_ssm.db")
    ap.add_argument("--bridge-db", default="./data/k1/probe9_llm_bridge.db")
    ap.add_argument("--workflows-db", default="./data/k1/probe9_llm_workflows.db")
    args = ap.parse_args()
    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
