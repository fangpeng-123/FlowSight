"""Runtime data-flow overlay correlator (ticket 05 / decision 06).

Pure transform: a viztracer Chrome Trace JSON + the parser skeleton -> runtime
``data_flow`` edges + per-node runtime stats + an actual-on-expected divergence
report. This is the unit-tested seam (spec Seam 2); it never imports viztracer,
so it runs - and is tested - without the runtime dependency installed.

Mapping (decision 06): trace events map onto skeleton ``Function`` nodes by
file:def-line. viztracer embeds ``"<qualname> (<abs_path>:<def_line>)"`` in each
FEE event's ``name``; the def-line is ``co_firstlineno`` - the same line the
skeleton records as ``location.line``. Caller->callee is reconstructed per
(pid, tid) from event nesting: ``X`` (complete) events nest by ts/dur, ``B``/``E``
(begin/end) pair by stack. Generators/async dedupe by f_code identity implicitly
- the same (file, line) maps to one node, so repeated/awaited calls aggregate.

Trust model (decision 05): the LLM's ``data_flow_role`` (ticket 03) is the
*expected* per-function role; viztracer's captured calls+args are the *actual*
flow. Divergence (ticket 05, last item) therefore uses ``data_flow_role`` now and
auto-activates the edge-level expected baseline (produces/consumes/transforms,
ticket 04) when those edges land - the correlator checks for them gracefully.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Any

from flowsight import schema as S

# bound the sampled values so a huge arg/return repr can't bloat the graph json
_MAX_SAMPLES = 5
_MAX_VALUE_LEN = 200

_NAME_RE = re.compile(r"^(?P<qual>.*) \((?P<path>.+):(?P<line>\d+)\)\s*$")

# data-flow-role values the LLM uses for functions on the data path (attacher prompt)
_DATA_ROLES = {"producer", "consumer", "transform"}


# --------------------------------------------------------------------------
# result shapes
# --------------------------------------------------------------------------

@dataclass
class NodeRuntime:
    """Aggregated runtime stats for one Function node."""

    call_count: int = 0
    total_dur_us: float = 0.0
    min_dur_us: float = math.inf
    max_dur_us: float = 0.0
    arg_values: list[str] = field(default_factory=list)
    return_values: list[str] = field(default_factory=list)

    @property
    def avg_dur_us(self) -> float:
        return self.total_dur_us / self.call_count if self.call_count else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_count": self.call_count,
            "total_dur_us": round(self.total_dur_us, 3),
            "avg_dur_us": round(self.avg_dur_us, 3),
            "min_dur_us": round(0.0 if self.min_dur_us is math.inf else self.min_dur_us, 3),
            "max_dur_us": round(self.max_dur_us, 3),
            "arg_values": list(self.arg_values),
            "return_values": list(self.return_values),
        }


@dataclass
class EdgeRuntime:
    """Aggregated runtime stats for one observed caller->callee pair."""

    call_count: int = 0
    total_dur_us: float = 0.0
    min_dur_us: float = math.inf
    max_dur_us: float = 0.0
    arg_values: list[str] = field(default_factory=list)
    return_values: list[str] = field(default_factory=list)
    trace_id: str = ""

    def to_attrs(self, expected: bool) -> dict[str, Any]:
        return {
            "call_count": self.call_count,
            "total_dur_us": round(self.total_dur_us, 3),
            "avg_dur_us": round(self.total_dur_us / self.call_count, 3) if self.call_count else 0.0,
            "min_dur_us": round(0.0 if self.min_dur_us is math.inf else self.min_dur_us, 3),
            "max_dur_us": round(self.max_dur_us, 3),
            "arg_values": list(self.arg_values),
            "return_values": list(self.return_values),
            "trace_id": self.trace_id,
            "expected": expected,
        }


@dataclass
class OverlayResult:
    trace_id: str
    observed_pairs: dict[tuple[str, str], EdgeRuntime]
    node_runtime: dict[str, NodeRuntime]
    divergence: dict[str, list]


# --------------------------------------------------------------------------
# public api
# --------------------------------------------------------------------------

def correlate(
    doc: S.GraphDocument,
    trace: dict[str, Any],
    *,
    project_root: str | None = None,
    trace_id: str = "trace",
) -> OverlayResult:
    """Correlate a viztracer Chrome Trace JSON against the skeleton.

    Pure: does not mutate ``doc``. Use :func:`apply_overlay` to write the result
    back onto a graph document for rendering.
    """
    events = trace.get("traceEvents", []) if isinstance(trace, dict) else []

    node_by_id = {n.id: n for n in doc.nodes}
    func_index = _build_func_index(doc)           # def_line -> [(rel_file, node_id)]
    parent_of = _parent_map(doc)                  # node_id -> parent node_id (via contains)
    observed: dict[tuple[str, str], EdgeRuntime] = {}
    node_rt: dict[str, NodeRuntime] = {}

    def _agg_node(nid: str, ev: dict[str, Any]) -> None:
        rt = node_rt.setdefault(nid, NodeRuntime())
        rt.call_count += 1
        dur = _as_float(ev.get("dur"))
        if dur is not None:
            rt.total_dur_us += dur
            rt.min_dur_us = min(rt.min_dur_us, dur)
            rt.max_dur_us = max(rt.max_dur_us, dur)
        args, ret = _extract_values(ev)
        _append_capped(rt.arg_values, args)
        _append_capped(rt.return_values, ret)

    def _agg_pair(caller: str, callee: str, ev: dict[str, Any]) -> None:
        er = observed.setdefault((caller, callee), EdgeRuntime(trace_id=trace_id))
        er.call_count += 1
        dur = _as_float(ev.get("dur"))
        if dur is not None:
            er.total_dur_us += dur
            er.min_dur_us = min(er.min_dur_us, dur)
            er.max_dur_us = max(er.max_dur_us, dur)
        args, ret = _extract_values(ev)
        _append_capped(er.arg_values, args)
        _append_capped(er.return_values, ret)

    for caller_id, callee_id, ev in _event_pairs(events, func_index, project_root):
        _agg_node(callee_id, ev)
        if caller_id is not None:
            _agg_pair(caller_id, callee_id, ev)

    divergence = _divergence(doc, observed, node_rt, parent_of, node_by_id)
    return OverlayResult(
        trace_id=trace_id,
        observed_pairs=observed,
        node_runtime=node_rt,
        divergence=divergence,
    )


def apply_overlay(doc: S.GraphDocument, result: OverlayResult) -> None:
    """Write a correlation result back onto ``doc`` (mutates).

    - appends runtime ``data_flow`` edges (origin=runtime) for observed pairs;
    - tags each parser ``calls``/``references`` edge with ``attrs["runtime"]``
      ``{fired, call_count}`` so the renderer can dim could-fire-but-didn't edges;
    - writes per-node ``runtime`` stats + ``attrs["runtime_fired"]``.
    """
    parent_of = _parent_map(doc)
    node_by_id = {n.id: n for n in doc.nodes}

    # methods observed per (caller, class) -> lets a references-edge to a class
    # count as fired when any of the class's methods ran (constructor calls).
    observed_caller_class: set[tuple[str, str]] = set()
    for (caller, callee) in result.observed_pairs:
        parent = parent_of.get(callee)
        if parent is not None and node_by_id.get(parent, None) and node_by_id[parent].type == S.CLASS:
            observed_caller_class.add((caller, parent))

    existing_df: set[tuple[str, str]] = {
        (e.source, e.target) for e in doc.edges if e.type == S.DATA_FLOW
    }
    for (caller, callee), er in result.observed_pairs.items():
        expected = _is_expected(doc, caller, callee, parent_of, node_by_id)
        attrs = er.to_attrs(expected)
        if (caller, callee) in existing_df:
            for e in doc.edges:
                if e.type == S.DATA_FLOW and e.source == caller and e.target == callee:
                    e.attrs.update(attrs)
                    break
        else:
            doc.edges.append(S.Edge(source=caller, target=callee, type=S.DATA_FLOW,
                                    origin=S.RUNTIME, attrs=attrs))
            existing_df.add((caller, callee))

    for e in doc.edges:
        if e.type not in (S.CALLS, S.REFERENCES):
            continue
        if e.type == S.REFERENCES and node_by_id.get(e.target) and node_by_id[e.target].type == S.CLASS:
            fired = (e.source, e.target) in observed_caller_class
        else:
            fired = (e.source, e.target) in result.observed_pairs
        pair = (e.source, e.target)
        if pair in result.observed_pairs:
            count = result.observed_pairs[pair].call_count
        elif fired:
            count = 1  # class reference fired via an observed constructor/method
        else:
            count = 0
        e.attrs["runtime"] = {"fired": fired, "call_count": count}

    for nid, rt in result.node_runtime.items():
        node = node_by_id.get(nid)
        if node is None:
            continue
        node.runtime = rt.to_dict()
        node.attrs["runtime_fired"] = rt.call_count > 0


# --------------------------------------------------------------------------
# trace event -> skeleton node mapping
# --------------------------------------------------------------------------

def _build_func_index(doc: S.GraphDocument) -> dict[int, list[tuple[str, str]]]:
    """def_line -> [(rel_file, node_id)] for every Function node."""
    index: dict[int, list[tuple[str, str]]] = {}
    for n in doc.nodes:
        if n.type == S.FUNCTION and n.location:
            index.setdefault(n.location.line, []).append((n.location.file, n.id))
    return index


def _parent_map(doc: S.GraphDocument) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in doc.edges:
        if e.type == S.CONTAINS:
            out[e.target] = e.source  # first parent wins; skeleton is a tree
    return out


def _parse_event(name: str) -> tuple[str, str, int] | None:
    """Split a viztracer ``"<qual> (<path>:<line>)"`` name into (qual, path, line)."""
    if not name:
        return None
    m = _NAME_RE.match(name)
    if not m:
        return None
    return m.group("qual"), m.group("path"), int(m.group("line"))


def _match_node(
    abs_path: str, def_line: int, index: dict[int, list[tuple[str, str]]],
    project_root: str | None,
) -> str | None:
    cands = index.get(def_line)
    if not cands:
        return None
    norm = abs_path.replace("\\", "/")
    rel = _relativize(abs_path, project_root) if project_root else None
    rel_n = rel.replace("\\", "/") if rel else None
    # 1. exact relativized match (precise, same machine as the trace)
    if rel_n:
        for rel_file, nid in cands:
            if rel_file.replace("\\", "/") == rel_n:
                return nid
    # 2. suffix match (portable: trace path ends with the project-relative file)
    for rel_file, nid in cands:
        rf = rel_file.replace("\\", "/")
        if norm == rf or norm.endswith("/" + rf):
            return nid
    return None


def _relativize(abs_path: str, project_root: str) -> str | None:
    try:
        rel = os.path.relpath(abs_path, project_root)
    except (ValueError, TypeError):
        return None
    if rel == ".." or rel.startswith(".." + os.sep) or rel.startswith(".." + "/"):
        return None  # not under the project root
    return rel


# --------------------------------------------------------------------------
# caller -> callee reconstruction (per pid/tid event nesting)
# --------------------------------------------------------------------------

def _event_pairs(
    events: list[dict[str, Any]],
    func_index: dict[int, list[tuple[str, str]]],
    project_root: str | None,
) -> list[tuple[str | None, str, dict[str, Any]]]:
    """Yield (caller_node_id|None, callee_node_id, event) from trace nesting."""
    # group mapped, function events by (pid, tid)
    by_thread: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for ev in events:
        ph = ev.get("ph")
        if ph not in ("X", "B", "E"):
            continue
        parsed = _parse_event(ev.get("name", ""))
        if parsed is None:
            continue
        qual, path, line = parsed
        if qual == "<module>":
            continue  # the script body, not a Function node (no skeleton target)
        nid = _match_node(path, line, func_index, project_root)
        if nid is None:
            continue  # external / unmapped call (C func, stdlib, etc.)
        rec = {"nid": nid, "ts": _as_float(ev.get("ts")) or 0.0,
               "dur": _as_float(ev.get("dur")), "ph": ph, "raw": ev}
        by_thread.setdefault((ev.get("pid"), ev.get("tid")), []).append(rec)

    out: list[tuple[str | None, str, dict[str, Any]]] = []
    for _key, recs in by_thread.items():
        recs.sort(key=lambda r: r["ts"])
        stack: list[tuple[str, float]] = []  # (node_id, end_ts); end=inf for B
        for rec in recs:
            if rec["ph"] == "E":
                # An E ends the innermost B. First drop any X children that have
                # already completed (end <= now) so the E pops its matching B, not
                # a leftover X. Assumes well-formed nesting (no overlap), which is
                # the viztracer contract; pure-X traces have no E events at all.
                ts = rec["ts"]
                while stack and stack[-1][1] <= ts:
                    stack.pop()
                if stack:
                    stack.pop()
                continue
            ts = rec["ts"]
            if rec["ph"] == "X" and rec["dur"] is not None:
                end = ts + rec["dur"]
                while stack and stack[-1][1] <= ts:
                    stack.pop()
            else:  # "B" (no dur; popped by its matching E)
                end = math.inf
            caller = stack[-1][0] if stack else None
            out.append((caller, rec["nid"], rec["raw"]))
            stack.append((rec["nid"], end))
    return out


# --------------------------------------------------------------------------
# value extraction + divergence
# --------------------------------------------------------------------------

def _extract_values(ev: dict[str, Any]) -> tuple[str, str]:
    """Return (arg_repr, return_repr) from a viztracer event's args, or ("","")."""
    args = ev.get("args") or {}
    fa = args.get("func_args")
    if isinstance(fa, dict) and fa:
        arg = ", ".join(f"{k}={_truncate(v)}" for k, v in fa.items())
    elif isinstance(fa, str) and fa:
        arg = _truncate(fa)
    else:
        arg = ""
    ret = args.get("return_value")
    if ret is None:
        ret = args.get("func_retval", "")
    ret = _truncate(ret) if isinstance(ret, str) and ret else ""
    return arg, ret


def _truncate(s: Any) -> str:
    s = str(s)
    return s if len(s) <= _MAX_VALUE_LEN else s[:_MAX_VALUE_LEN] + "…"


def _append_capped(dst: list[str], val: str) -> None:
    if not val:
        return
    if len(dst) < _MAX_SAMPLES:
        dst.append(val)


def _is_expected(
    doc: S.GraphDocument, caller: str, callee: str,
    parent_of: dict[str, str], node_by_id: dict[str, S.Node],
) -> bool:
    """An observed caller->callee pair is 'expected' if the static graph has a
    calls/references edge to the callee or (for a method) to its class, or a
    produces/consumes/transforms edge (ticket 04, auto-activates when present)."""
    direct = {S.CALLS, S.REFERENCES, S.PRODUCES, S.CONSUMES, S.TRANSFORMS}
    for e in doc.edges:
        if e.source == caller and e.target == callee and e.type in direct:
            return True
    parent = parent_of.get(callee)
    if parent is not None and node_by_id.get(parent) and node_by_id[parent].type == S.CLASS:
        for e in doc.edges:
            if e.source == caller and e.target == parent and e.type in (S.REFERENCES, S.CALLS):
                return True  # constructor / class call covers the method
    return False


def _divergence(
    doc: S.GraphDocument,
    observed: dict[tuple[str, str], EdgeRuntime],
    node_rt: dict[str, NodeRuntime],
    parent_of: dict[str, str],
    node_by_id: dict[str, S.Node],
) -> dict[str, list]:
    not_fired: list[tuple[str, str, str]] = []
    observed_caller_class: set[tuple[str, str]] = set()
    for (caller, callee) in observed:
        parent = parent_of.get(callee)
        if parent is not None and node_by_id.get(parent) and node_by_id[parent].type == S.CLASS:
            observed_caller_class.add((caller, parent))

    for e in doc.edges:
        if e.type not in (S.CALLS, S.REFERENCES):
            continue
        if e.type == S.REFERENCES and node_by_id.get(e.target) and node_by_id[e.target].type == S.CLASS:
            fired = (e.source, e.target) in observed_caller_class
        else:
            fired = (e.source, e.target) in observed
        if not fired:
            not_fired.append((e.source, e.target, e.type))

    unexpected: list[tuple[str, str]] = []
    for (caller, callee) in observed:
        if not _is_expected(doc, caller, callee, parent_of, node_by_id):
            unexpected.append((caller, callee))

    role: list[dict[str, Any]] = []
    for n in doc.nodes:
        if n.type != S.FUNCTION or not n.data_flow_role:
            continue
        rt = node_rt.get(n.id)
        count = rt.call_count if rt else 0
        if n.data_flow_role in _DATA_ROLES and count == 0:
            role.append({"node": n.id, "role": n.data_flow_role,
                         "call_count": 0, "reason": "cold"})
        elif n.data_flow_role == "none" and count > 0:
            role.append({"node": n.id, "role": "none",
                         "call_count": count, "reason": "hot"})

    return {"not_fired": not_fired, "unexpected": unexpected, "role": role}


def _as_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
