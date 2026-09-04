"""Build deterministic, bounded reading-subject dossiers from graph facts."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from flowsight import schema as S
from flowsight.reading_subjects import ReadingSubject, ReadingSubjectCatalog

DOSSIER_CONTRACT_VERSION = 3


@dataclass(frozen=True)
class ContextPolicy:
    """Readability budgets for primary cross-subject context."""

    max_external_subjects: int = 2
    max_external_nodes: int = 6

    def __post_init__(self) -> None:
        if self.max_external_subjects < 0 or self.max_external_nodes < 0:
            raise ValueError("context budgets cannot be negative")


def build_dossier(
    doc: S.GraphDocument,
    catalog: ReadingSubjectCatalog,
    subject_id: str,
    project_root: str | Path,
    *,
    context_policy: ContextPolicy | None = None,
    critical_path_extensions: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Snapshot one subject plus bounded, evidence-backed external context."""

    subject = next((item for item in catalog.subjects if item.id == subject_id), None)
    if subject is None:
        raise KeyError(f"unknown reading subject: {subject_id}")

    policy = context_policy or ContextPolicy()
    extensions = dict(critical_path_extensions or {})
    for node_id, justification in extensions.items():
        if not isinstance(justification, str) or not justification.strip():
            raise ValueError(f"critical-path extension {node_id!r} requires a non-empty justification")

    payload = S.doc_to_dict(doc)
    node_by_id = {node["id"]: node for node in payload["nodes"]}
    owner_by_file = _owner_index(catalog)
    owned_files = set(subject.member_files)

    def is_internal(node: dict[str, Any]) -> bool:
        path = _node_path(node)
        reading_subject = (node.get("attrs") or {}).get("reading_subject") or {}
        return path in owned_files or reading_subject.get("id") == subject_id

    internal_ids = {node["id"] for node in payload["nodes"] if is_internal(node)}
    internal_edges = [
        edge for edge in payload["edges"]
        if edge["source"] in internal_ids and edge["target"] in internal_ids
    ]
    evidence_edges = [
        edge for edge in payload["edges"] if edge.get("origin") in {S.PARSER, S.RUNTIME}
    ]
    candidates = _direct_candidates(
        evidence_edges, node_by_id, internal_ids, owner_by_file, subject_id
    )
    _extend_critical_path(
        candidates,
        extensions,
        evidence_edges,
        node_by_id,
        internal_ids,
        owner_by_file,
        subject_id,
    )
    selected_ids, subject_order = _apply_context_budget(candidates, policy)
    selected_set = set(selected_ids)
    selected_nodes = [
        _annotate_context(node_by_id[node_id], candidates[node_id]) for node_id in selected_ids
    ]
    allowance = _critical_path_allowance(
        evidence_edges,
        node_by_id,
        internal_ids,
        candidates,
        selected_ids,
        owner_by_file,
        subject_id,
        policy.max_external_nodes,
    )
    allowance_ids = set(allowance)
    allowance_nodes = [
        _annotate_context(node_by_id[node_id], allowance[node_id]) for node_id in allowance
    ]
    boundary_edges = [
        edge for edge in evidence_edges
        if (
            edge["source"] in internal_ids and edge["target"] in selected_set
        ) or (
            edge["target"] in internal_ids and edge["source"] in selected_set
        )
    ]
    visible_ids = internal_ids | selected_set
    context_edges = [
        edge for edge in evidence_edges
        if (
            edge["source"] in visible_ids
            and edge["target"] in visible_ids
            and (edge["source"] in selected_set or edge["target"] in selected_set)
        )
    ]
    selected_owners = {candidates[node_id]["owner"].id for node_id in selected_ids}
    external_subjects = [
        _owner_summary(next(owner for owner in catalog.subjects if owner.id == owner_id))
        for owner_id in subject_order
        if owner_id in selected_owners
    ]
    overflow = _overflow(candidates, selected_set, evidence_edges, internal_ids)
    external_files = sorted({_node_path(node) for node in selected_nodes if _node_path(node)})
    allowance_files = sorted({_node_path(node) for node in allowance_nodes if _node_path(node)})
    allowance_edges = [
        edge for edge in evidence_edges
        if edge["source"] in visible_ids | allowance_ids
        and edge["target"] in visible_ids | allowance_ids
        and (edge["source"] in allowance_ids or edge["target"] in allowance_ids)
    ]

    root = Path(project_root).resolve()
    included_files = list(subject.member_files) + sorted(set(external_files + allowance_files))
    source_hashes = {
        relative: hashlib.sha256((root / Path(relative)).read_bytes()).hexdigest()
        for relative in included_files
    }
    dossier: dict[str, Any] = {
        "contract_version": DOSSIER_CONTRACT_VERSION,
        "project": {
            "name": doc.project.get("name", ""),
            "id": hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16],
        },
        "subject": subject.to_dict(),
        "source_scope": {
            "owned_files": list(subject.member_files),
            "external_files": sorted(set(external_files + allowance_files)),
        },
        "source_hashes": source_hashes,
        "nodes": {
            "internal": [node for node in payload["nodes"] if node["id"] in internal_ids],
            "boundary": selected_nodes,
            "critical_path_candidates": allowance_nodes,
        },
        "relationships": {
            "internal": internal_edges,
            "boundary": boundary_edges,
            "external_context": context_edges,
            "critical_path_candidates": allowance_edges,
        },
        "context": {
            "policy": asdict(policy),
            "external_subjects": external_subjects,
            "selected_primary_node_count": len(selected_nodes),
            "omitted_primary_node_count": sum(item["node_count"] for item in overflow),
            "overflow": overflow,
            "critical_path_candidate_count": len(allowance_nodes),
        },
    }
    canonical = json.dumps(dossier, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    dossier["fingerprint"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return dossier


def _critical_path_allowance(
    edges: list[dict[str, Any]],
    node_by_id: dict[str, dict[str, Any]],
    internal_ids: set[str],
    direct_candidates: dict[str, dict[str, Any]],
    selected_ids: list[str],
    owner_by_file: dict[str, ReadingSubject],
    selected_subject_id: str,
    limit: int,
) -> dict[str, dict[str, Any]]:
    """Expose a bounded evidenced second hop so the Agent can choose after claiming."""

    selected = set(selected_ids)
    selected_owners = {direct_candidates[node_id]["owner"].id for node_id in selected_ids}
    allowance: dict[str, dict[str, Any]] = {}
    for edge in edges:
        if edge["source"] in selected:
            external_id = edge["target"]
        elif edge["target"] in selected:
            external_id = edge["source"]
        else:
            continue
        if external_id in internal_ids or external_id in direct_candidates:
            continue
        node = node_by_id.get(external_id)
        owner = _node_owner(node, owner_by_file) if node else None
        if owner is None or owner.id == selected_subject_id or owner.id not in selected_owners:
            continue
        info = allowance.setdefault(external_id, {
            "owner": owner,
            "node_type": node.get("type", "unknown"),
            "hop": 2,
            "directions": {"critical-path"},
            "origins": set(),
            "justification": "Agent-selectable evidenced continuation",
        })
        info["origins"].add(edge["origin"])
    ordered = sorted(allowance, key=lambda node_id: _candidate_key(node_id, allowance[node_id]))
    return {node_id: allowance[node_id] for node_id in ordered[:limit]}


def _owner_index(catalog: ReadingSubjectCatalog) -> dict[str, ReadingSubject]:
    return {
        member: subject
        for subject in catalog.subjects
        for member in subject.member_files
    }


def _node_path(node: dict[str, Any]) -> str:
    location = node.get("location") or {}
    return str(location.get("file") or (node.get("attrs") or {}).get("path") or "")


def _node_owner(
    node: dict[str, Any],
    owner_by_file: dict[str, ReadingSubject],
) -> ReadingSubject | None:
    return owner_by_file.get(_node_path(node))


def _direct_candidates(
    edges: list[dict[str, Any]],
    node_by_id: dict[str, dict[str, Any]],
    internal_ids: set[str],
    owner_by_file: dict[str, ReadingSubject],
    selected_subject_id: str,
) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for edge in edges:
        source_internal = edge["source"] in internal_ids
        target_internal = edge["target"] in internal_ids
        if source_internal == target_internal:
            continue
        external_id = edge["target"] if source_internal else edge["source"]
        node = node_by_id.get(external_id)
        if node is None:
            continue
        owner = _node_owner(node, owner_by_file)
        if owner is None or owner.id == selected_subject_id:
            continue
        info = candidates.setdefault(external_id, {
            "owner": owner,
            "node_type": node.get("type", "unknown"),
            "hop": 1,
            "directions": set(),
            "origins": set(),
            "justification": "",
        })
        info["directions"].add("outgoing" if source_internal else "incoming")
        info["origins"].add(edge["origin"])
    return candidates


def _extend_critical_path(
    candidates: dict[str, dict[str, Any]],
    extensions: dict[str, str],
    edges: list[dict[str, Any]],
    node_by_id: dict[str, dict[str, Any]],
    internal_ids: set[str],
    owner_by_file: dict[str, ReadingSubject],
    selected_subject_id: str,
) -> None:
    unresolved = {node_id for node_id in extensions if node_id not in candidates}
    while unresolved:
        progressed = False
        frontier = internal_ids | set(candidates)
        for node_id in sorted(unresolved):
            node = node_by_id.get(node_id)
            owner = _node_owner(node, owner_by_file) if node else None
            if node is None or owner is None or owner.id == selected_subject_id:
                continue
            connecting = [
                edge for edge in edges
                if (
                    edge["source"] == node_id and edge["target"] in frontier
                ) or (
                    edge["target"] == node_id and edge["source"] in frontier
                )
            ]
            if not connecting:
                continue
            neighbor_hops = [
                candidates[neighbor_id]["hop"]
                for edge in connecting
                for neighbor_id in [
                    edge["target"] if edge["source"] == node_id else edge["source"]
                ]
                if neighbor_id in candidates
            ]
            candidates[node_id] = {
                "owner": owner,
                "node_type": node.get("type", "unknown"),
                "hop": min(neighbor_hops, default=0) + 1,
                "directions": {"critical-path"},
                "origins": {edge["origin"] for edge in connecting},
                "justification": extensions[node_id].strip(),
            }
            unresolved.remove(node_id)
            progressed = True
            break
        if not progressed:
            names = ", ".join(sorted(unresolved))
            raise ValueError(f"critical-path extension is not an evidenced continuation: {names}")


def _apply_context_budget(
    candidates: dict[str, dict[str, Any]],
    policy: ContextPolicy,
) -> tuple[list[str], list[str]]:
    by_owner: dict[str, list[str]] = defaultdict(list)
    direct_counts: Counter[str] = Counter()
    runtime_counts: Counter[str] = Counter()
    for node_id, info in candidates.items():
        owner_id = info["owner"].id
        by_owner[owner_id].append(node_id)
        if info["hop"] == 1:
            direct_counts[owner_id] += 1
        if S.RUNTIME in info["origins"]:
            runtime_counts[owner_id] += 1
    subject_order = sorted(
        by_owner,
        key=lambda owner_id: (-direct_counts[owner_id], -runtime_counts[owner_id], owner_id),
    )[:policy.max_external_subjects]
    for owner_id in subject_order:
        by_owner[owner_id].sort(key=lambda node_id: _candidate_key(node_id, candidates[node_id]))

    selected: list[str] = []
    while len(selected) < policy.max_external_nodes:
        progressed = False
        for owner_id in subject_order:
            if by_owner[owner_id] and len(selected) < policy.max_external_nodes:
                selected.append(by_owner[owner_id].pop(0))
                progressed = True
        if not progressed:
            break
    return selected, subject_order


def _candidate_key(node_id: str, info: dict[str, Any]) -> tuple[Any, ...]:
    return (
        info["hop"],
        0 if S.RUNTIME in info["origins"] else 1,
        node_id,
    )


def _annotate_context(node: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    annotated = copy.deepcopy(node)
    annotated["context"] = {
        "owner": _owner_summary(info["owner"]),
        "hop": info["hop"],
        "directions": sorted(info["directions"]),
        "evidence_origins": sorted(info["origins"]),
        "justification": info["justification"],
    }
    return annotated


def _owner_summary(subject: ReadingSubject) -> dict[str, str]:
    return {"id": subject.id, "label": subject.label}


def _overflow(
    candidates: dict[str, dict[str, Any]],
    selected: set[str],
    edges: list[dict[str, Any]],
    internal_ids: set[str],
) -> list[dict[str, Any]]:
    omitted_by_owner: dict[str, list[str]] = defaultdict(list)
    for node_id, info in candidates.items():
        if node_id not in selected:
            omitted_by_owner[info["owner"].id].append(node_id)
    overflow = []
    eligible_ids = internal_ids | set(candidates)
    for owner_id in sorted(omitted_by_owner):
        node_ids = omitted_by_owner[owner_id]
        omitted_ids = set(node_ids)
        info = candidates[node_ids[0]]
        overflow.append({
            "owner": _owner_summary(info["owner"]),
            "node_count": len(node_ids),
            "node_types": dict(sorted(Counter(
                candidates[node_id]["node_type"] for node_id in node_ids
            ).items())),
            "directions": dict(sorted(Counter(
                direction
                for node_id in node_ids
                for direction in candidates[node_id]["directions"]
            ).items())),
            "evidence_origins": sorted({
                origin for node_id in node_ids for origin in candidates[node_id]["origins"]
            }),
            "relationship_count": sum(
                1 for edge in edges
                if (
                    edge["source"] in omitted_ids
                    and edge["target"] in eligible_ids
                ) or (
                    edge["target"] in omitted_ids
                    and edge["source"] in eligible_ids
                )
            ),
        })
    return overflow
