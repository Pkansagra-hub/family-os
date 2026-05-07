"""Shared helpers for kernel probe scripts (phase 1/2/3+)."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any


def _supports_color() -> bool:
    return sys.stdout.isatty()


_C_RED = "\x1b[31m"
_C_YEL = "\x1b[33m"
_C_GRN = "\x1b[32m"
_C_DIM = "\x1b[2m"
_C_BOLD = "\x1b[1m"
_C_RST = "\x1b[0m"


def _c(s: str, code: str) -> str:
    return f"{code}{s}{_C_RST}" if _supports_color() else s


@dataclass
class Probe:
    layer: str
    name: str
    status: str  # OK | WARN | FAIL | INFO
    value: Any = None
    note: str = ""

    def render(self) -> str:
        glyph = {
            "OK": _c("✓", _C_GRN),
            "WARN": _c("⚠", _C_YEL),
            "FAIL": _c("✗", _C_RED),
            "INFO": _c("·", _C_DIM),
        }.get(self.status, "?")
        val = "" if self.value is None else f" = {self.value!r}"
        note = f"  {_c(self.note, _C_DIM)}" if self.note else ""
        return f"  {glyph}  {self.name:<48s}{val}{note}"


@dataclass
class ProbeReport:
    probes: list[Probe] = field(default_factory=list)

    def add(self, layer: str, name: str, status: str, value: Any = None, note: str = "") -> None:
        self.probes.append(Probe(layer, name, status, value, note))

    def by_layer(self) -> dict[str, list[Probe]]:
        out: dict[str, list[Probe]] = {}
        for p in self.probes:
            out.setdefault(p.layer, []).append(p)
        return out

    def counts(self) -> dict[str, int]:
        c = {"OK": 0, "WARN": 0, "FAIL": 0, "INFO": 0}
        for p in self.probes:
            c[p.status] = c.get(p.status, 0) + 1
        return c

    def render(self, title: str) -> None:
        print("=" * 72)
        print(_c(f"  {title}", _C_BOLD))
        print("=" * 72)
        for layer, probes in self.by_layer().items():
            print(_c(f"\n[ {layer} ]", _C_BOLD))
            for p in probes:
                print(p.render())
        c = self.counts()
        print(_c("\n" + "=" * 72, _C_DIM))
        print(
            _c("  Summary: ", _C_BOLD)
            + _c(f"OK {c['OK']}", _C_GRN)
            + "  "
            + _c(f"WARN {c['WARN']}", _C_YEL)
            + "  "
            + _c(f"FAIL {c['FAIL']}", _C_RED)
            + f"  INFO {c['INFO']}  (total {len(self.probes)})"
        )

    def exit_code(self) -> int:
        return 0 if self.counts()["FAIL"] == 0 else 1


def _attr(obj: Any, attr: str, default: Any = None) -> Any:
    return getattr(obj, attr, default)
