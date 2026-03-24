import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import AsyncSessionLocal
from app.modules.diagnosis.dataset import build_training_record
from app.modules.diagnosis.store import export_diagnosis_dataset_rows


async def _export(output_path: Path, subject_area: str | None) -> int:
    async with AsyncSessionLocal() as session:
        rows = await export_diagnosis_dataset_rows(session, subject_area=subject_area)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        for row in rows:
            record = row if "combined_text" in row and "record_hash" in row else build_training_record(row)
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    return len(rows)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Export diagnosis runs as JSONL training records.")
    parser.add_argument(
        "--output",
        default="data/training/diagnosis_runs.jsonl",
        help="JSONL path relative to the backend root.",
    )
    parser.add_argument(
        "--subject-area",
        default=None,
        help="Optional subject area filter.",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path(__file__).resolve().parents[1] / output_path

    count = asyncio.run(_export(output_path, args.subject_area))
    print(f"Exported {count} diagnosis records to {output_path}")


if __name__ == "__main__":
    main()
