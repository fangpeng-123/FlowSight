"""Schema JSON round-trip (decision 05)."""

from flowsight import schema as S


def _sample_doc() -> S.GraphDocument:
    fn = S.Node(
        id="func:a/m.py::run@1",
        type=S.FUNCTION,
        label="run",
        origin=S.PARSER,
        location=S.Location(file="a/m.py", line=1, end_line=3, col=0),
        signature=S.Signature(
            params=[S.Param(name="frame", type="bytes")],
            returns="AudioChunk",
            decorators=["@app.route('/')"],
            is_async=False,
        ),
        code_hash="abc123",
        purpose="",  # filled by LLM enrichment later
    )
    cls = S.Node(
        id="class:a/m.py::AudioChunk@5",
        type=S.CLASS,
        label="AudioChunk",
        fields=[S.Param(name="pcm", type="bytes")],
    )
    ext = S.Node(id="ext:requests", type=S.EXTERNAL, label="requests", origin=S.PARSER)
    edges = [
        S.Edge(source="file:a/m.py", target=fn.id, type=S.CONTAINS, origin=S.PARSER,
               location=S.Location(file="a/m.py", line=1)),
        S.Edge(source=fn.id, target=cls.id, type=S.REFERENCES, origin=S.PARSER,
               location=S.Location(file="a/m.py", line=2)),
        S.Edge(source="file:a/m.py", target=ext.id, type=S.IMPORTS, origin=S.PARSER,
               location=S.Location(file="a/m.py", line=0)),
    ]
    return S.GraphDocument(project={"name": "demo"}, nodes=[fn, cls, ext], edges=edges)


def test_roundtrip_preserves_structure():
    doc = _sample_doc()
    d = S.doc_to_dict(doc)
    back = S.doc_from_dict(d)

    assert back.project == {"name": "demo"}
    assert [n.id for n in back.nodes] == [n.id for n in doc.nodes]
    fn = back.node_by_id("func:a/m.py::run@1")
    assert fn.type == S.FUNCTION
    assert fn.signature is not None
    assert fn.signature.params[0].name == "frame"
    assert fn.signature.params[0].type == "bytes"
    assert fn.signature.returns == "AudioChunk"
    assert fn.signature.decorators == ["@app.route('/')"]
    assert fn.code_hash == "abc123"
    cls = back.node_by_id("class:a/m.py::AudioChunk@5")
    assert cls.fields[0].name == "pcm"
    assert cls.fields[0].type == "bytes"


def test_roundtrip_preserves_edges_and_origin():
    doc = _sample_doc()
    back = S.doc_from_dict(S.doc_to_dict(doc))
    edge = back.edges[1]
    assert edge.source == "func:a/m.py::run@1"
    assert edge.target == "class:a/m.py::AudioChunk@5"
    assert edge.type == S.REFERENCES
    assert edge.origin == S.PARSER
    assert edge.location is not None and edge.location.line == 2


def test_json_is_plain_serializable():
    import json
    d = S.doc_to_dict(_sample_doc())
    s = json.dumps(d)  # must not raise
    assert "func:a/m.py::run@1" in s
