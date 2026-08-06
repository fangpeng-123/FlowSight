"""Pipeline end-to-end (the primary test seam, spec "Testing Decisions").

fixture project in -> graph JSON document out. Asserts the document conforms to
the 05 schema: skeleton correctness (nodes/edges/attributes), trust tags
(parser vs llm vs runtime), and JSON round-trip. The LLM is stubbed in ticket 03;
this seam asserts *attachment* plumbing, never LLM content.
"""

import json

from flowsight import schema as S
from flowsight.skeleton.extractor import extract


def test_pipeline_emits_valid_graph_json(fixture_root):
    doc = extract(fixture_root)
    payload = S.doc_to_dict(doc)

    # top-level shape
    assert set(payload) == {"project", "nodes", "edges"}
    assert payload["project"]["name"]
    assert payload["project"]["python"]

    # JSON-serializable
    text = json.dumps(payload, ensure_ascii=False)
    assert json.loads(text) == payload

    # round-trips back to typed objects
    back = S.doc_from_dict(payload)
    assert len(back.nodes) == len(doc.nodes)
    assert len(back.edges) == len(doc.edges)


def test_pipeline_schema_conformance(fixture_root):
    payload = S.doc_to_dict(extract(fixture_root))
    valid_nodes = {S.MODULE, S.FILE, S.FUNCTION, S.CLASS, S.EXTERNAL, S.DOMAIN_ENTITY}
    valid_edges = {S.CONTAINS, S.IMPORTS, S.CALLS, S.REFERENCES,
                   S.PRODUCES, S.CONSUMES, S.TRANSFORMS, S.DATA_FLOW}
    valid_origins = {S.PARSER, S.LLM, S.RUNTIME}

    node_ids = set()
    for n in payload["nodes"]:
        assert n["type"] in valid_nodes, n
        assert n["origin"] in valid_origins, n
        assert n["id"] not in node_ids, f"duplicate node id {n['id']}"
        node_ids.add(n["id"])

    for e in payload["edges"]:
        assert e["type"] in valid_edges, e
        assert e["origin"] in valid_origins, e
        assert e["source"] in node_ids, f"edge dangling source {e['source']}"
        assert e["target"] in node_ids, f"edge dangling target {e['target']}"
        if e["type"] in (S.CALLS, S.IMPORTS, S.REFERENCES):
            assert e["location"] and e["location"]["line"] > 0


def test_pipeline_trust_tags_static_skeleton(fixture_root):
    """In ticket 01, every node/edge is parser/trusted; llm+runtime arrive later."""
    payload = S.doc_to_dict(extract(fixture_root))
    for n in payload["nodes"]:
        assert n["origin"] == S.PARSER
    for e in payload["edges"]:
        assert e["origin"] == S.PARSER


def test_pipeline_skeleton_completeness(fixture_root):
    """The fixture's known structure is fully recovered by the skeleton."""
    payload = S.doc_to_dict(extract(fixture_root))
    types = {n["type"] for n in payload["nodes"]}
    assert {S.MODULE, S.FILE, S.FUNCTION, S.CLASS, S.EXTERNAL}.issubset(types)

    etypes = {e["type"] for e in payload["edges"]}
    assert {S.CONTAINS, S.IMPORTS, S.CALLS, S.REFERENCES}.issubset(etypes)

    # at least the 7-step pipeline calls
    calls = [e for e in payload["edges"] if e["type"] == S.CALLS]
    assert len(calls) >= 7
    # external (third-party) separated from project code
    externals = [n for n in payload["nodes"] if n["type"] == S.EXTERNAL]
    assert any(n["label"] == "requests" for n in externals)


def test_pipeline_function_code_hash_stable(fixture_root):
    """code_hash is deterministic across runs (enrichment cache key)."""
    d1 = S.doc_to_dict(extract(fixture_root))
    d2 = S.doc_to_dict(extract(fixture_root))
    h1 = {n["id"]: n["code_hash"] for n in d1["nodes"] if n["type"] == S.FUNCTION}
    h2 = {n["id"]: n["code_hash"] for n in d2["nodes"] if n["type"] == S.FUNCTION}
    assert h1 == h2
    assert all(h for h in h1.values())
