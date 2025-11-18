#!/usr/bin/env python3
"""Validate P02 pipeline YAML against actual module implementations."""

import os

from k0.runtime.schemas import PipelineSpec

# Load pipeline spec
spec = PipelineSpec.load("k0/contracts/pipelines/p02_write.v1.yaml")

# Map module IDs to expected file paths
module_map = {
    "hippocampus.pattern_separate:v1": "k0/modules/hippocampus/pattern_separate.py",
    "hippocampus.semantic_project:v1": "k0/modules/hippocampus/semantic_project.py",
    "affect.analyze:v1": "k0/modules/affect/analyze.py",
    "space.resolve_visibility:v1": "k0/modules/space/resolve_visibility.py",
    "social.family_graph_resolve:v1": "k0/modules/social/family_graph_resolve.py",
    "context.temporal_profile:v1": "k0/modules/context/temporal_profile.py",
    "context.device_profile:v1": "k0/modules/context/device_profile.py",
    "context.ingress_classify:v1": "k0/modules/context/ingress_classify.py",
    "context.geo_metadata:v1": "k0/modules/context/geo_metadata.py",
    "context.spatial_minimal:v1": "k0/modules/context/spatial_minimal.py",
    "context.retention_lookup:v1": "k0/modules/context/retention_lookup.py",
    "salience.score:v1": "k0/modules/salience/score.py",
    "builders.hipp_events_row:v1": "k0/modules/builders/hipp_events_row.py",
    "builders.embedding_queue_write:v1": "k0/modules/builders/embedding_queue_write.py",
    "core.hipp_events_writer:v1": "k0/modules/core/hipp_events_writer.py",
    "core.event_emitter:v1": "k0/modules/core/event_emitter.py",
}

print("=" * 80)
print("P02 PIPELINE MODULE VALIDATION")
print("=" * 80)
print()
print(f"Pipeline: {spec.pipeline_id} {spec.version}")
print(f"Entry Topic: {spec.entry_topic}")
print(f"Exit Topic: {spec.exit_topic}")
print(f"Total Stages: {len(spec.dag)}")
print()
print("Stage Validation:")
print("-" * 80)

all_valid = True
missing_modules = []

for i, stage in enumerate(spec.dag, 1):
    module_id = stage.module
    expected_path = module_map.get(module_id, "UNKNOWN")
    exists = os.path.exists(expected_path) if expected_path != "UNKNOWN" else False
    status = "✅" if exists else "❌"

    if not exists:
        all_valid = False
        missing_modules.append((stage.id, module_id, expected_path))

    deps = ", ".join(stage.after) if stage.after else "[entry]"
    print(f"{i:2}. {status} {stage.id:<35} {module_id}")
    print(f"    Dependencies: {deps}")

print()
print("=" * 80)

if all_valid:
    print("✅ VALIDATION PASSED: All 16 modules exist")
else:
    print(f"❌ VALIDATION FAILED: {len(missing_modules)} missing modules")
    print()
    print("Missing modules:")
    for stage_id, module_id, path in missing_modules:
        print(f"  - {stage_id}: {module_id}")
        print(f"    Expected: {path}")

print("=" * 80)
print("=" * 80)
