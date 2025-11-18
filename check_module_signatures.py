#!/usr/bin/env python3
"""Check which modules have Phase 2 vs Legacy signatures."""

import importlib
import inspect

modules = [
    ("hippocampus.semantic_project", "M02"),
    ("affect.analyze", "M04"),
    ("space.resolve_visibility", "M05"),
    ("social.family_graph_resolve", "M07"),
    ("context.temporal_profile", "M08"),
    ("context.device_profile", "M09"),
    ("context.ingress_classify", "M10"),
    ("context.retention_lookup", "M11"),
    ("context.geo_metadata", "M12"),
    ("salience.score", "M06"),
    ("context.spatial_minimal", "M15"),
    ("builders.hipp_events_row", "M13"),
    ("builders.embedding_queue_write", "M14"),
    ("core.hipp_events_writer", "M16"),
    ("core.event_emitter", "M17"),
]

print("=" * 80)
print("MODULE SIGNATURE ANALYSIS")
print("=" * 80)
print()

phase2_count = 0
legacy_count = 0
needs_migration = []

for mod_path, mid in modules:
    try:
        mod = importlib.import_module(f"k0.modules.{mod_path}")
        sig = inspect.signature(mod.run)
        params = list(sig.parameters.keys())

        has_message = "message" in params
        has_context = "context" in params
        has_envelope = "envelope" in params and len(params) == 1

        if has_message and has_context:
            status = "✅ Phase2"
            phase2_count += 1
        elif has_envelope:
            status = "❌ Legacy"
            legacy_count += 1
            needs_migration.append((mid, mod_path))
        else:
            status = "⚠️ Unknown"
            needs_migration.append((mid, mod_path))

        print(f"{mid:4} {status:12} {mod_path}")
        print(f"     Signature: {sig}")
        print()

    except Exception as e:
        print(f"{mid:4} ❌ ERROR    {mod_path}")
        print(f"     Error: {e}")
        print()

print("=" * 80)
print(f"Phase 2 Modules: {phase2_count}")
print(f"Legacy Modules:  {legacy_count}")
print(f"Total:           {len(modules)}")
print("=" * 80)

if needs_migration:
    print()
    print("MODULES REQUIRING MIGRATION:")
    print("-" * 80)
    for mid, mod_path in needs_migration:
        print(f"  {mid}: {mod_path}")
