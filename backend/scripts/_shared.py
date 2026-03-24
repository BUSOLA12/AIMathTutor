"""Shared utilities for diagnosis training and evaluation scripts."""
import json
from pathlib import Path


def resolve_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[1] / path


def load_records(path: Path) -> list[dict]:
    records: list[dict] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def topic_split(records: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    unique_topics = sorted({record["topic_key"] for record in records})
    holdout_count = max(1, round(len(unique_topics) * 0.2))
    holdout_topics = unique_topics[-holdout_count:]
    train = [record for record in records if record["topic_key"] not in holdout_topics]
    valid = [record for record in records if record["topic_key"] in holdout_topics]
    return train, valid, holdout_topics
