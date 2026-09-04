"""External Agent consumption and Archify delivery contract (Issue #6)."""

from __future__ import annotations

import io
import hashlib
import json
from pathlib import Path

import pytest

from flowsight.refinement.agent import AuthoredArchitecture, RefinementAgent
from flowsight.cli import main
from flowsight.refinement.jobs import JobStore


def _dossier(project: Path, subject_id: str = "pkg/api") -> dict:
    source = project / "pkg" / "api.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def route():\n    return 'ok'\n", encoding="utf-8")
    return {
        "contract_version": 1,
        "project": {"id": "project-1", "name": "fixture"},
        "subject": {
            "id": subject_id,
            "label": "Public API",
            "root": "pkg",
            "member_files": ["pkg/api.py"],
            "exclusions": [],
            "rationale": "Owns entry points.",
            "locked": False,
        },
        "source_scope": {"owned_files": ["pkg/api.py"]},
        "source_hashes": {"pkg/api.py": "fixture"},
        "nodes": {
            "internal": [
                {
                    "id": "function:pkg.api.route",
                    "type": "function",
                    "label": "route",
                    "origin": "parser",
                    "location": {"file": "pkg/api.py", "line": 1, "end_line": 2, "col": 0},
                    "signature": {"params": [], "returns": "", "decorators": [], "is_async": False},
                    "purpose": "",
                    "contract": None,
                    "data_flow_role": "",
                    "risk": None,
                    "fields": [],
                    "runtime": {},
                    "code_hash": "",
                    "attrs": {},
                }
            ],
            "boundary": [],
        },
        "relationships": {"internal": [], "boundary": []},
        "fingerprint": "a" * 64,
    }


def _architecture() -> AuthoredArchitecture:
    return AuthoredArchitecture(
        specification={
            "schema_version": 1,
            "diagram_type": "architecture",
            "meta": {
                "title": "Public API 模块深读",
                "locale": "zh-CN",
                "quality_profile": "showcase",
            },
            "components": [
                {
                    "id": "route",
                    "type": "backend",
                    "label": "route",
                    "sublabel": "入口 · parser",
                    "sources": [{"path": "pkg/api.py", "line": 1, "end_line": 2}],
                    "pos": [80, 120],
                    "size": [160, 72],
                }
            ],
            "boundaries": [{"kind": "region", "label": "内部 · Public API", "wraps": ["route"]}],
            "connections": [],
            "cards": [{"dot": "cyan", "title": "职责（LLM 建议）", "items": ["接收调用"]}],
        },
        reverse_id_map={"route": "function:pkg.api.route"},
    )


def _dossier_with_external_context(project: Path) -> dict:
    dossier = _dossier(project)
    external_path = project / "pkg" / "core.py"
    external_path.write_text("def execute(value: str) -> str:\n    return value\n", encoding="utf-8")
    external = {
        "id": "function:pkg.core.execute",
        "type": "function",
        "label": "execute",
        "origin": "parser",
        "location": {"file": "pkg/core.py", "line": 1, "end_line": 2, "col": 0},
        "signature": {
            "params": [{"name": "value", "type": "str", "default": ""}],
            "returns": "str",
            "decorators": [],
            "is_async": False,
        },
        "purpose": "",
        "contract": None,
        "data_flow_role": "",
        "risk": None,
        "fields": [],
        "runtime": {},
        "code_hash": "",
        "attrs": {},
        "context": {
            "owner": {"id": "pkg/core", "label": "Core"},
            "hop": 1,
            "directions": ["outgoing"],
            "evidence_origins": ["parser"],
            "justification": "",
        },
    }
    edge = {
        "source": "function:pkg.api.route",
        "target": external["id"],
        "type": "calls",
        "origin": "parser",
        "location": {"file": "pkg/api.py", "line": 2, "end_line": 0, "col": 0},
        "attrs": {},
    }
    dossier["nodes"]["boundary"] = [external]
    dossier["relationships"]["boundary"] = [edge]
    dossier["relationships"]["external_context"] = [edge]
    dossier["source_scope"]["external_files"] = ["pkg/core.py"]
    dossier["context"] = {
        "policy": {"max_external_subjects": 2, "max_external_nodes": 6},
        "external_subjects": [{"id": "pkg/core", "label": "Core"}],
        "selected_primary_node_count": 1,
        "omitted_primary_node_count": 0,
        "overflow": [],
    }
    return dossier


def _architecture_with_external_context() -> AuthoredArchitecture:
    authored = _architecture()
    authored.specification["components"].append({
        "id": "execute",
        "type": "external",
        "label": "execute",
        "sublabel": "execute(value: str) -> str · pkg/core.py:1 · parser",
        "tag": "Core · pkg/core",
        "pos": [340, 120],
        "size": [220, 72],
    })
    authored.specification["boundaries"] = [
        {"kind": "region", "label": "内部 · Public API", "wraps": ["route"]},
        {"kind": "region", "label": "外部上下文 · Core · pkg/core", "wraps": ["execute"]},
    ]
    authored.specification["connections"] = [
        {"from": "route", "to": "execute", "label": "calls"}
    ]
    authored.reverse_id_map["execute"] = "function:pkg.core.execute"
    return authored


class FixtureAuthor:
    def __init__(self, store: JobStore):
        self.store = store
        self.calls: list[dict] = []

    def author(self, request: dict, diagnostic: str = "") -> AuthoredArchitecture:
        assert self.store.get_status(request["job_id"])["status"] == "generating"
        assert set(request) == {
            "version", "job_id", "subject_id", "input_fingerprint", "project",
            "source_scope", "dossier", "created_at",
        }
        self.calls.append(request)
        return _architecture()


class FixtureArchify:
    version = "fixture-2.17"

    def __init__(self, store: JobStore, *, failures: int = 0, corrupt_hash: bool = False):
        self.store = store
        self.failures = failures
        self.corrupt_hash = corrupt_hash
        self.calls = 0

    def deliver(self, specification_path: Path, artifact_path: Path) -> dict:
        self.calls += 1
        request = json.loads((specification_path.parent / "request.json").read_text(encoding="utf-8"))
        assert self.store.get_status(request["job_id"])["status"] == "validating"
        if self.calls <= self.failures:
            raise ValueError(f"fixture validation failure {self.calls}")
        artifact_path.write_text("<!doctype html><title>checked architecture</title>", encoding="utf-8")
        specification_hash = hashlib.sha256(specification_path.read_bytes()).hexdigest()
        artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        return {
            "schemaVersion": 1,
            "ok": True,
            "command": "deliver",
            "type": "architecture",
            "specification": {
                "sha256": "0" * 64 if self.corrupt_hash else specification_hash,
                "bytes": specification_path.stat().st_size,
            },
            "artifact": {"sha256": artifact_hash, "bytes": artifact_path.stat().st_size},
            "validation": {"checksPassed": 9, "checkCount": 9, "errors": 0, "warnings": 0},
        }


def test_agent_scans_existing_pending_job_and_atomically_publishes_result(tmp_path):
    project = tmp_path / "project"
    store = JobStore(project)
    pending, _ = store.create_request(_dossier(project), event_stream=io.StringIO())
    author = FixtureAuthor(store)
    archify = FixtureArchify(store)

    ready = RefinementAgent(store, author, archify, agent_id="fixture-agent").process_next()

    assert ready is not None
    assert ready["status"] == "ready"
    assert archify.calls == 1
    assert len(author.calls) == 1
    job_dir = store.job_dir(pending["job_id"])
    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    receipt = json.loads(
        (store.project_root / ready["receipt_path"]).read_text(encoding="utf-8")
    )
    assert result["diagram_type"] == "architecture"
    assert store.artifact_path(pending["job_id"]).is_file()
    assert (store.project_root / ready["specification_path"]).is_file()
    assert json.loads(
        (store.project_root / ready["reverse_id_map_path"]).read_text(encoding="utf-8")
    ) == {
        "route": "function:pkg.api.route"
    }
    assert receipt["success"] is True
    assert receipt["archify_version"] == "fixture-2.17"
    assert receipt["archify_delivery"]["validation"]["checksPassed"] == 9


def test_agent_releases_claim_when_immutable_request_is_missing(tmp_path):
    project = tmp_path / "project"
    store = JobStore(project)
    broken, _ = store.create_request(_dossier(project, "pkg/broken"), event_stream=io.StringIO())
    healthy, _ = store.create_request(_dossier(project, "pkg/healthy"), event_stream=io.StringIO())
    store.request_path(broken["job_id"]).unlink()
    agent = RefinementAgent(
        store, FixtureAuthor(store), FixtureArchify(store), agent_id="fixture-agent"
    )

    failed = agent.process_next()

    assert failed is not None
    assert failed["status"] == "failed"
    claimed = store.claim(healthy["job_id"], agent_id="recovery-agent")
    assert claimed["status"] == "claimed"


def test_claim_is_atomic_across_store_instances_and_pending_order_is_stable(tmp_path):
    project = tmp_path / "project"
    first_store = JobStore(project)
    first, _ = first_store.create_request(_dossier(project, "pkg/first"), event_stream=io.StringIO())
    second, _ = first_store.create_request(_dossier(project, "pkg/second"), event_stream=io.StringIO())
    recovering_store = JobStore(project)

    assert [status["job_id"] for status in recovering_store.pending()] == [
        first["job_id"], second["job_id"]
    ]
    claimed = first_store.claim(first["job_id"], agent_id="agent-a")
    assert claimed["status"] == "claimed"
    with pytest.raises(ValueError, match="already active"):
        recovering_store.claim(first["job_id"], agent_id="agent-b")
    with pytest.raises(ValueError, match="already active"):
        recovering_store.claim(second["job_id"], agent_id="agent-b")


def test_agent_stops_after_two_repair_rounds_and_records_bounded_failure(tmp_path):
    project = tmp_path / "project"
    store = JobStore(project)
    pending, _ = store.create_request(_dossier(project), event_stream=io.StringIO())
    author = FixtureAuthor(store)
    archify = FixtureArchify(store, failures=3)

    result = RefinementAgent(store, author, archify, agent_id="fixture-agent").process_next()

    assert result is not None
    assert result["status"] == "failed"
    assert archify.calls == 3  # first candidate plus two focused repairs
    assert len(author.calls) == 3
    assert "fixture validation failure 3" in result["diagnostic"]
    assert len(result["diagnostic"]) <= 1000
    assert not (store.job_dir(pending["job_id"]) / "result.json").exists()


def test_agent_rejects_invented_topology_before_delivery(tmp_path):
    project = tmp_path / "project"
    store = JobStore(project)
    store.create_request(_dossier(project), event_stream=io.StringIO())
    authored = _architecture()
    authored.specification["components"].append({
        "id": "invented", "type": "backend", "label": "invented", "pos": [300, 120],
        "size": [160, 72],
    })
    authored.specification["connections"] = [{"from": "route", "to": "invented"}]

    class InventingAuthor:
        def author(self, request, diagnostic=""):
            return authored

    archify = FixtureArchify(store)
    failed = RefinementAgent(store, InventingAuthor(), archify, agent_id="fixture-agent").process_next()

    assert failed is not None
    assert failed["status"] == "failed"
    assert archify.calls == 0
    assert "reverse mapping" in failed["diagnostic"]


def test_agent_rejects_delivery_receipt_that_does_not_bind_exact_bytes(tmp_path):
    project = tmp_path / "project"
    store = JobStore(project)
    store.create_request(_dossier(project), event_stream=io.StringIO())

    failed = RefinementAgent(
        store,
        FixtureAuthor(store),
        FixtureArchify(store, corrupt_hash=True),
        agent_id="fixture-agent",
        max_repair_rounds=0,
    ).process_next()

    assert failed is not None
    assert failed["status"] == "failed"
    assert "specification SHA-256 mismatch" in failed["diagnostic"]


def test_agent_accepts_external_context_with_owner_location_and_distinct_boundary(tmp_path):
    project = tmp_path / "project"
    store = JobStore(project)
    dossier = _dossier_with_external_context(project)
    store.create_request(dossier, event_stream=io.StringIO())

    class ContextAuthor:
        def author(self, request, diagnostic=""):
            return _architecture_with_external_context()

    ready = RefinementAgent(
        store, ContextAuthor(), FixtureArchify(store), agent_id="fixture-agent"
    ).process_next()

    assert ready is not None
    assert ready["status"] == "ready"


@pytest.mark.parametrize("mutation", ["owner", "location", "signature", "visual_type", "boundary"])
def test_agent_rejects_context_that_hides_ownership_or_module_boundary(tmp_path, mutation):
    project = tmp_path / "project"
    store = JobStore(project)
    store.create_request(_dossier_with_external_context(project), event_stream=io.StringIO())
    authored = _architecture_with_external_context()
    external = authored.specification["components"][1]
    if mutation == "owner":
        external.pop("tag")
    elif mutation == "location":
        external["sublabel"] = "execute(value: str) -> str · parser"
    elif mutation == "signature":
        external["sublabel"] = "execute · pkg/core.py:1 · parser"
    elif mutation == "visual_type":
        external["type"] = "backend"
    else:
        authored.specification["boundaries"] = authored.specification["boundaries"][:1]

    class HiddenContextAuthor:
        def author(self, request, diagnostic=""):
            return authored

    archify = FixtureArchify(store)
    failed = RefinementAgent(
        store,
        HiddenContextAuthor(),
        archify,
        agent_id="fixture-agent",
        max_repair_rounds=0,
    ).process_next()

    assert failed is not None
    assert failed["status"] == "failed"
    assert archify.calls == 0
    assert "external context" in failed["diagnostic"]


def test_agent_enforces_internal_primary_budget_and_truthful_helper_aggregate(tmp_path):
    project = tmp_path / "project"
    store = JobStore(project)
    dossier = _dossier(project)
    for index in range(1, 9):
        dossier["nodes"]["internal"].append({
            **dossier["nodes"]["internal"][0],
            "id": f"function:pkg.api.helper_{index}",
            "label": f"helper_{index}",
        })
    store.create_request(dossier, event_stream=io.StringIO())

    class UnderCuratingAuthor:
        def author(self, request, diagnostic=""):
            return _architecture()

    failed = RefinementAgent(
        store,
        UnderCuratingAuthor(),
        FixtureArchify(store),
        agent_id="fixture-agent",
        max_repair_rounds=0,
    ).process_next()

    assert failed is not None
    assert failed["status"] == "failed"
    assert "at least 8 internal primary nodes" in failed["diagnostic"]


def test_parser_edge_cannot_be_presented_as_runtime_observation(tmp_path):
    project = tmp_path / "project"
    store = JobStore(project)
    store.create_request(_dossier_with_external_context(project), event_stream=io.StringIO())
    authored = _architecture_with_external_context()
    authored.specification["connections"][0].update(
        label="runtime observed", variant="emphasis"
    )

    class SimulatingAuthor:
        def author(self, request, diagnostic=""):
            return authored

    failed = RefinementAgent(
        store,
        SimulatingAuthor(),
        FixtureArchify(store),
        agent_id="fixture-agent",
        max_repair_rounds=0,
    ).process_next()

    assert failed is not None
    assert failed["status"] == "failed"
    assert "runtime presentation requires runtime evidence" in failed["diagnostic"]


def test_runtime_context_must_be_visibly_observed_and_emphasized(tmp_path):
    project = tmp_path / "project"
    store = JobStore(project)
    dossier = _dossier_with_external_context(project)
    for group in ("boundary", "external_context"):
        dossier["relationships"][group][0]["origin"] = "runtime"
    dossier["nodes"]["boundary"][0]["context"]["evidence_origins"] = ["runtime"]
    store.create_request(dossier, event_stream=io.StringIO())
    authored = _architecture_with_external_context()

    class RuntimeAuthor:
        def author(self, request, diagnostic=""):
            return authored

    archify = FixtureArchify(store)
    failed = RefinementAgent(
        store, RuntimeAuthor(), archify, agent_id="fixture-agent", max_repair_rounds=0
    ).process_next()

    assert failed is not None
    assert failed["status"] == "failed"
    assert archify.calls == 0
    assert "visibly marked as observed" in failed["diagnostic"]


def test_context_overflow_must_be_acknowledged_with_owner_and_count(tmp_path):
    project = tmp_path / "project"
    store = JobStore(project)
    dossier = _dossier_with_external_context(project)
    dossier["context"]["omitted_primary_node_count"] = 2
    dossier["context"]["overflow"] = [{
        "owner": {"id": "pkg/core", "label": "Core"},
        "node_count": 2,
        "node_types": {"function": 2},
        "directions": {"outgoing": 2},
        "evidence_origins": ["parser"],
        "relationship_count": 2,
    }]
    store.create_request(dossier, event_stream=io.StringIO())

    class SilentOverflowAuthor:
        def author(self, request, diagnostic=""):
            return _architecture_with_external_context()

    archify = FixtureArchify(store)
    failed = RefinementAgent(
        store,
        SilentOverflowAuthor(),
        archify,
        agent_id="fixture-agent",
        max_repair_rounds=0,
    ).process_next()

    assert failed is not None
    assert failed["status"] == "failed"
    assert archify.calls == 0
    assert "external context overflow" in failed["diagnostic"]


def test_refine_once_cli_consumes_agent_authored_files(tmp_path, monkeypatch, capsys):
    project = tmp_path / "project"
    store = JobStore(project)
    pending, _ = store.create_request(_dossier(project), event_stream=io.StringIO())
    specification_path = tmp_path / "architecture.json"
    reverse_map_path = tmp_path / "reverse-map.json"
    specification_path.write_text(json.dumps(_architecture().specification), encoding="utf-8")
    reverse_map_path.write_text(json.dumps(_architecture().reverse_id_map), encoding="utf-8")
    monkeypatch.setattr(
        "flowsight.refinement.agent.ArchifyRunner",
        lambda unused_root: FixtureArchify(JobStore(project)),
    )

    exit_code = main([
        "refine", str(project), "--once", "--spec", str(specification_path),
        "--reverse-map", str(reverse_map_path), "--archify-root", str(tmp_path),
        "--agent-id", "fixture-cli-agent",
    ])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["job_id"] == pending["job_id"]
    assert output["status"] == "ready"
