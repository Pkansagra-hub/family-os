#!/usr/bin/env python3
"""Generate SHA256 checksums for all K0 contract files."""

import hashlib
from pathlib import Path

import yaml


def sha256_file(path):
    """Calculate SHA256 checksum of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def main():
    contracts_dir = Path("k0/contracts")

    # Collect all contract files
    all_files = []
    for ext in ["*.yaml", "*.json"]:
        all_files.extend(contracts_dir.rglob(ext))

    # Group by category
    categories = {
        "modules": [],
        "pipelines": [],
        "capabilities": [],
        "jsonschema": [],
        "schemas": [],
        "policy": [],
        "table_schemas": [],
        "taxonomies": [],
        "root": [],
    }

    for f in sorted(all_files):
        if f.name == "VERSION":
            continue  # Skip VERSION file itself
        rel_path = f.relative_to(contracts_dir)
        parts = rel_path.parts

        if len(parts) == 1:
            categories["root"].append(f)
        elif parts[0] in categories:
            categories[parts[0]].append(f)
        else:
            categories["root"].append(f)

    # Print YAML output for VERSION file
    print("# K0 Contract Artifacts - Full Registry")
    print("# Canonical version and checksum registry for all frozen contract artifacts")
    print("# To verify: sha256sum -c <(grep sha256 VERSION | awk '{print $2, $1}')")
    print("#")
    print("# Categories:")
    for cat in [
        "root",
        "modules",
        "pipelines",
        "capabilities",
        "policy",
        "schemas",
        "table_schemas",
        "taxonomies",
        "jsonschema",
    ]:
        if categories.get(cat):
            print(f"#   {cat}: {len(categories[cat])} files")
    total = sum(len(files) for files in categories.values())
    print(f"#   TOTAL: {total} files")
    print()

    for cat in [
        "root",
        "modules",
        "pipelines",
        "capabilities",
        "policy",
        "schemas",
        "table_schemas",
        "taxonomies",
        "jsonschema",
    ]:
        files = categories.get(cat, [])
        if not files:
            continue

        # Print category header
        cat_display = cat if cat != "root" else "root-level"
        print(f"# === {cat_display.upper()} ===")

        for f in sorted(files):
            rel_path = str(f.relative_to(contracts_dir)).replace("\\", "/")
            checksum = sha256_file(f)

            # Try to get version from file
            version = "N/A"
            if f.suffix == ".yaml":
                try:
                    with open(f, "r", encoding="utf-8") as fp:
                        data = yaml.safe_load(fp)
                        if isinstance(data, dict) and "version" in data:
                            version = str(data["version"])
                except Exception:
                    pass

            print(f"{rel_path}:")
            print(f'  version: "{version}"')
            print(f"  sha256: {checksum}")

        print()


if __name__ == "__main__":
    main()
