"""CI gate: every cross-kernel topic prefix in ``k1/config/bus.yaml``
has at least one matching manifest in the bridge contract registry.

Walls only hold if every cross-kernel topic the bus knows about is
declared in the registry. Day-one this gate fails loudly because no
cross-kernel manifests exist yet; the failure surfaces every leaking
prefix by name. After MS-2.5 close, every prefix has at least a
``status: proposed`` stub manifest and the gate stays GREEN.

Cross-kernel prefix patterns (any one match makes the prefix relevant):

* ``k0.*``
* ``memory.*``
* ``feedback.*``
* ``recall.*``
* ``curiosity.*``
* ``p0[1-9].*``
* ``family.*``
* ``ifl.*``

The bus.yaml file structure today is::

    timing_rules:
      <prefix>: STRICT|RELAXED|BEST_EFFORT
      ...

We extract the keys, classify cross-kernel ones, and require for each
that some manifest in ``bridge/contracts/manifests/`` has a topic
starting with that prefix's first dotted token.
"""

from __future__ import annotations

import re
import sys
from argparse import Namespace
from pathlib import Path

import yaml

from tooling.ci.gates._harness import run_gate
from tooling.contracts.manifest_loader import discover_manifest_files

GATE_NAME = "bus_yaml_aligned_with_registry"

_CROSS_KERNEL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"^k0(?:\..+)?$",
        r"^memory(?:\..+)?$",
        r"^feedback(?:\..+)?$",
        r"^recall(?:\..+)?$",
        r"^curiosity(?:\..+)?$",
        r"^p0[1-9](?:\..+)?$",
        r"^family(?:\..+)?$",
        r"^ifl(?:\..+)?$",
        # K1 namespace MAY contain cross-kernel sub-prefixes such as
        # ``k1.k0.sse``; flag those too.
        r"^k1\.k0(?:\..+)?$",
    )
)


def _repo_root(args: Namespace) -> Path:
    if args.repo_root:
        return Path(args.repo_root).resolve()
    return Path(__file__).resolve().parents[3]


def _is_cross_kernel(prefix: str) -> bool:
    return any(p.match(prefix) for p in _CROSS_KERNEL_PATTERNS)


def _registry_topics(contracts_root: Path) -> set[str]:
    """Topics from manifest YAMLs without booting the loader (gate stays
    independent of meta-schema validation, which is its own gate)."""
    out: set[str] = set()
    for path in discover_manifest_files(contracts_root):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if isinstance(raw, dict) and isinstance(raw.get("topic"), str):
            out.add(raw["topic"])
    return out


def _topic_matches_prefix(topic: str, prefix: str) -> bool:
    """A topic like ``memory.write.v1`` matches prefix ``memory.write`` or
    ``memory``. Match boundary is at the dot, so ``memorize`` does not
    match prefix ``memory``.
    """
    return topic == prefix or topic.startswith(prefix + ".")


def _body(args: Namespace) -> list[str]:
    repo_root = _repo_root(args)
    bus_yaml = repo_root / "k1" / "config" / "bus.yaml"
    if not bus_yaml.exists():
        return [f"missing bus config: {bus_yaml.relative_to(repo_root).as_posix()}"]

    raw = yaml.safe_load(bus_yaml.read_text(encoding="utf-8")) or {}
    timing_rules = raw.get("timing_rules") or {}
    if not isinstance(timing_rules, dict):
        return [f"{bus_yaml.name}: timing_rules must be a mapping"]

    contracts_root = repo_root / "bridge" / "contracts"
    topics = _registry_topics(contracts_root)

    violations: list[str] = []
    for prefix in sorted(timing_rules.keys()):
        if not _is_cross_kernel(prefix):
            continue
        if not any(_topic_matches_prefix(t, prefix) for t in topics):
            violations.append(
                f"{bus_yaml.name}: cross-kernel prefix '{prefix}' has no "
                f"matching manifest in bridge/contracts/manifests/"
            )
    return violations


def main(argv: list[str] | None = None) -> int:
    return run_gate(GATE_NAME, _body, argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
