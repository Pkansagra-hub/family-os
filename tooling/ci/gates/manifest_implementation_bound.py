"""CI gate: every ``status: active`` manifest has a generated implementation.

For each role (k0, k1) we boot a :class:`bridge.runtime.BridgeRuntime` from
the contract registry. For each active manifest in that role's traffic we
assert that a generated artifact exists in ``bridge/_generated/<role>/``
that names the topic.

Day-one (MS-2.5 PR#1) behaviour: ``bridge/_generated/`` may be empty or
have no per-contract files yet. In that mode the gate emits WARN entries
(does not fail). The orchestrator runs this gate with ``--warn-only`` at
day-one. The flag flips to ``--fail-on-violation`` at MS-2.5 close.
"""

from __future__ import annotations

import re
import sys
from argparse import Namespace
from pathlib import Path

from tooling.ci.gates._harness import run_gate

GATE_NAME = "manifest_implementation_bound"

_PER_CONTRACT_SUBDIRS: tuple[str, ...] = ("clients", "handlers", "models", "ports")


def _repo_root(args: Namespace) -> Path:
    if args.repo_root:
        return Path(args.repo_root).resolve()
    return Path(__file__).resolve().parents[3]


def _topic_to_module(topic: str) -> str:
    """``memory.write.v1`` -> ``memory_write_v1``."""
    return re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")


def _generated_root_empty(generated_root: Path, role: str) -> bool:
    """True when no per-contract files exist for ``role`` (day-one mode)."""
    role_root = generated_root / role
    if not role_root.exists():
        return True
    for sub in _PER_CONTRACT_SUBDIRS:
        d = role_root / sub
        if d.exists() and any(p.suffix == ".py" for p in d.iterdir()):
            return False
    return True


def _missing_artifacts_for(
    topic_module: str, role: str, generated_root: Path, *, kind: str
) -> list[str]:
    """For consumer side check handlers; for producer side check clients."""
    expected = generated_root / role / kind / f"{topic_module}.py"
    if not expected.exists():
        return [
            f"missing generated {kind[:-1]} for {role}: "
            f"{expected.relative_to(generated_root.parent.parent).as_posix()}"
        ]
    return []


def _body(args: Namespace) -> list[str]:
    repo_root = _repo_root(args)
    contracts_path = repo_root / "bridge" / "contracts"
    generated_root = repo_root / "bridge" / "_generated"
    if not contracts_path.exists():
        return [f"contracts root not found: {contracts_path.as_posix()}"]

    # Lazy imports so a broken bridge package surfaces in a single test.
    from bridge.runtime import BridgeRuntime, Role
    from bridge.runtime_errors import ManifestValidationError
    from tooling.contracts.manifest_loader import load_manifests

    # Pre-compute the set of response-only topics (targets of another
    # manifest's ``paired_with``). These are emitted as model-only artifacts
    # because the response rides on the request's HTTP response body — there
    # is no independent client/handler/port for them.
    try:
        all_manifests = load_manifests(contracts_path)
    except ManifestValidationError as exc:
        return [f"manifest registry boot failed: {exc}"]
    response_only_topics: set[str] = {
        m.paired_with for m in all_manifests if m.paired_with is not None
    }

    violations: list[str] = []
    for role_value in ("k0", "k1"):
        role = Role(role_value)
        try:
            runtime = BridgeRuntime.from_registry(contracts_path=contracts_path, role=role)
        except ManifestValidationError as exc:
            violations.append(f"{role_value}: registry boot failed: {exc}")
            continue

        # Day-one short-circuit: no per-contract files yet means we WARN
        # for every active topic instead of failing.
        empty = _generated_root_empty(generated_root, role_value)

        for m in runtime.manifests:
            if m.status != "active":
                continue
            if m.topic in response_only_topics:
                # Response-only manifests get model-only emission; no
                # client/handler/port files are expected.
                continue
            module = _topic_to_module(m.topic)
            # Producer side -> client; consumer side -> handler.
            if m.consumer_kernel == role_value:
                missing = _missing_artifacts_for(
                    module, role_value, generated_root, kind="handlers"
                )
            elif m.producer_kernel == role_value:
                missing = _missing_artifacts_for(module, role_value, generated_root, kind="clients")
            else:  # device leg routes through k0 in v1
                continue

            if missing:
                tag = "WARN(empty_generated)" if empty else "FAIL"
                for line in missing:
                    violations.append(f"[{tag}] topic={m.topic} {line}")
    # When in empty-generated mode, emit a leading note so the orchestrator
    # log clearly shows why the gate is in WARN territory.
    return violations


def main(argv: list[str] | None = None) -> int:
    return run_gate(GATE_NAME, _body, argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
