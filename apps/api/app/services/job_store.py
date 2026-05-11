from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from app.config import settings


class JobStore:
    def __init__(self) -> None:
        self.root = Path(settings.data_dir) / "jobs"

    def create_job(
        self,
        kind: str,
        status: str = "completed",
        result: dict[str, object] | None = None,
    ) -> dict[str, object]:
        job = {
            "id": str(uuid4()),
            "kind": kind,
            "status": status,
            "result": result or {},
        }
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / f"{job['id']}.json").write_text(
            json.dumps(job, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return job

    def get_job(self, job_id: str) -> dict[str, object] | None:
        if not job_id or "/" in job_id or "\\" in job_id or ".." in job_id:
            return None
        path = self.root / f"{job_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
