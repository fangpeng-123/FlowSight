"""Enrichment tests (ticket 03).

The LLM is non-deterministic, so these tests NEVER assert its content - only that
enrichment is correctly keyed (by code_hash), attached to the node, cached, and
invalidated on code change. ``StubLLMClient`` provides deterministic canned JSON.
"""

from flowsight import schema as S
from flowsight.enrich.attacher import enrich_eager, enrich_function
from flowsight.enrich.cache import EnrichCache
from flowsight.enrich.llm import StubLLMClient
from flowsight.skeleton.extractor import extract


def _first_function(doc):
    return next(n for n in doc.nodes if n.type == S.FUNCTION and n.code_hash)


# ---------- per-function (lazy) enrichment ----------

def test_enrich_function_attaches_advisory_and_caches(fixture_root, tmp_path):
    doc = extract(fixture_root)
    fn = _first_function(doc)
    stub = StubLLMClient()
    cache = EnrichCache(str(tmp_path / "c.json"))

    payload = enrich_function(fn, stub, cache)

    assert payload is not None            # LLM was consulted
    assert len(stub.calls) == 1           # exactly one LLM call
    assert fn.purpose                      # advisory fields attached...
    assert fn.contract is not None
    assert fn.risk is not None
    assert fn.attrs.get("enriched") is True
    # ...and cached under (node_id, code_hash)
    assert cache.get(fn.id, fn.code_hash) is not None


def test_enrich_function_cache_hit_skips_llm(fixture_root, tmp_path):
    doc = extract(fixture_root)
    fn = _first_function(doc)
    stub = StubLLMClient()
    cache = EnrichCache(str(tmp_path / "c.json"))
    # pre-seed the cache so the LLM should not be called
    cache.put(fn.id, fn.code_hash, {"purpose": "cached", "contract": {}})

    payload = enrich_function(fn, stub, cache)

    assert payload == {"purpose": "cached", "contract": {}}
    assert stub.calls == []               # cache hit -> no LLM call
    assert fn.purpose == "cached"         # applied from cache


def test_enrich_function_invalidated_on_code_hash_change(fixture_root, tmp_path):
    doc = extract(fixture_root)
    fn = _first_function(doc)
    stub = StubLLMClient()
    cache = EnrichCache(str(tmp_path / "c.json"))

    enrich_function(fn, stub, cache)
    assert len(stub.calls) == 1
    old_hash = fn.code_hash

    # simulate a code change: the hash moves, so the cached entry no longer matches
    fn.code_hash = "changedhash00000"
    fn.purpose = ""  # clear to observe re-enrichment
    enrich_function(fn, stub, cache)

    assert len(stub.calls) == 2           # re-enriched because hash changed
    assert cache.get(fn.id, "changedhash00000") is not None  # new entry cached
    assert cache.get(fn.id, old_hash) is None               # old entry invalidated


def test_enrich_function_no_llm_returns_none(fixture_root, tmp_path):
    doc = extract(fixture_root)
    fn = _first_function(doc)
    cache = EnrichCache(str(tmp_path / "c.json"))

    assert enrich_function(fn, None, cache) is None
    assert fn.purpose == ""               # node left untouched


def test_enrich_preserves_parser_origin(fixture_root, tmp_path):
    """Advisory fields are layered on; the node's structure origin stays parser."""
    doc = extract(fixture_root)
    fn = _first_function(doc)
    assert fn.origin == S.PARSER

    enrich_function(fn, StubLLMClient(), EnrichCache(str(tmp_path / "c.json")))

    assert fn.origin == S.PARSER          # not upgraded to llm


# ---------- eager module-purpose enrichment ----------

def test_enrich_eager_gives_modules_purpose_with_llm(fixture_root, tmp_path):
    doc = extract(fixture_root)
    stub = StubLLMClient()
    cache = EnrichCache(str(tmp_path / "c.json"))
    modules = [n for n in doc.nodes if n.type == S.MODULE]
    assert modules  # fixture has at least one

    enrich_eager(doc, stub, cache)

    for m in modules:
        assert m.purpose                       # every module gets a purpose
        assert m.code_hash                     # keyed by content hash
        assert m.attrs["purpose_origin"] == "llm"
    assert len(stub.calls) == len(modules)     # one LLM call per module


def test_enrich_eager_docstring_fallback_without_llm(fixture_root, tmp_path):
    doc = extract(fixture_root)
    cache = EnrichCache(str(tmp_path / "c.json"))
    modules = [n for n in doc.nodes if n.type == S.MODULE]

    enrich_eager(doc, None, cache)

    for m in modules:
        assert m.purpose                                  # docstring or count fallback
        assert m.attrs["purpose_origin"] == "docstring"
        assert m.origin == S.PARSER                       # still trusted structure


def test_enrich_eager_cache_hit_skips_llm(fixture_root, tmp_path):
    doc = extract(fixture_root)
    cache = EnrichCache(str(tmp_path / "c.json"))
    stub1 = StubLLMClient()
    enrich_eager(doc, stub1, cache)
    n_modules = sum(1 for n in doc.nodes if n.type == S.MODULE)
    assert len(stub1.calls) == n_modules

    # second pass over the same project: every module is cached -> no LLM calls
    doc2 = extract(fixture_root)
    stub2 = StubLLMClient()
    enrich_eager(doc2, stub2, cache)

    assert len(stub2.calls) == 0
    assert all(n.purpose for n in doc2.nodes if n.type == S.MODULE)
