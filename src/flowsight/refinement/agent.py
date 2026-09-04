"""Agent-side adapter for consuming one durable refinement job.

FlowSight does not create an Agent runtime.  The external Agent that owns the
session supplies the authorship strategy and invokes this adapter to claim,
check, and publish one Architecture artifact.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from flowsight.refinement.jobs import JobStore

MAX_REPAIR_ROUNDS = 2


@dataclass
class AuthoredArchitecture:
    specification: dict[str, Any]
    reverse_id_map: dict[str, str]


class ArchitectureAuthor(Protocol):
    def author(self, request: dict[str, Any], diagnostic: str = "") -> AuthoredArchitecture:
        """Author from the immutable bounded request, optionally repairing a diagnostic."""


class ArchitectureDelivery(Protocol):
    version: str

    def deliver(self, specification_path: Path, artifact_path: Path) -> dict[str, Any]:
        """Deliver exactly one checked Architecture artifact or raise ValueError."""


class FileArchitectureAuthor:
    """Load the exact spec and reverse map authored by the monitoring Agent."""

    def __init__(self, specification_path: str | Path, reverse_id_map_path: str | Path):
        self.specification_path = Path(specification_path).resolve()
        self.reverse_id_map_path = Path(reverse_id_map_path).resolve()

    def author(self, request: dict[str, Any], diagnostic: str = "") -> AuthoredArchitecture:
        del request, diagnostic
        try:
            specification = json.loads(self.specification_path.read_text(encoding="utf-8"))
            reverse_id_map = json.loads(self.reverse_id_map_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read Agent-authored Architecture files: {exc}") from exc
        if not isinstance(specification, dict) or not isinstance(reverse_id_map, dict):
            raise ValueError("Agent-authored specification and reverse map must be JSON objects")
        return AuthoredArchitecture(
            specification=specification,
            reverse_id_map={str(key): str(value) for key, value in reverse_id_map.items()},
        )


class ArchifyRunner:
    """Zero-dependency subprocess adapter for Archify's atomic delivery command."""

    def __init__(self, archify_root: str | Path):
        self.root = Path(archify_root).resolve()
        self.executable = self.root / "bin" / "archify.mjs"
        package = self.root / "package.json"
        if not self.executable.is_file() or not package.is_file():
            raise ValueError(f"invalid Archify root: {self.root}")
        try:
            self.version = str(json.loads(package.read_text(encoding="utf-8"))["version"])
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("Archify package version is unavailable") from exc

    def deliver(self, specification_path: Path, artifact_path: Path) -> dict[str, Any]:
        command = [
            "node",
            str(self.executable),
            "deliver",
            "architecture",
            str(specification_path),
            str(artifact_path),
            "--quality",
            "showcase",
            "--json",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=180,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Archify delivery exceeded the 180-second limit") from exc
        output = completed.stdout.strip() or completed.stderr.strip()
        try:
            receipt = json.loads(output)
        except json.JSONDecodeError as exc:
            raise ValueError(_bounded(f"Archify returned a non-JSON delivery result: {output}")) from exc
        if completed.returncode != 0 or receipt.get("ok") is not True:
            diagnostic = receipt.get("error") or output or f"Archify exited {completed.returncode}"
            raise ValueError(_bounded(str(diagnostic)))
        if receipt.get("command") != "deliver" or receipt.get("type") != "architecture":
            raise ValueError("Archify receipt is not an Architecture delivery")
        validation = receipt.get("validation") or {}
        if validation.get("errors") != 0 or validation.get("warnings") != 0:
            raise ValueError("Archify delivery did not pass without errors and warnings")
        return receipt


class RefinementAgent:
    """Consume the oldest durable pending job and publish a verified result."""

    def __init__(
        self,
        store: JobStore,
        author: ArchitectureAuthor,
        archify: ArchitectureDelivery,
        *,
        agent_id: str,
        max_repair_rounds: int = MAX_REPAIR_ROUNDS,
    ):
        if max_repair_rounds < 0 or max_repair_rounds > MAX_REPAIR_ROUNDS:
            raise ValueError(f"max_repair_rounds must be between 0 and {MAX_REPAIR_ROUNDS}")
        self.store = store
        self.author = author
        self.archify = archify
        self.agent_id = agent_id
        self.max_repair_rounds = max_repair_rounds

    def process_next(self) -> dict[str, Any] | None:
        """Scan before waiting, then claim and completely process at most one job."""

        pending = self.store.pending()
        if not pending:
            return None
        job_id = pending[0]["job_id"]
        try:
            self.store.claim(job_id, agent_id=self.agent_id)
        except ValueError:
            return None
        request = self.store.read_request(job_id)
        self.store.advance(job_id, "generating")
        diagnostic = ""
        for attempt in range(self.max_repair_rounds + 1):
            try:
                authored = self.author.author(request, diagnostic)
                _validate_authorship(request, authored)
                receipt = self._deliver_candidate(job_id, authored)
                self._publish(job_id, request, authored, receipt)
                return self.store.accept_result(job_id)
            except (KeyError, OSError, TypeError, ValueError, subprocess.SubprocessError) as exc:
                diagnostic = _bounded(str(exc))
                if attempt >= self.max_repair_rounds:
                    return self.store.fail(job_id, diagnostic)
                status = self.store.get_status(job_id)
                if status["status"] == "validating":
                    self.store.restart_generation(job_id, diagnostic)
        return self.store.fail(job_id, diagnostic)

    def _deliver_candidate(
        self,
        job_id: str,
        authored: AuthoredArchitecture,
    ) -> dict[str, Any]:
        job_dir = self.store.job_dir(job_id)
        specification = job_dir / "specification.staged.json"
        artifact = job_dir / "artifact.staged.html"
        _write_json(specification, authored.specification)
        self.store.advance(job_id, "validating")
        return self.archify.deliver(specification, artifact)

    def _publish(
        self,
        job_id: str,
        request: dict[str, Any],
        authored: AuthoredArchitecture,
        archify_receipt: dict[str, Any],
    ) -> None:
        job_dir = self.store.job_dir(job_id)
        staged_specification = job_dir / "specification.staged.json"
        staged_artifact = job_dir / "artifact.staged.html"
        if not staged_specification.is_file() or not staged_artifact.is_file():
            raise ValueError("Archify delivery did not produce complete staged outputs")
        _verify_delivery_bytes(staged_specification, staged_artifact, archify_receipt)

        final_specification = job_dir / "specification.json"
        final_artifact = job_dir / "artifact.html"
        reverse_map = job_dir / "reverse-id-map.json"
        receipt_path = job_dir / "delivery-receipt.json"
        result_path = job_dir / "result.json"
        _write_json(reverse_map.with_suffix(".json.staged"), authored.reverse_id_map)
        receipt = {
            "success": True,
            "job_id": job_id,
            "subject_id": request["subject_id"],
            "input_fingerprint": request["input_fingerprint"],
            "archify_version": self.archify.version,
            "archify_delivery": archify_receipt,
        }
        _write_json(receipt_path.with_suffix(".json.staged"), receipt)

        os.replace(staged_specification, final_specification)
        os.replace(staged_artifact, final_artifact)
        os.replace(reverse_map.with_suffix(".json.staged"), reverse_map)
        os.replace(receipt_path.with_suffix(".json.staged"), receipt_path)
        result = {
            "job_id": job_id,
            "subject_id": request["subject_id"],
            "input_fingerprint": request["input_fingerprint"],
            "diagram_type": "architecture",
            "artifact_path": self.store._relative(final_artifact),
            "specification_path": self.store._relative(final_specification),
            "reverse_id_map_path": self.store._relative(reverse_map),
            "receipt_path": self.store._relative(receipt_path),
        }
        _write_json(result_path.with_suffix(".json.staged"), result)
        os.replace(result_path.with_suffix(".json.staged"), result_path)


def _validate_authorship(request: dict[str, Any], authored: AuthoredArchitecture) -> None:
    specification = authored.specification
    if specification.get("diagram_type") != "architecture":
        raise ValueError("the first integration accepts exactly one Architecture specification")
    if specification.get("schema_version") != 1:
        raise ValueError("Architecture schema_version must be 1")
    meta = specification.get("meta") or {}
    if meta.get("quality_profile") != "showcase":
        raise ValueError("Architecture quality_profile must be showcase")
    components = specification.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("Architecture must contain at least one component")

    dossier = request["dossier"]
    evidence_nodes = {
        node["id"]: node
        for group in ("internal", "boundary")
        for node in dossier["nodes"].get(group, [])
    }
    component_ids = {component.get("id") for component in components}
    if None in component_ids or len(component_ids) != len(components):
        raise ValueError("Architecture component IDs must be present and unique")
    for component_id in component_ids:
        node_id = authored.reverse_id_map.get(component_id)
        if node_id not in evidence_nodes:
            raise ValueError(f"component {component_id!r} has no parser/runtime evidence reverse mapping")

    evidence_edges = {
        (edge["source"], edge["target"])
        for group in ("internal", "boundary")
        for edge in dossier["relationships"].get(group, [])
        if edge.get("origin") in {"parser", "runtime"}
    }
    for connection in specification.get("connections", []):
        source = authored.reverse_id_map.get(connection.get("from"))
        target = authored.reverse_id_map.get(connection.get("to"))
        if (source, target) not in evidence_edges:
            raise ValueError(
                f"connection {connection.get('from')!r} -> {connection.get('to')!r} "
                "has no parser/runtime topology evidence"
            )

    runtime_present = any(node.get("runtime") for node in evidence_nodes.values()) or any(
        edge.get("origin") == "runtime"
        for group in ("internal", "boundary")
        for edge in dossier["relationships"].get(group, [])
    )
    for view in meta.get("views", []):
        text = f"{view.get('id', '')} {view.get('label', '')}".lower()
        if "runtime" in text or "运行" in text:
            if not runtime_present:
                raise ValueError("runtime guided view requires observed runtime evidence")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _verify_delivery_bytes(
    specification_path: Path,
    artifact_path: Path,
    receipt: dict[str, Any],
) -> None:
    for label, path in (("specification", specification_path), ("artifact", artifact_path)):
        claim = receipt.get(label)
        if not isinstance(claim, dict):
            raise ValueError(f"Archify receipt is missing {label} byte identity")
        contents = path.read_bytes()
        if claim.get("bytes") != len(contents):
            raise ValueError(f"Archify {label} byte count mismatch")
        actual_hash = hashlib.sha256(contents).hexdigest()
        if claim.get("sha256") != actual_hash:
            raise ValueError(f"Archify {label} SHA-256 mismatch")


def _bounded(message: str) -> str:
    return message.strip()[:1000]
