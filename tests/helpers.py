"""Test helpers for graph assertions."""

from flowsight import schema as S


def by_type(doc: S.GraphDocument, t: str) -> list[S.Node]:
    return [n for n in doc.nodes if n.type == t]


def find_node(doc: S.GraphDocument, label: str, type: str | None = None) -> S.Node | None:
    for n in doc.nodes:
        if n.label == label and (type is None or n.type == type):
            return n
    return None


def find_func(doc: S.GraphDocument, qualname_suffix: str) -> S.Node | None:
    """Find a function whose qualname ends with the given suffix (e.g. 'VADDetector.detect')."""
    for n in doc.nodes:
        if n.type == S.FUNCTION and n.attrs.get("qualname", "").endswith(qualname_suffix):
            return n
    return None


def find_class(doc: S.GraphDocument, name: str) -> S.Node | None:
    return find_node(doc, name, S.CLASS)


def has_edge(doc: S.GraphDocument, source_label: str, target_label: str, etype: str) -> bool:
    src = find_node(doc, source_label)
    tgt = find_node(doc, target_label)
    if not src or not tgt:
        return False
    return any(
        e.source == src.id and e.target == tgt.id and e.type == etype
        for e in doc.edges
    )


def edges_of(doc: S.GraphDocument, etype: str) -> list[S.Edge]:
    return [e for e in doc.edges if e.type == etype]


def edge_labels(doc: S.GraphDocument, etype: str) -> list[tuple[str, str]]:
    id_to_label = {n.id: n.label for n in doc.nodes}
    out = []
    for e in edges_of(doc, etype):
        out.append((id_to_label.get(e.source, e.source), id_to_label.get(e.target, e.target)))
    return out
