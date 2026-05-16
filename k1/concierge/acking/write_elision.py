"""Pure write-elision decisions for low-signal backchannel turns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class WriteElisionDecision:
    write_safety_band: bool = True
    write_temporal: bool = True
    write_control: bool = False
    write_intents: bool = False
    write_beliefs: bool = False
    write_affect: bool = False
    elided_sections: set[str] = field(default_factory=set)
    reason: str = ""


class WriteElisionGate:
    """Stateless gate for optional Session State writes."""

    _LOW_SIGNAL_INTENTS = frozenset({"backchannel", "filler"})

    def evaluate(self, phase1_output: dict[str, Any]) -> WriteElisionDecision:
        intent_class = str(phase1_output.get("intent_class") or "").lower()
        safety_band = str(phase1_output.get("safety_band") or "GREEN").upper()
        prior_safety_band = str(phase1_output.get("prior_safety_band") or safety_band).upper()
        control_signals = phase1_output.get("control_signals") or []
        intents = phase1_output.get("intents") or []
        beliefs = phase1_output.get("beliefs") or []
        affect_label = str(phase1_output.get("affect_label") or "").lower()
        affect_detected = bool(phase1_output.get("affect_detected", False))

        low_signal = intent_class in self._LOW_SIGNAL_INTENTS
        write_control = safety_band != prior_safety_band or not low_signal or bool(control_signals)
        write_intents = not low_signal and bool(intents)
        write_beliefs = bool(beliefs)
        write_affect = affect_detected or bool(affect_label and affect_label != "neutral")

        elided: set[str] = set()
        if not write_control:
            elided.add("control")
        if not write_intents:
            elided.add("intents")
        if not write_beliefs:
            elided.add("beliefs")
        if not write_affect:
            elided.add("affect")

        reason = "low_signal_backchannel" if low_signal else "no_optional_payload"
        return WriteElisionDecision(
            write_safety_band=True,
            write_temporal=True,
            write_control=write_control,
            write_intents=write_intents,
            write_beliefs=write_beliefs,
            write_affect=write_affect,
            elided_sections=elided,
            reason=reason,
        )
