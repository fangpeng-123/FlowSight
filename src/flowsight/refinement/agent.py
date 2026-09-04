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
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from flowsight.refinement.jobs import JobStore, write_json_atomic

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
        try:
            request = self.store.read_request(job_id)
            self.store.advance(job_id, "generating")
        except (KeyError, OSError, ValueError) as exc:
            return self.store.fail(job_id, _bounded(str(exc)))
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
        write_json_atomic(specification, authored.specification)
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
        write_json_atomic(reverse_map.with_suffix(".json.staged"), authored.reverse_id_map)
        receipt = {
            "success": True,
            "job_id": job_id,
            "subject_id": request["subject_id"],
            "input_fingerprint": request["input_fingerprint"],
            "archify_version": self.archify.version,
            "archify_delivery": archify_receipt,
        }
        write_json_atomic(receipt_path.with_suffix(".json.staged"), receipt)

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
        write_json_atomic(result_path.with_suffix(".json.staged"), result)
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
        for group in ("internal", "boundary", "critical_path_candidates")
        for node in dossier["nodes"].get(group, [])
    }
    component_ids = {component.get("id") for component in components}
    if None in component_ids or len(component_ids) != len(components):
        raise ValueError("Architecture component IDs must be present and unique")
    for component_id in component_ids:
        node_id = authored.reverse_id_map.get(component_id)
        if node_id not in evidence_nodes:
            raise ValueError(f"component {component_id!r} has no parser/runtime evidence reverse mapping")
        if evidence_nodes[node_id].get("origin") not in {"parser", "runtime"}:
            raise ValueError(f"component {component_id!r} is not parser/runtime topology evidence")

    internal_primary = {
        node["id"]: node
        for node in dossier["nodes"].get("internal", [])
        if node.get("type") in {"function", "class"}
    }
    selected_internal = {
        authored.reverse_id_map[component_id]
        for component_id in component_ids
        if authored.reverse_id_map[component_id] in internal_primary
    }
    all_internal_components = {
        component_id for component_id in component_ids
        if authored.reverse_id_map[component_id] in {
            node["id"] for node in dossier["nodes"].get("internal", [])
        }
    }
    if len(internal_primary) >= 8 and len(selected_internal) < 8:
        raise ValueError("Architecture must curate at least 8 internal primary nodes")
    if len(all_internal_components) > 18:
        raise ValueError("Architecture may curate at most 18 internal primary nodes")
    _validate_internal_curation(specification, internal_primary, selected_internal)
    _validate_advisory_presentation(specification)

    _validate_context_presentation(specification, authored.reverse_id_map, dossier)

    evidence_edges: dict[tuple[str, str], set[str]] = {}
    for group in ("internal", "boundary", "external_context", "critical_path_candidates"):
        for edge in dossier["relationships"].get(group, []):
            if edge.get("origin") in {"parser", "runtime"}:
                evidence_edges.setdefault((edge["source"], edge["target"]), set()).add(
                    edge["origin"]
                )
    for connection in specification.get("connections", []):
        source = authored.reverse_id_map.get(connection.get("from"))
        target = authored.reverse_id_map.get(connection.get("to"))
        if (source, target) not in evidence_edges:
            raise ValueError(
                f"connection {connection.get('from')!r} -> {connection.get('to')!r} "
                "has no parser/runtime topology evidence"
            )
        presentation = f"{connection.get('label', '')} {connection.get('variant', '')}".lower()
        runtime_marked = any(
            marker in presentation for marker in ("runtime", "observed", "运行", "观测")
        )
        if runtime_marked and "runtime" not in evidence_edges[(source, target)]:
            raise ValueError("runtime presentation requires runtime evidence")
        if "runtime" in evidence_edges[(source, target)]:
            if connection.get("variant") != "emphasis" or not any(
                marker in presentation for marker in ("runtime", "observed", "运行", "观测")
            ):
                raise ValueError("runtime connection must be visibly marked as observed and emphasized")

    runtime_present = any(node.get("runtime") for node in evidence_nodes.values()) or any(
        edge.get("origin") == "runtime"
        for group in ("internal", "boundary", "external_context", "critical_path_candidates")
        for edge in dossier["relationships"].get(group, [])
    )
    for view in meta.get("views", []):
        text = f"{view.get('id', '')} {view.get('label', '')}".lower()
        if "runtime" in text or "运行" in text:
            if not runtime_present:
                raise ValueError("runtime guided view requires observed runtime evidence")

    if not runtime_present:
        for card in specification.get("cards", []):
            text = json.dumps(card, ensure_ascii=False).lower()
            if any(marker in text for marker in ("observed", "观测", "实际运行")) and not any(
                marker in text
                for marker in ("no runtime", "without runtime", "not observed", "未", "无", "省略")
            ):
                raise ValueError("runtime narrative requires runtime evidence or an explicit absence label")


def _validate_internal_curation(
    specification: dict[str, Any],
    internal_primary: dict[str, dict[str, Any]],
    selected_internal: set[str],
) -> None:
    omitted = [node for node_id, node in internal_primary.items() if node_id not in selected_internal]
    if not omitted:
        return
    categories = dict(sorted(Counter(str(node.get("type", "unknown")) for node in omitted).items()))
    expected_count = len(omitted)
    narrative = json.dumps(specification.get("cards", []), ensure_ascii=False).lower()
    if not any(marker in narrative for marker in ("helper", "omitted", "aggregate", "省略", "聚合")):
        raise ValueError("omitted internal helpers must be visibly acknowledged as an aggregate")
    if str(expected_count) not in narrative or any(
        category.lower() not in narrative or str(count) not in narrative
        for category, count in categories.items()
    ):
        raise ValueError("internal helper aggregate must display its exact count and categories")


def _validate_advisory_presentation(specification: dict[str, Any]) -> None:
    provenance_markers = (
        "parser", "runtime", "observed", "llm", "advisory", "inferred", "suggested",
        "解析", "运行", "观测", "建议", "推断",
    )
    for card in specification.get("cards", []):
        title = str(card.get("title", "")).lower()
        if not any(marker in title for marker in provenance_markers):
            raise ValueError("every explanatory card must visibly identify parser, LLM, or runtime provenance")


def _validate_context_presentation(
    specification: dict[str, Any],
    reverse_id_map: dict[str, str],
    dossier: dict[str, Any],
) -> None:
    internal_ids = {node["id"] for node in dossier["nodes"].get("internal", [])}
    context_by_id = {
        node["id"]: node
        for group in ("boundary", "critical_path_candidates")
        for node in dossier["nodes"].get(group, [])
    }
    candidate_ids = {
        node["id"] for node in dossier["nodes"].get("critical_path_candidates", [])
    }
    components = {component["id"]: component for component in specification.get("components", [])}
    boundaries = specification.get("boundaries", [])

    for component_id, component in components.items():
        node_id = reverse_id_map[component_id]
        node = context_by_id.get(node_id)
        if node is None:
            continue
        context = node.get("context") or {}
        owner = context.get("owner") or {}
        presentation = " ".join(
            str(component.get(field, "")) for field in ("label", "sublabel", "tag")
        )
        if component.get("type") != "external":
            raise ValueError(f"external context component {component_id!r} needs a distinct external type")
        owner_tag = str(component.get("tag", ""))
        if not owner or not any(
            str(owner.get(field, "")) and str(owner[field]) in owner_tag
            for field in ("id", "label")
        ):
            raise ValueError(f"external context component {component_id!r} must display its owner")
        location = node.get("location") or {}
        source_paths = {
            source.get("path") for source in component.get("sources", []) if isinstance(source, dict)
        }
        location_file = str(location.get("file", ""))
        compact_location = (
            bool(location_file)
            and Path(location_file).name in presentation
            and f":{location.get('line')}" in presentation
        )
        if location_file not in presentation and location_file not in source_paths and not compact_location:
            raise ValueError(f"external context component {component_id!r} must display its source location")
        signature = node.get("signature")
        if signature:
            if component.get("label") != node.get("label"):
                raise ValueError(
                    f"external context component {component_id!r} must retain its exact identifier"
                )
            required_signature_tokens = [
                str(parameter.get(field, ""))
                for parameter in signature.get("params", [])
                if isinstance(parameter, dict)
                for field in ("name", "type")
                if str(parameter.get(field, ""))
            ]
            if signature.get("returns"):
                required_signature_tokens.append(str(signature["returns"]))
            if any(token not in presentation for token in required_signature_tokens):
                raise ValueError(
                    f"external context component {component_id!r} must display its signature"
                )
        matching_boundaries = [
            boundary for boundary in boundaries if component_id in boundary.get("wraps", [])
        ]
        if not any(
            ("external" in str(boundary.get("label", "")).lower() or "外部" in str(boundary.get("label", "")))
            and any(
                str(owner.get(field, "")) in str(boundary.get("label", ""))
                for field in ("id", "label")
                if owner.get(field)
            )
            for boundary in matching_boundaries
        ):
            raise ValueError(
                f"external context component {component_id!r} must be inside an owner-labelled external boundary"
            )

    internal_components = {
        component_id for component_id in components
        if reverse_id_map[component_id] in internal_ids
    }
    external_components = {
        component_id for component_id in components
        if reverse_id_map[component_id] in context_by_id
    }
    policy = (dossier.get("context") or {}).get("policy") or {}
    if len(external_components) > int(policy.get("max_external_nodes", 6)):
        raise ValueError("Architecture exceeds the external primary-node budget")
    external_owners = {
        (context_by_id[reverse_id_map[component_id]].get("context") or {}).get("owner", {}).get("id")
        for component_id in external_components
    }
    if len(external_owners) > int(policy.get("max_external_subjects", 2)):
        raise ValueError("Architecture exceeds the external reading-subject budget")
    chosen_candidates = [
        context_by_id[reverse_id_map[component_id]]
        for component_id in external_components
        if reverse_id_map[component_id] in candidate_ids
    ]
    if chosen_candidates:
        narrative = json.dumps(specification.get("cards", []), ensure_ascii=False).lower()
        for node in chosen_candidates:
            if str(node.get("label", "")).lower() not in narrative or not any(
                marker in narrative for marker in ("critical", "continuation", "关键", "路径", "延伸")
            ):
                raise ValueError("selected critical-path continuation needs a visible justification")
    for boundary in boundaries:
        wraps = set(boundary.get("wraps", []))
        if wraps & internal_components and wraps & external_components:
            raise ValueError("internal and external context components require distinct boundaries")

    overflow = (dossier.get("context") or {}).get("overflow", [])
    if overflow:
        narrative = json.dumps(specification.get("cards", []), ensure_ascii=False).lower()
        if not any(marker in narrative for marker in ("overflow", "omitted", "aggregate", "省略", "聚合", "未展示")):
            raise ValueError("external context overflow must be acknowledged as an aggregate")
        for aggregate in overflow:
            owner = aggregate.get("owner") or {}
            owner_visible = any(
                str(owner.get(field, "")) and str(owner[field]).lower() in narrative
                for field in ("id", "label")
            )
            count_visible = str(aggregate.get("node_count", "")) in narrative
            if not owner_visible or not count_visible:
                raise ValueError("external context overflow must display each owner and omitted count")


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
