// Data adapter unit tests (spec Seam 2: viz data adapter - pure transform).
// Run: node --test tests/test_adapter.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildIndexes, buildRenderModel, isVisible, neighbors, nodeColor, linkColor,
  linkWidth, nodeVal, arrowLen, particles, nodeBaseColor, hasRisk, DIM, THEMES,
  EDGES, TYPES,
} from "../src/flowsight/web/adapter.js";

// A mini graph mirroring the fixture's shape: module > file > class > function.
const GRAPH = {
  project: { name: "demo" },
  nodes: [
    { id: "mod:pkg", type: "module", label: "pkg", origin: "parser", attrs: { dotted: "pkg" } },
    { id: "mod:pkg.sub", type: "module", label: "sub", origin: "parser", attrs: { dotted: "pkg.sub" } },
    { id: "file:pkg/a.py", type: "file", label: "a.py", origin: "parser", attrs: { path: "pkg/a.py" } },
    { id: "file:pkg/sub/b.py", type: "file", label: "b.py", origin: "parser", attrs: { path: "pkg/sub/b.py" } },
    { id: "class:pkg/a.py::C@1", type: "class", label: "C", origin: "parser" },
    { id: "func:pkg/a.py::run@5", type: "function", label: "run", origin: "parser",
      signature: { params: [{ name: "x", type: "int" }], returns: "C", is_async: false } },
    { id: "func:pkg/a.py::C.m@10", type: "function", label: "m", origin: "parser",
      risk: { description: "bad", severity: "high" } },
    { id: "ext:requests", type: "external", label: "requests", origin: "parser" },
  ],
  edges: [
    { source: "mod:pkg", target: "mod:pkg.sub", type: "contains", origin: "parser" },
    { source: "mod:pkg", target: "file:pkg/a.py", type: "contains", origin: "parser" },
    { source: "mod:pkg.sub", target: "file:pkg/sub/b.py", type: "contains", origin: "parser" },
    { source: "file:pkg/a.py", target: "class:pkg/a.py::C@1", type: "contains", origin: "parser" },
    { source: "class:pkg/a.py::C@1", target: "func:pkg/a.py::C.m@10", type: "contains", origin: "parser" },
    { source: "file:pkg/a.py", target: "func:pkg/a.py::run@5", type: "contains", origin: "parser" },
    { source: "func:pkg/a.py::run@5", target: "func:pkg/a.py::C.m@10", type: "calls", origin: "parser" },
    { source: "func:pkg/a.py::run@5", target: "class:pkg/a.py::C@1", type: "references", origin: "parser" },
    { source: "file:pkg/a.py", target: "ext:requests", type: "imports", origin: "parser" },
  ],
};

test("buildIndexes derives parent/child from contains edges", () => {
  const { parentOf, childrenOf } = buildIndexes(GRAPH);
  assert.equal(parentOf.get("file:pkg/a.py"), "mod:pkg");
  assert.equal(parentOf.get("mod:pkg.sub"), "mod:pkg");
  assert.equal(parentOf.get("func:pkg/a.py::C.m@10"), "class:pkg/a.py::C@1");
  assert.equal(parentOf.get("mod:pkg"), undefined); // root
  assert.ok(childrenOf.get("mod:pkg").includes("file:pkg/a.py"));
});

test("isVisible respects the expanded set up the parent chain", () => {
  const { parentOf } = buildIndexes(GRAPH);
  // expand only the top module: subpackage + its file should be hidden
  const exp = new Set(["mod:pkg"]);
  assert.ok(isVisible("mod:pkg", parentOf, exp));
  assert.ok(isVisible("file:pkg/a.py", parentOf, exp));       // parent mod:pkg expanded
  assert.ok(isVisible("mod:pkg.sub", parentOf, exp));          // parent mod:pkg expanded
  assert.ok(!isVisible("file:pkg/sub/b.py", parentOf, exp));  // parent sub NOT expanded
  // expand sub too
  exp.add("mod:pkg.sub");
  assert.ok(isVisible("file:pkg/sub/b.py", parentOf, exp));
});

test("buildRenderModel returns only visible nodes and the links between them", () => {
  const state = { selectedId: null, dim: "dep", neigh: new Set() };
  // expand top module + a file + that file's class -> run, C, C.m all visible
  const exp = new Set(["mod:pkg", "file:pkg/a.py", "class:pkg/a.py::C@1"]);
  const model = buildRenderModel(GRAPH, { expanded: exp, state });
  const ids = new Set(model.nodes.map((n) => n.id));
  assert.ok(ids.has("mod:pkg"));
  assert.ok(ids.has("file:pkg/a.py"));
  assert.ok(ids.has("func:pkg/a.py::run@5"));     // file expanded -> function visible
  assert.ok(ids.has("class:pkg/a.py::C@1"));
  assert.ok(ids.has("func:pkg/a.py::C.m@10"));    // class expanded -> method visible
  assert.ok(ids.has("mod:pkg.sub"));              // top module expanded -> subpackage visible
  assert.ok(!ids.has("file:pkg/sub/b.py"));       // sub NOT expanded -> its file hidden
  // links between two visible nodes are kept; links touching a hidden node are dropped
  assert.ok(model.links.some((l) => l.type === "calls"));       // run -> C.m, both visible
  assert.ok(model.links.some((l) => l.type === "references"));  // run -> C, both visible
  assert.ok(model.links.some((l) => l.type === "imports"));     // file -> ext, both visible
  // b.py is hidden, so the contains edge into it is dropped
  assert.ok(!model.links.some((l) => l.target === "file:pkg/sub/b.py"));
});

test("style-by-type: nodeBaseColor maps each type to its theme color", () => {
  const t = THEMES.dark;
  assert.equal(nodeBaseColor({ type: TYPES.MODULE }, "dark"), t.module);
  assert.equal(nodeBaseColor({ type: TYPES.FILE }, "dark"), t.file);
  assert.equal(nodeBaseColor({ type: TYPES.CLASS }, "dark"), t.class);
  assert.equal(nodeBaseColor({ type: TYPES.EXTERNAL }, "dark"), t.external);
  assert.equal(nodeBaseColor({ type: TYPES.FUNCTION, risk: { description: "x" } }, "dark"), t.risk);
  assert.equal(nodeBaseColor({ type: TYPES.FUNCTION }, "dark"), t.function);
});

test("style-by-type: linkColor/width/arrow/particles follow the edge encoding", () => {
  const state = { selectedId: null, dim: "dep", neigh: new Set() };
  const contains = { type: EDGES.CONTAINS };
  const calls = { type: EDGES.CALLS };
  const transforms = { type: EDGES.TRANSFORMS };
  assert.equal(linkColor(contains, "dark", state), THEMES.dark.contains);
  assert.equal(linkColor(calls, "dark", state), THEMES.dark.calls);
  assert.equal(linkWidth(contains, state), 0.7);
  assert.equal(linkWidth(calls, state), 1.2);
  assert.equal(linkWidth(transforms, state), 3);
  assert.equal(arrowLen(contains), 0);
  assert.equal(arrowLen(calls), 3.2);
  assert.equal(arrowLen(transforms), 6.5);
  assert.equal(particles(contains), 0);
  assert.equal(particles(calls), 0);
  assert.equal(particles(transforms), 5);
});

test("nodeVal sizes modules above files above functions; risk bumps functions", () => {
  assert.ok(nodeVal({ type: TYPES.MODULE }) > nodeVal({ type: TYPES.FILE }));
  assert.ok(nodeVal({ type: TYPES.FILE }) > nodeVal({ type: TYPES.FUNCTION }));
  assert.ok(nodeVal({ type: TYPES.FUNCTION, risk: { description: "x" } }) > nodeVal({ type: TYPES.FUNCTION }));
});

test("selection lighting: neighbors lit, rest dimmed", () => {
  const neigh = neighbors(GRAPH, "func:pkg/a.py::run@5");
  const state = { selectedId: "func:pkg/a.py::run@5", dim: "dep", neigh };
  const run = GRAPH.nodes.find((n) => n.id === "func:pkg/a.py::run@5");
  const ext = GRAPH.nodes.find((n) => n.id === "ext:requests");
  assert.equal(nodeColor(run, "dark", state), nodeBaseColor(run, "dark")); // lit
  assert.equal(nodeColor(ext, "dark", state), THEMES.dark.dim);            // dimmed
});

test("ctr view keeps functions/files/classes + calls/contains, drops imports", () => {
  const state = { selectedId: null, dim: "ctr", neigh: new Set() };
  const exp = new Set(["mod:pkg", "mod:pkg.sub"]);
  const model = buildRenderModel(GRAPH, { expanded: exp, state });
  // the filter is applied via linkLit/nodeLit at render time; here we check the DIM predicates directly
  assert.ok(DIM.ctr.nodeOk({ type: TYPES.FUNCTION }));
  assert.ok(DIM.ctr.nodeOk({ type: TYPES.CLASS }));
  assert.ok(!DIM.ctr.nodeOk({ type: TYPES.EXTERNAL }));
  assert.ok(DIM.ctr.linkOk({ type: EDGES.CALLS }));
  assert.ok(DIM.ctr.linkOk({ type: EDGES.CONTAINS }));
  assert.ok(!DIM.ctr.linkOk({ type: EDGES.IMPORTS }));
});

test("hasRisk and risk view predicate", () => {
  assert.ok(hasRisk({ risk: { description: "x" } }));
  assert.ok(!hasRisk({ risk: {} }));
  assert.ok(!hasRisk({}));
  assert.ok(DIM.risk.nodeOk({ risk: { description: "x" } }));
  assert.ok(!DIM.risk.nodeOk({}));
});

test("external nodes appear only when a visible node imports them", () => {
  const state = { selectedId: null, dim: "dep", neigh: new Set() };
  // only top module expanded: a.py's importer is visible, so ext:requests shows
  let exp = new Set(["mod:pkg"]);
  let m = buildRenderModel(GRAPH, { expanded: exp, state });
  assert.ok(m.nodes.some((n) => n.id === "ext:requests"));
  assert.ok(m.links.some((l) => l.type === EDGES.IMPORTS));
  // collapse the top module: a.py hidden -> ext:requests has no visible importer -> hidden
  exp = new Set([]);
  m = buildRenderModel(GRAPH, { expanded: exp, state });
  assert.ok(!m.nodes.some((n) => n.id === "ext:requests"));
  assert.ok(!m.links.some((l) => l.type === EDGES.IMPORTS));
});
