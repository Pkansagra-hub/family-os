"""Bridge contract codegen orchestrator.

Reads every manifest under ``bridge/contracts/manifests/``, validates them
against the meta-schema (via :mod:`tooling.contracts.manifest_loader`),
groups by kernel, and renders four Jinja2 templates per kernel:

* ``port_protocol.py``    — :class:`Protocol` facade per (kernel, direction).
* ``client_stub.py``      — thin publish/request client per kernel.
* ``handler_registry.py`` — ``register_handlers(runtime, impl)`` wiring.
* ``package_index.py``    — list of topics for greppability.

Output goes to ``bridge/_generated/{k0,k1}/``. Invocation:

    python -m tooling.contracts.codegen          # generate
    python -m tooling.contracts.codegen --check  # diff vs vendored, exit 1 on drift

The flags below are committed verbatim because the no-diff CI gate depends
on byte-stable output across machines.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from tooling.contracts._artifact_header import render_header
from tooling.contracts.checksums import manifest_bundle_sha
from tooling.contracts.manifest_loader import Manifest, load_manifests

# datamodel-code-generator invocation flags. These are passed *verbatim* to
# the binary and are part of the substrate contract — changing them changes
# every generated payload model, which the no-diff gate will catch.
DATAMODEL_CODEGEN_FLAGS: tuple[str, ...] = (
    "--input-file-type",
    "jsonschema",
    "--target-python-version",
    "3.13",
    "--output-model-type",
    "pydantic_v2.BaseModel",
    "--use-schema-description",
    "--use-field-description",
    "--use-default",
    "--strict-nullable",
    "--disable-timestamp",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACTS_ROOT = REPO_ROOT / "bridge" / "contracts"
DEFAULT_GENERATED_ROOT = REPO_ROOT / "bridge" / "_generated"
TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass(frozen=True)
class TopicView:
    """Subset of manifest fields the templates use."""

    topic: str
    method_name: str
    transport: str
    schema_path: str
    schema_uri: str
    model_class: str
    client_class: str
    protocol_class: str
    paired_response_method_name: str | None = None
    paired_response_model_class: str | None = None
    obs_kind: str | None = None
    codec: str = "json"
    codecs_allowed: tuple[str, ...] = ("json",)
    codec_negotiation: str = "client_choice_in_allowed"

    @property
    def is_sse(self) -> bool:
        """True for SSE-direction (k0\u2192k1 streaming) contracts.

        SSE topics get a different generated surface: the producer side
        emits an ``<Topic>Emitter`` (publish-style for the K0 outbound
        side) and the consumer side gets an ``<Topic>Subscriber`` with
        an async-context-manager ``subscribe(handler)`` API instead of
        the request/response handler-registry shape.
        """
        return self.transport == "sse"

    @property
    def is_obs(self) -> bool:
        """True for the K1\u2192K0 ``/k0/obs.emit`` (obs/feedback) channel.

        Obs contracts carry an ``obs_kind`` (feedback|metrics|logs) and
        post ``{kind, body}`` shaped payloads to a dedicated endpoint
        that bypasses the signed-envelope path used by ``/k0/command.submit``.
        Producer side emits an ``<Topic>Client`` that delegates to the
        runtime-bound ``_obs_emitter``; consumer side has no codegen
        handler because dispatch happens directly inside K0
        ``ports.observe`` by ``kind``.
        """
        return self.transport == "obs"


def _method_name(topic: str) -> str:
    """``memory.write.v1`` -> ``memory_write_v1``."""
    name = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")
    return name


def _class_name(topic: str, *, suffix: str = "") -> str:
    """``memory.write.v1`` -> ``MemoryWriteV1`` (+ optional suffix)."""
    parts = re.split(r"[^a-z0-9]+", topic.lower())
    pascal = "".join(p[:1].upper() + p[1:] for p in parts if p)
    return pascal + suffix


def _topic_view(m: Manifest, *, all_by_topic: dict[str, Manifest]) -> TopicView:
    base = _class_name(m.topic)
    paired_method: str | None = None
    paired_model: str | None = None
    if m.paired_with is not None:
        partner = all_by_topic.get(m.paired_with)
        if partner is not None:
            paired_method = _method_name(partner.topic)
            paired_model = _class_name(partner.topic)
    delivery = m.raw["delivery"]
    codec = delivery.get("codec", "json")
    codecs_allowed_raw = delivery.get("codecs_allowed") or [codec]
    codec_negotiation = delivery.get("codec_negotiation", "client_choice_in_allowed")
    return TopicView(
        topic=m.topic,
        method_name=_method_name(m.topic),
        transport=delivery["transport"],
        schema_path=m.raw["schema"],
        schema_uri=f"bridge://contracts/{m.raw['schema']}",
        model_class=base,
        client_class=base + "Client",
        protocol_class=base + "Port",
        paired_response_method_name=paired_method,
        paired_response_model_class=paired_model,
        obs_kind=delivery.get("obs_kind"),
        codec=codec,
        codecs_allowed=tuple(codecs_allowed_raw),
        codec_negotiation=codec_negotiation,
    )


def _paired_response_targets(manifests: Iterable[Manifest]) -> set[str]:
    """Topics that appear as another manifest's ``paired_with`` value.

    These are emitted as model-only artifacts: no client/handler/port. The
    request-side client deserialises HTTP responses into the response model
    in-line; the response is never published as an independent envelope.
    """
    return {m.paired_with for m in manifests if m.paired_with is not None}


def _kernel_buckets(manifests: Iterable[Manifest]) -> dict[str, list[TopicView]]:
    """Group active manifests by *consumer* kernel for protocol/handler emission.

    K0/K1 disjoint trees: a topic with consumer.kernel=k0 lands under
    ``_generated/k0/``; consumer.kernel=k1 under ``_generated/k1/``. Device
    consumers route to k0 in v1 (per design doc Q12). Response-only
    manifests (targets of ``paired_with``) are excluded — they get
    model-only emission elsewhere.
    """
    manifests = list(manifests)
    all_by_topic = {m.topic: m for m in manifests}
    response_only = _paired_response_targets(manifests)
    buckets: dict[str, list[TopicView]] = {"k0": [], "k1": []}
    for m in manifests:
        if m.status != "active":
            continue
        if m.topic in response_only:
            continue
        kernel = m.consumer_kernel
        if kernel == "device":
            kernel = "k0"  # device-bound topics are still authored in K0 tree
        if kernel not in buckets:
            buckets[kernel] = []
        buckets[kernel].append(_topic_view(m, all_by_topic=all_by_topic))
    for v in buckets.values():
        v.sort(key=lambda t: t.topic)
    return buckets


def _producer_buckets(manifests: Iterable[Manifest]) -> dict[str, list[TopicView]]:
    """Group active manifests by *producer* kernel.

    Response-only manifests are excluded; see :func:`_kernel_buckets`.
    """
    manifests = list(manifests)
    all_by_topic = {m.topic: m for m in manifests}
    response_only = _paired_response_targets(manifests)
    buckets: dict[str, list[TopicView]] = {"k0": [], "k1": []}
    for m in manifests:
        if m.status != "active":
            continue
        if m.topic in response_only:
            continue
        kernel = m.producer_kernel
        if kernel == "device":
            kernel = "k0"
        if kernel not in buckets:
            buckets[kernel] = []
        buckets[kernel].append(_topic_view(m, all_by_topic=all_by_topic))
    for v in buckets.values():
        v.sort(key=lambda t: t.topic)
    return buckets


def _model_only_buckets(manifests: Iterable[Manifest]) -> dict[str, list[TopicView]]:
    """Per-kernel TopicViews for response-only manifests (model emission only).

    A response model is needed both on the producer side (K0 builds it) and
    the consumer side (K1 deserialises it), so we emit it under both
    kernels referenced by the response manifest.
    """
    manifests = list(manifests)
    all_by_topic = {m.topic: m for m in manifests}
    response_only = _paired_response_targets(manifests)
    buckets: dict[str, list[TopicView]] = {"k0": [], "k1": []}
    for m in manifests:
        if m.status != "active" or m.topic not in response_only:
            continue
        tv = _topic_view(m, all_by_topic=all_by_topic)
        for k in (m.producer_kernel, m.consumer_kernel):
            kk = "k0" if k == "device" else k
            if kk in buckets and tv not in buckets[kk]:
                buckets[kk].append(tv)
    for v in buckets.values():
        v.sort(key=lambda t: t.topic)
    return buckets


def _make_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def render_kernel_files(
    kernel: str,
    topics: list[TopicView],
    *,
    bundle_sha: str,
    env: Environment,
    source_label: str,
) -> dict[str, str]:
    """Render the 4 standard files for a kernel.

    The aggregate ``handler_registry.py`` and ``client_stub.py`` are
    request/response shaped \u2014 they enforce ``impl.<method>`` bindings
    and emit publish methods. SSE topics use a different shape (push
    subscribe / replay-buffer emit) and are excluded from the aggregate
    files; their per-contract subscriber/emitter files are emitted
    separately by :func:`render_per_contract_files`.
    """
    aggregate_topics = [t for t in topics if not t.is_sse and not t.is_obs]
    header = render_header(manifest_bundle_sha=bundle_sha, source_manifest=source_label)
    ctx = {
        "kernel": kernel,
        "direction_label": "Bridge",
        "topics": aggregate_topics,
        "header": header,
    }
    package_index_ctx = {**ctx, "topics": topics}
    return {
        "port_protocol.py": env.get_template("port_protocol.py.jinja").render(**ctx),
        "client_stub.py": env.get_template("client_stub.py.jinja").render(**ctx),
        "handler_registry.py": env.get_template("handler_registry.py.jinja").render(**ctx),
        "package_index.py": env.get_template("package_index.py.jinja").render(**package_index_ctx),
    }


def _resolve_schema_for_codegen(schema_path: Path) -> Path:
    """If the schema is a thin ``$ref`` wrapper, return the referenced file.

    datamodel-code-generator's ``--output`` only accepts a single file when
    the schema has no modular ``$ref``s. Our bridge contracts use a thin
    indirection so the canonical record can live in ``k1/contracts/``;
    we redirect the codegen at the canonical file.
    """
    import json

    raw = json.loads(schema_path.read_text(encoding="utf-8"))
    ref = raw.get("$ref")
    if isinstance(ref, str) and not ref.startswith("#"):
        target = (schema_path.parent / ref).resolve()
        if target.exists():
            return target
    return schema_path


def _render_pydantic_model(*, schema_path: Path, model_class: str, header: str) -> str:
    """Invoke datamodel-code-generator to emit a Pydantic v2 model.

    The body is the contents of the generated file, byte-for-byte
    deterministic with ``--disable-timestamp``. We prefix our standard
    ``header`` so reviewers can identify the source manifest.
    """
    # Lazy import: keeps tooling startup cheap when codegen is not invoked.
    import tempfile

    from datamodel_code_generator import (
        DataModelType,
        InputFileType,
        PythonVersion,
        generate,
    )

    canonical_schema = _resolve_schema_for_codegen(schema_path)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "model.py"
        generate(
            input_=canonical_schema,
            input_file_type=InputFileType.JsonSchema,
            output=out,
            output_model_type=DataModelType.PydanticV2BaseModel,
            target_python_version=PythonVersion.PY_312,
            class_name=model_class,
            use_schema_description=True,
            use_field_description=True,
            use_default_kwarg=True,
            strict_nullable=True,
            disable_timestamp=True,
        )
        body = out.read_text(encoding="utf-8")
    return header + body


def render_per_contract_files(
    kernel: str,
    *,
    producer_topics: list[TopicView],
    consumer_topics: list[TopicView],
    model_only_topics: list[TopicView] | None = None,
    bundle_sha: str,
    env: Environment,
    contracts_root: Path,
) -> dict[Path, str]:
    """Render model + client + handler + port per contract, per role.

    The ``kernel`` arg is the role we are emitting for. ``producer_topics``
    are contracts where this kernel publishes (clients + ports + models);
    ``consumer_topics`` are contracts where this kernel handles (handlers
    + models). The intersection (a topic where the kernel is both producer
    and consumer) gets the union of artifacts. ``model_only_topics`` are
    paired-response contracts: only their Pydantic models are emitted; no
    client/handler/port files are generated for them because they ride on
    the request's HTTP response and are not independently published.
    """
    out: dict[Path, str] = {}
    model_only = list(model_only_topics or [])
    union: dict[str, TopicView] = {tv.topic: tv for tv in producer_topics}
    for tv in consumer_topics:
        union.setdefault(tv.topic, tv)
    for tv in model_only:
        union.setdefault(tv.topic, tv)
    if not union:
        return out

    subdirs: set[str] = set()
    if producer_topics:
        subdirs.update({"models", "clients", "ports"})
    if consumer_topics:
        subdirs.update({"models", "handlers"})
    if model_only:
        subdirs.add("models")

    for sub in sorted(subdirs):
        out[Path(kernel) / sub / "__init__.py"] = (
            f'"""Auto-generated per-contract {sub} for kernel ``{kernel}``."""\n'
        )

    producer_topic_set = {tv.topic for tv in producer_topics}
    consumer_topic_set = {tv.topic for tv in consumer_topics}

    for topic in sorted(union):
        tv = union[topic]
        header = render_header(
            manifest_bundle_sha=bundle_sha,
            source_manifest=f"manifests/{tv.topic}.yaml",
        )
        ctx = {"kernel": kernel, "topic": tv, "header": header}
        # Model is needed whenever the kernel touches the topic.
        schema_full_path = (contracts_root / tv.schema_path).resolve()
        out[Path(kernel) / "models" / f"{tv.method_name}.py"] = _render_pydantic_model(
            schema_path=schema_full_path,
            model_class=tv.model_class,
            header=header,
        )
        if topic in producer_topic_set:
            out[Path(kernel) / "clients" / f"{tv.method_name}.py"] = env.get_template(
                "contract_client.py.jinja"
            ).render(**ctx)
            out[Path(kernel) / "ports" / f"{tv.method_name}.py"] = env.get_template(
                "contract_port.py.jinja"
            ).render(**ctx)
        if topic in consumer_topic_set:
            out[Path(kernel) / "handlers" / f"{tv.method_name}.py"] = env.get_template(
                "contract_handler.py.jinja"
            ).render(**ctx)
    return out


def generate_outputs(
    *,
    contracts_root: Path = DEFAULT_CONTRACTS_ROOT,
) -> dict[Path, str]:
    """Pure function: produce ``{relative_path: rendered_text}``.

    Does not touch the filesystem (apart from the datamodel-codegen scratch
    tempdir for Pydantic model emission). Tests assert determinism against
    this.
    """
    manifests = load_manifests(contracts_root)
    bundle_sha = manifest_bundle_sha(contracts_root)
    env = _make_env()
    consumer_buckets = _kernel_buckets(manifests)
    producer_buckets = _producer_buckets(manifests)
    model_only = _model_only_buckets(manifests)

    files: dict[Path, str] = {}
    files[Path("__init__.py")] = (
        '"""Auto-generated bridge contract artifacts. Do not edit by hand."""\n'
    )
    for kernel in ("k0", "k1"):
        topics = consumer_buckets.get(kernel, [])
        source_label = "<no manifests>" if not topics else f"{kernel}: {len(topics)} topic(s)"
        rendered = render_kernel_files(
            kernel,
            topics,
            bundle_sha=bundle_sha,
            env=env,
            source_label=source_label,
        )
        kernel_init = f'"""Auto-generated artifacts for kernel ``{kernel}``."""\n'
        files[Path(kernel) / "__init__.py"] = kernel_init
        for fname, text in rendered.items():
            files[Path(kernel) / fname] = text

        # Per-contract files (models + clients + handlers + ports).
        per_contract = render_per_contract_files(
            kernel,
            producer_topics=producer_buckets.get(kernel, []),
            consumer_topics=consumer_buckets.get(kernel, []),
            model_only_topics=model_only.get(kernel, []),
            bundle_sha=bundle_sha,
            env=env,
            contracts_root=contracts_root,
        )
        files.update(per_contract)
    return files


def write_outputs(
    files: dict[Path, str],
    *,
    target_root: Path,
) -> None:
    target_root.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        out = target_root / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")


def diff_against_target(
    files: dict[Path, str],
    *,
    target_root: Path,
) -> list[str]:
    """Return a list of unified-diff strings, one per drifted file."""
    diffs: list[str] = []
    expected_paths = {target_root / rel for rel in files}
    # Drift: a generated file would be added or changed.
    for rel, text in sorted(files.items(), key=lambda kv: kv[0].as_posix()):
        out = target_root / rel
        if not out.exists():
            diffs.append(f"--- missing: {rel.as_posix()}")
            continue
        existing = out.read_text(encoding="utf-8")
        if existing != text:
            d = difflib.unified_diff(
                existing.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile=f"vendored/{rel.as_posix()}",
                tofile=f"regenerated/{rel.as_posix()}",
            )
            diffs.append("".join(d))
    # Drift: a vendored file that codegen no longer produces.
    if target_root.exists():
        for path in sorted(target_root.rglob("*.py")):
            if path not in expected_paths:
                diffs.append(f"--- stale: {path.relative_to(target_root).as_posix()}")
    return diffs


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bridge contract codegen")
    parser.add_argument(
        "--check", action="store_true", help="Diff against vendored output; exit 1 on drift."
    )
    parser.add_argument("--contracts-root", type=Path, default=DEFAULT_CONTRACTS_ROOT)
    parser.add_argument("--target-root", type=Path, default=DEFAULT_GENERATED_ROOT)
    args = parser.parse_args(argv)

    files = generate_outputs(contracts_root=args.contracts_root)
    if args.check:
        diffs = diff_against_target(files, target_root=args.target_root)
        if diffs:
            print("codegen drift detected:")
            for d in diffs:
                print(d)
            return 1
        print("codegen: no drift")
        return 0
    write_outputs(files, target_root=args.target_root)
    print(f"codegen: wrote {len(files)} file(s) under {args.target_root}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
