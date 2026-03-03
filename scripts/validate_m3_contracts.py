"""Validate all M3 Part A contract YAML files (Epics 3.1-3.8)."""

import sys

import yaml

files = {
    "Epic 3.1": "k0/contracts/schemas/st_hipp_events_v2.columns.yaml",
    "Epic 3.2": "k0/contracts/modules/affect.analyze.v2.yaml",
    "Epic 3.3": "k0/contracts/modules/social.family_graph_resolve.v2.yaml",
    "Epic 3.4": "k0/contracts/modules/salience.score.v2.yaml",
    "Epic 3.5": "k0/contracts/modules/context.temporal_profile.v2.yaml",
    "Epic 3.6": "k0/contracts/modules/builders.hipp_events_row.v2.yaml",
    "Epic 3.7": "k0/contracts/pipelines/p02_write.v2.yaml",
    "Epic 3.8": "k0/contracts/modules/hippocampus.semantic_project.v2.yaml",
}

all_ok = True
for epic, path in files.items():
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        version = data.get("version", "?")
        mid = data.get("module_id", data.get("pipeline_id", data.get("schema", "?")))
        mode = data.get("mode", data.get("role", "-"))
        print(f"  OK  {epic:10s}  {mid:40s}  v{version}  mode={mode}")
    except Exception as e:
        print(f"  FAIL {epic}: {e}")
        all_ok = False

print()
if all_ok:
    print(f"All {len(files)} Part A contracts validated successfully.")
else:
    print("ERRORS DETECTED.")
    sys.exit(1)
    sys.exit(1)
