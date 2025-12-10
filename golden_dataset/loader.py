"""
Golden Dataset Loader.

Utilities for loading and filtering the golden dataset.

Issue: 1.2.1 - Golden Dataset for Module Accuracy
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from .models import GoldenDataset, GoldenMemory

logger = logging.getLogger(__name__)

# Path to the golden dataset directory
GOLDEN_DATASET_DIR = Path(__file__).parent
DATASET_FILE = GOLDEN_DATASET_DIR / "dataset.yaml"
DATASET_JSON_FILE = GOLDEN_DATASET_DIR / "dataset.json"


def load_golden_dataset(
    path: Path | None = None,
    validate: bool = True,
) -> "GoldenDataset":
    """
    Load the golden dataset from file.

    Args:
        path: Optional path to dataset file. Defaults to built-in dataset.
        validate: Whether to validate all entries with Pydantic models.

    Returns:
        GoldenDataset containing all annotated memories.

    Raises:
        FileNotFoundError: If dataset file doesn't exist.
        ValidationError: If validate=True and data is malformed.
    """
    from .models import GoldenDataset

    if path is None:
        # Try JSON first (faster), then YAML
        if DATASET_JSON_FILE.exists():
            path = DATASET_JSON_FILE
        elif DATASET_FILE.exists():
            path = DATASET_FILE
        else:
            raise FileNotFoundError(
                f"No dataset file found. Expected at {DATASET_FILE} or {DATASET_JSON_FILE}"
            )

    logger.info(f"Loading golden dataset from {path}")

    with open(path, encoding="utf-8") as f:
        if path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(f)
        else:
            data = json.load(f)

    if validate:
        dataset = GoldenDataset.model_validate(data)
    else:
        dataset = GoldenDataset(**data)

    logger.info(f"Loaded {len(dataset.memories)} memories from golden dataset v{dataset.version}")
    return dataset


def get_golden_memories_by_tag(
    tag: str,
    dataset: "GoldenDataset | None" = None,
) -> list["GoldenMemory"]:
    """
    Get all memories with a specific tag.

    Args:
        tag: Tag to filter by (e.g., 'birthday', 'travel').
        dataset: Optional pre-loaded dataset. Loads default if not provided.

    Returns:
        List of GoldenMemory objects matching the tag.
    """
    if dataset is None:
        dataset = load_golden_dataset()
    return dataset.get_by_tag(tag)


def save_golden_dataset(
    dataset: "GoldenDataset",
    path: Path | None = None,
    format: str = "yaml",
) -> None:
    """
    Save the golden dataset to file.

    Args:
        dataset: Dataset to save.
        path: Output path. Defaults to built-in location.
        format: Output format ('yaml' or 'json').
    """
    if path is None:
        path = DATASET_FILE if format == "yaml" else DATASET_JSON_FILE

    logger.info(f"Saving golden dataset to {path}")

    data = dataset.model_dump(mode="json")

    with open(path, "w", encoding="utf-8") as f:
        if format == "yaml":
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        else:
            json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(dataset.memories)} memories to {path}")
