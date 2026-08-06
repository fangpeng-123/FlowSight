"""Lazy per-function enrichment endpoint (ticket 03 + ticket 04).

``GET /api/enrich?node=<id>`` enriches a function node (purpose/contract/
data_flow_role/risk) via the LLM, keyed by code-hash so only changed functions
re-enrich, and infers ``DomainEntity`` nodes + produces/consumes/transforms edges
(ticket 04). Returns the enriched node plus the entity/edge *delta* (newly added
nodes/edges) so the client can merge them into its graph copy. The LLM is advisory;
the function node's ``origin`` stays ``parser`` (structure is parser-derived) while
``DomainEntity`` nodes are ``origin=llm``.

``GET /api/enrich-all`` enriches every unenriched function at once (the
"progressive" affordance so the data-structures / risk views fill in on demand).
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from flowsight import schema as S
from flowsight.enrich.attacher import attach_entities, enrich_function


def handle_enrich(handler, state) -> None:
    node_id = parse_qs(urlparse(handler.path).query).get("node", [None])[0]
    if not node_id:
        handler._json({"ok": False, "error": "missing ?node=<id>"}, code=400)
        return
    node = state.doc.node_by_id(node_id)
    if node is None:
        handler._json({"ok": False, "error": f"unknown node: {node_id}"}, code=404)
        return
    if node.type != S.FUNCTION:
        handler._json({"ok": False, "error": "only function nodes are enriched"}, code=400)
        return
    if state.llm is None:
        handler._json(
            {"ok": False, "error": "LLM not configured (set FLOWSIGHT_LLM_API_KEY)"},
            code=503,
        )
        return
    try:
        payload = enrich_function(node, state.llm, state.cache)
        new_nodes: list[S.Node] = []
        new_edges: list[S.Edge] = []
        if payload:
            new_nodes, new_edges = attach_entities(node, state.doc, payload)
        state.cache.save()
        state.refresh_payload()
    except Exception as e:  # LLM/parse failure -> advisory, don't crash the view
        handler._json({"ok": False, "error": f"enrichment failed: {e}"}, code=502)
        return
    handler._json({
        "ok": True,
        "node": S.node_to_dict(node),
        "entities": {
            "nodes": [S.node_to_dict(n) for n in new_nodes],
            "edges": [S.edge_to_dict(e) for e in new_edges],
        },
    })


def enrich_all(handler, state) -> None:
    """Enrich every unenriched function (ticket 04 progressive affordance).

    Cache-aware: functions whose code-hash is already cached skip the LLM. A single
    function's failure never aborts the batch (enrichment is advisory).
    """
    if state.llm is None:
        handler._json(
            {"ok": False, "error": "LLM not configured (set FLOWSIGHT_LLM_API_KEY)"},
            code=503,
        )
        return
    count = 0
    for n in list(state.doc.nodes):
        if n.type != S.FUNCTION or n.attrs.get("enriched"):
            continue
        try:
            payload = enrich_function(n, state.llm, state.cache)
            if payload:
                attach_entities(n, state.doc, payload)
            count += 1
        except Exception:
            continue  # advisory: keep going so one bad function doesn't block the rest
    state.cache.save()
    state.refresh_payload()
    handler._json({"ok": True, "count": count,
                   "nodes": len(state.doc.nodes), "edges": len(state.doc.edges)})
