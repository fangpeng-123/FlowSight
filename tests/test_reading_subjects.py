"""Reading Subject Catalog public contract (GitHub issue #3)."""

from __future__ import annotations

import json
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
        "rationale": "Owns HTTP entry points.",
        "locked": True,
    }


@pytest.mark.parametrize(
    ("subjects", "message"),
    [
        ([_subject(), _subject(label="Duplicate")], "duplicate subject id"),
        ([_subject(member_files=["pkg/api/missing.py"])], "missing member file"),
        ([_subject(member_files=["../outside.py"])], "outside the project"),
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


def test_locked_subject_survives_agent_catalog_refresh(tmp_path):
    project = _write_project(tmp_path, _catalog(_subject(locked=True)))
    state = GraphState(str(project))
    refreshed_path = project / ".flowsight" / "reading-subjects.json"
    refreshed_path.write_text(json.dumps(_catalog()), encoding="utf-8")

    state.reindex()

    assert [subject.id for subject in state.catalog.subjects] == ["pkg/api"]
    assert state.catalog.subjects[0].locked is True
    module = next(n for n in state.payload()["nodes"] if n["id"] == "mod:pkg.api")
    assert module["attrs"]["reading_subject"]["locked"] is True


def test_apply_catalog_rejects_a_root_without_a_parser_module(tmp_path):
    project = _write_project(tmp_path, _catalog(_subject(id="pkg/api/group", root="pkg/api/group")))
    (project / "pkg" / "api" / "group").mkdir()
    catalog = load_catalog(project)

    with pytest.raises(CatalogValidationError, match="does not map to a parser module"):
        apply_catalog(extract(project), catalog)


def test_missing_catalog_is_backward_compatible(tmp_path):
    project = _write_project(tmp_path)

    catalog = load_catalog(project)

    assert catalog == ReadingSubjectCatalog(version=1, subjects=())
