"""E5.M1.6 bulk rename script -- run once to migrate planner test fakes.

Replaces, in 5 planner test files:
  - `class FakeHILCoordinator:` body (full 7-method block ending with
    `return "approve"`) with the IHILPort-shaped FakeHILPort class.
  - `hil_coord=` constructor kwarg with `hil_port=`
  - `_hil_coord` slot/attribute references with `_hil_port`
  - `.hil_coord` property accesses with `.hil_port`
  - drops `HILCoordinatorLike` from imports.

Idempotent: re-running on already-migrated files is a no-op.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    "tests/k1/planner/test_planner_sketch_3_1_1.py",
    "tests/k1/planner/test_planner_sketch_3_1_2.py",
    "tests/k1/planner/test_planner_micro_prompt_5_1_2_3.py",
    "tests/k1/planner/test_planner_micro_validate_5_1_4.py",
    "tests/k1/planner/test_planner_validate_3_3.py",
]

NEW_FAKE_BLOCK = '''class FakeHILCoordinator:
    """E5: minimal IHILPort fake (renamed from FakeHILCoordinator).

    Exposes the unified k1.kernel.ports.hil_port.IHILPort surface.
    Default behaviour: ask_clarification times out; request_approval
    auto-approves. Tests that need other behaviour replace the
    `_clar_response` / `_approval_response` attributes.
    """

    def __init__(self) -> None:
        from k1.hil.types import ApprovalResponse, ClarificationResponse

        self._budget: dict[str, int] = {}
        self.clarification_calls: list = []
        self.approval_calls: list = []
        self.reset_calls: list[str] = []
        self._clar_response = ClarificationResponse(
            hil_request_id="fake",
            answer=None,
            timed_out=True,
            round_budget_exhausted=False,
        )
        self._approval_response = ApprovalResponse(
            hil_request_id="fake",
            decision="approve",
            modifications=None,
            timed_out=False,
        )

    async def ask_clarification(self, req):  # type: ignore[no-untyped-def]
        from k1.hil.types import ClarificationResponse

        self.clarification_calls.append(req)
        used = self._budget.get(req.caller_key, 0)
        if used >= 2:
            return ClarificationResponse(
                hil_request_id="",
                answer=None,
                timed_out=False,
                round_budget_exhausted=True,
            )
        self._budget[req.caller_key] = used + 1
        return self._clar_response

    async def request_approval(self, req):  # type: ignore[no-untyped-def]
        self.approval_calls.append(req)
        return self._approval_response

    async def needs_human(self, req):  # type: ignore[no-untyped-def]
        from k1.hil.types import NeedsHumanResponse

        return NeedsHumanResponse(
            hil_request_id="fake",
            decision="timeout",
            resolution={},
            raw_user_text=None,
            timed_out=True,
        )

    async def request_override(self, req):  # type: ignore[no-untyped-def]
        from k1.hil.types import OverrideResponse

        return OverrideResponse(
            hil_request_id="fake",
            choice="abort",
            selected_alternative=None,
            fallback_action=None,
            timed_out=True,
        )

    async def gate_capability(self, req):  # type: ignore[no-untyped-def]
        from k1.hil.types import GateDecision, GateOutcome

        return GateDecision(
            outcome=GateOutcome.ALLOW,
            hil_request_id=None,
            reason="fake_allow",
            user_approved=None,
            audit_only=False,
        )

    def reset_round_budget(self, caller_key: str) -> None:
        self.reset_calls.append(caller_key)
        self._budget.pop(caller_key, None)

    async def shutdown(self) -> None:
        return None
'''

# Regex to match the OLD FakeHILCoordinator class body (greedy until next
# top-level construct). Anchored on the class header.
OLD_CLASS_RE = re.compile(
    r'class FakeHILCoordinator:.*?(?=\n(?:class |def |@|# ---|$))',
    re.DOTALL,
)


def migrate_file(path: Path) -> tuple[bool, list[str]]:
    text = path.read_text(encoding="utf-8")
    notes: list[str] = []
    original = text

    # 1. Replace FakeHILCoordinator class body.
    if "class FakeHILCoordinator" in text:
        text, n = OLD_CLASS_RE.subn(NEW_FAKE_BLOCK.rstrip() + "\n\n", text, count=1)
        if n:
            notes.append(f"replaced FakeHILCoordinator class ({n})")

    # 2. hil_coord= -> hil_port= in constructor calls.
    text2, n = re.subn(r"\bhil_coord\s*=", "hil_port=", text)
    if n:
        notes.append(f"hil_coord= -> hil_port= ({n})")
    text = text2

    # 3. _hil_coord -> _hil_port (slot strings, attribute access).
    text2, n = re.subn(r"\b_hil_coord\b", "_hil_port", text)
    if n:
        notes.append(f"_hil_coord -> _hil_port ({n})")
    text = text2

    # 4. .hil_coord (property access) -> .hil_port
    text2, n = re.subn(r"\.hil_coord\b", ".hil_port", text)
    if n:
        notes.append(f".hil_coord -> .hil_port ({n})")
    text = text2

    # 5. Drop HILCoordinatorLike from imports
    text2, n = re.subn(r",\s*HILCoordinatorLike", "", text)
    if n:
        notes.append(f"dropped HILCoordinatorLike imports ({n})")
    text = text2
    text2, n = re.subn(r"HILCoordinatorLike,\s*", "", text)
    if n:
        notes.append(f"dropped HILCoordinatorLike imports leading ({n})")
    text = text2
    # Standalone import line
    text2, n = re.subn(r"^from k1\.planner\.types import HILCoordinatorLike\n", "", text, flags=re.M)
    if n:
        notes.append(f"dropped HILCoordinatorLike standalone import ({n})")
    text = text2

    if text != original:
        path.write_text(text, encoding="utf-8")
        return True, notes
    return False, notes


def main() -> None:
    for rel in TARGETS:
        p = ROOT / rel
        if not p.exists():
            print(f"SKIP missing: {rel}")
            continue
        changed, notes = migrate_file(p)
        status = "CHANGED" if changed else "no change"
        print(f"{status}: {rel}")
        for n in notes:
            print(f"  - {n}")


if __name__ == "__main__":
    main()
