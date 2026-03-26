"""
JSONL data loader.
Reads all .jsonl files from a subdirectory under sample_data/ and returns records.
"""
import json
from pathlib import Path
from typing import Iterator

from .config import DATA_DIR


def load_entity(entity_name: str) -> list[dict]:
    """Load all records for an entity type from its JSONL files."""
    entity_dir = DATA_DIR / entity_name
    if not entity_dir.exists():
        raise FileNotFoundError(f"Entity directory not found: {entity_dir}")

    records = []
    for jsonl_file in sorted(entity_dir.rglob("*.jsonl")):
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def load_all_entities() -> dict[str, list[dict]]:
    """Load every entity type found under sample_data/."""
    entities = {}
    for subdir in sorted(DATA_DIR.iterdir()):
        if subdir.is_dir() and not subdir.name.startswith("_"):
            records = load_entity(subdir.name)
            if records:
                entities[subdir.name] = records
    return entities
