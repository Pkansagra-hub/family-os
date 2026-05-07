"""Bridge contract tooling.

Build-time code only. Never import from a runtime module under
``bridge/``, ``k0/``, or ``k1/``. The CI gate ``bridge_not_imported``
enforces that direction.

Modules:

* :mod:`tooling.contracts.manifest_loader` — discover + validate manifest
  YAMLs against ``bridge/contracts/_meta/manifest.schema.json``.
* :mod:`tooling.contracts.checksums` — content checksums + a manifest
  bundle SHA used to stamp generated artifacts.
* :mod:`tooling.contracts.compatibility` — SemVer + breaking/compatible/
  patch classification per ADR-0013.
* :mod:`tooling.contracts.codegen` — orchestrator. CLI entrypoint
  ``python -m tooling.contracts.codegen [--check]``.
"""
