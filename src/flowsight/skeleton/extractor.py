"""Static skeleton extractor (decisions 02/04/05).

Walks a Python project with ``ast`` + ``importlib`` and emits a schema-conformant
graph document: Module/File/Function/Class/External nodes and
contains/imports/calls/references edges, every attribute tagged ``origin=parser``
(trusted). Call sites are upgraded to true call/reference edges by jedi.

Two passes: (1) build nodes + contains + imports + indexes; (2) resolve calls.
"""

from __future__ import annotations

import ast
import os
import sys
from dataclasses import dataclass
from typing import Any

from flowsight import schema as S
from flowsight.skeleton import resolver as R
from flowsight.skeleton import venv as V

_SKIP_DIRS = {"__pycache__", ".git", ".hg", ".svn", "node_modules", ".tox", ".mypy_cache", ".pytest_cache", "build", "dist", ".eggs"}


@dataclass
class _CallSite:
    caller_id: str | None      # enclosing Function node id (None = module-level)
    node: ast.Call
    abs_path: str
    rel_path: str
    source: str
    line: int


def extract(project_path: str) -> S.GraphDocument:
    root = os.path.abspath(project_path)
    if not os.path.isdir(root):
        raise FileNotFoundError(f"project path is not a directory: {root}")

    venv = V.detect(root)
    py_files = _walk_py_files(root)
    package_dirs = _package_dirs(root, py_files)

    nodes: list[S.Node] = []
    edges: list[S.Edge] = []
    call_sites: list[_CallSite] = []

    # indexes
    func_by_file_line: dict[tuple[str, int], S.Node] = {}
    class_by_file_line: dict[tuple[str, int], S.Node] = {}
    methods_by_class: dict[str, dict[str, S.Node]] = {}
    funcs_by_file: dict[str, dict[str, S.Node]] = {}   # top-level funcs of a file, by name
    module_name_to_id: dict[str, str] = {}              # dotted module name -> node id
    project_modules: set[str] = set()

    # --- modules (packages) ---
    for pdir_rel in sorted(package_dirs):
        dotted = _dotted(pdir_rel)
        node = S.Node(id=f"mod:{dotted}", type=S.MODULE, label=dotted.split(".")[-1],
                      origin=S.PARSER, attrs={"dotted": dotted})
        nodes.append(node)
        module_name_to_id[dotted] = node.id
        project_modules.add(dotted)
        project_modules.add(dotted.split(".")[0])
        methods_by_class.setdefault(node.id, {})  # not used for modules, uniformity
    # module containment (parent package -> sub package)
    for pdir_rel in package_dirs:
        dotted = _dotted(pdir_rel)
        parent_dotted = _parent_package_dotted(pdir_rel, package_dirs)
        if parent_dotted is not None:
            edges.append(S.Edge(source=f"mod:{parent_dotted}", target=f"mod:{dotted}", type=S.CONTAINS, origin=S.PARSER))

    # --- files + their defs ---
    for abs_path, rel_path in py_files:
        source = _read(abs_path)
        dotted = _dotted_module(rel_path)
        file_node = S.Node(
            id=f"file:{rel_path}", type=S.FILE, label=os.path.basename(rel_path),
            origin=S.PARSER,
            location=S.Location(file=rel_path, line=1),
            attrs={"dotted": dotted, "path": rel_path},
        )
        nodes.append(file_node)
        module_name_to_id[dotted] = file_node.id
        project_modules.add(dotted)
        project_modules.add(dotted.split(".")[0])
        # contains: package -> file
        pkg_dotted = _package_of_file(rel_path, package_dirs)
        if pkg_dotted is not None:
            edges.append(S.Edge(source=f"mod:{pkg_dotted}", target=file_node.id, type=S.CONTAINS, origin=S.PARSER))
        funcs_by_file.setdefault(file_node.id, {})
        _walk_file(rel_path, source, file_node, nodes, edges, call_sites,
                   func_by_file_line, class_by_file_line, methods_by_class, funcs_by_file)

    # --- imports ---
    _emit_imports(py_files, root, venv, project_modules, module_name_to_id, nodes, edges)

    # --- calls / references (jedi) ---
    _emit_calls(call_sites, root, func_by_file_line, class_by_file_line,
                methods_by_class, funcs_by_file, edges)

    project = {
        "path": root,
        "name": os.path.basename(root.rstrip(os.sep)) or root,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": sys.platform,
    }
    return S.GraphDocument(project=project, nodes=nodes, edges=edges)


# ---------- file discovery ----------

def _walk_py_files(root: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        # skip venv/site-packages dirs inside the project
        dirnames[:] = [d for d in dirnames if not _is_venv_dir(os.path.join(dirpath, d))]
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                abs_path = os.path.join(dirpath, fn)
                rel = os.path.relpath(abs_path, root).replace("\\", "/")
                out.append((abs_path, rel))
    return out


def _is_venv_dir(path: str) -> bool:
    base = os.path.basename(path)
    if base in {"venv", ".venv", "env", ".env"}:
        return True
    pyvenv = os.path.join(path, "pyvenv.cfg")
    return os.path.exists(pyvenv)


def _package_dirs(root: str, py_files: list[tuple[str, str]]) -> set[str]:
    """Project-relative dirs that contain an ``__init__.py``."""
    pkgs: set[str] = set()
    for _, rel in py_files:
        parts = rel.split("/")
        for i in range(len(parts) - 1):
            d = "/".join(parts[: i + 1])
            if os.path.exists(os.path.join(root, d, "__init__.py")):
                pkgs.add(d)
    return pkgs


# ---------- name helpers ----------

def _dotted(rel_dir: str) -> str:
    return rel_dir.replace("/", ".") if rel_dir else ""


def _dotted_module(rel_path: str) -> str:
    parts = rel_path[:-3].split("/")  # strip .py
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _parent_package_dotted(pkg_rel: str, package_dirs: set[str]) -> str | None:
    parts = pkg_rel.split("/")
    for i in range(len(parts) - 1, 0, -1):
        ancestor = "/".join(parts[:i])
        if ancestor in package_dirs:
            return _dotted(ancestor)
    return None


def _package_of_file(rel_path: str, package_dirs: set[str]) -> str | None:
    parts = rel_path.split("/")
    for i in range(len(parts) - 1, 0, -1):
        ancestor = "/".join(parts[:i])
        if ancestor in package_dirs:
            return _dotted(ancestor)
    return None


# ---------- per-file AST walk ----------

def _read(abs_path: str) -> str:
    with open(abs_path, encoding="utf-8") as f:
        return f.read()


def _walk_file(rel_path, source, file_node, nodes, edges, call_sites,
               func_by_file_line, class_by_file_line, methods_by_class, funcs_by_file):
    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError:
        return
    _visit_body(tree.body, rel_path, source, file_node, nodes, edges, call_sites,
                func_by_file_line, class_by_file_line, methods_by_class, funcs_by_file,
                parent_class_id=None, qual_prefix="", caller_id=None)


def _visit_body(body, rel_path, source, file_node, nodes, edges, call_sites,
                func_by_file_line, class_by_file_line, methods_by_class, funcs_by_file,
                parent_class_id, qual_prefix, caller_id):
    """Walk one body of statements. ``caller_id`` attributes calls to a function."""
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _define_func(stmt, rel_path, source, file_node, nodes, edges, call_sites,
                         func_by_file_line, class_by_file_line, methods_by_class, funcs_by_file,
                         parent_class_id, qual_prefix)
        elif isinstance(stmt, ast.ClassDef):
            _define_class(stmt, rel_path, source, file_node, nodes, edges, call_sites,
                          func_by_file_line, class_by_file_line, methods_by_class, funcs_by_file,
                          parent_class_id, qual_prefix)
        elif caller_id:
            # a non-def statement inside a function: attribute its calls here
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Call):
                    call_sites.append(_CallSite(caller_id, sub, "", rel_path, source, sub.lineno))


def _define_func(node, rel_path, source, file_node, nodes, edges, call_sites,
                 func_by_file_line, class_by_file_line, methods_by_class, funcs_by_file,
                 parent_class_id, qual_prefix):
    name = node.name
    qualname = f"{qual_prefix}.{name}" if qual_prefix else name
    func_id = f"func:{rel_path}::{qualname}@{node.lineno}"
    seg = R.func_source_segment(source, node)
    fn_node = S.Node(
        id=func_id, type=S.FUNCTION, label=name, origin=S.PARSER,
        location=S.Location(file=rel_path, line=node.lineno, end_line=node.end_lineno or node.lineno, col=node.col_offset),
        signature=_signature(node),
        code_hash=R.code_hash(seg),
        attrs={"qualname": qualname, "source": seg},
    )
    nodes.append(fn_node)
    parent_id = parent_class_id or file_node.id
    edges.append(S.Edge(source=parent_id, target=func_id, type=S.CONTAINS, origin=S.PARSER))
    func_by_file_line[(rel_path, node.lineno)] = fn_node
    if parent_class_id:
        methods_by_class.setdefault(parent_class_id, {})[name] = fn_node
    else:
        funcs_by_file.setdefault(file_node.id, {})[name] = fn_node
    # recurse: calls inside this function are attributed to it
    _visit_body(node.body, rel_path, source, file_node, nodes, edges, call_sites,
                func_by_file_line, class_by_file_line, methods_by_class, funcs_by_file,
                parent_class_id=parent_class_id, qual_prefix=qualname, caller_id=func_id)


def _define_class(node, rel_path, source, file_node, nodes, edges, call_sites,
                  func_by_file_line, class_by_file_line, methods_by_class, funcs_by_file,
                  parent_class_id, qual_prefix):
    name = node.name
    qualname = f"{qual_prefix}.{name}" if qual_prefix else name
    cls_id = f"class:{rel_path}::{qualname}@{node.lineno}"
    cls_node = S.Node(
        id=cls_id, type=S.CLASS, label=name, origin=S.PARSER,
        location=S.Location(file=rel_path, line=node.lineno, end_line=node.end_lineno or node.lineno, col=node.col_offset),
        fields=_class_fields(node),
        attrs={"qualname": qualname, "is_dataclass": _is_dataclass(node)},
    )
    nodes.append(cls_node)
    parent_id = parent_class_id or file_node.id
    edges.append(S.Edge(source=parent_id, target=cls_id, type=S.CONTAINS, origin=S.PARSER))
    class_by_file_line[(rel_path, node.lineno)] = cls_node
    methods_by_class.setdefault(cls_id, {})
    # recurse: methods/nested classes belong to this class; class-body calls have no caller
    _visit_body(node.body, rel_path, source, file_node, nodes, edges, call_sites,
                func_by_file_line, class_by_file_line, methods_by_class, funcs_by_file,
                parent_class_id=cls_id, qual_prefix=qualname, caller_id=None)


def _signature(node) -> S.Signature:
    a = node.args
    params: list[S.Param] = []
    all_args = []
    # positional-only, regular, vararg, kwonly, kwarg
    posonly = getattr(a, "posonlyargs", []) or []
    for arg in list(posonly) + list(a.args):
        if arg.arg in ("self", "cls") and not params:
            continue  # skip implicit self/cls
        params.append(S.Param(name=arg.arg, type=_unparse(arg.annotation)))
    if a.vararg:
        params.append(S.Param(name="*" + a.vararg.arg, type=_unparse(a.vararg.annotation)))
    for arg in a.kwonlyargs:
        params.append(S.Param(name=arg.arg, type=_unparse(arg.annotation)))
    if a.kwarg:
        params.append(S.Param(name="**" + a.kwarg.arg, type=_unparse(a.kwarg.annotation)))
    decorators = [_unparse(d) for d in node.decorator_list]
    returns = _unparse(node.returns)
    return S.Signature(params=params, returns=returns, decorators=decorators, is_async=isinstance(node, ast.AsyncFunctionDef))


def _class_fields(node) -> list[S.Param]:
    fields: list[S.Param] = []
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            fields.append(S.Param(name=stmt.target.id, type=_unparse(stmt.annotation)))
    return fields


def _is_dataclass(node) -> bool:
    for dec in node.decorator_list:
        if "dataclass" in _unparse(dec):
            return True
    return False


def _unparse(node) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


# ---------- imports ----------

def _emit_imports(py_files, root, venv, project_modules, module_name_to_id, nodes, edges):
    externals: dict[str, S.Node] = {}

    def external_node(top: str) -> S.Node:
        if top not in externals:
            n = S.Node(id=f"ext:{top}", type=S.EXTERNAL, label=top, origin=S.PARSER,
                       attrs={"installed": venv.find_installed_path(top) is not None})
            externals[top] = n
            nodes.append(n)
        return externals[top]

    for abs_path, rel_path in py_files:
        source = _read(abs_path)
        try:
            tree = ast.parse(source, filename=rel_path)
        except SyntaxError:
            continue
        file_id = f"file:{rel_path}"
        cur_pkg = _dotted_module(rel_path)
        for node in ast.walk(tree):
            targets: list[tuple[str, int]] = []  # (module_name, line)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    targets.append((alias.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                mod = _resolve_relative(node, cur_pkg)
                if mod:
                    targets.append((mod, node.lineno))
            for mod_name, line in targets:
                _emit_one_import(mod_name, line, rel_path, file_id, venv, project_modules,
                                 module_name_to_id, external_node, edges)


def _emit_one_import(mod_name, line, rel_path, file_id, venv, project_modules,
                     module_name_to_id, external_node, edges):
    top = mod_name.split(".")[0]
    # project-local?
    target_id = module_name_to_id.get(mod_name) or module_name_to_id.get(top)
    if target_id:
        edges.append(S.Edge(source=file_id, target=target_id, type=S.IMPORTS, origin=S.PARSER,
                            location=S.Location(file=rel_path, line=line)))
        return
    kind = V.classify(top, project_modules, venv)
    if kind == "stdlib":
        return
    # external (third-party)
    ext = external_node(top)
    edges.append(S.Edge(source=file_id, target=ext.id, type=S.IMPORTS, origin=S.PARSER,
                        location=S.Location(file=rel_path, line=line)))


def _resolve_relative(node: ast.ImportFrom, cur_pkg: str) -> str:
    """Resolve a (possibly relative) ``from`` import to an absolute dotted name."""
    if node.level == 0:
        return node.module or ""
    parts = cur_pkg.split(".") if cur_pkg else []
    # level 1 = current package; level N = go up N-1 parents
    up = node.level - 1
    if up > 0:
        parts = parts[: len(parts) - up] if len(parts) - up >= 0 else []
    if node.module:
        parts.append(node.module)
    return ".".join(parts)


# ---------- calls / references ----------

def _emit_calls(call_sites, root, func_by_file_line, class_by_file_line,
                methods_by_class, funcs_by_file, edges):
    resolver = R.Resolver(root)
    seen: set[tuple[str, str, str, int]] = set()  # de-dup (caller, target, type, line)

    for cs in call_sites:
        if cs.caller_id is None:
            continue  # only function->* call edges for now (module-level calls skipped)
        res = resolver.resolve_call(cs.node, os.path.join(root, cs.rel_path), cs.source)
        if res is None:
            continue
        target_id, etype = _map_resolution(res, func_by_file_line, class_by_file_line,
                                           methods_by_class, funcs_by_file)
        if target_id is None or target_id == cs.caller_id:
            continue
        key = (cs.caller_id, target_id, etype, cs.line)
        if key in seen:
            continue
        seen.add(key)
        edges.append(S.Edge(source=cs.caller_id, target=target_id, type=etype, origin=S.PARSER,
                            location=S.Location(file=cs.rel_path, line=cs.line)))


def _map_resolution(res, func_by_file_line, class_by_file_line,
                    methods_by_class, funcs_by_file) -> tuple[str | None, str]:
    if isinstance(res, R.NameResolution):
        if res.is_function:
            n = func_by_file_line.get((res.file, res.line))
            return (n.id if n else None), S.CALLS
        if res.type in ("class", "instance"):
            n = class_by_file_line.get((res.file, res.line))
            return (n.id if n else None), S.REFERENCES
        return None, S.CALLS
    if isinstance(res, R.AttrResolution):
        if res.receiver_is_class:
            cls = class_by_file_line.get((res.receiver_file, res.receiver_line))
            if cls:
                m = methods_by_class.get(cls.id, {}).get(res.attr)
                if m:
                    return m.id, S.CALLS
            return None, S.CALLS
        if res.receiver_is_module:
            # in-project module: look up a top-level function by attr name
            for fid, fns in funcs_by_file.items():
                # fid like "file:voice_agent/x.py"; match by dotted module of the file
                if _file_id_matches_module(fid, res.receiver_file):
                    m = fns.get(res.attr)
                    if m:
                        return m.id, S.CALLS
            return None, S.CALLS
    return None, S.CALLS


def _file_id_matches_module(file_id: str, receiver_file_rel: str) -> bool:
    # file_id = "file:<rel>"; receiver_file is also a project-relative path
    return file_id == f"file:{receiver_file_rel}"
