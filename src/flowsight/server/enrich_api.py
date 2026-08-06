"""Lazy per-function enrichment endpoint (ticket 03).

``GET /api/enrich?node=<id>`` enriches a function node (purpose/contract/
data_flow_role/risk) via the LLM, keyed by code-hash so only changed functions
re-enrich. Returns the enriched node as JSON. The LLM is advisory; the node's
``origin`` stays ``parser`` (structure is parser-derived).
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from flowsight import schema as S
from flowsight.enrich.attacher import enrich_function


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
        enrich_function(node, state.llm, state.cache)
        state.cache.save()
    except Exception as e:  # LLM/parse failure -> advisory, don't crash the view
        handler._json({"ok": False, "error": f"enrichment failed: {e}"}, code=502)
        return
    handler._json({"ok": True, "node": S.node_to_dict(node)})
