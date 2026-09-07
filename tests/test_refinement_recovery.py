"""Regression coverage for refinement freshness, recovery and final acceptance."""

import hashlib
import io
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from flowsight.refinement.agent import RefinementAgent
from flowsight.refinement.jobs import JobStore
from flowsight.refinement.dossier import build_dossier
from flowsight.server.app import GraphState
from tests.test_refinement_agent import _architecture, _dossier, FixtureArchify, FixtureAuthor
from tests.test_refinement_results import _state, _request, _stage_fixture


def _ready(state):
    job = _request(state)
    store = state.refinements
    store.claim(job["job_id"], agent_id="fixture")
    store.advance(job["job_id"], "generating")
    store.advance(job["job_id"], "validating")
    _stage_fixture(state, job)
    return store.accept_result(job["job_id"])


def test_changed_source_is_stale_and_keeps_verified_fallback(tmp_path):
    state = _state(tmp_path)
    ready = _ready(state)
    source = Path(state.project_path) / "pkg/api/routes.py"
    source.write_text("def route():\n    return 'changed'\n", encoding="utf-8")
    state.reindex()

    current = state.refinements.latest_status("pkg/api")
    assert current["status"] == "stale"
    assert current["stale_reason"]
    assert current["artifact_available"] is False
    assert current["fallback_artifact_available"] is True
    assert state.refinements.artifact_path(ready["job_id"]).is_file()
    replacement = _request(state)
    assert replacement["job_id"] != ready["job_id"]
    state.refinements.fail(replacement["job_id"], "delivery failed")
    assert state.refinements.latest_status("pkg/api")["fallback_job_id"] == ready["job_id"]


def test_changed_source_is_detected_without_reindex(tmp_path):
    state = _state(tmp_path)
    ready = _ready(state)
    (Path(state.project_path) / "pkg/api/routes.py").unlink()
    assert state.refinements.get_status(ready["job_id"])["status"] == "stale"


def test_subject_change_invalidates_ready_artifact(tmp_path):
    state = _state(tmp_path)
    _ready(state)
    path = Path(state.project_path) / ".flowsight/reading-subjects.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    catalog["subjects"][0]["rationale"] = "Updated responsibility"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    state.reindex()
    assert state.refinements.latest_status("pkg/api")["status"] == "stale"


def test_unchanged_reindex_and_unrelated_source_preserve_ready(tmp_path):
    state = _state(tmp_path)
    _ready(state)
    (Path(state.project_path) / "pkg/core/service.py").write_text("# unrelated\n", encoding="utf-8")
    state.reindex()
    assert state.refinements.latest_status("pkg/api")["status"] == "ready"


def test_result_for_source_changed_during_generation_preserves_previous_output(tmp_path):
    state = _state(tmp_path)
    previous = _ready(state)
    source = Path(state.project_path) / "pkg/api/routes.py"
    source.write_text("def route():\n    return 2\n", encoding="utf-8")
    state.reindex()
    job = _request(state)
    store = state.refinements
    store.claim(job["job_id"], agent_id="fixture")
    store.advance(job["job_id"], "generating")
    store.advance(job["job_id"], "validating")
    _stage_fixture(state, job)
    source.write_text("def route():\n    return 3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Source changed"):
        store.accept_result(job["job_id"])
    assert store.latest_status("pkg/api")["fallback_job_id"] == previous["job_id"]
    assert store.artifact_path(previous["job_id"]).is_file()


def test_included_external_source_change_invalidates_artifact(tmp_path):
    from flowsight.server.app import GraphState
    from tests.test_refinement_jobs import _project

    state = GraphState(str(_project(tmp_path)))
    _ready(state)
    source = Path(state.project_path) / "pkg/core/service.py"
    source.write_text(source.read_text(encoding="utf-8") + "\n# changed dependency\n", encoding="utf-8")
    state.reindex()
    assert state.refinements.latest_status("pkg/api")["status"] == "stale"


def test_reindex_during_generation_rejects_changed_subject_definition(tmp_path):
    state = _state(tmp_path)
    job = _request(state)
    store = state.refinements
    store.claim(job["job_id"], agent_id="fixture")
    store.advance(job["job_id"], "generating")
    store.advance(job["job_id"], "validating")
    _stage_fixture(state, job)
    catalog_path = Path(state.project_path) / ".flowsight/reading-subjects.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["subjects"][0]["rationale"] = "Responsibility changed during delivery"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    state.reindex()
    with pytest.raises(ValueError, match="dossier facts changed"):
        store.accept_result(job["job_id"])
    assert store.get_status(job["job_id"])["status"] == "failed"


def test_freshness_replays_extensions_omitted_by_context_budget(tmp_path):
    from tests.test_refinement_context import _fixture

    project, doc, catalog = _fixture(tmp_path)
    dossier = build_dossier(doc, catalog, "pkg/api", project,
                            critical_path_extensions={"core-deep": "Completes normalization."})
    state = GraphState.__new__(GraphState)
    state.doc, state.catalog, state.project_path = doc, catalog, str(project)
    assert state._refinement_fingerprint({"dossier": dossier, "subject_id": "pkg/api"}) == dossier["fingerprint"]


@pytest.mark.parametrize("field,value", [("components", [None]), ("meta", []), ("connections", [None])])
def test_malformed_authorship_fails_cleanly_and_releases_claim(tmp_path, field, value):
    store = JobStore(tmp_path)
    job, _ = store.create_request(_dossier(tmp_path), event_stream=io.StringIO())

    class MalformedAuthor:
        def author(self, request, diagnostic=""):
            authored = _architecture()
            authored.specification[field] = value
            return authored

    result = RefinementAgent(store, MalformedAuthor(), FixtureArchify(store), agent_id="fixture").process_next()
    assert result["status"] == "failed"
    assert result["diagnostic"]
    retry, _ = store.create_request(_dossier(tmp_path), event_stream=io.StringIO())
    assert store.claim(retry["job_id"], agent_id="retry")["status"] == "claimed"


def test_final_acceptance_rejects_connections_without_dossier_evidence(tmp_path):
    state = _state(tmp_path)
    job = _request(state)
    store = state.refinements
    store.claim(job["job_id"], agent_id="fixture")
    store.advance(job["job_id"], "generating")
    store.advance(job["job_id"], "validating")
    result_path = _stage_fixture(state, job)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    specification_path = store.project_root / result["specification_path"]
    specification = json.loads(specification_path.read_text(encoding="utf-8"))
    specification["connections"] = [{"from": "fixture", "to": "fixture", "label": "calls"}]
    specification_path.write_text(json.dumps(specification), encoding="utf-8")
    receipt_path = store.project_root / result["receipt_path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    contents = specification_path.read_bytes()
    receipt["archify_delivery"]["specification"] = {
        "sha256": hashlib.sha256(contents).hexdigest(), "bytes": len(contents),
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="evidence"):
        store.accept_result(job["job_id"])
    assert store.get_status(job["job_id"])["status"] == "failed"


def test_stopped_claiming_process_does_not_block_pending_queue(tmp_path):
    store = JobStore(tmp_path)
    first, _ = store.create_request(_dossier(tmp_path), event_stream=io.StringIO())
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    script = (
        "import sys; from flowsight.refinement.jobs import JobStore; "
        "JobStore(sys.argv[1]).claim(sys.argv[2], agent_id='child'); "
        "print('claimed', flush=True); sys.stdin.read()"
    )
    child = subprocess.Popen([sys.executable, "-c", script, str(tmp_path), first["job_id"]],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env)
    try:
        assert child.stdout.readline().strip() == "claimed"
        second, _ = store.create_request(_dossier(tmp_path, "pkg/second"), event_stream=io.StringIO())
        with pytest.raises(ValueError, match="active"):
            JobStore(tmp_path).claim(second["job_id"], agent_id="other")
    finally:
        child.terminate()
        child.communicate(timeout=5)
    restarted = JobStore(tmp_path)
    result = RefinementAgent(restarted, FixtureAuthor(restarted), FixtureArchify(restarted),
                             agent_id="restarted").process_next()
    assert result is not None
    assert result["status"] == "ready"
    assert restarted.get_status(first["job_id"])["status"] == "failed"


def test_cancellation_cannot_overwrite_concurrent_claim(tmp_path, monkeypatch):
    store = JobStore(tmp_path)
    job, _ = store.create_request(_dossier(tmp_path), event_stream=io.StringIO())
    worker = JobStore(tmp_path)
    read_pending, release_cancel, claim_started, claim_finished = (threading.Event() for _ in range(4))
    original = store.get_status
    outcomes = {}

    def paused_read(job_id):
        status = original(job_id)
        read_pending.set()
        assert release_cancel.wait(5)
        return status

    def claim():
        claim_started.set()
        try:
            outcomes["claim"] = worker.claim(job["job_id"], agent_id="worker")
        except ValueError:
            outcomes["claim"] = "rejected"
        finally:
            claim_finished.set()

    monkeypatch.setattr(store, "get_status", paused_read)
    cancel_thread = threading.Thread(target=lambda: outcomes.update(cancel=store.cancel(job["job_id"])))
    claim_thread = threading.Thread(target=claim)
    cancel_thread.start()
    try:
        assert read_pending.wait(5)
        claim_thread.start()
        assert claim_started.wait(5)
        assert not claim_finished.wait(0.2)
    finally:
        release_cancel.set()
        cancel_thread.join(5)
        if claim_thread.ident is not None:
            claim_thread.join(5)
    assert outcomes["cancel"]["status"] == "cancelled"
    assert outcomes["claim"] == "rejected"
