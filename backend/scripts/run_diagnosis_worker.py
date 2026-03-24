import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.diagnosis.background import run_diagnosis_worker_forever


def main() -> None:
    asyncio.run(run_diagnosis_worker_forever())


if __name__ == "__main__":
    main()
