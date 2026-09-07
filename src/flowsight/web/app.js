// FlowSight web app - adapts the verified prototype to consume real served graph
// JSON. Rendering uses 3d-force-graph v1.80; all graph/style logic goes through
// the renderer-agnostic adapter (adapter.js), the tested seam.
//
// v1.80 constraints (from the prototype): no onNodeDblClick (detected in
// onNodeClick ~350ms); overlays live outside #cy (constructor clears it); theme
// background is triple-set (backgroundColor + renderer.clearColor + scene.background).

import {
  buildIndexes, buildRenderModel, neighbors, nodeColor, linkColor, linkWidth,
  nodeVal, arrowLen, particles, nodeBaseColor, hasRisk, THEMES, TYPES, EDGES,
  search, topLevelModules, riskRank, domainPipeline, deepReadAction, refinementPresentation,
  captureExplorationState, restoreExplorationState,
} from "./adapter.js";

let graph = null;
let state = { selectedId: null, neigh: new Set(), dim: "dep" };
let expanded = new Set();
let theme = "dark";
const refinements = new Map();
const refinementLoads = new Set();
let refinementEpoch = 0;
const T = () => THEMES[theme];

let Graph = null;
let deepReadSnapshot = null;
let _dcId = null, _dcT = 0; // single/double-click detection
const nodeById = (id) => graph && graph.nodes.find((n) => n.id === id);
const { parentOf } = { parentOf: null }; // set after load

// ---------- load ----------
async function load() {
  refinementEpoch += 1;
  refinements.clear();
  refinementLoads.clear();
  const r = await fetch("/api/graph");
  graph = await r.json();
  const idx = buildIndexes(graph);
  window.__parentOf = idx.parentOf;
  // default: expand top-level modules only (clean overview; drill in on demand)
  expanded = new Set(topLevelModules(graph).map((n) => n.id));
  document.getElementById("project-title").textContent = graph.project.name || "FlowSight";
  document.getElementById("project-sub").textContent =
    `${graph.project.python || ""} · ${graph.nodes.length} 节点 · ${graph.edges.length} 边`;
  syncLegendVars();
  renderPanel(null);
  loadTraceBadge();
}

// ticket 05: surface the runtime overlay. If a trace is active, /api/divergence
// returns its trace_id + an actual-on-expected divergence summary; show a badge
// in the panel head so the overlay is discoverable. Silent no-op without a trace.
async function loadTraceBadge() {
  const $b = document.getElementById("trace-badge");
  if (!$b) return;
  try {
    const r = await fetch("/api/divergence");
    const j = await r.json();
    if (!j.ok || !j.trace_id) { $b.style.display = "none"; return; }
    const d = j.divergence || {};
    const nf = (d.not_fired || []).length, un = (d.unexpected || []).length, rl = (d.role || []).length;
    const bits = [`<span class="tdot"></span>运行时追踪已叠加`];
    const sub = [];
    if (nf) sub.push(`${nf} 未触发`);
    if (un) sub.push(`${un} 异常`);
    if (rl) sub.push(`${rl} 角色偏离`);
    if (sub.length) bits.push(sub.join(" · "));
    $b.innerHTML = bits.join(" · ");
    $b.style.display = "inline-flex";
  } catch (e) { $b.style.display = "none"; }
}

window.addEventListener("engines-ready", async () => {
  await load();
  if (window.__esmOK || typeof ForceGraph3D !== "undefined") {
    try { initGraph(); }
    catch (e) { setStatus("渲染出错：" + e.message, true); console.error(e); }
  } else {
    setStatus("3D 引擎未就绪（ESM 与本地 UMD 均不可用），请检查网络后刷新。", true);
  }
});

// ---------- 3D graph ----------
function visibleData() {
  return buildRenderModel(graph, { expanded, state });
}

function labelObj(n) {
  const lit = state.selectedId ? state.neigh.has(n.id) : true;
  const color = (state.selectedId && n.id === state.selectedId) ? "#ffffff" : (lit ? T().label : T().dimLink);
  const h = n.type === TYPES.MODULE ? 3.6 : (n.type === TYPES.FILE ? 2.8 : 2.2);
  const y = -(nodeVal(n.raw) * 2.4) - 4;
  if (typeof SpriteText !== "undefined") {
    const s = new SpriteText(n.label); s.color = color; s.textHeight = h; s.padding = 1; s.position.y = y; return s;
  }
  if (typeof THREE !== "undefined") { const sp = makeCanvasSprite(n.label, color, h); sp.position.y = y; return sp; }
  return null;
}

function makeCanvasSprite(text, color, h) {
  const cvs = document.createElement("canvas");
  const ctx = cvs.getContext("2d"); const fs = 64;
  ctx.font = fs + 'px "Segoe UI",sans-serif';
  const w = Math.ceil(ctx.measureText(text).width) + 24;
  cvs.width = w; cvs.height = fs + 24;
  ctx.font = fs + 'px "Segoe UI",sans-serif';
  ctx.fillStyle = color; ctx.textBaseline = "middle"; ctx.textAlign = "left";
  ctx.fillText(text, 12, cvs.height / 2);
  const tex = new THREE.CanvasTexture(cvs); tex.minFilter = THREE.LinearFilter; tex.magFilter = THREE.LinearFilter;
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false });
  const sp = new THREE.Sprite(mat);
  const bw = h * 1.5; sp.scale.set(bw * (w / cvs.height), bw, 1);
  return sp;
}

function initGraph() {
  if (typeof ForceGraph3D === "undefined") { setStatus("3D 引擎未就绪，请刷新重试。", true); return; }
  const d = visibleData();
  Graph = ForceGraph3D()(document.getElementById("cy"))
    .graphData({ nodes: d.nodes.map((n) => ({ ...n })), links: d.links.map((l) => ({ ...l })) })
    .backgroundColor(T().graphBg)
    .nodeRelSize(5)
    .nodeVal((n) => nodeVal(n.raw))
    .nodeColor((n) => nodeColor(n.raw, theme, state))
    .nodeLabel((n) => n.label + (n.hasRisk ? " ⚠" : "") + "  ·  " + n.type)
    .nodeThreeObjectExtend(true).nodeThreeObject(labelObj)
    .linkColor((l) => linkColor(l, theme, state))
    .linkWidth((l) => linkWidth(l, state))
    .linkDirectionalArrowLength((l) => arrowLen(l))
    .linkDirectionalArrowRelPos(1)
    .linkDirectionalParticles((l) => particles(l))
    .linkDirectionalParticleWidth(1)
    .linkDirectionalParticleSpeed(0.01)
    .linkDirectionalParticleColor(() => T().flow)
    .onNodeClick((n) => {
      const now = Date.now();
      if (_dcId === n.id && now - _dcT < 350) { _dcId = null; toggleExpand(n.id); return; }
      _dcId = n.id; _dcT = now; selectNode(n.id);
    })
    .onBackgroundClick(() => clearSelection());
  Graph.d3Force("link").distance((l) => l.type === EDGES.CONTAINS ? 11 : 32).strength((l) => l.type === EDGES.CONTAINS ? 0.7 : 0.22);
  Graph.d3Force("charge").strength(-100);
  Graph.d3VelocityDecay(0.35);
  Graph.onEngineStop(() => Graph.zoomToFit(400, 40));
  applyGraphBg();
  document.getElementById("status").style.display = "none";
}

function rebuild() {
  if (!Graph) return;
  const oldPos = {};
  try { Graph.graphData().nodes.forEach((n) => { oldPos[n.id] = { x: n.x, y: n.y, z: n.z }; }); } catch (e) {}
  const d = visibleData();
  d.nodes.forEach((n) => {
    if (oldPos[n.id]) { n.x = oldPos[n.id].x; n.y = oldPos[n.id].y; n.z = oldPos[n.id].z; }
    else {
      const p = window.__parentOf && window.__parentOf.get(n.id);
      const o = p && oldPos[p];
      if (o) { n.x = o.x + (Math.random() * 8 - 4); n.y = o.y + (Math.random() * 8 - 4); n.z = o.z + (Math.random() * 8 - 4); }
    }
  });
  Graph.graphData({ nodes: d.nodes.map((n) => ({ ...n })), links: d.links.map((l) => ({ ...l })) });
  Graph.refresh();
}

function applyGraphBg() {
  if (!Graph) return;
  const c = T().graphBg;
  Graph.backgroundColor(c);
  try { const r = Graph.renderer && Graph.renderer(); if (r) { r.setClearColor(new THREE.Color(c), 1); if (r.domElement) r.domElement.style.backgroundColor = c; } } catch (e) {}
  try { const sc = Graph.scene(); if (sc) sc.background = new THREE.Color(c); } catch (e) {}
}

function refreshGraph({ resume = true } = {}) {
  if (!Graph) return;
  applyGraphBg();
  Graph.nodeColor((n) => nodeColor(n.raw, theme, state))
    .nodeThreeObject(labelObj)
    .linkColor((l) => linkColor(l, theme, state))
    .linkWidth((l) => linkWidth(l, state))
    .linkDirectionalParticleColor(() => T().flow);
  if (resume) { try { Graph.resumeAnimation && Graph.resumeAnimation(); } catch (e) {} }
  Graph.refresh();
}

function flyTo(id) {
  if (!Graph) return;
  const n = Graph.graphData().nodes.find((x) => x.id === id);
  if (!n) return;
  const d = 80;
  Graph.cameraPosition({ x: n.x + d, y: n.y + d * 0.5, z: n.z + d }, { x: n.x, y: n.y, z: n.z }, 800);
}

// ---------- selection / expand / dim ----------
function selectNode(id) {
  closeSearch();
  // keep the current view (ticket 04): selecting a domain entity in the ds view or
  // a risk in the risk view stays in that view rather than yanking back to dep.
  state.selectedId = id; state.neigh = neighbors(graph, id);
  document.querySelectorAll(".dim-tab").forEach((t) => t.classList.toggle("active", t.dataset.dim === state.dim));
  refreshGraph(); flyTo(id); renderPanel(id);
  maybeEnrich(id);
}

// Lazy per-function LLM enrichment (ticket 03 + 04). Advisory: a fetch failure or
// an unconfigured LLM never blocks viewing the trusted parser structure. Ticket 04
// also merges the inferred DomainEntity nodes + flow edges into the client graph.
async function maybeEnrich(id) {
  const n = nodeById(id);
  if (!n || n.type !== TYPES.FUNCTION) return;
  if (n.attrs && (n.attrs.enriched || n.attrs.enriching)) return;
  n.attrs = { ...(n.attrs || {}), enriching: true };
  if (state.selectedId === id) renderPanel(id);
  try {
    const r = await fetch(`/api/enrich?node=${encodeURIComponent(id)}`);
    const j = await r.json();
    if (j.ok && j.node) {
      n.purpose = j.node.purpose || "";
      n.contract = j.node.contract || null;
      n.data_flow_role = j.node.data_flow_role || "";
      n.risk = j.node.risk || null;
      n.attrs = { ...(n.attrs || {}), enriched: true, enriching: false };
      mergeEntities(j.entities);          // ticket 04: inferred domain entities
    } else {
      n.attrs = { ...(n.attrs || {}), enriching: false, enrichError: (j && j.error) || "富化不可用" };
    }
  } catch (e) {
    n.attrs = { ...(n.attrs || {}), enriching: false, enrichError: e.message };
  }
  if (state.selectedId === id) renderPanel(id);
}

// Merge a delta of entity nodes/edges (from /api/enrich) into the client graph,
// deduping by id / (source,target,type,via). Rebuilds the graph if anything was added.
function mergeEntities(entities) {
  if (!graph || !entities) return;
  let added = false;
  const haveNode = new Set(graph.nodes.map((n) => n.id));
  for (const n of (entities.nodes || [])) {
    if (!haveNode.has(n.id)) { graph.nodes.push(n); haveNode.add(n.id); added = true; }
  }
  const ekey = (e) => `${e.source}|${e.target}|${e.type}|${(e.attrs && e.attrs.via) || ""}`;
  const haveEdge = new Set(graph.edges.map(ekey));
  for (const e of (entities.edges || [])) {
    const k = ekey(e);
    if (!haveEdge.has(k)) { graph.edges.push(e); haveEdge.add(k); added = true; }
  }
  if (added) {
    window.__parentOf = buildIndexes(graph).parentOf;
    rebuild();
  }
}

// "Progressive" affordance (ticket 04): enrich every function at once so the
// data-structures / risk views fill in. Cache-aware server-side; re-fetches the
// graph afterward. Preserves expand state.
async function enrichAll() {
  setStatus("正在富化全部函数…");
  try {
    const r = await fetch("/api/enrich-all");
    const j = await r.json();
    if (!j.ok) { setStatus(j.error || "富化失败", true); return; }
    graph = await (await fetch("/api/graph")).json();
    window.__parentOf = buildIndexes(graph).parentOf;
    rebuild(); refreshGraph();
    renderPanel(state.selectedId);
    document.getElementById("status").style.display = "none";
  } catch (e) {
    setStatus("富化失败：" + e.message, true);
  }
}
window.enrichAll = enrichAll;
function clearSelection() {
  state.selectedId = null; state.neigh = new Set();
  document.querySelectorAll(".dim-tab").forEach((t) => t.classList.toggle("active", t.dataset.dim === state.dim));
  refreshGraph(); renderPanel(null);
}
function toggleExpand(id) {
  const n = nodeById(id);
  if (!n) return;
  if (![TYPES.MODULE, TYPES.FILE, TYPES.CLASS].includes(n.type)) return;
  if (expanded.has(id)) expanded.delete(id); else expanded.add(id);
  rebuild(); refreshGraph(); renderPanel(state.selectedId);
}
function setDim(d) {
  state.dim = d; state.selectedId = null; state.neigh = new Set();
  document.querySelectorAll(".dim-tab").forEach((t) => t.classList.toggle("active", t.dataset.dim === d));
  refreshGraph(); renderPanel(null);
}
window.selectNode = selectNode;
window.toggleExpand = toggleExpand;
window.clearSelection = clearSelection;

// ---------- graph edge helpers (for the panel) ----------
// one shape, parameterised by direction + type, instead of five near-copies.
function edgesOf(id, dir, type) {
  const key = dir === "out" ? "source" : "target";
  const other = dir === "out" ? "target" : "source";
  return graph.edges.filter((e) => e[key] === id && e.type === type).map((e) => nodeById(e[other])).filter(Boolean);
}
const childrenOf = (id) => edgesOf(id, "out", EDGES.CONTAINS);
const callersOf = (id) => edgesOf(id, "in", EDGES.CALLS);
const calleesOf = (id) => edgesOf(id, "out", EDGES.CALLS);
const refsOf = (id) => edgesOf(id, "out", EDGES.REFERENCES);
const importsOf = (id) => edgesOf(id, "out", EDGES.IMPORTS);

// ---------- side panel ----------
const $c = document.getElementById("panel-content");
const $s = document.getElementById("sel-info");

function sevColor(s) { return s === "high" ? T().risk : "#eab308"; }
function trustPill(origin) { return `<span class="trust ${origin}">${origin}</span>`; }
function nodeRow(n) {
  if (!n) return "";
  return `<div class="row" onclick="selectNode('${n.id}')"><span class="n" style="background:${nodeBaseColor(n, theme)}"></span>${n.label}<span class="arr">›</span></div>`;
}
function secOpen(cls, title, dot) { return `<div class="sec ${cls || ""}" id="sec-${cls}"><h2><span class="dot" style="background:${dot}"></span>${title}</h2>`; }
function expandBtn(id) { const o = expanded.has(id); return `<button class="exp-btn" onclick="toggleExpand('${id}')">${o ? "▾ 收起子节点" : "▸ 展开子节点"}</button>`; }
function paramsStr(p) { return (p || []).map((x) => x.name + (x.type ? ": " + x.type : "")).join("  ·  "); }
function fieldsStr(f) { return (f || []).map((x) => x.name + (x.type ? ": " + x.type : "")).join("  ·  "); }
const labelOf = (id) => { const n = nodeById(id); return n ? n.label : id; };
function enrichAllBtn() {
  return `<button class="exp-btn" onclick="enrichAll()">✦ 富化全部函数（推断领域实体与风险）</button>`;
}

function deepReadBtn(node) {
  const action = deepReadAction(node);
  if (!action) return "";
  const encodedId = encodeURIComponent(action.subjectId).replace(/'/g, "%27");
  const current = refinements.get(action.subjectId);
  if (!current && !refinementLoads.has(action.subjectId)) {
    loadCurrentRefinement(action.subjectId);
    return `<button class="exp-btn deep-read-btn" disabled>Checking deep read…</button>`;
  }
  const presentation = refinementPresentation(current);
  if (current && current.status === "pending") {
    return `<button class="exp-btn deep-read-btn" onclick="cancelDeepRead(decodeURIComponent('${encodedId}'), '${current.job_id}')">Cancel pending deep read</button>`;
  }
  if (presentation && presentation.busy) {
    return `<button class="exp-btn deep-read-btn" disabled>${presentation.label}</button>`;
  }
  if (current && current.status === "ready" && current.artifact_available) {
    return `<button class="exp-btn deep-read-btn" onclick="openDeepRead(decodeURIComponent('${encodedId}'))">Open deep read</button>`;
  }
  if (current && current.status === "failed" && current.fallback_artifact_available) {
    return `<button class="exp-btn deep-read-btn" onclick="openDeepRead(decodeURIComponent('${encodedId}'))">Open previous deep read</button><button class="exp-btn deep-read-btn" onclick="requestDeepRead(decodeURIComponent('${encodedId}'))">Retry deep read</button>`;
  }
  if (current && current.status === "stale") {
    const previous = current.fallback_artifact_available
      ? `<button class="exp-btn deep-read-btn" onclick="openDeepRead(decodeURIComponent('${encodedId}'))">Open previous deep read</button>` : "";
    return `<div class="empty">Stale · source or reading context changed</div>${previous}<button class="exp-btn deep-read-btn" onclick="requestDeepRead(decodeURIComponent('${encodedId}'))">Regenerate deep read</button>`;
  }
  return `<button class="exp-btn deep-read-btn" onclick="requestDeepRead(decodeURIComponent('${encodedId}'))">${action.label}</button>`;
}

async function loadCurrentRefinement(subjectId) {
  const epoch = refinementEpoch;
  refinementLoads.add(subjectId);
  try {
    const response = await fetch(`/api/refinements/current?subject_id=${encodeURIComponent(subjectId)}`);
    const status = response.ok ? await response.json() : { status: "missing" };
    if (epoch !== refinementEpoch) return;
    refinements.set(subjectId, status);
    const presentation = refinementPresentation(status);
    if (presentation && presentation.busy) pollRefinement(subjectId, status.job_id, 0);
  } catch (error) {
    if (epoch !== refinementEpoch) return;
    refinements.set(subjectId, { status: "failed", display: error.message });
  } finally {
    if (epoch === refinementEpoch) {
      refinementLoads.delete(subjectId);
      if (state.selectedId) renderPanel(state.selectedId);
    }
  }
}

async function cancelDeepRead(subjectId, jobId) {
  const epoch = refinementEpoch;
  const response = await fetch(`/api/refinements/${encodeURIComponent(jobId)}`, { method: "DELETE" });
  const status = await response.json();
  if (epoch !== refinementEpoch) return;
  refinements.set(subjectId, response.ok ? status : { status: "failed", display: status.error });
  if (state.selectedId) renderPanel(state.selectedId);
}
window.cancelDeepRead = cancelDeepRead;

async function requestDeepRead(subjectId) {
  const epoch = refinementEpoch;
  try {
    const response = await fetch("/api/refinements", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject_id: subjectId }),
    });
    const status = await response.json();
    if (epoch !== refinementEpoch) return;
    if (!response.ok) throw new Error(status.error || `HTTP ${response.status}`);
    refinements.set(subjectId, status);
    renderPanel(state.selectedId);
    pollRefinement(subjectId, status.job_id, 0);
  } catch (error) {
    if (epoch !== refinementEpoch) return;
    refinements.set(subjectId, { status: "failed", display: error.message });
    renderPanel(state.selectedId);
  }
}
window.requestDeepRead = requestDeepRead;

function currentCameraState() {
  if (!Graph) return null;
  const camera = Graph.camera();
  const controls = Graph.controls();
  return {
    position: { x: camera.position.x, y: camera.position.y, z: camera.position.z },
    target: controls && controls.target
      ? { x: controls.target.x, y: controls.target.y, z: controls.target.z }
      : { x: 0, y: 0, z: 0 },
  };
}

async function openDeepRead(subjectId) {
  const epoch = refinementEpoch;
  const openingCurrent = refinements.get(subjectId)?.status === "ready";
  await loadCurrentRefinement(subjectId);
  if (epoch !== refinementEpoch || deepReadSnapshot) return;
  const current = refinements.get(subjectId);
  // A newly stale result needs an explicit click on its previous-output action.
  if (openingCurrent && current?.status !== "ready") return;
  const artifactUrl = current && current.status === "ready" && current.artifact_available
    ? current.artifact_url
    : current && current.fallback_artifact_available ? current.fallback_artifact_url : "";
  if (!artifactUrl) return;
  const panel = document.getElementById("panel");
  deepReadSnapshot = captureExplorationState({
    camera: currentCameraState(), expanded, selectedId: state.selectedId,
    dim: state.dim, theme, panelCollapsed: panel.classList.contains("collapsed"),
    panelScrollTop: document.getElementById("panel-content").scrollTop,
  });
  document.getElementById("cy").style.display = "none";
  panel.style.display = "none";
  document.getElementById("legend").style.display = "none";
  document.querySelector(".hint").style.display = "none";
  const view = document.getElementById("deep-read-view");
  document.getElementById("deep-read-crumb").textContent = `Module deep read · ${subjectId}`;
  document.getElementById("deep-read-frame").src = artifactUrl;
  view.hidden = false;
}
window.openDeepRead = openDeepRead;

function closeDeepRead() {
  if (!deepReadSnapshot) return;
  const snapshot = restoreExplorationState(deepReadSnapshot);
  document.getElementById("deep-read-view").hidden = true;
  document.getElementById("deep-read-frame").src = "about:blank";
  document.getElementById("cy").style.display = "block";
  const panel = document.getElementById("panel");
  panel.style.display = "flex";
  panel.classList.toggle("collapsed", snapshot.panelCollapsed);
  document.getElementById("legend").style.display = "";
  document.querySelector(".hint").style.display = "";
  expanded = snapshot.expanded;
  state.selectedId = snapshot.selectedId;
  state.dim = snapshot.dim;
  state.neigh = snapshot.selectedId ? neighbors(graph, snapshot.selectedId) : new Set();
  theme = snapshot.theme;
  document.documentElement.dataset.theme = theme;
  applyTheme({ preserveCamera: true });
  if (Graph && snapshot.camera) {
    Graph.cameraPosition(snapshot.camera.position, snapshot.camera.target, 0);
  }
  renderPanel(state.selectedId);
  document.getElementById("panel-content").scrollTop = snapshot.panelScrollTop;
  deepReadSnapshot = null;
}
document.getElementById("deep-read-back").addEventListener("click", closeDeepRead);

async function pollRefinement(subjectId, jobId, attempt, epoch = refinementEpoch) {
  if (epoch !== refinementEpoch || refinements.get(subjectId)?.job_id !== jobId) return;
  try {
    const response = await fetch(`/api/refinements/${encodeURIComponent(jobId)}`);
    const status = await response.json();
    if (epoch !== refinementEpoch || refinements.get(subjectId)?.job_id !== jobId) return;
    if (!response.ok) throw new Error(status.error || `HTTP ${response.status}`);
    refinements.set(subjectId, status);
    if (state.selectedId) renderPanel(state.selectedId);
    const presentation = refinementPresentation(status);
    if (presentation && presentation.busy) {
      const delay = Math.min(1000 + attempt * 100, 5000);
      setTimeout(() => pollRefinement(subjectId, jobId, attempt + 1, epoch), delay);
    } else if (status.status === "failed") {
      loadCurrentRefinement(subjectId);
    }
  } catch (error) {
    if (epoch !== refinementEpoch) return;
    const current = refinements.get(subjectId);
    const presentation = refinementPresentation(current);
    if (presentation && presentation.busy) {
      const delay = Math.min(1000 + attempt * 100, 5000);
      setTimeout(() => pollRefinement(subjectId, jobId, attempt + 1, epoch), delay);
    } else {
      refinements.set(subjectId, { status: "failed", display: error.message });
      if (state.selectedId) renderPanel(state.selectedId);
    }
  }
}

// ---- runtime overlay card (ticket 05) ----
// Per-function runtime stats captured by a viztracer trace: call_count, timings,
// and sampled arg/return value reprs. Shown only when a trace observed the
// function running. origin=runtime (actual, observed).
function fmtUs(us) {
  if (us == null) return "-";
  if (us >= 1000) return (us / 1000).toFixed(2) + " ms";
  return us.toFixed(1) + " µs";
}
function valList(label, vals) {
  if (!vals || !vals.length) return "";
  return `<div class="kv"><span class="k">${label}</span><span class="v"><div class="params">${vals.map((v) => `<div>${v}</div>`).join("")}</div></span></div>`;
}
function runtimeCard(n) {
  const rt = n.runtime;
  if (!rt || !rt.call_count) return "";
  let h = secOpen("rt", "运行时追踪", T().flow);
  h += `<div class="card"><div class="t">${n.label} ${trustPill("runtime")}</div>`;
  h += `<div class="kv"><span class="k">调用次数</span><span class="v">${rt.call_count}</span></div>`;
  h += `<div class="kv"><span class="k">耗时</span><span class="v">均值 ${fmtUs(rt.avg_dur_us)} · 区间 ${fmtUs(rt.min_dur_us)}–${fmtUs(rt.max_dur_us)} · 累计 ${fmtUs(rt.total_dur_us)}</span></div>`;
  h += valList("参数采样", rt.arg_values);
  h += valList("返回采样", rt.return_values);
  h += `</div></div>`;
  return h;
}

// ---- dim-aware project overview (no node selected) ----
function overviewPanel() {
  if (state.dim === "risk") return riskOverview();
  if (state.dim === "ds") return dsOverview();
  return defaultOverview();
}

function defaultOverview() {
  let h = secOpen("dep", "依赖关系 / 数据流", T().call);
  const mods = graph.nodes.filter((n) => n.type === TYPES.MODULE);
  h += `<div class="card"><div class="t">模块（${mods.length}）</div>${mods.map(nodeRow).join("")}</div>`;
  h += `<div class="empty">提示：双击模块/文件展开子节点，单击节点查看详情。切换上方标签可查看 契约 / 数据结构 / 风险。</div></div>`;
  h += secOpen("ctr", "接口契约", T().function);
  h += `<div class="empty">单击函数节点查看 参数 / 返回 / 调用方 / 被调用。${trustPill("parser")} 为解析器可信结构。</div></div>`;
  h += secOpen("ds", `数据结构（${graph.nodes.filter((n) => n.type === TYPES.DOMAIN_ENTITY).length}）`, T().domain_entity);
  h += `<div class="empty">领域实体（LLM 推断）在富化后出现；切换到「数据结构」标签查看管线。</div></div>`;
  h += secOpen("risk", `风险清单（${riskRank(graph).length}）`, T().risk);
  h += `<div class="empty">风险（LLM 推断）在富化后出现；切换到「风险」标签按严重度排列。</div></div>`;
  return h;
}

function riskOverview() {
  const risks = riskRank(graph);
  let h = secOpen("risk", `风险清单（${risks.length}） ${trustPill("llm")}`, T().risk);
  if (!risks.length) {
    h += `<div class="empty">尚无风险--函数经 LLM 富化后，风险会按严重度（high > medium > low）排列在此。</div>`;
    h += enrichAllBtn();
  } else {
    risks.forEach((n) => {
      const r = n.risk || {};
      const sc = sevColor(r.severity);
      h += `<div class="card"><div class="t" onclick="selectNode('${n.id}')" style="cursor:pointer"><span class="n" style="background:${sc}"></span>${n.label} <span class="pill" style="color:${sc};border-color:${sc}">${r.severity || "?"}</span></div>`;
      h += `<div class="kv"><span class="k">类别</span><span class="v">${r.category || "-"}</span></div>`;
      h += `<div class="kv"><span class="k">坑点</span><span class="v">${r.description || "-"}</span></div>`;
      h += `<div class="kv"><span class="k">规避</span><span class="v">${r.avoidance || "-"}</span></div></div>`;
    });
  }
  h += `</div>`;
  return h;
}

function entityCard(n) {
  const producers = edgesOf(n.id, "in", EDGES.PRODUCES).map(nodeRow).join("") || '<span class="empty">-</span>';
  const consumers = edgesOf(n.id, "in", EDGES.CONSUMES).map(nodeRow).join("") || '<span class="empty">-</span>';
  return `<div class="card"><div class="t" onclick="selectNode('${n.id}')" style="cursor:pointer"><span class="n" style="background:${T().domain_entity}"></span>${n.label} ${trustPill("llm")}</div>`
    + `<div class="kv"><span class="k">生产者</span><span class="v">${producers}</span></div>`
    + `<div class="kv"><span class="k">消费者</span><span class="v">${consumers}</span></div></div>`;
}

function dsOverview() {
  const ents = domainPipeline(graph);
  const tfs = graph.edges.filter((e) => e.type === EDGES.TRANSFORMS);
  let h = secOpen("ds", `数据结构 / 领域管线（${ents.length} 实体） ${trustPill("llm")}`, T().domain_entity);
  if (!ents.length) {
    h += `<div class="empty">尚无领域实体--函数经 LLM 富化后，会推断出领域数据管线（如 AudioChunk -> Transcript -> LLMMessage -> TTSAudio）。</div>`;
    h += enrichAllBtn();
  } else {
    ents.forEach((n) => { h += entityCard(n); });
    if (tfs.length) {
      h += `<div class="kv" style="margin-top:6px"><span class="k">转换</span><span class="v">`;
      tfs.forEach((e) => {
        const via = (e.attrs && e.attrs.via_label) || "";
        h += `<div class="row" onclick="selectNode('${(e.attrs && e.attrs.via) || ""}')"><span class="n" style="background:${T().flow}"></span>${labelOf(e.source)} → ${labelOf(e.target)}${via ? ` <span class="empty">经 ${via}</span>` : ""}<span class="arr">›</span></div>`;
      });
      h += `</span></div>`;
    }
  }
  h += `</div>`;
  return h;
}

function renderPanel(sel) {
  if (!graph) return;
  if (!sel) {
    $s.innerHTML = state.dim === "risk" ? "风险清单 · 按严重度排列"
      : state.dim === "ds" ? "数据结构 · 领域数据管线"
      : "未选中节点 · 显示项目总览";
    $c.innerHTML = overviewPanel();
    return;
  }
  const n = nodeById(sel);
  if (!n) { renderPanel(null); return; }
  const tn = { module: "模块", file: "文件", class: "类", function: "函数", external: "外部依赖", domain_entity: "结构体" }[n.type] || n.type;
  $s.innerHTML = `已选中 <b>${n.label}</b> · ${n.hasRisk ? "风险" : ""}${tn} ${trustPill(n.origin)}`;
  const loc = n.location ? `${n.location.file}:${n.location.line}` : (n.attrs && n.attrs.path) || "";
  let crumbHtml = loc ? `<div class="crumb"><b>位置：</b>${loc}</div>` : "";

  if (n.type === TYPES.FUNCTION) {
    let h = crumbHtml + secOpen("ctr", "接口契约", T().function);
    const sig = n.signature || {};
    h += `<div class="card"><div class="t">${n.label} ${sig.is_async ? '<span class="pill" style="color:#f0a03b;border-color:#f0a03b">async</span>' : ""}</div>`;
    h += `<div class="kv"><span class="k">返回</span><span class="v">${sig.returns || "—"}</span></div>`;
    h += `<div class="kv"><span class="k">参数</span><span class="v"><div class="params">${paramsStr(sig.params) || "—"}</div></span></div>`;
    if (sig.decorators && sig.decorators.length) h += `<div class="kv"><span class="k">装饰器</span><span class="v">${sig.decorators.join(" · ")}</span></div>`;
    h += `</div>`;
    // LLM advisory (ticket 03 fills these)
    const ea = n.attrs || {};
    if (n.purpose || n.contract || n.risk) {
      h += `<div class="card"><div class="t">语义富化 ${trustPill("llm")}</div>`;
      if (n.purpose) h += `<div class="kv"><span class="k">用途</span><span class="v">${n.purpose}</span></div>`;
      if (n.contract) {
        h += `<div class="kv"><span class="k">输入</span><span class="v">${n.contract.inputs || "—"}</span></div>`;
        h += `<div class="kv"><span class="k">输出</span><span class="v">${n.contract.outputs || "—"}</span></div>`;
        h += `<div class="kv"><span class="k">错误</span><span class="v">${n.contract.errors || "—"}</span></div>`;
        h += `<div class="kv"><span class="k">边界</span><span class="v">${n.contract.boundaries || "—"}</span></div>`;
      }
      if (n.data_flow_role) h += `<div class="kv"><span class="k">数据流</span><span class="v">${n.data_flow_role}</span></div>`;
      h += `</div>`;
      if (n.risk && n.risk.description) {
        h += `<div class="card"><div class="t">${n.label} <span class="pill" style="color:${sevColor(n.risk.severity)};border-color:${sevColor(n.risk.severity)}">${n.risk.severity}</span></div>`;
        h += `<div class="kv"><span class="k">类别</span><span class="v">${n.risk.category || "—"}</span></div>`;
        h += `<div class="kv"><span class="k">坑点</span><span class="v">${n.risk.description}</span></div>`;
        h += `<div class="kv"><span class="k">规避</span><span class="v">${n.risk.avoidance || "—"}</span></div></div>`;
      }
    } else if (ea.enriching) {
      h += `<div class="empty">LLM 富化中…（用途 / 契约 / 风险） ${trustPill("llm")}</div>`;
    } else if (ea.enrichError) {
      h += `<div class="empty">富化不可用：${ea.enrichError}。${trustPill("parser")} 结构仍可信。</div>`;
    } else {
      h += `<div class="empty">单击节点可触发 LLM 富化（用途 / 契约 / 风险）。${trustPill("parser")} 结构为解析器可信。</div>`;
    }
    h += `</div>`;
    h += runtimeCard(n);
    h += secOpen("dep", "依赖 / 数据流", T().call);
    const callers = callersOf(sel), callees = calleesOf(sel);
    h += `<div class="kv"><span class="k">调用方</span><span class="v">${callers.length ? callers.map(nodeRow).join("") : '<span class="empty">入口</span>'}</span></div>`;
    h += `<div class="kv"><span class="k">被调用</span><span class="v">${callees.length ? callees.map(nodeRow).join("") : '<span class="empty">出口</span>'}</span></div>`;
    const refs = refsOf(sel);
    if (refs.length) h += `<div class="kv"><span class="k">引用</span><span class="v">${refs.map(nodeRow).join("")}</span></div>`;
    h += `</div>`;
    $c.innerHTML = h;
  } else if (n.type === TYPES.CLASS) {
    let h = crumbHtml + secOpen("ds", "类 / 数据结构", T().class);
    h += `<div class="card"><div class="t">${n.label} ${n.attrs && n.attrs.is_dataclass ? '<span class="pill" style="color:' + T().domain_entity + ';border-color:' + T().domain_entity + '">dataclass</span>' : ""}</div>`;
    h += `<div class="params">${fieldsStr(n.fields) || "（无字段）"}</div></div>`;
    h += secOpen("ctr", "方法 / 成员", T().function);
    const methods = childrenOf(sel).filter((c) => c.type === TYPES.FUNCTION);
    methods.forEach((m) => (h += nodeRow(m)));
    if (!methods.length) h += `<div class="empty">无方法</div>`;
    h += `</div>`;
    $c.innerHTML = h;
  } else if (n.type === TYPES.FILE) {
    const kids = childrenOf(sel);
    const fns = kids.filter((c) => c.type === TYPES.FUNCTION);
    const cls = kids.filter((c) => c.type === TYPES.CLASS);
    let h = crumbHtml + secOpen("dep", "文件概览", T().file);
    h += `<div class="card"><div class="t">${n.label}</div><div class="kv"><span class="k">路径</span><span class="v">${n.attrs && n.attrs.path || ""}</span></div>`;
    h += `<div class="kv"><span class="k">成员</span><span class="v">类 ${cls.length} · 函数 ${fns.length}</span></div></div>${expandBtn(sel)}${deepReadBtn(n)}</div>`;
    h += secOpen("ctr", "成员", T().function);
    cls.forEach((c) => (h += nodeRow(c)));
    fns.forEach((c) => (h += nodeRow(c)));
    if (!kids.length) h += `<div class="empty">无成员</div>`;
    h += `</div>`;
    const imps = importsOf(sel);
    if (imps.length) {
      h += secOpen("dep", "导入", T().external);
      imps.forEach((c) => (h += nodeRow(c)));
      h += `</div>`;
    }
    $c.innerHTML = h;
  } else if (n.type === TYPES.MODULE) {
    const kids = childrenOf(sel);
    const files = kids.filter((c) => c.type === TYPES.FILE);
    const subMods = kids.filter((c) => c.type === TYPES.MODULE);
    let h = secOpen("dep", "模块概览", T().module);
    h += `<div class="card"><div class="t">${n.label}</div><div class="kv"><span class="k">dotted</span><span class="v">${n.attrs && n.attrs.dotted || n.label}</span></div>`;
    if (n.purpose) h += `<div class="kv"><span class="k">用途</span><span class="v">${n.purpose} ${trustPill(n.attrs && n.attrs.purpose_origin === "llm" ? "llm" : "parser")}</span></div>`;
    const subject = n.attrs && n.attrs.reading_subject;
    h += `<div class="kv"><span class="k">成员</span><span class="v">文件 ${files.length} · 子模块 ${subMods.length}</span></div>`;
    if (subject) {
      h += `<div class="kv"><span class="k">阅读主题</span><span class="v">${subject.label}<br><span class="empty">${subject.rationale}</span></span></div>`;
    }
    h += `</div>${expandBtn(sel)}${deepReadBtn(n)}</div>`;
    h += secOpen("ctr", "成员", T().file);
    subMods.forEach((c) => (h += nodeRow(c)));
    files.forEach((c) => (h += nodeRow(c)));
    if (!kids.length) h += `<div class="empty">无成员</div>`;
    h += `</div>`;
    $c.innerHTML = h;
  } else if (n.type === TYPES.EXTERNAL) {
    let h = crumbHtml + secOpen("dep", "外部依赖", T().external);
    h += `<div class="card"><div class="t">${n.label}</div><div class="kv"><span class="k">已安装</span><span class="v">${n.attrs && n.attrs.installed ? "是" : "否（未在当前环境解析）"}</span></div></div>`;
    const importers = edgesOf(sel, "in", EDGES.IMPORTS);
    h += `<div class="kv"><span class="k">被导入</span><span class="v">${importers.length ? importers.map(nodeRow).join("") : '<span class="empty">—</span>'}</span></div></div>`;
    $c.innerHTML = h;
  } else if (n.type === TYPES.DOMAIN_ENTITY) {
    const producers = edgesOf(sel, "in", EDGES.PRODUCES);
    const consumers = edgesOf(sel, "in", EDGES.CONSUMES);
    const tIn = graph.edges.filter((e) => e.type === EDGES.TRANSFORMS && e.target === sel);
    const tOut = graph.edges.filter((e) => e.type === EDGES.TRANSFORMS && e.source === sel);
    let h = secOpen("ds", "领域实体", T().domain_entity);
    h += `<div class="card"><div class="t">${n.label} ${trustPill("llm")}</div><div class="kv"><span class="k">来源</span><span class="v">LLM 推断（advisory）</span></div></div>`;
    h += `<div class="kv"><span class="k">生产者</span><span class="v">${producers.length ? producers.map(nodeRow).join("") : '<span class="empty">-</span>'}</span></div>`;
    h += `<div class="kv"><span class="k">消费者</span><span class="v">${consumers.length ? consumers.map(nodeRow).join("") : '<span class="empty">-</span>'}</span></div>`;
    if (tIn.length || tOut.length) {
      h += `<div class="kv"><span class="k">转换</span><span class="v">`;
      tIn.forEach((e) => { h += `<div class="row" onclick="selectNode('${e.source}')"><span class="n" style="background:${T().flow}"></span>${labelOf(e.source)} -> ${n.label}<span class="arr">›</span></div>`; });
      tOut.forEach((e) => { h += `<div class="row" onclick="selectNode('${e.target}')"><span class="n" style="background:${T().flow}"></span>${n.label} -> ${labelOf(e.target)}<span class="arr">›</span></div>`; });
      h += `</span></div>`;
    }
    h += `</div>`;
    $c.innerHTML = h;
  } else {
    $c.innerHTML = crumbHtml + `<div class="empty">暂无详细信息。</div>`;
  }
}

// ---------- search ----------
const $si = document.getElementById("search-input");
const $sr = document.getElementById("search-results");
let searchTimer = null;
function doSearch(q) {
  q = q.trim(); if (!q) { $sr.style.display = "none"; return; }
  const res = search(graph, q);  // tested adapter seam; no per-keystroke refetch
  if (!res.length) { $sr.innerHTML = '<div class="sr-empty">无匹配结果</div>'; }
  else {
    $sr.innerHTML = res.map((r) => {
      const n = nodeById(r.id);
      return `<div class="sr-item" onclick="selectNode('${r.id}')"><span class="sr-tag" style="background:${nodeBaseColor(n || r, theme)}">${r.type}</span><span class="sr-label">${r.label}</span><span class="sr-sub">${(n && n.attrs && n.attrs.path) || (n && n.attrs && n.attrs.dotted) || r.type}</span></div>`;
    }).join("");
  }
  $sr.style.display = "block";
}
function closeSearch() { $sr.style.display = "none"; }
$si.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => doSearch($si.value), 180); });
$si.addEventListener("focus", () => { if ($si.value) doSearch($si.value); });
document.addEventListener("click", (e) => { if (!e.target.closest(".search")) closeSearch(); });

// ---------- theme / panel / reindex ----------
function syncLegendVars() {
  const r = document.documentElement.style;
  r.setProperty("--c-mod", T().module); r.setProperty("--c-file", T().file); r.setProperty("--c-cls", T().class);
  r.setProperty("--c-func", T().function); r.setProperty("--c-ext", T().external); r.setProperty("--c-risk", T().risk);
  r.setProperty("--c-de", T().domain_entity);
  r.setProperty("--c-flow", T().flow); r.setProperty("--c-notfired", T().notFired); r.setProperty("--c-unexpected", T().unexpected);
}
function applyTheme({ preserveCamera = false } = {}) {
  document.documentElement.setAttribute("data-theme", theme);
  document.getElementById("theme-toggle").textContent = theme === "dark" ? "🌙 暗色" : "☀️ 亮色";
  syncLegendVars(); refreshGraph({ resume: !preserveCamera }); renderPanel(state.selectedId);
}
document.getElementById("theme-toggle").addEventListener("click", () => { theme = theme === "dark" ? "light" : "dark"; applyTheme(); });
document.getElementById("panel-toggle").addEventListener("click", () => document.getElementById("panel").classList.toggle("collapsed"));
document.querySelectorAll(".dim-tab").forEach((t) => t.addEventListener("click", () => setDim(t.dataset.dim)));
document.getElementById("reindex-btn").addEventListener("click", async () => {
  setStatus("重新索引中…");
  try {
    const r = await fetch("/api/reindex"); const j = await r.json();
    if (j.ok) { await load(); rebuild(); refreshGraph(); document.getElementById("status").style.display = "none"; }
    else setStatus("重新索引失败", true);
  } catch (e) { setStatus("重新索引失败：" + e.message, true); }
});

function setStatus(msg, isErr) {
  const box = document.getElementById("status");
  document.getElementById("status-text").innerHTML = msg;
  box.style.display = "flex";
  box.querySelector(".spin").style.display = isErr ? "none" : "block";
}

syncLegendVars();
