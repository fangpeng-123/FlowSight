"""Build deterministic, bounded reading-subject dossiers from graph facts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from flowsight import schema as S
from flowsight.reading_subjects import ReadingSubjectCatalog

DOSSIER_CONTRACT_VERSION = 1


def build_dossier(
    doc: S.GraphDocument,
    catalog: ReadingSubjectCatalog,
    subject_id: str,
    project_root: str | Path,
) -> dict[str, Any]:
    """Snapshot facts for one subject without embedding source contents."""

    subject = next((item for item in catalog.subjects if item.id == subject_id), None)
    if subject is None:
        raise KeyError(f"unknown reading subject: {subject_id}")

    payload = S.doc_to_dict(doc)
    node_by_id = {node["id"]: node for node in payload["nodes"]}
    owned_files = set(subject.member_files)

    def is_internal(node: dict[str, Any]) -> bool:
        location = node.get("location") or {}
        path = location.get("file") or (node.get("attrs") or {}).get("path")
        reading_subject = (node.get("attrs") or {}).get("reading_subject") or {}
        return path in owned_files or reading_subject.get("id") == subject_id

    internal_ids = {node["id"] for node in payload["nodes"] if is_internal(node)}
    internal_edges: list[dict[str, Any]] = []
    boundary_edges: list[dict[str, Any]] = []
    boundary_ids: set[str] = set()
    for edge in payload["edges"]:
        source_internal = edge["source"] in internal_ids
        target_internal = edge["target"] in internal_ids
        if source_internal and target_internal:
            internal_edges.append(edge)
        elif source_internal != target_internal:
            boundary_edges.append(edge)
            boundary_ids.add(edge["target"] if source_internal else edge["source"])

    root = Path(project_root).resolve()
    source_hashes = {
        relative: hashlib.sha256((root / Path(relative)).read_bytes()).hexdigest()
        for relative in subject.member_files
    }
    dossier: dict[str, Any] = {
        "contract_version": DOSSIER_CONTRACT_VERSION,
        "project": {
            "name": doc.project.get("name", ""),
            "id": hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16],
        },
        "subject": subject.to_dict(),
        "source_scope": {"owned_files": list(subject.member_files)},
        "source_hashes": source_hashes,
        "nodes": {
            "internal": [node for node in payload["nodes"] if node["id"] in internal_ids],
            "boundary": [node_by_id[node_id] for node_id in sorted(boundary_ids) if node_id in node_by_id],
        },
        "relationships": {
            "internal": internal_edges,
            "boundary": boundary_edges,
        },
    }
    canonical = json.dumps(dossier, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    dossier["fingerprint"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return dossier
