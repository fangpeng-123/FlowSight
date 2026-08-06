"""Enrichment attacher (decision 04).

- Eager: every module gets a one-line ``purpose`` at index time (LLM if
  configured, else the __init__ docstring fallback).
- Lazy: per-function ``purpose`` + ``contract`` + ``data_flow_role`` + ``risk``
  on drill-down, cached per code-hash so only changed functions re-enrich.

LLM-sourced attributes are advisory; parser structure stays trusted. A node's
``origin`` remains ``parser`` (its structure is parser-derived); advisory fields
are tagged via ``attrs["purpose_origin"]`` / their presence so the panel can mark
them ``llm``.
"""

from __future__ import annotations

import ast
import hashlib
import os

from flowsight import schema as S
from flowsight.enrich.cache import EnrichCache
from flowsight.enrich.llm import LLMClient, SYSTEM


# ---------- eager: module purpose ----------

def enrich_eager(doc: S.GraphDocument, llm: LLMClient | None, cache: EnrichCache | None) -> None:
    """Give every module a one-line purpose. LLM if available, else docstring fallback."""
    project_root = doc.project.get("path", "")
    for n in doc.nodes:
        if n.type != S.MODULE:
            continue
        files = _module_files(doc, n)
        ch = _module_content_hash(project_root, files)
        n.code_hash = ch

        cached = cache.get(n.id, ch) if cache is not None else None
        if cached:
            n.purpose = cached.get("purpose", "")
            n.attrs["purpose_origin"] = "llm"
            continue

        docstring = _module_docstring(project_root, n, files)
        if llm is None:
            if docstring:
                n.purpose = docstring
                n.attrs["purpose_origin"] = "docstring"
            else:
                n.purpose = f"模块 {n.label}（{len(files)} 个文件）"
                n.attrs["purpose_origin"] = "fallback"
            continue
        payload = llm.chat_json(SYSTEM, _module_prompt(n, files, docstring))
        n.purpose = payload.get("purpose", "") or docstring or f"模块 {n.label}"
        n.attrs["purpose_origin"] = "llm"
        if cache is not None:
            cache.put(n.id, ch, {"purpose": n.purpose})


def _module_files(doc: S.GraphDocument, module: S.Node) -> list[S.Node]:
    """Direct File children of a module."""
    ids = {e.target for e in doc.edges if e.source == module.id and e.type == S.CONTAINS}
    return [n for n in doc.nodes if n.id in ids and n.type == S.FILE]


def _module_content_hash(project_root: str, files: list[S.Node]) -> str:
    h = hashlib.sha256()
    for f in sorted(files, key=lambda n: n.id):
        h.update(f.id.encode("utf-8"))
        path = os.path.join(project_root, f.attrs.get("path", "")) if project_root else ""
        try:
            with open(path, encoding="utf-8") as fh:
                h.update(fh.read().encode("utf-8"))
        except OSError:
            pass
    return h.hexdigest()[:16]


def _module_docstring(project_root: str, module: S.Node, files: list[S.Node]) -> str:
    init = next((f for f in files if f.label == "__init__.py"), None)
    if not init or not project_root:
        return ""
    path = os.path.join(project_root, init.attrs.get("path", ""))
    try:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        return (ast.get_docstring(tree) or "").strip().splitlines()[0] if ast.get_docstring(tree) else ""
    except (OSError, SyntaxError):
        return ""


def _module_prompt(module: S.Node, files: list[S.Node], docstring: str) -> str:
    file_list = ", ".join(f.label for f in files if f.label != "__init__.py") or "(无)"
    return (
        f"Python 模块 `{module.label}`（dotted: {module.attrs.get('dotted', module.label)}）"
        f"包含文件: {file_list}。模块文档字符串: {docstring or '(无)'}。"
        f"用一句中文概括该模块的职责。只返回 JSON: {{\"purpose\": \"...\"}}"
    )


# ---------- lazy: per-function enrichment ----------

def enrich_function(node: S.Node, llm: LLMClient, cache: EnrichCache | None) -> dict | None:
    """Lazy enrichment of a function: purpose/contract/data_flow_role/risk.

    Cached per code-hash; a code change invalidates only this entry. Returns the
    advisory payload (never asserted on content by tests). Returns None if no LLM.
    """
    if not llm:
        return None
    cached = cache.get(node.id, node.code_hash) if cache is not None else None
    if cached:
        _apply(node, cached)
        return cached
    payload = llm.chat_json(SYSTEM, _function_prompt(node))
    _apply(node, payload)
    if cache is not None:
        cache.put(node.id, node.code_hash, payload)
    return payload


def _apply(node: S.Node, payload: dict) -> None:
    node.purpose = payload.get("purpose", "")
    c = payload.get("contract") or {}
    node.contract = S.Contract(
        inputs=c.get("inputs", ""), outputs=c.get("outputs", ""),
        errors=c.get("errors", ""), boundaries=c.get("boundaries", ""),
    )
    node.data_flow_role = payload.get("data_flow_role", "")
    r = payload.get("risk") or {}
    if r and (r.get("description") or r.get("category")):
        node.risk = S.Risk(
            category=r.get("category", ""), severity=r.get("severity", ""),
            description=r.get("description", ""), avoidance=r.get("avoidance", ""),
        )
    node.attrs["enriched"] = True


def _function_prompt(node: S.Node) -> str:
    sig = node.signature
    params = ", ".join(p.name + (": " + p.type if p.type else "") for p in (sig.params if sig else []))
    src = node.attrs.get("source", "")
    return (
        f"分析这个 Python 函数并输出 JSON。函数: `{node.attrs.get('qualname', node.label)}`"
        f"（参数: {params}; 返回: {sig.returns if sig else ''}）。\n源码:\n```python\n{src}\n```\n"
        f"返回 JSON: {{\"purpose\":\"一句话用途\","
        f"\"contract\":{{\"inputs\":\"\",\"outputs\":\"\",\"errors\":\"\",\"boundaries\":\"\"}},"
        f"\"data_flow_role\":\"producer|consumer|transform|none\","
        f"\"risk\":{{\"category\":\"\",\"severity\":\"high|medium|low\",\"description\":\"\",\"avoidance\":\"\"}}}}"
    )
