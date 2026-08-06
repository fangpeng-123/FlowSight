"""Runtime overlay correlator tests (ticket 05).

The correlator is the unit-tested seam (spec Seam 2): a checked-in viztracer
trace + the parser skeleton -> runtime data_flow edges + per-node runtime stats +
an actual-on-expected divergence report. It never imports viztracer, so the
checked-in fixture trace (``tests/fixtures/trace.json``) drives every assertion.
"""

import json
import os

from flowsight import schema as S
from flowsight.overlay.correlator import apply_overlay, correlate
from flowsight.skeleton.extractor import extract
from tests.helpers import find_func, find_node

TRACE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "trace.json")


def _load_trace():
    with open(TRACE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _voice_doc(fixture_root):
    return extract(fixture_root)


# --------------------------------------------------------------------------
# fixture trace -> skeleton correlation (the primary scenario)
# --------------------------------------------------------------------------

def test_correlate_maps_events_to_function_nodes_by_file_line(fixture_root):
    doc = _voice_doc(fixture_root)
    res = correlate(doc, _load_trace(), project_root=fixture_root, trace_id="t1")

    run = find_func(doc, "run")
    recv = find_func(doc, "receive_chunk")
    init = find_func(doc, "VADDetector.__init__")
    detect = find_func(doc, "VADDetector.detect")
    end = find_func(doc, "is_utterance_end")

    # four observed caller->callee pairs, all rooted at run()
    assert set(res.observed_pairs) == {
        (run.id, recv.id), (run.id, init.id), (run.id, detect.id), (run.id, end.id)
    }
    # five functions ran (run + its four callees)
    assert set(res.node_runtime) == {run.id, recv.id, init.id, detect.id, end.id}
    assert res.trace_id == "t1"


def test_correlate_aggregates_timings_and_values(fixture_root):
    doc = _voice_doc(fixture_root)
    res = correlate(doc, _load_trace(), project_root=fixture_root)

    run_rt = res.node_runtime[find_func(doc, "run").id]
    assert run_rt.call_count == 1
    assert run_rt.total_dur_us == 200.0
    assert run_rt.min_dur_us == 200.0
    assert run_rt.max_dur_us == 200.0

    recv_rt = res.node_runtime[find_func(doc, "receive_chunk").id]
    # arg/return reprs are captured from viztracer's args
    assert recv_rt.arg_values and "frame=" in recv_rt.arg_values[0]
    assert recv_rt.return_values and "AudioChunk" in recv_rt.return_values[0]


def test_correlate_divergence_fired_vs_not_fired(fixture_root):
    """The trace ran run() with is_utterance_end=False, so the second half of
    the pipeline (transcribe/generate/synthesize/play + the LLMClient/Player
    constructors) never fired - the static graph said they could."""
    doc = _voice_doc(fixture_root)
    res = correlate(doc, _load_trace(), project_root=fixture_root)

    not_fired_targets = {tgt for _src, tgt, _t in res.divergence["not_fired"]}
    for cold in ("transcribe", "generate", "synthesize", "play"):
        assert find_func(doc, cold).id in not_fired_targets
    # the two never-constructed classes are not-fired references
    assert find_node(doc, "LLMClient").id in not_fired_targets
    assert find_node(doc, "Player").id in not_fired_targets
    # what did fire is NOT in the not-fired set
    assert find_func(doc, "receive_chunk").id not in not_fired_targets
    assert find_func(doc, "detect").id not in not_fired_targets

    # every observed pair has a static counterpart -> nothing unexpected
    assert res.divergence["unexpected"] == []
    # no LLM enrichment in the bare skeleton -> no role divergence yet
    assert res.divergence["role"] == []


def test_correlate_is_pure_does_not_mutate_doc(fixture_root):
    doc = _voice_doc(fixture_root)
    n_before = len(doc.edges)
    correlate(doc, _load_trace(), project_root=fixture_root)
    assert len(doc.edges) == n_before  # no data_flow edges added by correlate


# --------------------------------------------------------------------------
# apply_overlay writes the result back onto the graph
# --------------------------------------------------------------------------

def test_apply_overlay_adds_runtime_data_flow_edges(fixture_root):
    doc = _voice_doc(fixture_root)
    n_before = len(doc.edges)
    res = correlate(doc, _load_trace(), project_root=fixture_root)
    apply_overlay(doc, res)

    df = [e for e in doc.edges if e.type == S.DATA_FLOW]
    assert len(df) == 4
    assert all(e.origin == S.RUNTIME for e in df)
    run = find_func(doc, "run")
    recv = find_func(doc, "receive_chunk")
    edge = next(e for e in df if e.target == recv.id)
    assert edge.source == run.id
    assert edge.attrs["call_count"] == 1
    assert edge.attrs["trace_id"] == "trace"
    assert edge.attrs["expected"] is True  # a static calls edge exists run->receive_chunk
    assert len(doc.edges) == n_before + 4


def test_apply_overlay_tags_calls_edges_fired_and_not_fired(fixture_root):
    doc = _voice_doc(fixture_root)
    res = correlate(doc, _load_trace(), project_root=fixture_root)
    apply_overlay(doc, res)

    run = find_func(doc, "run").id
    fired_targets, cold_targets = set(), set()
    for e in doc.edges:
        if e.type == S.CALLS and e.source == run:
            (fired_targets if e.attrs["runtime"]["fired"] else cold_targets).add(e.target)
    assert find_func(doc, "receive_chunk").id in fired_targets
    assert find_func(doc, "detect").id in fired_targets
    assert find_func(doc, "is_utterance_end").id in fired_targets
    for cold in ("transcribe", "generate", "synthesize", "play"):
        assert find_func(doc, cold).id in cold_targets


def test_apply_overlay_references_edge_to_class_fires_via_constructor(fixture_root):
    """run()->VADDetector() is a references edge to the class; it should count
    as fired because VADDetector.__init__ ran. LLMClient/Player never
    constructed -> their references edges are not-fired."""
    doc = _voice_doc(fixture_root)
    res = correlate(doc, _load_trace(), project_root=fixture_root)
    apply_overlay(doc, res)

    run = find_func(doc, "run").id
    by_target = {e.target: e.attrs["runtime"] for e in doc.edges
                 if e.type == S.REFERENCES and e.source == run}
    assert by_target[find_node(doc, "VADDetector").id]["fired"] is True
    assert by_target[find_node(doc, "LLMClient").id]["fired"] is False
    assert by_target[find_node(doc, "Player").id]["fired"] is False


def test_apply_overlay_writes_node_runtime(fixture_root):
    doc = _voice_doc(fixture_root)
    res = correlate(doc, _load_trace(), project_root=fixture_root)
    apply_overlay(doc, res)

    run = find_func(doc, "run")
    assert run.runtime["call_count"] == 1
    assert run.runtime["total_dur_us"] == 200.0
    assert run.attrs["runtime_fired"] is True
    # a function that never ran has no runtime dict / no runtime_fired flag
    cold = find_func(doc, "transcribe")
    assert cold.runtime == {}
    assert "runtime_fired" not in cold.attrs


# --------------------------------------------------------------------------
# mapping + caller reconstruction (constructed mini-graphs)
# --------------------------------------------------------------------------

def _fn(node_id, label, file_, line):
    return S.Node(id=node_id, type=S.FUNCTION, label=label, origin=S.PARSER,
                  location=S.Location(file=file_, line=line),
                  attrs={"qualname": label})


def _trace(events):
    return {"traceEvents": events}


def _x(name, ts, dur, tid=1, args=None):
    e = {"ph": "X", "cat": "FEE", "pid": 1, "tid": tid, "ts": ts, "dur": dur, "name": name}
    if args is not None:
        e["args"] = args
    return e


def _b(name, ts, tid=1):
    return {"ph": "B", "cat": "FEE", "pid": 1, "tid": tid, "ts": ts, "name": name}


def _e(name, ts, tid=1):
    return {"ph": "E", "cat": "FEE", "pid": 1, "tid": tid, "ts": ts, "name": name}


def test_caller_reconstruction_handles_siblings(tmp_path):
    root = str(tmp_path)
    doc = S.GraphDocument(project={"path": root}, nodes=[
        _fn("f:p.py::p@1", "p", "p.py", 1),
        _fn("f:p.py::a@2", "a", "p.py", 2),
        _fn("f:p.py::b@3", "b", "p.py", 3),
    ], edges=[
        S.Edge("f:p.py::p@1", "f:p.py::a@2", S.CALLS, S.PARSER),
        S.Edge("f:p.py::p@1", "f:p.py::b@3", S.CALLS, S.PARSER),
    ])
    tr = _trace([
        _x("p (/srv/p.py:1)", 0, 100),
        _x("a (/srv/p.py:2)", 10, 20),
        _x("b (/srv/p.py:3)", 40, 20),
    ])
    res = correlate(doc, tr, project_root=root)
    assert set(res.observed_pairs) == {
        ("f:p.py::p@1", "f:p.py::a@2"), ("f:p.py::p@1", "f:p.py::b@3")
    }
    assert res.divergence["not_fired"] == []
    assert res.divergence["unexpected"] == []


def test_relativize_matches_abs_path_under_project_root(tmp_path):
    root = str(tmp_path)
    src = os.path.join(root, "pkg", "mod.py")
    os.makedirs(os.path.dirname(src))
    with open(src, "w", encoding="utf-8") as f:
        f.write("def f():\n    return 1\n")
    doc = S.GraphDocument(project={"path": root}, nodes=[
        _fn("f:pkg/mod.py::f@1", "f", "pkg/mod.py", 1),
    ], edges=[])
    tr = _trace([_x(f"f ({src}:1)", 0, 5)])
    res = correlate(doc, tr, project_root=root)
    assert "f:pkg/mod.py::f@1" in res.node_runtime


def test_unmapped_events_are_skipped(fixture_root):
    doc = _voice_doc(fixture_root)
    tr = _load_trace()
    tr["traceEvents"].append(_x("outside.func (/nowhere/x.py:999)", 5, 1))
    res = correlate(doc, tr, project_root=fixture_root)
    assert all("outside" not in nid for nid in res.node_runtime)


def test_unexpected_observed_edge_flagged_when_no_static_counterpart():
    doc = S.GraphDocument(project={"path": ""}, nodes=[
        _fn("f:p.py::p@1", "p", "p.py", 1),
        _fn("f:p.py::q@2", "q", "p.py", 2),
    ], edges=[])  # note: no calls edge p->q
    tr = _trace([_x("p (/srv/p.py:1)", 0, 10), _x("q (/srv/p.py:2)", 1, 2)])
    res = correlate(doc, tr, project_root="")
    assert res.divergence["unexpected"] == [("f:p.py::p@1", "f:p.py::q@2")]
    apply_overlay(doc, res)
    df = next(e for e in doc.edges if e.type == S.DATA_FLOW)
    assert df.attrs["expected"] is False


def test_async_events_on_separate_thread_reconstruct_independently():
    doc = S.GraphDocument(project={"path": ""}, nodes=[
        _fn("f:p.py::p@1", "p", "p.py", 1),
        _fn("f:p.py::cb@2", "cb", "p.py", 2),
    ], edges=[])
    # p on tid 1; cb on tid 2 (an async callback resumed elsewhere) is a root
    tr = _trace([
        _x("p (/srv/p.py:1)", 0, 50, tid=1),
        _x("cb (/srv/p.py:2)", 60, 5, tid=2),
    ])
    res = correlate(doc, tr, project_root="")
    assert set(res.node_runtime) == {"f:p.py::p@1", "f:p.py::cb@2"}
    # cb has no caller on its own thread -> no pair into it
    assert all(callee != "f:p.py::cb@2" for _c, callee in res.observed_pairs)


def test_mixed_begin_end_and_complete_events_pop_correctly():
    """B/E (begin/end) intermixed with X (complete) must nest correctly: an E
    ends its matching B, not a leftover completed X child. viztracer emits X by
    default; B/E is a compatibility path, but the mixed case must still work."""
    doc = S.GraphDocument(project={"path": ""}, nodes=[
        _fn("f:p.py::outer@1", "outer", "p.py", 1),
        _fn("f:p.py::child@2", "child", "p.py", 2),
        _fn("f:p.py::after@3", "after", "p.py", 3),
    ], edges=[])
    tr = _trace([
        _b("outer (/srv/p.py:1)", 0),
        _x("child (/srv/p.py:2)", 1, 1),   # completes at ts=2, nested in outer
        _e("outer (/srv/p.py:1)", 10),     # ends outer
        _x("after (/srv/p.py:3)", 20, 1),  # after outer ended -> root, no caller
    ])
    res = correlate(doc, tr, project_root="")
    assert ("f:p.py::outer@1", "f:p.py::child@2") in res.observed_pairs
    # the E must have popped outer; otherwise `after` would wrongly get outer as caller
    assert all(callee != "f:p.py::after@3" for _c, callee in res.observed_pairs)


# --------------------------------------------------------------------------
# LLM-role divergence (expected baseline from ticket 03)
# --------------------------------------------------------------------------

def test_role_divergence_flags_cold_participant_and_hot_none():
    transform = _fn("f:p.py::t@1", "t", "p.py", 1)
    transform.data_flow_role = "transform"  # LLM said it's on the data path...
    none_fn = _fn("f:p.py::n@2", "n", "p.py", 2)
    none_fn.data_flow_role = "none"         # ...but it never ran, while "none" did
    doc = S.GraphDocument(project={"path": ""}, nodes=[transform, none_fn], edges=[
        S.Edge("f:p.py::n@2", "f:p.py::t@1", S.CALLS, S.PARSER),
    ])
    tr = _trace([
        _x("n (/srv/p.py:2)", 0, 10),
        # t is called in the static graph but absent from this trace
    ])
    res = correlate(doc, tr, project_root="")
    role = {r["node"]: r for r in res.divergence["role"]}
    assert role["f:p.py::t@1"]["reason"] == "cold"
    assert role["f:p.py::t@1"]["call_count"] == 0
    assert role["f:p.py::n@2"]["reason"] == "hot"
    assert role["f:p.py::n@2"]["call_count"] == 1


# --------------------------------------------------------------------------
# value sampling is bounded
# --------------------------------------------------------------------------

def test_arg_and_return_values_are_capped():
    p = _fn("f:p.py::p@1", "p", "p.py", 1)
    doc = S.GraphDocument(project={"path": ""}, nodes=[p], edges=[])
    big = "x" * 500
    evs = [_x("p (/srv/p.py:1)", i, 1, args={"func_args": {"a": big}, "return_value": big})
           for i in range(10)]
    res = correlate(doc, _trace(evs), project_root="")
    rt = res.node_runtime["f:p.py::p@1"]
    assert len(rt.arg_values) == 5          # at most _MAX_SAMPLES
    assert len(rt.return_values) == 5
    assert rt.arg_values[0].endswith("…")   # each value truncated
    assert rt.call_count == 10
