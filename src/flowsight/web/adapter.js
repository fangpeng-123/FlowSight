// FlowSight data adapter (decision 03/05) — the renderer-agnostic seam.
//
// Pure transform: schema graph JSON -> renderer model + style-by-type. No DOM, no
// 3d-force-graph dependency, so a Cytoscape/2D host can swap in later without
// rewriting the graph layer (decision 03's portability advice). Unit-tested with
// node:test; the 3D host (app.js) consumes these pure functions.
//
// Graph JSON shape (see src/flowsight/schema.py):
//   { project, nodes:[{id,type,label,origin,location,signature,purpose,contract,
//                       data_flow_role,risk,fields,code_hash,attrs}],
//     edges:[{source,target,type,origin,location,attrs}] }
//
// Node types: module | file | function | class | external | domain_entity
// Edge types: contains | imports | calls | references | produces | consumes | transforms | data_flow
// origin (trust): parser | llm | runtime

export const TYPES = {
  MODULE: "module", FILE: "file", FUNCTION: "function", CLASS: "class",
  EXTERNAL: "external", DOMAIN_ENTITY: "domain_entity",
};

export const EDGES = {
  CONTAINS: "contains", IMPORTS: "imports", CALLS: "calls", REFERENCES: "references",
  PRODUCES: "produces", CONSUMES: "consumes", TRANSFORMS: "transforms", DATA_FLOW: "data_flow",
};

// data-flow (advisory+runtime) edges animate; structural edges do not
const FLOW_EDGES = new Set([EDGES.PRODUCES, EDGES.CONSUMES, EDGES.TRANSFORMS, EDGES.DATA_FLOW]);

// ---- themes (carried from the verified prototype) ----
export const THEMES = {
  dark: {
    graphBg: "#000000", label: "#c2cad6",
    module: "#2dd4bf", file: "#38bdf8", class: "#a78bfa",
    domain_entity: "#f0a03b", function: "#5b8def", external: "#6b7480", risk: "#ef4444",
    contains: "#23282f", calls: "#4a5260", imports: "#3a5a8a", references: "#5a4a6a",
    flow: "#ffc107", dim: "#1e232b", dimLink: "#15191f",
  },
  light: {
    graphBg: "#eef1f5", label: "#2a3140",
    module: "#0d9488", file: "#0284c7", class: "#7c3aed",
    domain_entity: "#d97706", function: "#2563eb", external: "#94a3b8", risk: "#dc2626",
    contains: "#cbd5e1", calls: "#94a3b8", imports: "#3b6ea5", references: "#8b7aa3",
    flow: "#c2410c", dim: "#dde2ea", dimLink: "#e6eaf0",
  },
};

// ---- graph structure helpers ----

export function buildIndexes(graph) {
  const nodesById = new Map();
  for (const n of graph.nodes) nodesById.set(n.id, n);
  // parent map from `contains` edges (target -> source)
  const parentOf = new Map();
  const childrenOf = new Map();
  for (const e of graph.edges) {
    if (e.type === EDGES.CONTAINS) {
      parentOf.set(e.target, e.source);
      if (!childrenOf.has(e.source)) childrenOf.set(e.source, []);
      childrenOf.get(e.source).push(e.target);
    }
  }
  return { nodesById, parentOf, childrenOf };
}

export function topLevelModules(graph) {
  const { parentOf } = buildIndexes(graph);
  return graph.nodes.filter((n) => n.type === TYPES.MODULE && !parentOf.has(n.id));
}

// A node is visible if it is a root (no parent) OR its parent is expanded and visible.
export function isVisible(nodeId, parentOf, expanded) {
  let cur = nodeId;
  let guard = 0;
  while (cur && guard++ < 1000) {
    const parent = parentOf.get(cur);
    if (parent === undefined) return true; // root
    if (!expanded.has(parent)) return false;
    cur = parent;
  }
  return false;
}

export function neighbors(graph, nodeId) {
  const s = new Set([nodeId]);
  for (const e of graph.edges) {
    if (e.source === nodeId) s.add(e.target);
    if (e.target === nodeId) s.add(e.source);
  }
  return s;
}

// ---- the four views = data subsets over one schema (decision 05) ----
// dep: everything (calls+imports+contains+references + runtime overlay later)
// ctr: functions/files/classes + calls/contains (parser contracts surface)
// ds:  domain_entity + produces/consumes/transforms (LLM, ticket 04)
// risk: nodes with risk (LLM, ticket 03)
export const DIM = {
  dep:  { nodeOk: () => true,                       linkOk: () => true },
  ctr:  { nodeOk: (n) => [TYPES.FUNCTION, TYPES.FILE, TYPES.CLASS].includes(n.type),
          linkOk: (l) => [EDGES.CALLS, EDGES.CONTAINS].includes(l.type) },
  ds:   { nodeOk: (n) => n.type === TYPES.DOMAIN_ENTITY || n.type === TYPES.FUNCTION,
          linkOk: (l) => FLOW_EDGES.has(l.type) },
  risk: { nodeOk: (n) => hasRisk(n),                 linkOk: () => false },
};

export function hasRisk(n) {
  return !!(n.risk && n.risk.description);
}

// ---- lighting (selection + view filtering) ----
export function nodeLit(node, state) {
  if (state.selectedId) return state.neigh.has(node.id);
  const dim = DIM[state.dim] || DIM.dep;
  return dim.nodeOk(node);
}

export function linkLit(link, state) {
  if (state.selectedId) return link.source === state.selectedId || link.target === state.selectedId;
  const dim = DIM[state.dim] || DIM.dep;
  return dim.linkOk(link);
}

// ---- style-by-type (the spec's trust -> visual encoding) ----
export function nodeBaseColor(node, theme) {
  const t = THEMES[theme];
  switch (node.type) {
    case TYPES.MODULE: return t.module;
    case TYPES.FILE: return t.file;
    case TYPES.CLASS: return t.class;
    case TYPES.DOMAIN_ENTITY: return t.domain_entity;
    case TYPES.EXTERNAL: return t.external;
    default: return hasRisk(node) ? t.risk : t.function;
  }
}

export function nodeColor(node, theme, state) {
  return nodeLit(node, state) ? nodeBaseColor(node, theme) : THEMES[theme].dim;
}

export function linkColor(link, theme, state) {
  const t = THEMES[theme];
  if (!linkLit(link, state)) return t.dimLink;
  switch (link.type) {
    case EDGES.CONTAINS: return t.contains;
    case EDGES.CALLS: return t.calls;
    case EDGES.IMPORTS: return t.imports;
    case EDGES.REFERENCES: return t.references;
    default: return t.flow; // produces/consumes/transforms/data_flow
  }
}

export function linkWidth(link, state) {
  if (!linkLit(link, state)) return 0.4;
  switch (link.type) {
    case EDGES.CONTAINS: return 0.7;
    case EDGES.CALLS: return 1.2;
    case EDGES.IMPORTS: return 0.8;
    case EDGES.REFERENCES: return 0.6;
    case EDGES.TRANSFORMS: return 3;
    case EDGES.PRODUCES:
    case EDGES.CONSUMES: return 1.8;
    case EDGES.DATA_FLOW: return 2.4;
    default: return 1;
  }
}

export function nodeVal(node) {
  switch (node.type) {
    case TYPES.MODULE: return 3.5;
    case TYPES.FILE: return 2.5;
    case TYPES.CLASS: return 2;
    case TYPES.DOMAIN_ENTITY: return 2.5;
    case TYPES.EXTERNAL: return 1.2;
    default: return hasRisk(node) ? 1.9 : 1.5;
  }
}

export function arrowLen(link) {
  switch (link.type) {
    case EDGES.CONTAINS: return 0;
    case EDGES.CALLS: return 3.2;
    case EDGES.IMPORTS: return 3.2;
    case EDGES.REFERENCES: return 2.5;
    case EDGES.TRANSFORMS: return 6.5;
    case EDGES.PRODUCES:
    case EDGES.CONSUMES: return 4.5;
    case EDGES.DATA_FLOW: return 5;
    default: return 2;
  }
}

export function particles(link) {
  switch (link.type) {
    case EDGES.TRANSFORMS: return 5;
    case EDGES.PRODUCES:
    case EDGES.CONSUMES: return 3;
    case EDGES.DATA_FLOW: return 4;
    default: return 0;
  }
}

// ---- the transform: graph JSON -> render model ----
export function buildRenderModel(graph, { expanded, state }) {
  const { parentOf } = buildIndexes(graph);
  const chainVisible = new Set(
    graph.nodes.filter((n) => n.type !== TYPES.EXTERNAL && isVisible(n.id, parentOf, expanded)).map((n) => n.id)
  );
  // External nodes have no parent; show one only when a visible node imports/references it,
  // so an unexpanded dependency never floats alone.
  const visNodeIds = new Set(chainVisible);
  for (const n of graph.nodes) {
    if (n.type !== TYPES.EXTERNAL) continue;
    const hasVisibleImporter = graph.edges.some(
      (e) => (e.type === EDGES.IMPORTS || e.type === EDGES.REFERENCES)
        && e.target === n.id && chainVisible.has(e.source)
    );
    if (hasVisibleImporter) visNodeIds.add(n.id);
  }
  const nodes = graph.nodes
    .filter((n) => visNodeIds.has(n.id))
    .map((n) => ({
      id: n.id,
      label: n.label,
      type: n.type,
      origin: n.origin,
      hasRisk: hasRisk(n),
      parent: parentOf.get(n.id) || null,
      raw: n,
    }));
  const links = graph.edges
    .filter((e) => visNodeIds.has(e.source) && visNodeIds.has(e.target))
    .map((e) => ({ source: e.source, target: e.target, type: e.type, origin: e.origin, raw: e }));
  return { nodes, links };
}

// ---- search (covers functions/classes/files/modules/external; risks+structs in 03/04) ----
export function search(graph, query) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const out = [];
  for (const n of graph.nodes) {
    const hay = [n.label, n.attrs && n.attrs.dotted, n.attrs && n.attrs.path,
      n.purpose, n.data_flow_role,
      n.signature && n.signature.returns,
      n.signature && (n.signature.params || []).map((p) => p.name + ":" + p.type).join(" "),
    ].filter(Boolean).join(" ").toLowerCase();
    if (!hay.includes(q)) continue;
    let tag = n.type;
    if (n.type === TYPES.FUNCTION && hasRisk(n)) tag = "risk";
    out.push({ id: n.id, label: n.label, type: n.type, tag });
  }
  return out;
}
