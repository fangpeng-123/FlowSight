// Data adapter unit tests (spec Seam 2: viz data adapter - pure transform).
// Run: node --test tests/test_adapter.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  buildIndexes, buildRenderModel, isVisible, neighbors, nodeColor, linkColor,
  linkWidth, nodeVal, arrowLen, particles, nodeBaseColor, hasRisk, hasRuntime,
  linkRuntime, isUnexpectedFlow, DIM, THEMES, EDGES, TYPES, search, riskRank,
  domainPipeline, dsSubgraph, riskSubgraph, deepReadAction, refinementPresentation,
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
  const dep = { selectedId: null, dim: "dep", neigh: new Set() };
  const ds = { selectedId: null, dim: "ds", neigh: new Set() };
  const contains = { type: EDGES.CONTAINS };
  const calls = { type: EDGES.CALLS };
  const transforms = { type: EDGES.TRANSFORMS };
  // structural edges are lit in the dep view
  assert.equal(linkColor(contains, "dark", dep), THEMES.dark.contains);
  assert.equal(linkColor(calls, "dark", dep), THEMES.dark.calls);
  assert.equal(linkWidth(contains, dep), 0.7);
  assert.equal(linkWidth(calls, dep), 1.2);
  // flow edges are lit in the ds view (dimmed in dep)
  assert.equal(linkWidth(transforms, ds), 3);
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

test("deep-read action exists only for a subject-backed module", () => {
  const fixtureCatalog = JSON.parse(readFileSync(
    new URL("./fixtures/reading-subjects.json", import.meta.url), "utf8",
  ));
  const subject = fixtureCatalog.subjects[0];
  const backed = {
    id: "mod:pkg.api", type: TYPES.MODULE, label: "api", origin: "parser",
    attrs: { reading_subject: subject },
  };
  const plainModule = { id: "mod:pkg", type: TYPES.MODULE, label: "pkg", origin: "parser" };
  const file = { id: "file:pkg/api.py", type: TYPES.FILE, label: "api.py", origin: "parser" };

  assert.deepEqual(deepReadAction(backed), {
    subjectId: subject.id,
    label: "Deep read this module",
  });
  assert.equal(deepReadAction(plainModule), null);
  assert.equal(deepReadAction(file), null);
});

test("a non-package reading subject can use its parser file as the action anchor", () => {
  const file = {
    id: "file:pkg/handlers/run.py", type: TYPES.FILE, label: "run.py", origin: "parser",
    attrs: { reading_subject: { id: "pkg/handlers", label: "Handlers", root: "pkg/handlers" } },
  };

  assert.equal(deepReadAction(file).subjectId, "pkg/handlers");
});

test("pending refinement is presented truthfully as Waiting for Agent", () => {
  assert.deepEqual(refinementPresentation({ status: "pending", stage: "waiting_for_agent" }), {
    label: "Waiting for Agent",
    busy: true,
  });
});

// ---- ticket 04: domain entities, four views, ranking, pipeline, search ----

// A domain graph mirroring the voice-agent pipeline: AudioChunk -> Transcript ->
// LLMMessage -> TTSAudio via produces/consumes/transforms, plus ranked risks.
const DGRAPH = {
  project: { name: "voice_agent" },
  nodes: [
    { id: "de:AudioChunk", type: "domain_entity", label: "AudioChunk", origin: "llm" },
    { id: "de:Transcript", type: "domain_entity", label: "Transcript", origin: "llm" },
    { id: "de:LLMMessage", type: "domain_entity", label: "LLMMessage", origin: "llm" },
    { id: "de:TTSAudio", type: "domain_entity", label: "TTSAudio", origin: "llm" },
    { id: "func:receive_chunk", type: "function", label: "receive_chunk", origin: "parser" },
    { id: "func:transcribe", type: "function", label: "transcribe", origin: "parser",
      risk: { description: "rm-hi", severity: "high" } },
    { id: "func:generate", type: "function", label: "generate", origin: "parser",
      risk: { description: "rm-lo", severity: "low" } },
    { id: "func:synthesize", type: "function", label: "synthesize", origin: "parser",
      risk: { description: "rm-md", severity: "medium" } },
  ],
  edges: [
    { source: "func:receive_chunk", target: "de:AudioChunk", type: "produces", origin: "llm" },
    { source: "func:transcribe", target: "de:AudioChunk", type: "consumes", origin: "llm" },
    { source: "func:transcribe", target: "de:Transcript", type: "produces", origin: "llm" },
    { source: "func:generate", target: "de:Transcript", type: "consumes", origin: "llm" },
    { source: "func:generate", target: "de:LLMMessage", type: "produces", origin: "llm" },
    { source: "func:synthesize", target: "de:LLMMessage", type: "consumes", origin: "llm" },
    { source: "func:synthesize", target: "de:TTSAudio", type: "produces", origin: "llm" },
    { source: "de:AudioChunk", target: "de:Transcript", type: "transforms", origin: "llm" },
    { source: "de:Transcript", target: "de:LLMMessage", type: "transforms", origin: "llm" },
    { source: "de:LLMMessage", target: "de:TTSAudio", type: "transforms", origin: "llm" },
  ],
};

test("dep view excludes domain_entity nodes and restricts to structural edges", () => {
  assert.ok(!DIM.dep.nodeOk({ type: TYPES.DOMAIN_ENTITY }));
  assert.ok(DIM.dep.nodeOk({ type: TYPES.FUNCTION }));
  assert.ok(DIM.dep.linkOk({ type: EDGES.CALLS }));
  assert.ok(DIM.dep.linkOk({ type: EDGES.IMPORTS }));
  assert.ok(!DIM.dep.linkOk({ type: EDGES.TRANSFORMS }));
  assert.ok(!DIM.dep.linkOk({ type: EDGES.PRODUCES }));
});

test("dsSubgraph returns domain entities + connected functions + domain edges", () => {
  const m = dsSubgraph(DGRAPH);
  const ids = new Set(m.nodes.map((n) => n.id));
  assert.ok(ids.has("de:AudioChunk"));
  assert.ok(ids.has("de:TTSAudio"));
  assert.ok(ids.has("func:receive_chunk"));   // connected via produces
  assert.ok(ids.has("func:transcribe"));      // connected via consumes/produces
  // only domain edges (produces/consumes/transforms) appear
  assert.ok(m.links.every((l) => [EDGES.PRODUCES, EDGES.CONSUMES, EDGES.TRANSFORMS].includes(l.type)));
  assert.equal(m.links.filter((l) => l.type === EDGES.TRANSFORMS).length, 3);
});

test("buildRenderModel in ds view returns the ds subgraph (ignores expand state)", () => {
  const state = { selectedId: null, dim: "ds", neigh: new Set() };
  const m = buildRenderModel(DGRAPH, { expanded: new Set(), state });
  assert.ok(m.nodes.some((n) => n.id === "de:AudioChunk"));
  assert.ok(m.nodes.some((n) => n.id === "func:receive_chunk"));
  assert.ok(!m.links.some((l) => l.type === EDGES.CALLS));
});

test("riskSubgraph returns only risk-bearing nodes", () => {
  const m = riskSubgraph(DGRAPH);
  assert.equal(m.nodes.length, 3);            // transcribe, generate, synthesize
  assert.ok(m.nodes.every((n) => n.hasRisk));
  assert.equal(m.links.length, 0);
});

test("buildRenderModel in risk view returns only risk nodes", () => {
  const state = { selectedId: null, dim: "risk", neigh: new Set() };
  const m = buildRenderModel(DGRAPH, { expanded: new Set(), state });
  assert.equal(m.nodes.length, 3);
  assert.ok(m.nodes.every((n) => n.hasRisk));
});

test("riskRank sorts high > medium > low, then by label", () => {
  // transcribe=high, synthesize=medium, generate=low
  const ranked = riskRank(DGRAPH).map((n) => n.label);
  assert.deepEqual(ranked, ["transcribe", "synthesize", "generate"]);
});

test("domainPipeline orders entities along the transforms chain (sources first)", () => {
  const order = domainPipeline(DGRAPH).map((n) => n.label);
  assert.deepEqual(order, ["AudioChunk", "Transcript", "LLMMessage", "TTSAudio"]);
});

test("search covers risks and domain entities and tags them", () => {
  // risk description
  let r = search(DGRAPH, "rm-hi");
  assert.ok(r.some((x) => x.id === "func:transcribe" && x.tag === "risk"));
  // domain entity by name
  r = search(DGRAPH, "Transcript");
  assert.ok(r.some((x) => x.id === "de:Transcript" && x.type === TYPES.DOMAIN_ENTITY));
  // severity is searchable
  r = search(DGRAPH, "medium");
  assert.ok(r.some((x) => x.id === "func:synthesize"));
});

// ---- ticket 05: runtime data-flow overlay (fired / not-fired / unexpected) ----

// runtime helpers
test("hasRuntime is true only for nodes a trace observed running", () => {
  assert.ok(hasRuntime({ runtime: { call_count: 3 } }));
  assert.ok(!hasRuntime({ runtime: { call_count: 0 } }));
  assert.ok(!hasRuntime({ runtime: {} }));
  assert.ok(!hasRuntime({}));
});

// link styling reads attrs.runtime (calls/references) and attrs.expected (data_flow)
const dep = { selectedId: null, dim: "dep", neigh: new Set() };
const mkCalls = (rt) => ({ type: EDGES.CALLS, raw: { attrs: rt ? { runtime: rt } : {} } });
const mkFlow = (expected) => ({ type: EDGES.DATA_FLOW, raw: { attrs: { expected } } });

test("data_flow edge: expected -> flow color, unexpected -> divergence color", () => {
  assert.equal(linkColor(mkFlow(true), "dark", dep), THEMES.dark.flow);
  assert.equal(linkColor(mkFlow(false), "dark", dep), THEMES.dark.unexpected);
  assert.ok(isUnexpectedFlow(mkFlow(false)));
  assert.ok(!isUnexpectedFlow(mkFlow(true)));
});

test("calls edge: fired -> normal, not-fired -> dim+thin, untraced -> normal", () => {
  const fired = mkCalls({ fired: true, call_count: 2 });
  const cold = mkCalls({ fired: false, call_count: 0 });
  const untraced = mkCalls(null);  // no trace loaded
  assert.equal(linkColor(fired, "dark", dep), THEMES.dark.calls);
  assert.equal(linkWidth(fired, dep), 1.2);
  assert.equal(linkColor(cold, "dark", dep), THEMES.dark.notFired);
  assert.equal(linkWidth(cold, dep), 0.5);
  // without a trace, calls edges keep their normal style (backward compatible)
  assert.equal(linkColor(untraced, "dark", dep), THEMES.dark.calls);
  assert.equal(linkWidth(untraced, dep), 1.2);
  assert.equal(linkRuntime(untraced), null);
});

test("buildRenderModel carries runtime attrs through to the render model", () => {
  // run -> a (fired), run -> b (not-fired), run -> c (data_flow, unexpected)
  const g = {
    project: { name: "ov" },
    nodes: [
      { id: "f:run", type: "function", label: "run", origin: "parser" },
      { id: "f:a", type: "function", label: "a", origin: "parser", runtime: { call_count: 1 } },
      { id: "f:b", type: "function", label: "b", origin: "parser" },
      { id: "f:c", type: "function", label: "c", origin: "parser" },
    ],
    edges: [
      { source: "f:run", target: "f:a", type: "calls", origin: "parser", attrs: { runtime: { fired: true, call_count: 1 } } },
      { source: "f:run", target: "f:b", type: "calls", origin: "parser", attrs: { runtime: { fired: false, call_count: 0 } } },
      { source: "f:run", target: "f:c", type: "data_flow", origin: "runtime", attrs: { expected: false, call_count: 1 } },
    ],
  };
  const m = buildRenderModel(g, { expanded: new Set(), state: dep });
  const byTarget = new Map(m.links.map((l) => [l.target, l]));
  assert.equal(linkColor(byTarget.get("f:a"), "dark", dep), THEMES.dark.calls);      // fired
  assert.equal(linkColor(byTarget.get("f:b"), "dark", dep), THEMES.dark.notFired);   // not-fired
  assert.equal(linkColor(byTarget.get("f:c"), "dark", dep), THEMES.dark.unexpected); // unexpected flow
  assert.ok(hasRuntime(m.nodes.find((n) => n.id === "f:a").raw));
});
