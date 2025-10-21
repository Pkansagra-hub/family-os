"""Template rendering helpers for Pulumi deployment programs."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader

_generated_directory_override: Path | None = None


@lru_cache(maxsize=1)
def _template_environment() -> Environment:
    """Return a cached Jinja2 environment for compose templates."""

    templates_dir = Path(__file__).resolve().parent.parent / "compose" / "templates"
    loader = FileSystemLoader(str(templates_dir))
    return Environment(
        loader=loader, autoescape=False, trim_blocks=True, lstrip_blocks=True
    )


def render_template(template_name: str, context: dict[str, Any]) -> str:
    """Render the named template with the provided context."""

    template = _template_environment().get_template(template_name)
    return template.render(**context)


def generated_directory() -> Path:
    """Return the directory used for storing generated compose bundles."""

    if _generated_directory_override is not None:
        target_dir = Path(_generated_directory_override)
    else:
        target_dir = Path(__file__).resolve().parent.parent / "compose" / "generated"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def set_generated_directory_override(path: Path | None) -> None:
    """Override the generated directory location (used for testing)."""

    global _generated_directory_override
    _generated_directory_override = path


@dataclass(frozen=True, slots=True)
class RenderedArtifact:
    """Metadata describing a rendered template artifact."""

    path: Path
    sha256: str
    size_bytes: int

    def as_output(self) -> Dict[str, Any]:
        """Return a Pulumi-friendly dictionary for stack outputs."""

        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


def _secure_permissions(path: Path) -> None:
    """Attempt to apply restrictive file permissions on supported platforms."""

    if os.name != "posix":  # Windows permission semantics differ; skip adjustments.
        return

    try:
        path.chmod(0o640)
    except PermissionError:
        # Some filesystems may not support chmod adjustments; continue without failing.
        pass


def write_template(
    template_name: str,
    *,
    target_name: str,
    context: dict[str, Any],
    subdir: str | Path | None = None,
) -> RenderedArtifact:
    """Render a template and persist it to the generated directory."""

    contents = render_template(template_name, context)
    encoded = contents.encode("utf-8")

    return _persist_artifact_bytes(target_name=target_name, data=encoded, subdir=subdir)


def write_raw_artifact(
    *, target_name: str, data: bytes, subdir: str | Path | None = None
) -> RenderedArtifact:
    """Persist pre-rendered bytes next to compose artifacts."""

    return _persist_artifact_bytes(target_name=target_name, data=data, subdir=subdir)


def _persist_artifact_bytes(
    *, target_name: str, data: bytes, subdir: str | Path | None
) -> RenderedArtifact:
    base_dir = generated_directory()
    if subdir is not None:
        base_dir = base_dir / Path(subdir)
        base_dir.mkdir(parents=True, exist_ok=True)

    target_path = base_dir / target_name
    target_path.write_bytes(data)
    _secure_permissions(target_path)

    digest = hashlib.sha256(data).hexdigest()

    return RenderedArtifact(
        path=target_path,
        sha256=digest,
        size_bytes=len(data),
    )
