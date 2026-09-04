"""Bounded, ownership-preserving cross-module context (Issue #7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from flowsight import schema as S
from flowsight.reading_subjects import ReadingSubject, ReadingSubjectCatalog
from flowsight.refinement.agent import AuthoredArchitecture, _validate_authorship
from flowsight.refinement.dossier import ContextPolicy, build_dossier


def _subject(root: str, label: str, files: tuple[str, ...]) -> ReadingSubject:
    return ReadingSubject(
        id=root,
        label=label,
        root=root,
        member_files=files,
        exclusions=(),
        rationale=f"Owns {label} behavior.",
    )


def _function(node_id: str, label: str, file: str, line: int) -> S.Node:
    return S.Node(
        id=node_id,
        type=S.FUNCTION,
        label=label,
        origin=S.PARSER,
        location=S.Location(file=file, line=line, end_line=line + 2),
        signature=S.Signature(params=[S.Param("value", "str")], returns="str"),
    )


def _fixture(tmp_path: Path) -> tuple[Path, S.GraphDocument, ReadingSubjectCatalog]:
    project = tmp_path / "project"
    files = (
        "pkg/api/routes.py",
        "pkg/core/service.py",
        "pkg/storage/repository.py",
        "pkg/extra/audit.py",
    )
    for relative in files:
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative}\n", encoding="utf-8")
    catalog = ReadingSubjectCatalog(subjects=(
        _subject("pkg/api", "Public API", (files[0],)),
        _subject("pkg/core", "Core", (files[1],)),
        _subject("pkg/storage", "Storage", (files[2],)),
        _subject("pkg/extra", "Audit", (files[3],)),
    ))
    nodes = [
        _function("api", "route", files[0], 1),
        *[_function(f"core-{index}", f"core_{index}", files[1], index * 10) for index in range(1, 6)],
        _function("core-deep", "normalize", files[1], 80),
        *[_function(f"storage-{index}", f"storage_{index}", files[2], index * 10) for index in range(1, 5)],
        _function("audit", "audit", files[3], 10),
        _function("isolated", "isolated", files[3], 30),
    ]
    edges = [
        S.Edge("core-1", "api", S.CALLS, S.PARSER),
        *[S.Edge("api", f"core-{index}", S.CALLS, S.PARSER) for index in range(2, 6)],
        *[S.Edge("api", f"storage-{index}", S.CALLS, S.RUNTIME if index == 1 else S.PARSER)
          for index in range(1, 5)],
        S.Edge("api", "audit", S.CALLS, S.PARSER),
        S.Edge("core-2", "core-deep", S.CALLS, S.PARSER),
    ]
    return project, S.GraphDocument(project={"name": "fixture"}, nodes=nodes, edges=edges), catalog


def test_direct_context_preserves_owner_signature_location_and_direction(tmp_path):
    project, doc, catalog = _fixture(tmp_path)

    dossier = build_dossier(doc, catalog, "pkg/api", project)

    context = dossier["nodes"]["boundary"]
    ids = {node["id"] for node in context}
    assert "core-1" in ids
    assert "core-2" in ids
    assert "core-deep" not in ids
    assert {node["id"] for node in dossier["nodes"]["critical_path_candidates"]} == {
        "core-deep"
    }
    caller = next(node for node in context if node["id"] == "core-1")
    callee = next(node for node in context if node["id"] == "core-2")
    assert caller["context"]["owner"] == {"id": "pkg/core", "label": "Core"}
    assert caller["context"]["directions"] == ["incoming"]
    assert callee["context"]["directions"] == ["outgoing"]
    assert caller["signature"]["params"][0]["type"] == "str"
    assert caller["location"] == {
        "file": "pkg/core/service.py", "line": 10, "end_line": 12, "col": 0
    }


def test_justified_critical_path_can_extend_beyond_one_hop(tmp_path):
    project, doc, catalog = _fixture(tmp_path)

    dossier = build_dossier(
        doc,
        catalog,
        "pkg/api",
        project,
        context_policy=ContextPolicy(max_external_subjects=1, max_external_nodes=6),
        critical_path_extensions={"core-deep": "Completes the normalization path."},
    )

    extended = next(node for node in dossier["nodes"]["boundary"] if node["id"] == "core-deep")
    assert extended["context"]["hop"] == 2
    assert extended["context"]["justification"] == "Completes the normalization path."
    assert any(
        edge["source"] == "core-2" and edge["target"] == "core-deep"
        for edge in dossier["relationships"]["external_context"]
    )


def test_agent_can_choose_bounded_critical_path_after_request_is_frozen(tmp_path):
    project, doc, catalog = _fixture(tmp_path)
    dossier = build_dossier(doc, catalog, "pkg/api", project)
    dossier["context"]["overflow"] = []
    dossier["context"]["omitted_primary_node_count"] = 0
    request = {"dossier": dossier}
    authored = AuthoredArchitecture(
        specification={
            "diagram_type": "architecture",
            "schema_version": 1,
            "meta": {"quality_profile": "showcase", "views": []},
            "components": [
                {"id": "api", "type": "backend", "label": "route", "sublabel": "parser"},
                {
                    "id": "normalize",
                    "type": "external",
                    "label": "normalize",
                    "sublabel": "normalize(value: str) -> str · pkg/core/service.py:80 · parser",
                    "tag": "Core · pkg/core",
                },
            ],
            "boundaries": [
                {"kind": "region", "label": "内部 · Public API", "wraps": ["api"]},
                {
                    "kind": "region",
                    "label": "外部上下文 · Core · pkg/core",
                    "wraps": ["normalize"],
                },
            ],
            "connections": [],
            "cards": [{
                "title": "Critical path continuation (parser evidence)",
                "items": ["normalize continues the selected path after the direct boundary."],
            }],
        },
        reverse_id_map={"api": "api", "normalize": "core-deep"},
    )

    _validate_authorship(request, authored)


def test_context_budgets_choose_two_strongest_subjects_and_aggregate_overflow(tmp_path):
    project, doc, catalog = _fixture(tmp_path)

    dossier = build_dossier(doc, catalog, "pkg/api", project)

    context = dossier["context"]
    assert context["policy"] == {"max_external_subjects": 2, "max_external_nodes": 6}
    assert [subject["id"] for subject in context["external_subjects"]] == [
        "pkg/core", "pkg/storage"
    ]
    assert len(dossier["nodes"]["boundary"]) == 6
    overflow = {item["owner"]["id"]: item for item in context["overflow"]}
    assert overflow["pkg/extra"]["node_count"] == 1
    assert overflow["pkg/core"]["node_count"] + overflow["pkg/storage"]["node_count"] == 3
    assert sum(item["node_count"] for item in context["overflow"]) == 4
    assert context["omitted_primary_node_count"] == 4
    assert dossier["source_scope"]["external_files"] == [
        "pkg/core/service.py", "pkg/storage/repository.py"
    ]


def test_unconnected_or_unjustified_extension_is_rejected(tmp_path):
    project, doc, catalog = _fixture(tmp_path)

    with pytest.raises(ValueError, match="non-empty justification"):
        build_dossier(
            doc, catalog, "pkg/api", project,
            critical_path_extensions={"core-deep": ""},
        )
    with pytest.raises(ValueError, match="evidenced continuation"):
        build_dossier(
            doc, catalog, "pkg/api", project,
            critical_path_extensions={"isolated": "Looks useful but is disconnected."},
        )
