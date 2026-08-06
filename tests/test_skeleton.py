"""Skeleton extractor unit tests (decision 02/04/05) - the fixture's known graph.

The voice_agent fixture is a hand-written mini codebase mirroring the prototype's
fake data, so we assert the extractor recovers its exact structure: nodes, edges,
signatures, fields, line offsets, and trust tags.
"""

from flowsight import schema as S
from flowsight.skeleton.extractor import extract
from tests.helpers import (
    by_type,
    edges_of,
    find_class,
    find_func,
    find_node,
    has_edge,
)


def test_fixture_indexed_at_package_parent(fixture_root):
    doc = extract(fixture_root)
    assert doc.project["name"]
    assert len(doc.nodes) > 0


# ---- node types present ----

def test_all_node_types_present(fixture_root):
    doc = extract(fixture_root)
    types = {n.type for n in doc.nodes}
    assert S.MODULE in types
    assert S.FILE in types
    assert S.FUNCTION in types
    assert S.CLASS in types
    assert S.EXTERNAL in types


def test_modules_are_the_six_packages(fixture_root):
    doc = extract(fixture_root)
    dotted = sorted(n.attrs.get("dotted", "") for n in by_type(doc, S.MODULE))
    assert "voice_agent" in dotted
    assert "voice_agent.audio_in" in dotted
    assert "voice_agent.asr" in dotted
    assert "voice_agent.llm" in dotted
    assert "voice_agent.tts" in dotted
    assert "voice_agent.audio_out" in dotted


def test_external_requests_node(fixture_root):
    doc = extract(fixture_root)
    ext = find_node(doc, "requests", S.EXTERNAL)
    assert ext is not None
    assert ext.attrs.get("installed") is False  # not installed in the test env


def test_pipeline_functions_present(fixture_root):
    doc = extract(fixture_root)
    for q in ["run", "receive_chunk", "is_utterance_end", "transcribe", "synthesize"]:
        assert find_func(doc, q) is not None, f"missing function {q}"
    for q in ["VADDetector.detect", "LLMClient.generate", "Player.play"]:
        assert find_func(doc, q) is not None, f"missing method {q}"


def test_domain_dataclasses_present(fixture_root):
    doc = extract(fixture_root)
    for name in ["AudioChunk", "Transcript", "LLMMessage", "TTSAudio"]:
        c = find_class(doc, name)
        assert c is not None, f"missing class {name}"
        assert c.attrs.get("is_dataclass") is True


# ---- edge types present ----

def test_all_four_edge_types_present(fixture_root):
    doc = extract(fixture_root)
    types = {e.type for e in doc.edges}
    assert {S.CONTAINS, S.IMPORTS, S.CALLS, S.REFERENCES}.issubset(types)


def test_calls_edges_recover_the_pipeline(fixture_root):
    """run() orchestrates the full chain; calls edges must capture it."""
    doc = extract(fixture_root)
    run = find_func(doc, "run")
    assert run is not None
    callees = {
        e.target for e in edges_of(doc, S.CALLS) if e.source == run.id
    }
    expected = [
        find_func(doc, "receive_chunk"),
        find_func(doc, "VADDetector.detect"),
        find_func(doc, "is_utterance_end"),
        find_func(doc, "transcribe"),
        find_func(doc, "LLMClient.generate"),
        find_func(doc, "synthesize"),
        find_func(doc, "Player.play"),
    ]
    assert all(f is not None for f in expected)
    for f in expected:
        assert f.id in callees, f"run should call {f.label}"


def test_references_capture_class_instantiations(fixture_root):
    doc = extract(fixture_root)
    assert has_edge(doc, "run", "VADDetector", S.REFERENCES)
    assert has_edge(doc, "run", "LLMClient", S.REFERENCES)
    assert has_edge(doc, "run", "Player", S.REFERENCES)


def test_references_capture_produces_in_returns(fixture_root):
    """receive_chunk returns AudioChunk(...) -> a reference (produce) edge."""
    doc = extract(fixture_root)
    assert has_edge(doc, "receive_chunk", "AudioChunk", S.REFERENCES)
    assert has_edge(doc, "transcribe", "Transcript", S.REFERENCES)
    assert has_edge(doc, "synthesize", "TTSAudio", S.REFERENCES)


def test_imports_to_external_and_local(fixture_root):
    doc = extract(fixture_root)
    # third-party
    assert has_edge(doc, "generate.py", "requests", S.IMPORTS)
    # local file import
    assert has_edge(doc, "stream.py", "models.py", S.IMPORTS)


def test_contains_hierarchy(fixture_root):
    doc = extract(fixture_root)
    assert has_edge(doc, "audio_in", "stream.py", S.CONTAINS)
    assert has_edge(doc, "audio_in", "vad.py", S.CONTAINS)
    assert has_edge(doc, "voice_agent", "audio_in", S.CONTAINS)
    assert has_edge(doc, "vad.py", "VADDetector", S.CONTAINS)
    assert has_edge(doc, "VADDetector", "detect", S.CONTAINS)


# ---- trust tags + line offsets ----

def test_static_skeleton_is_all_parser_trusted(fixture_root):
    doc = extract(fixture_root)
    for n in doc.nodes:
        assert n.origin == S.PARSER, f"{n.id} origin should be parser, got {n.origin}"
    for e in doc.edges:
        assert e.origin == S.PARSER, f"{e.type} edge origin should be parser"


def test_edges_carry_line_offsets(fixture_root):
    doc = extract(fixture_root)
    assert len(edges_of(doc, S.CALLS)) > 0
    assert len(edges_of(doc, S.IMPORTS)) > 0
    for e in doc.edges:
        if e.type in (S.CALLS, S.IMPORTS, S.REFERENCES):
            assert e.location is not None, f"{e.type} edge must carry a location"
            assert e.location.line > 0, f"{e.type} edge must carry a positive line"
            assert e.location.file.endswith(".py")


def test_functions_have_signatures_and_hashes(fixture_root):
    doc = extract(fixture_root)
    rc = find_func(doc, "receive_chunk")
    assert rc.signature is not None
    names = [p.name for p in rc.signature.params]
    assert names == ["frame"]
    assert rc.signature.params[0].type == "bytes"
    assert rc.signature.returns == "AudioChunk"
    assert rc.signature.is_async is False
    assert rc.code_hash, "function must have a code_hash for enrichment caching"
    assert rc.location and rc.location.line > 0


def test_method_skips_self_and_detects_async():
    """A standalone snippet: self/cls is dropped from params; async is flagged."""
    import ast
    from flowsight.skeleton.extractor import _signature

    src = "class C:\n    async def m(self, x: int) -> str:\n        return 'a'\n"
    tree = ast.parse(src)
    method = tree.body[0].body[0]
    sig = _signature(method)
    assert [p.name for p in sig.params] == ["x"]
    assert sig.params[0].type == "int"
    assert sig.returns == "str"
    assert sig.is_async is True


def test_dataclass_fields_extracted(fixture_root):
    doc = extract(fixture_root)
    chunk = find_class(doc, "AudioChunk")
    fields = {f.name: f.type for f in chunk.fields}
    assert fields == {"pcm": "bytes", "sample_rate": "int", "frame_ms": "int"}
