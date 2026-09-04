"""Durable browser-to-Agent refinement protocol (GitHub issue #4)."""

from __future__ import annotations

import io
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from flowsight.refinement.dossier import build_dossier
from flowsight.refinement.jobs import JobStore
from flowsight.server.app import GraphState, make_handler


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "pkg" / "api").mkdir(parents=True)
    (project / "pkg" / "core").mkdir(parents=True)
    for package in (project / "pkg", project / "pkg" / "api", project / "pkg" / "core"):
        (package / "__init__.py").write_text("", encoding="utf-8")
    (project / "pkg" / "api" / "routes.py").write_text(
        "from pkg.core.service import execute\n\ndef route(name: str) -> str:\n    return execute(name)\n",
        encoding="utf-8",
    )
    (project / "pkg" / "core" / "service.py").write_text(
        "def normalize(name: str) -> str:\n    return name.upper()\n\n"
        "def execute(name: str) -> str:\n    return normalize(name)\n",
        encoding="utf-8",
    )
    (project / ".flowsight").mkdir()
    catalog = {
        "version": 1,
        "subjects": [
            {
                "id": "pkg/api",
                "label": "Public API",
                "root": "pkg/api",
                "member_files": ["pkg/api/__init__.py", "pkg/api/routes.py"],
                "exclusions": [],
                "rationale": "Owns request entry points.",
                "locked": False,
            },
            {
                "id": "pkg/core",
                "label": "Core service",
                "root": "pkg/core",
                "member_files": ["pkg/core/__init__.py", "pkg/core/service.py"],
                "exclusions": [],
                "rationale": "Owns core behavior.",
                "locked": False,
            },
        ],
    }
    (project / ".flowsight" / "reading-subjects.json").write_text(
        json.dumps(catalog), encoding="utf-8"
    )
    return project


def test_dossier_contains_owned_facts_and_boundary_relationships(tmp_path):
    project = _project(tmp_path)
    state = GraphState(str(project))

    dossier = build_dossier(state.doc, state.catalog, "pkg/api", project)

    assert dossier["subject"]["id"] == "pkg/api"
    assert dossier["source_scope"]["owned_files"] == [
        "pkg/api/__init__.py", "pkg/api/routes.py"
    ]
    assert dossier["source_scope"]["external_files"] == ["pkg/core/service.py"]
    internal = dossier["nodes"]["internal"]
    assert any(node["label"] == "route" and node["signature"]["returns"] == "str" for node in internal)
    assert all(node["origin"] == "parser" for node in internal)
    boundary = dossier["relationships"]["boundary"]
    assert any(edge["type"] == "calls" and edge["origin"] == "parser" for edge in boundary)
    assert dossier["fingerprint"]


def test_identical_request_is_reused_and_event_follows_durable_commit(tmp_path):
    project = _project(tmp_path)
    state = GraphState(str(project))
    dossier = build_dossier(state.doc, state.catalog, "pkg/api", project)
    writes: list[dict] = []

    class InspectingStream(io.StringIO):
        def write(self, value):
            event = json.loads(value)
            assert (project / event["request_path"]).is_file()
            writes.append(event)
            return super().write(value)

    stream = InspectingStream()
    store = JobStore(project)
    first, created = store.create_request(dossier, event_stream=stream)
    request_before = store.request_path(first["job_id"]).read_bytes()
    second, created_again = store.create_request(dossier, event_stream=stream)

    assert created is True
    assert created_again is False
    assert second["job_id"] == first["job_id"]
    assert store.request_path(first["job_id"]).read_bytes() == request_before
    assert len(writes) == 1
    assert writes[0]["event"] == "refinement.requested"
    assert set(writes[0]) == {
        "event", "job_id", "subject_id", "project_id", "request_path", "expected_result_path"
    }
    assert "source" not in stream.getvalue().lower()


def test_browser_request_to_waiting_status_end_to_end(tmp_path):
    project = _project(tmp_path)
    events = io.StringIO()
    state = GraphState(str(project))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state, event_stream=events))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        body = json.dumps({"subject_id": "pkg/api"})
        conn.request("POST", "/api/refinements", body, {"Content-Type": "application/json"})
        response = conn.getresponse()
        created = json.loads(response.read())
        assert response.status == 202
        assert created["status"] == "pending"
        assert created["display"] == "Waiting for Agent"

        conn.request("GET", f"/api/refinements/{created['job_id']}")
        polled_response = conn.getresponse()
        polled = json.loads(polled_response.read())
        assert polled_response.status == 200
        assert polled["stage"] == "waiting_for_agent"
        assert polled["artifact_available"] is False

        request = json.loads(state.refinements.request_path(created["job_id"]).read_text(encoding="utf-8"))
        assert request["dossier"]["subject"]["id"] == "pkg/api"
        assert json.loads(events.getvalue())["job_id"] == created["job_id"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_request_accepts_evidenced_critical_path_extension(tmp_path):
    project = _project(tmp_path)
    state = GraphState(str(project))
    extension_id = next(node.id for node in state.doc.nodes if node.label == "normalize")

    status = state.request_refinement(
        "pkg/api",
        event_stream=io.StringIO(),
        critical_path_extensions={extension_id: "Keeps the evidenced call path explicit."},
    )

    request = json.loads(state.refinements.request_path(status["job_id"]).read_text(encoding="utf-8"))
    extension = next(
        node for node in request["dossier"]["nodes"]["boundary"] if node["id"] == extension_id
    )
    assert extension["context"]["justification"] == "Keeps the evidenced call path explicit."


def test_request_rejects_unknown_subject_and_pending_job_can_be_cancelled(tmp_path):
    project = _project(tmp_path)
    state = GraphState(str(project))

    with pytest.raises(KeyError, match="unknown reading subject"):
        state.request_refinement("missing", event_stream=io.StringIO())

    status = state.request_refinement("pkg/api", event_stream=io.StringIO())
    cancelled = state.refinements.cancel(status["job_id"])
    assert cancelled["status"] == "cancelled"
