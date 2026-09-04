"""Verified result acceptance and deep-read artifact serving (Issue #5)."""

from __future__ import annotations

import io
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from flowsight.server.app import GraphState, make_handler


FIXTURES = Path(__file__).parent / "fixtures"


def _state(tmp_path: Path) -> GraphState:
    project = tmp_path / "project"
    (project / "pkg" / "api").mkdir(parents=True)
    (project / "pkg" / "core").mkdir(parents=True)
    for package in (project / "pkg", project / "pkg" / "api", project / "pkg" / "core"):
        (package / "__init__.py").write_text("", encoding="utf-8")
    (project / "pkg" / "api" / "routes.py").write_text("def route():\n    return 'ok'\n", encoding="utf-8")
    (project / "pkg" / "core" / "service.py").write_text("def execute():\n    return 'ok'\n", encoding="utf-8")
    (project / ".flowsight").mkdir()
    subjects = []
    for root, label, file in (
        ("pkg/api", "Public API", "routes.py"),
        ("pkg/core", "Core", "service.py"),
    ):
        subjects.append({
            "id": root,
            "label": label,
            "root": root,
            "member_files": [f"{root}/__init__.py", f"{root}/{file}"],
            "exclusions": [],
            "rationale": label,
            "locked": False,
        })
    (project / ".flowsight" / "reading-subjects.json").write_text(
        json.dumps({"version": 1, "subjects": subjects}), encoding="utf-8"
    )
    return GraphState(str(project))


def _request(state: GraphState, subject_id: str = "pkg/api") -> dict:
    return state.request_refinement(subject_id, event_stream=io.StringIO())


def _stage_fixture(state: GraphState, status: dict, **result_overrides) -> Path:
    store = state.refinements
    job_id = status["job_id"]
    job_dir = store.job_dir(job_id)
    artifact = job_dir / "artifact.html"
    specification = job_dir / "specification.json"
    receipt = job_dir / "delivery-receipt.json"
    artifact.write_bytes((FIXTURES / "archify-artifact.html").read_bytes())
    specification.write_bytes((FIXTURES / "archify-specification.json").read_bytes())
    receipt_payload = json.loads((FIXTURES / "archify-receipt.json").read_text(encoding="utf-8"))
    receipt_payload.update({
        "job_id": job_id,
        "subject_id": status["subject_id"],
        "input_fingerprint": status["fingerprint"],
    })
    receipt.write_text(json.dumps(receipt_payload), encoding="utf-8")
    result = {
        "job_id": job_id,
        "subject_id": status["subject_id"],
        "input_fingerprint": status["fingerprint"],
        "artifact_path": artifact.relative_to(store.project_root).as_posix(),
        "specification_path": specification.relative_to(store.project_root).as_posix(),
        "receipt_path": receipt.relative_to(store.project_root).as_posix(),
    }
    result.update(result_overrides)
    result_path = job_dir / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    return result_path


def test_job_states_and_bounded_failure_diagnostic(tmp_path):
    state = _state(tmp_path)
    pending = _request(state)
    claimed = state.refinements.claim(pending["job_id"], agent_id="fixture-agent")
    generating = state.refinements.advance(claimed["job_id"], "generating")
    validating = state.refinements.advance(generating["job_id"], "validating")
    failed = state.refinements.fail(validating["job_id"], "x" * 5000)

    assert [claimed["status"], generating["status"], validating["status"], failed["status"]] == [
        "claimed", "generating", "validating", "failed"
    ]
    assert len(failed["diagnostic"]) <= 1000
    assert failed["artifact_available"] is False


def test_fixture_result_becomes_ready_and_is_served_same_origin(tmp_path):
    state = _state(tmp_path)
    pending = _request(state)
    state.refinements.claim(pending["job_id"], agent_id="fixture-agent")
    state.refinements.advance(pending["job_id"], "generating")
    state.refinements.advance(pending["job_id"], "validating")
    _stage_fixture(state, pending)

    ready = state.refinements.accept_result(pending["job_id"])

    assert ready["status"] == "ready"
    assert ready["artifact_available"] is True
    assert ready["artifact_url"] == f"/api/refinements/{pending['job_id']}/artifact"

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", ready["artifact_url"])
        response = conn.getresponse()
        assert response.status == 200
        assert b"Verified fixture deep read" in response.read()

        conn.request("GET", "/api/refinements/../../README.md/artifact")
        rejected = conn.getresponse()
        rejected.read()
        assert rejected.status in {400, 404}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_receipt", "receipt"),
        ("failed_delivery", "delivery receipt reports failure"),
        ("mismatched_fingerprint", "fingerprint"),
        ("outside_path", "outside the job directory"),
    ],
)
def test_untrustworthy_results_are_rejected(tmp_path, mutation, message):
    state = _state(tmp_path)
    pending = _request(state)
    state.refinements.claim(pending["job_id"], agent_id="fixture-agent")
    state.refinements.advance(pending["job_id"], "generating")
    state.refinements.advance(pending["job_id"], "validating")
    result_path = _stage_fixture(state, pending)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if mutation == "missing_receipt":
        (state.refinements.project_root / result["receipt_path"]).unlink()
    elif mutation == "failed_delivery":
        receipt_path = state.refinements.project_root / result["receipt_path"]
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["success"] = False
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    elif mutation == "mismatched_fingerprint":
        result["input_fingerprint"] = "wrong"
        result_path.write_text(json.dumps(result), encoding="utf-8")
    else:
        result["artifact_path"] = "README.md"
        result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        state.refinements.accept_result(pending["job_id"])
    assert state.refinements.get_status(pending["job_id"])["status"] == "failed"


def test_failed_result_does_not_break_another_ready_artifact(tmp_path):
    state = _state(tmp_path)
    first = _request(state, "pkg/api")
    state.refinements.claim(first["job_id"], agent_id="fixture-agent")
    state.refinements.advance(first["job_id"], "generating")
    state.refinements.advance(first["job_id"], "validating")
    _stage_fixture(state, first)
    state.refinements.accept_result(first["job_id"])

    second = _request(state, "pkg/core")
    state.refinements.claim(second["job_id"], agent_id="fixture-agent")
    state.refinements.fail(second["job_id"], "fixture failure")

    assert state.refinements.get_status(first["job_id"])["status"] == "ready"
    assert state.refinements.artifact_path(first["job_id"]).is_file()
