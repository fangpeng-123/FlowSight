"""Filesystem-backed refinement jobs consumed by an external Agent."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

ACTIVE_OR_REUSABLE = frozenset({"pending", "claimed", "generating", "validating", "ready"})
_JOB_ID = re.compile(r"^job-[0-9a-f]{20}(?:-[0-9]+)?$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _display(status: str) -> str:
    return {
        "pending": "Waiting for Agent",
        "claimed": "Claimed",
        "generating": "Generating",
        "validating": "Validating",
        "ready": "Ready",
        "failed": "Failed",
        "cancelled": "Cancelled",
        "stale": "Stale",
    }.get(status, status)


class JobStore:
    """Owns durable request/status files below the project's refinement area."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.root = self.project_root / ".flowsight" / "refinements" / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def create_request(
        self,
        dossier: dict[str, Any],
        *,
        event_stream: TextIO | None = None,
    ) -> tuple[dict[str, Any], bool]:
        subject_id = dossier["subject"]["id"]
        fingerprint = dossier["fingerprint"]
        with self._lock:
            reusable = self._find_reusable(subject_id, fingerprint)
            if reusable is not None:
                return reusable, False

            stem = hashlib.sha256(f"{subject_id}\0{fingerprint}".encode("utf-8")).hexdigest()[:20]
            job_id = self._next_job_id(f"job-{stem}")
            job_dir = self.root / job_id
            job_dir.mkdir()
            created_at = _now()
            request = {
                "version": 1,
                "job_id": job_id,
                "subject_id": subject_id,
                "input_fingerprint": fingerprint,
                "project": dossier["project"],
                "source_scope": dossier["source_scope"],
                "dossier": dossier,
                "created_at": created_at,
            }
            status = {
                "job_id": job_id,
                "subject_id": subject_id,
                "fingerprint": fingerprint,
                "status": "pending",
                "stage": "waiting_for_agent",
                "display": _display("pending"),
                "created_at": created_at,
                "updated_at": created_at,
                "stale_reason": "",
                "artifact_available": False,
                "diagnostic": "",
            }
            self._write_json(self.request_path(job_id), request)
            self._write_json(self.status_path(job_id), status)

            event = {
                "event": "refinement.requested",
                "job_id": job_id,
                "subject_id": subject_id,
                "project_id": dossier["project"]["id"],
                "request_path": self._relative(self.request_path(job_id)),
                "expected_result_path": self._relative(job_dir / "result.json"),
            }
            stream = event_stream if event_stream is not None else sys.stderr
            stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            stream.flush()
            return status, True

    def request_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "request.json"

    def status_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "status.json"

    def job_dir(self, job_id: str) -> Path:
        if not _JOB_ID.fullmatch(job_id):
            raise KeyError(f"invalid job id: {job_id}")
        return self.root / job_id

    def get_status(self, job_id: str) -> dict[str, Any]:
        path = self.status_path(job_id)
        if not path.is_file():
            raise KeyError(f"unknown job: {job_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            status = self.get_status(job_id)
            if status["status"] != "pending":
                raise ValueError("only a pending job can be cancelled")
            status.update(
                status="cancelled",
                stage="cancelled",
                display=_display("cancelled"),
                updated_at=_now(),
            )
            self._write_json(self.status_path(job_id), status)
            return status

    def _find_reusable(self, subject_id: str, fingerprint: str) -> dict[str, Any] | None:
        if not self.root.is_dir():
            return None
        for path in sorted(self.root.glob("job-*/status.json")):
            try:
                status = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                status.get("subject_id") == subject_id
                and status.get("fingerprint") == fingerprint
                and status.get("status") in ACTIVE_OR_REUSABLE
            ):
                return status
        return None

    def _next_job_id(self, base: str) -> str:
        candidate = base
        suffix = 2
        while (self.root / candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.project_root).as_posix()

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
