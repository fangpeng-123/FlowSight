"""Domain-entity inference tests (ticket 04).

The LLM infers ``DomainEntity`` nodes (origin=llm) + produces/consumes/transforms
edges from function inputs/outputs. As with all LLM tests, content is never
asserted - only that entities are attached, deduped by canonical name, edged
correctly, re-applied idempotently from a cache hit, and that ``DomainEntity`` is
the first true ``origin=llm`` node (decision 05 / handoff).
"""

from flowsight import schema as S
from flowsight.enrich.attacher import attach_entities, enrich_function
from flowsight.enrich.cache import EnrichCache
from flowsight.enrich.llm import StubLLMClient
from flowsight.skeleton.extractor import extract
from tests.helpers import find_func


def _payload(produces=None, consumes=None, transforms=None):
    """A canned LLM payload carrying inferred entities (content is irrelevant)."""
    return {
        "purpose": "p",
        "contract": {},
        "data_flow_role": "transform",
        "risk": {},
        "entities": {
            "produces": produces or [],
            "consumes": consumes or [],
            "transforms": transforms or [],
        },
    }


def _func(doc, qualname_suffix):
    f = find_func(doc, qualname_suffix)
    assert f, f"fixture missing function ending {qualname_suffix!r}"
    return f


# ---------- DomainEntity nodes ----------

def test_attach_entities_creates_domain_entity_node_with_llm_origin(fixture_root):
    doc = extract(fixture_root)
    fn = _func(doc, "receive_chunk")

    new_nodes, new_edges = attach_entities(fn, doc, _payload(produces=["AudioChunk"]))

    de = doc.node_by_id("de:AudioChunk")
    assert de is not None
    assert de.type == S.DOMAIN_ENTITY
    assert de.origin == S.LLM            # the first true origin=llm node
    assert de.label == "AudioChunk"
    assert any(n.id == "de:AudioChunk" for n in new_nodes)
    # produces edge: function -> entity
    assert any(e.source == fn.id and e.target == "de:AudioChunk" and e.type == S.PRODUCES
               for e in doc.edges)
    assert any(e.type == S.PRODUCES and e.origin == S.LLM for e in new_edges)


def test_attach_entities_dedups_entity_by_name_across_functions(fixture_root):
    """AudioChunk produced by receive_chunk and consumed by transcribe -> one node."""
    doc = extract(fixture_root)
    rc = _func(doc, "receive_chunk")
    tr = _func(doc, "transcribe")
    attach_entities(rc, doc, _payload(produces=["AudioChunk"]))
    attach_entities(tr, doc, _payload(consumes=["AudioChunk"], produces=["Transcript"]))

    audios = [n for n in doc.nodes if n.label == "AudioChunk" and n.type == S.DOMAIN_ENTITY]
    assert len(audios) == 1
    assert any(e.source == rc.id and e.type == S.PRODUCES for e in doc.edges)
    assert any(e.source == tr.id and e.type == S.CONSUMES for e in doc.edges)


def test_attach_entities_transforms_edge_carries_via_function(fixture_root):
    doc = extract(fixture_root)
    tr = _func(doc, "transcribe")  # AudioChunk -> Transcript via transcribe

    attach_entities(tr, doc, _payload(transforms=[{"from": "AudioChunk", "to": "Transcript"}]))

    tf = next(e for e in doc.edges if e.type == S.TRANSFORMS)
    assert tf.source == "de:AudioChunk"
    assert tf.target == "de:Transcript"
    assert tf.origin == S.LLM
    assert tf.attrs.get("via") == tr.id
    assert tf.attrs.get("via_label") == tr.label


def test_attach_entities_idempotent_on_reapply(fixture_root):
    """Re-attaching the same payload (a cache hit) adds no duplicate nodes/edges."""
    doc = extract(fixture_root)
    fn = _func(doc, "transcribe")
    payload = _payload(produces=["Transcript"], consumes=["AudioChunk"],
                       transforms=[{"from": "AudioChunk", "to": "Transcript"}])
    attach_entities(fn, doc, payload)

    new_nodes, new_edges = attach_entities(fn, doc, payload)

    assert new_nodes == []
    assert new_edges == []
    assert sum(1 for e in doc.edges if e.type == S.TRANSFORMS) == 1
    assert sum(1 for n in doc.nodes if n.id == "de:Transcript") == 1


def test_attach_entities_no_entities_in_payload_is_noop(fixture_root):
    doc = extract(fixture_root)
    fn = _func(doc, "run")
    before_nodes, before_edges = len(doc.nodes), len(doc.edges)

    new_nodes, new_edges = attach_entities(fn, doc, {"purpose": "x"})  # no entities key

    assert new_nodes == [] and new_edges == []
    assert len(doc.nodes) == before_nodes
    assert len(doc.edges) == before_edges


# ---------- end-to-end with the stubbed LLM ----------

def test_enrich_function_returns_payload_carrying_entities(fixture_root, tmp_path):
    """enrich_function returns the LLM payload (incl. entities) so the caller can
    attach_entities; a cache hit returns the same payload for idempotent re-attach."""
    doc = extract(fixture_root)
    fn = _func(doc, "transcribe")
    stub = StubLLMClient(_payload(produces=["Transcript"], consumes=["AudioChunk"],
                                  transforms=[{"from": "AudioChunk", "to": "Transcript"}]))
    cache = EnrichCache(str(tmp_path / "c.json"))

    payload = enrich_function(fn, stub, cache)
    assert "entities" in payload
    new_nodes, _ = attach_entities(fn, doc, payload)
    assert any(n.label == "Transcript" for n in new_nodes)

    # cache hit on a fresh doc: same payload, re-attach still surfaces the entities
    doc2 = extract(fixture_root)
    fn2 = _func(doc2, "transcribe")
    calls_before = len(stub.calls)
    cached = enrich_function(fn2, stub, cache)
    assert cached == payload
    assert len(stub.calls) == calls_before      # cache hit -> no new LLM call
    nn, _ = attach_entities(fn2, doc2, cached)
    assert any(n.label == "Transcript" for n in nn)


def test_attach_entities_builds_full_voice_pipeline(fixture_root):
    """Enriching the four pipeline functions yields AudioChunk->Transcript->LLMMessage->TTSAudio."""
    doc = extract(fixture_root)
    attach_entities(_func(doc, "receive_chunk"), doc, _payload(produces=["AudioChunk"]))
    attach_entities(_func(doc, "transcribe"), doc,
                    _payload(consumes=["AudioChunk"], produces=["Transcript"],
                             transforms=[{"from": "AudioChunk", "to": "Transcript"}]))
    attach_entities(_func(doc, "LLMClient.generate"), doc,
                    _payload(consumes=["Transcript"], produces=["LLMMessage"],
                             transforms=[{"from": "Transcript", "to": "LLMMessage"}]))
    attach_entities(_func(doc, "synthesize"), doc,
                    _payload(consumes=["LLMMessage"], produces=["TTSAudio"],
                             transforms=[{"from": "LLMMessage", "to": "TTSAudio"}]))

    names = {n.label for n in doc.nodes if n.type == S.DOMAIN_ENTITY}
    assert {"AudioChunk", "Transcript", "LLMMessage", "TTSAudio"}.issubset(names)
    transforms = {(e.source, e.target) for e in doc.edges if e.type == S.TRANSFORMS}
    assert ("de:AudioChunk", "de:Transcript") in transforms
    assert ("de:Transcript", "de:LLMMessage") in transforms
    assert ("de:LLMMessage", "de:TTSAudio") in transforms
