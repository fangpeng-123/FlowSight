"""Reading Subject Catalog public contract (GitHub issue #3)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from flowsight.reading_subjects import (
    CatalogValidationError,
    ReadingSubjectCatalog,
    apply_catalog,
    load_catalog,
)
from flowsight.server.app import GraphState
from flowsight.skeleton.extractor import extract


FIXTURE_CATALOG = Path(__file__).parent / "fixtures" / "reading-subjects.json"


def _write_project(tmp_path: Path, catalog: dict | None = None) -> Path:
    project = tmp_path / "project"
    (project / "pkg" / "api").mkdir(parents=True)
    (project / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (project / "pkg" / "api" / "__init__.py").write_text("", encoding="utf-8")
    (project / "pkg" / "api" / "routes.py").write_text("def route():\n    pass\n", encoding="utf-8")
    if catalog is not None:
        (project / ".flowsight").mkdir()
        (project / ".flowsight" / "reading-subjects.json").write_text(
            json.dumps(catalog), encoding="utf-8"
        )
    return project


def _subject(**overrides) -> dict:
    subject = {
        "id": "pkg/api",
        "label": "Public API",
        "root": "pkg/api",
        "member_files": ["pkg/api/__init__.py", "pkg/api/routes.py"],
        "exclusions": [],
        "rationale": "Owns HTTP entry points.",
        "locked": False,
    }
    subject.update(overrides)
    return subject


def _catalog(*subjects: dict) -> dict:
    return {"version": 1, "subjects": list(subjects)}


def test_fixture_catalog_reaches_graph_payload_without_replacing_parser_structure(tmp_path):
    project = _write_project(tmp_path, json.loads(FIXTURE_CATALOG.read_text(encoding="utf-8")))

    state = GraphState(str(project))
    module = next(n for n in state.payload()["nodes"] if n["id"] == "mod:pkg.api")
    member_file = next(n for n in state.payload()["nodes"] if n["id"] == "file:pkg/api/routes.py")
    subject = module["attrs"]["reading_subject"]

    assert module["origin"] == "parser"
    assert member_file["origin"] == "parser"
    assert member_file["attrs"]["reading_subject_id"] == "pkg/api"
    assert subject == {
        "id": "pkg/api",
        "label": "Public API",
        "root": "pkg/api",
        "member_files": ["pkg/api/__init__.py", "pkg/api/routes.py"],
        "exclusions": [],
        "rationale": "Owns HTTP entry points.",
        "locked": True,
    }


@pytest.mark.parametrize(
    ("subjects", "message"),
    [
        ([_subject(), _subject(label="Duplicate")], "duplicate subject id"),
        ([_subject(member_files=["pkg/api/missing.py"])], "missing member file"),
        ([_subject(member_files=["../outside.py"])], "outside the project"),
        ([_subject(id=".git", root=".git")], "excluded by project policy"),
        (
            [
                _subject(),
                _subject(
                    id="pkg",
                    root="pkg",
                    label="Package",
                    member_files=["pkg/api/routes.py"],
                ),
            ],
            "duplicate primary ownership",
        ),
    ],
)
def test_invalid_catalogs_are_rejected(tmp_path, subjects, message):
    project = _write_project(tmp_path, _catalog(*subjects))

    with pytest.raises(CatalogValidationError, match=message):
        load_catalog(project)


def test_subject_id_is_the_normalized_project_relative_root(tmp_path):
    project = _write_project(tmp_path, _catalog(_subject(id="agent-invented-id")))

    with pytest.raises(CatalogValidationError, match="stable id.*pkg/api"):
        load_catalog(project)


def test_locked_subject_survives_agent_catalog_refresh_and_process_restart(tmp_path):
    project = _write_project(tmp_path, _catalog(_subject(locked=True)))
    state = GraphState(str(project))
    refreshed_path = project / ".flowsight" / "reading-subjects.json"
    refreshed_path.write_text(json.dumps(_catalog()), encoding="utf-8")

    state.reindex()

    assert [subject.id for subject in state.catalog.subjects] == ["pkg/api"]
    assert state.catalog.subjects[0].locked is True
    module = next(n for n in state.payload()["nodes"] if n["id"] == "mod:pkg.api")
    assert module["attrs"]["reading_subject"]["locked"] is True

    restarted = GraphState(str(project))
    assert [subject.id for subject in restarted.catalog.subjects] == ["pkg/api"]


def test_non_package_subject_root_maps_to_member_file_nodes(tmp_path):
    project = _write_project(tmp_path)
    group = project / "pkg" / "api" / "group"
    group.mkdir()
    (group / "handler.py").write_text("def handle():\n    pass\n", encoding="utf-8")
    catalog_path = project / ".flowsight" / "reading-subjects.json"
    catalog_path.parent.mkdir()
    catalog_path.write_text(
        json.dumps(
            _catalog(
                _subject(
                    id="pkg/api/group",
                    root="pkg/api/group",
                    member_files=["pkg/api/group/handler.py"],
                )
            )
        ),
        encoding="utf-8",
    )
    catalog = load_catalog(project)

    doc = extract(project)
    apply_catalog(doc, catalog)

    handler = doc.node_by_id("file:pkg/api/group/handler.py")
    assert handler is not None
    assert handler.origin == "parser"
    assert handler.attrs["reading_subject"]["id"] == "pkg/api/group"


def test_missing_catalog_is_backward_compatible(tmp_path):
    project = _write_project(tmp_path)

    catalog = load_catalog(project)

    assert catalog == ReadingSubjectCatalog(version=1, subjects=())


def test_fixture_catalog_payload_reaches_browser_action_model(tmp_path):
    project = _write_project(tmp_path, json.loads(FIXTURE_CATALOG.read_text(encoding="utf-8")))
    payload_path = tmp_path / "graph.json"
    payload_path.write_text(json.dumps(GraphState(str(project)).payload()), encoding="utf-8")
    adapter_uri = (Path(__file__).parents[1] / "src" / "flowsight" / "web" / "adapter.js").as_uri()
    script = f"""
      import {{ deepReadAction }} from {json.dumps(adapter_uri)};
      import {{ readFileSync }} from 'node:fs';
      const graph = JSON.parse(readFileSync(process.argv[1], 'utf8'));
      const module = graph.nodes.find((node) => node.id === 'mod:pkg.api');
      process.stdout.write(JSON.stringify(deepReadAction(module)));
    """

    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(payload_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "subjectId": "pkg/api",
        "label": "Deep read this module",
    }
