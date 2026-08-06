"""FlowSight graph schema (decision 05).

One schema, four views (data subsets). Every node and edge carries an ``origin``
trust tag so the renderer always knows what to trust:

    parser  - exact, instant, trusted  (ast/jedi/importlib skeleton)
    llm     - advisory, layered        (purpose/contract/risk/domain entities)
    runtime - actual, observed         (viztracer data_flow overlay)

Node types:  module | file | function | class | external | domain_entity
Edge types:  contains | imports | calls | references | produces | consumes | transforms | data_flow

The four views are filters over this schema, not separate models:
  - dependency  : calls + imports + contains  (+ runtime data_flow overlay)
  - data-struct : domain_entity + produces/consumes/transforms
  - contracts   : function + contract
  - risk        : nodes with risk, ranked by severity
"""

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

# --- trust tags -------------------------------------------------------------
PARSER = "parser"
LLM = "llm"
RUNTIME = "runtime"
TRUST_ORDER = {PARSER: 0, LLM: 1, RUNTIME: 2}

# --- node types -------------------------------------------------------------
MODULE = "module"
FILE = "file"
FUNCTION = "function"
CLASS = "class"
EXTERNAL = "external"
DOMAIN_ENTITY = "domain_entity"

# --- edge types -------------------------------------------------------------
CONTAINS = "contains"
IMPORTS = "imports"
CALLS = "calls"
REFERENCES = "references"
PRODUCES = "produces"
CONSUMES = "consumes"
TRANSFORMS = "transforms"
DATA_FLOW = "data_flow"


@dataclass
class Location:
    """A position in source. ``file`` is project-relative. Lines are 1-based."""

    file: str
    line: int
    end_line: int = 0
    col: int = 0


@dataclass
class Param:
    name: str
    type: str = ""
    default: str = ""


@dataclass
class Signature:
    """Parser-derived (trusted) callable signature."""

    params: list[Param] = field(default_factory=list)
    returns: str = ""
    decorators: list[str] = field(default_factory=list)
    is_async: bool = False


@dataclass
class Contract:
    """LLM-derived (advisory) interface contract."""

    inputs: str = ""
    outputs: str = ""
    errors: str = ""
    boundaries: str = ""


@dataclass
class Risk:
    """LLM-derived (advisory) risk note."""

    category: str = ""
    severity: str = ""  # high | medium | low
    description: str = ""
    avoidance: str = ""


@dataclass
class Node:
    id: str
    type: str
    label: str
    origin: str = PARSER
    location: Location | None = None
    signature: Signature | None = None
    # LLM advisory (origin=llm when populated)
    purpose: str = ""
    contract: Contract | None = None
    data_flow_role: str = ""
    risk: Risk | None = None
    # class / domain-entity fields
    fields: list[Param] = field(default_factory=list)
    # runtime overlay (origin=runtime) - ticket 05
    runtime: dict[str, Any] = field(default_factory=dict)
    # enrichment cache key (sha256 of the function's source text)
    code_hash: str = ""
    # free-form, origin-tagged extras (e.g. module summary provenance)
    attrs: dict[str, Any] = field(default_factory=dict)

    def has_risk(self) -> bool:
        return bool(self.risk and self.risk.description)


@dataclass
class Edge:
    source: str  # from-node id
    target: str  # to-node id
    type: str
    origin: str = PARSER
    location: Location | None = None
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphDocument:
    project: dict[str, Any]
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def node_by_id(self, node_id: str) -> Node | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def children(self, parent_id: str) -> list[Node]:
        """Nodes this parent `contains`."""
        ids = {e.target for e in self.edges if e.source == parent_id and e.type == CONTAINS}
        return [n for n in self.nodes if n.id in ids]

    def parent_of(self, node_id: str) -> str | None:
        """The id of the node that `contains` this one, or None."""
        for e in self.edges:
            if e.target == node_id and e.type == CONTAINS:
                return e.source
        return None


# --- JSON round-trip --------------------------------------------------------
# dataclasses.asdict recurses into nested dataclasses, but loses type info; the
# from_* helpers rebuild the typed shapes so the rest of the codebase works with
# real objects, not dicts.

_NESTED = {
    "location": Location,
    "signature": Signature,
    "contract": Contract,
    "risk": Risk,
}


def _to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, list):
        return [_to_dict(x) for x in obj]
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    return obj


def _build(cls, d: Any):
    if d is None:
        return None
    if cls is Param:
        return Param(**{k: d.get(k) for k in ("name", "type", "default")})
    if cls is Location:
        return Location(**{k: d.get(k, 0 if k != "file" else "") for k in ("file", "line", "end_line", "col")})
    if cls is Signature:
        return Signature(
            params=[_build(Param, p) for p in d.get("params", [])],
            returns=d.get("returns", ""),
            decorators=list(d.get("decorators", [])),
            is_async=d.get("is_async", False),
        )
    if cls is Contract:
        return Contract(**{k: d.get(k, "") for k in ("inputs", "outputs", "errors", "boundaries")})
    if cls is Risk:
        return Risk(**{k: d.get(k, "") for k in ("category", "severity", "description", "avoidance")})
    return None


def node_to_dict(n: Node) -> dict[str, Any]:
    d = _to_dict(n)
    return d


def node_from_dict(d: dict[str, Any]) -> Node:
    return Node(
        id=d["id"],
        type=d["type"],
        label=d.get("label", d["id"]),
        origin=d.get("origin", PARSER),
        location=_build(Location, d.get("location")),
        signature=_build(Signature, d.get("signature")),
        purpose=d.get("purpose", ""),
        contract=_build(Contract, d.get("contract")),
        data_flow_role=d.get("data_flow_role", ""),
        risk=_build(Risk, d.get("risk")),
        fields=[_build(Param, p) for p in d.get("fields", [])],
        runtime=dict(d.get("runtime", {})),
        code_hash=d.get("code_hash", ""),
        attrs=dict(d.get("attrs", {})),
    )


def edge_to_dict(e: Edge) -> dict[str, Any]:
    return _to_dict(e)


def edge_from_dict(d: dict[str, Any]) -> Edge:
    return Edge(
        source=d["source"],
        target=d["target"],
        type=d["type"],
        origin=d.get("origin", PARSER),
        location=_build(Location, d.get("location")),
        attrs=dict(d.get("attrs", {})),
    )


def doc_to_dict(doc: GraphDocument) -> dict[str, Any]:
    return {
        "project": dict(doc.project),
        "nodes": [node_to_dict(n) for n in doc.nodes],
        "edges": [edge_to_dict(e) for e in doc.edges],
    }


def doc_from_dict(d: dict[str, Any]) -> GraphDocument:
    return GraphDocument(
        project=dict(d.get("project", {})),
        nodes=[node_from_dict(n) for n in d.get("nodes", [])],
        edges=[edge_from_dict(e) for e in d.get("edges", [])],
    )
