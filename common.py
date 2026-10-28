
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def log_event(run_id, stage, status, **details):
    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    event = {
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "run_id": run_id,
        "stage": stage,
        "status": status,
        **details,
    }

    log_path = log_dir / f"{run_id}.jsonl"

    with log_path.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                event,
                ensure_ascii=False,
                default=str,
            ) + "\n"
        )
