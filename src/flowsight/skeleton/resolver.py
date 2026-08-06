"""jedi-based call-site -> definition resolution (decisions 02/04).

``ast`` records call *sites* (the expression, not the target). jedi turns those
sites into true edges by inference. pyright/LSP is the optional precision
upgrade behind a future flag; jedi is the default in-process resolver.

Resolution is best-effort: dynamic patterns jedi can't infer simply yield no
edge (the skeleton stays correct, just less connected).
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from typing import Any

import jedi


@dataclass
class NameResolution:
    """A call on a bare name, e.g. ``foo(x)`` or ``VADDetector()``."""

    file: str          # project-relative module path of the def
    line: int          # def line (1-based)
    type: str          # jedi type: function | class | instance | module | ...

    @property
    def is_function(self) -> bool:
        return self.type == "function"

    @property
    def is_class(self) -> bool:
        return self.type in ("class", "instance")


@dataclass
class AttrResolution:
    """A call on an attribute, e.g. ``vad.detect(x)`` or ``mod.helper()``.

    ``receiver`` is what the value expression infers to; ``attr`` is the method
    name. The extractor looks up ``attr`` inside the receiver's class/module.
    """

    receiver_file: str
    receiver_line: int
    receiver_type: str
    attr: str

    @property
    def receiver_is_class(self) -> bool:
        return self.receiver_type in ("class", "instance")

    @property
    def receiver_is_module(self) -> bool:
        return self.receiver_type == "module"


Resolution = NameResolution | AttrResolution | None


class Resolver:
    """Resolves ast Call nodes to definitions via jedi."""

    def __init__(self, project_root: str):
        self.project_root = str(project_root)
        self._project = jedi.Project(path=self.project_root)
        self._scripts: dict[str, jedi.Script] = {}

    def _script(self, abs_path: str, source: str) -> jedi.Script:
        cached = self._scripts.get(abs_path)
        if cached is not None:
            return cached
        scr = jedi.Script(source, path=abs_path, project=self._project)
        self._scripts[abs_path] = scr
        return scr

    def resolve_call(self, call: ast.Call, abs_path: str, source: str) -> Resolution:
        func = call.func
        if isinstance(func, ast.Name):
            return self._infer_name(func.lineno, func.col_offset, abs_path, source)
        if isinstance(func, ast.Attribute):
            recv = self._infer_name(func.value.lineno, func.value.col_offset, abs_path, source)
            if recv is None or not isinstance(recv, NameResolution):
                return None
            return AttrResolution(
                receiver_file=recv.file,
                receiver_line=recv.line,
                receiver_type=recv.type,
                attr=func.attr,
            )
        return None

    def _infer_name(self, line: int, col: int, abs_path: str, source: str) -> NameResolution | None:
        scr = self._script(abs_path, source)
        try:
            defs = scr.infer(line, col)
        except Exception:
            defs = []
        if not defs:
            return None
        d = defs[0]
        mp = d.module_path
        if mp is None:
            return None
        # only care about in-project definitions
        try:
            mp.relative_to(self.project_root)
        except (ValueError, AttributeError):
            return None
        rel = str(mp.relative_to(self.project_root)).replace("\\", "/")
        return NameResolution(file=rel, line=d.line, type=d.type)


def code_hash(source_segment: str) -> str:
    """Stable hash of a function's source text (enrichment cache key)."""
    return hashlib.sha256(source_segment.encode("utf-8")).hexdigest()[:16]


def func_source_segment(source: str, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Exact source text of a function node (for hashing + LLM context)."""
    seg = ast.get_source_segment(source, node)
    return seg if seg is not None else ast.unparse(node)
