"""scripts/generate_smith_json.py — Dump SMITH_PROFILE to data/families/smith.json.

Run: python scripts/generate_smith_json.py
"""

from __future__ import annotations

import json
from pathlib import Path

from verticals.family.smith import SMITH_PROFILE


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "data" / "families" / "smith.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(SMITH_PROFILE.to_dict(), indent=2), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
