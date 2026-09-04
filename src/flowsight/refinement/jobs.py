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
ACTIVE = frozenset({"claimed", "generating", "validating"})
NEXT_STATE = {"claimed": "generating", "generating": "validating"}
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


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Commit one deterministic JSON document with a same-directory replace."""

    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


class JobStore:
    """Owns durable request/status files below the project's refinement area."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.root = self.project_root / ".flowsight" / "refinements" / "jobs"
        self.current_root = self.root.parent / "current"
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
            write_json_atomic(self.request_path(job_id), request)
            write_json_atomic(self.status_path(job_id), status)

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

    def latest_status(self, subject_id: str) -> dict[str, Any]:
        """Return the newest visible job for restoring browser state after reload."""

        matches = [
            status for status in self._statuses()
            if status.get("subject_id") == subject_id
            and status.get("status") not in {"cancelled", "stale"}
        ]
        if not matches:
            raise KeyError(f"no refinement exists for subject: {subject_id}")
        active = [status for status in matches if status.get("status") in ACTIVE | {"pending"}]
        if active:
            return max(active, key=lambda status: (status.get("created_at", ""), status["job_id"]))
        ready = [status for status in matches if status.get("status") == "ready"]
        latest = max(matches, key=lambda status: (status.get("created_at", ""), status["job_id"]))
        if latest.get("status") == "failed" and ready:
            fallback = max(
                ready, key=lambda status: (status.get("created_at", ""), status["job_id"])
            )
            latest = dict(latest)
            latest.update(
                fallback_artifact_available=True,
                fallback_artifact_url=fallback.get("artifact_url"),
                fallback_job_id=fallback.get("job_id"),
            )
        return latest

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
            write_json_atomic(self.status_path(job_id), status)
            return status

    def pending(self) -> list[dict[str, Any]]:
        """Return durable pending work in creation order for recovering Agents."""

        return sorted(
            (status for status in self._statuses() if status.get("status") == "pending"),
            key=lambda status: (status.get("created_at", ""), status.get("job_id", "")),
        )

    def read_request(self, job_id: str) -> dict[str, Any]:
        path = self.request_path(job_id)
        if not path.is_file():
            raise KeyError(f"missing request for job: {job_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def claim(self, job_id: str, *, agent_id: str) -> dict[str, Any]:
        with self._lock:
            self._acquire_active_claim(job_id, agent_id)
            try:
                status = self.get_status(job_id)
                if status["status"] != "pending":
                    raise ValueError("another refinement job is already active")
                for other in self._statuses():
                    if other["job_id"] != job_id and other.get("status") in ACTIVE:
                        raise ValueError("another refinement job is already active")
                return self._set_status(status, "claimed", "claimed", agent_id=agent_id)
            except Exception:
                self._release_active_claim(job_id)
                raise

    def advance(self, job_id: str, next_status: str) -> dict[str, Any]:
        with self._lock:
            status = self.get_status(job_id)
            expected = NEXT_STATE.get(status["status"])
            if next_status != expected:
                raise ValueError(f"cannot advance {status['status']} to {next_status}")
            return self._set_status(status, next_status, next_status)

    def restart_generation(self, job_id: str, diagnostic: str) -> dict[str, Any]:
        """Return a validating job to generation for one bounded repair round."""

        with self._lock:
            status = self.get_status(job_id)
            if status["status"] != "validating":
                raise ValueError("only a validating job can begin a repair")
            return self._set_status(
                status,
                "generating",
                "repairing",
                diagnostic=str(diagnostic)[:1000],
            )

    def fail(self, job_id: str, diagnostic: str) -> dict[str, Any]:
        with self._lock:
            status = self.get_status(job_id)
            if status["status"] in {"ready", "cancelled"}:
                raise ValueError(f"cannot fail a {status['status']} job")
            failed = self._set_status(
                status,
                "failed",
                "failed",
                diagnostic=str(diagnostic)[:1000],
                artifact_available=False,
            )
            self._release_active_claim(job_id)
            return failed

    def accept_result(self, job_id: str) -> dict[str, Any]:
        """Independently validate Agent result metadata and register its artifact."""

        try:
            with self._lock:
                status = self.get_status(job_id)
                if status["status"] != "validating":
                    raise ValueError("job must be validating before accepting a result")
                result_path = self.job_dir(job_id) / "result.json"
                if not result_path.is_file():
                    raise ValueError("missing result metadata")
                result = json.loads(result_path.read_text(encoding="utf-8"))
                self._match_identity(result, status, "result")
                request = self.read_request(job_id)
                self._match_identity(request, status, "request")
                if result.get("diagram_type") != "architecture":
                    raise ValueError("result is not an Architecture diagram")
                artifact = self._validated_result_path(job_id, result.get("artifact_path"), "artifact")
                specification = self._validated_result_path(
                    job_id, result.get("specification_path"), "specification"
                )
                reverse_map_path = self._validated_result_path(
                    job_id, result.get("reverse_id_map_path"), "reverse ID map"
                )
                receipt_path = self._validated_result_path(job_id, result.get("receipt_path"), "receipt")
                if not artifact.is_file():
                    raise ValueError("missing artifact HTML")
                if not specification.is_file():
                    raise ValueError("missing Archify specification")
                if not reverse_map_path.is_file():
                    raise ValueError("missing reverse ID map")
                if not receipt_path.is_file():
                    raise ValueError("missing delivery receipt")
                try:
                    specification_payload = json.loads(specification.read_text(encoding="utf-8"))
                    reverse_map = json.loads(reverse_map_path.read_text(encoding="utf-8"))
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise ValueError("invalid refinement result JSON") from exc
                self._validate_specification_binding(request, specification_payload, reverse_map)
                self._match_identity(receipt, status, "delivery receipt")
                if receipt.get("success") is not True:
                    raise ValueError("delivery receipt reports failure")
                if not str(receipt.get("archify_version", "")).strip():
                    raise ValueError("delivery receipt is missing the Archify version")
                delivery = receipt.get("archify_delivery")
                if not isinstance(delivery, dict) or (
                    delivery.get("ok") is not True
                    or delivery.get("command") != "deliver"
                    or delivery.get("type") != "architecture"
                ):
                    raise ValueError("delivery receipt is not an Archify Architecture delivery")
                validation = delivery.get("validation") or {}
                if validation.get("errors") != 0 or validation.get("warnings") != 0:
                    raise ValueError("Archify Architecture delivery has validation findings")
                self._verify_file_claim(specification, delivery.get("specification"), "specification")
                self._verify_file_claim(artifact, delivery.get("artifact"), "artifact")

                current_dir = self._current_dir(status["subject_id"])
                current_dir.mkdir(parents=True, exist_ok=True)
                current_specification = current_dir / "specification.json"
                current_reverse_map = current_dir / "reverse-id-map.json"
                current_receipt = current_dir / "delivery-receipt.json"
                current_artifact = current_dir / "artifact.html"
                for source, target in (
                    (specification, current_specification),
                    (reverse_map_path, current_reverse_map),
                    (receipt_path, current_receipt),
                    (artifact, current_artifact),
                ):
                    os.replace(source, target)
                ready = self._set_status(
                    status,
                    "ready",
                    "ready",
                    artifact_available=True,
                    artifact_path=self._relative(current_artifact),
                    specification_path=self._relative(current_specification),
                    reverse_id_map_path=self._relative(current_reverse_map),
                    receipt_path=self._relative(current_receipt),
                    artifact_url=f"/api/refinements/{job_id}/artifact",
                    archify_version=str(receipt.get("archify_version", "")),
                    diagnostic="",
                )
                for previous in self._statuses():
                    if (
                        previous.get("job_id") != job_id
                        and previous.get("subject_id") == status["subject_id"]
                        and previous.get("status") == "ready"
                    ):
                        self._set_status(
                            previous,
                            "stale",
                            "replaced",
                            stale_reason=f"replaced by {job_id}",
                            artifact_available=False,
                        )
                self._release_active_claim(job_id)
                return ready
        except (OSError, KeyError, json.JSONDecodeError, ValueError) as exc:
            try:
                self.fail(job_id, str(exc))
            except ValueError:
                pass
            if isinstance(exc, ValueError):
                raise
            raise ValueError(str(exc)) from exc

    def artifact_path(self, job_id: str) -> Path:
        status = self.get_status(job_id)
        if status.get("status") != "ready" or status.get("artifact_available") is not True:
            raise KeyError("artifact is not registered as ready")
        path = self._validated_current_artifact_path(status)
        if not path.is_file():
            raise KeyError("registered artifact is missing")
        return path

    def _current_dir(self, subject_id: str) -> Path:
        key = hashlib.sha256(subject_id.encode("utf-8")).hexdigest()[:20]
        return self.current_root / key

    def _validated_current_artifact_path(self, status: dict[str, Any]) -> Path:
        value = status.get("artifact_path")
        if not isinstance(value, str) or not value:
            raise KeyError("registered artifact path is missing")
        candidate = (self.project_root / value).resolve()
        expected = (self._current_dir(status["subject_id"]) / "artifact.html").resolve()
        if candidate != expected:
            raise KeyError("registered artifact path is invalid")
        return candidate

    @staticmethod
    def _verify_file_claim(path: Path, claim: Any, label: str) -> None:
        if not isinstance(claim, dict):
            raise ValueError(f"Archify delivery is missing the {label} fingerprint")
        actual = path.read_bytes()
        if claim.get("sha256") != hashlib.sha256(actual).hexdigest():
            raise ValueError(f"{label} SHA-256 mismatch")
        if claim.get("bytes") != len(actual):
            raise ValueError(f"{label} byte count mismatch")

    @staticmethod
    def _validate_specification_binding(
        request: dict[str, Any], specification: Any, reverse_map: Any
    ) -> None:
        if not isinstance(specification, dict) or specification.get("diagram_type") != "architecture":
            raise ValueError("specification is not an Architecture diagram")
        if not isinstance(reverse_map, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in reverse_map.items()
        ):
            raise ValueError("reverse ID map must be a JSON string map")
        components = specification.get("components")
        if not isinstance(components, list) or not components:
            raise ValueError("Architecture specification has no components")
        component_ids = {component.get("id") for component in components if isinstance(component, dict)}
        if None in component_ids or component_ids != set(reverse_map):
            raise ValueError("reverse ID map does not match Architecture components")
        dossier = request.get("dossier") or {}
        evidence_ids = {
            node.get("id")
            for group in ("internal", "boundary", "critical_path_candidates")
            for node in (dossier.get("nodes") or {}).get(group, [])
            if isinstance(node, dict)
        }
        if not set(reverse_map.values()) <= evidence_ids:
            raise ValueError("reverse ID map contains topology outside the request dossier")

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

    def _statuses(self) -> list[dict[str, Any]]:
        statuses = []
        for path in sorted(self.root.glob("job-*/status.json")):
            try:
                statuses.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return statuses

    def _set_status(self, status: dict[str, Any], value: str, stage: str, **updates) -> dict[str, Any]:
        status.update(
            status=value,
            stage=stage,
            display=_display(value),
            updated_at=_now(),
            **updates,
        )
        write_json_atomic(self.status_path(status["job_id"]), status)
        return status

    @staticmethod
    def _match_identity(payload: dict[str, Any], status: dict[str, Any], label: str) -> None:
        expected = {
            "job_id": status["job_id"],
            "subject_id": status["subject_id"],
            "input_fingerprint": status["fingerprint"],
        }
        for key, value in expected.items():
            if payload.get(key) != value:
                raise ValueError(f"{label} {key.replace('_', ' ')} mismatch")

    def _validated_result_path(self, job_id: str, value: Any, label: str) -> Path:
        if not isinstance(value, str) or not value:
            raise ValueError(f"missing {label} path")
        candidate = (self.project_root / value).resolve()
        job_dir = self.job_dir(job_id).resolve()
        try:
            candidate.relative_to(job_dir)
        except ValueError as exc:
            raise ValueError(f"{label} path is outside the job directory") from exc
        return candidate

    def _next_job_id(self, base: str) -> str:
        candidate = base
        suffix = 2
        while (self.root / candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    @property
    def _active_claim_path(self) -> Path:
        return self.root / ".active-claim.json"

    def _acquire_active_claim(self, job_id: str, agent_id: str) -> None:
        payload = json.dumps(
            {"job_id": job_id, "agent_id": agent_id, "claimed_at": _now()},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        try:
            descriptor = os.open(
                self._active_claim_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            )
        except FileExistsError as exc:
            raise ValueError("another refinement job is already active") from exc
        try:
            os.write(descriptor, payload)
        finally:
            os.close(descriptor)

    def _release_active_claim(self, job_id: str) -> None:
        try:
            payload = json.loads(self._active_claim_path.read_text(encoding="utf-8"))
            if payload.get("job_id") == job_id:
                self._active_claim_path.unlink()
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.project_root).as_posix()
