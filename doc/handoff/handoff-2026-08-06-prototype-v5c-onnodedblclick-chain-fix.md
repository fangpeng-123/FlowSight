# Handoff · FlowSight 原型 v5c（onNodeDblClick 链断裂根因修复）

- **日期**: 2026-08-06
- **状态**: 三处修复已全部应用 + 语法校验通过，**等待用户硬刷新确认**（未验证）
- **活跃产物**: `F:\FlowSight\.scratch\flowsight\prototype\index.html`（单文件 HTML+JS+CSS，~535 行）
- **上一份 handoff**: `F:\FlowSight\doc\handoff\handoff-2026-08-06-prototype-v4-labels-esm.md`（标签/顶栏/ESM 迁移背景，本文不重复）

---

## TL;DR

本轮修三个问题：①主题切换不改图谱底色；②左下角节点图例消失；③数据流不明显。前两轮没修好，第三轮才挖到**真正的病根**：3d-force-graph **v1.80 没有 `onNodeDblClick` 方法**，构造链每次在那里抛错，`Graph` 一直为 `null`，导致 `refreshGraph()` 直接 return（底色永不更新）、旧版"挂回图例"代码也没机会跑（图例不回）。删掉该方法、改在 `onNodeClick` 里自测双击后，链能跑完，三个问题应一并解决。

---

## 病根故事（最重要的教训）

`initGraph` 的构造链长这样：
```js
Graph = ForceGraph3D()(cy).graphData(...).backgroundColor(...)...linkDirectionalParticleColor(...)
  .onNodeClick(n=>selectNode(n.id))
  .onNodeDblClick(n=>toggleExpand(n.id))   // ← v1.80 不存在！
  .onBackgroundClick(()=>clearSelection());
```

- `onNodeDblClick` 在 `lib/3d-force-graph.min.js`（v1.80）里 **0 次出现**。v1.80 的节点事件只有：`onNodeClick` / `onNodeHover` / `onNodeDrag` / `onNodeDragEnd` / `onNodeRightClick`。
- 链在 `.onNodeDblClick(...)` 抛 `TypeError: ...onNodeDblClick is not a function`，**赋值未完成**，`Graph` 保持 `null`。
- 后果链：
  - `refreshGraph()` 开头 `if(!Graph)return` → 主题切换时底色永远不变（Issue ①）。
  - 旧版"渲染后挂回图例"在抛错点之后 → 不执行 → 图例不回（Issue ②）。
  - "数据流更醒目"是链里 `onNodeDblClick` **之前**设的（linkWidth/粒子/颜色），所以一直生效（Issue ③ 已好）。
- **教训**：3d-force-graph 用的是 **v1.80（非最新）**，所有方法名必须对照本版本 dist 核实，不能信最新 README。

### 验证过确实存在且公开的方法（v1.80 dist）
链中用到的：`graphData / backgroundColor / nodeRelSize / nodeVal / nodeColor / nodeLabel / nodeThreeObject(Extend) / linkColor / linkWidth / linkDirectionalArrowLength / linkDirectionalArrowRelPos / linkDirectionalParticles / linkDirectionalParticleWidth / linkDirectionalParticleSpeed / linkDirectionalParticleColor / onNodeClick / onBackgroundClick`。
链后用到：`d3Force` / `d3VelocityDecay`（prop）/ `onEngineStop` / `zoomToFit`。
公开访问器：`Graph.scene()` / `Graph.renderer()` / `Graph.camera()`（与 `pauseAnimation`/`resumeAnimation` 同一 methods 块，确认暴露）。

---

## 本轮改动（全部在 index.html）

### 1. 删 onNodeDblClick，onNodeClick 内自测双击
```js
let _dcId=null,_dcT=0;  // 顶层
// 链中：
.onNodeClick(n=>{const now=Date.now();
  if(_dcId===n.id&&now-_dcT<350){_dcId=null;toggleExpand(n.id);return;}  // 双击→展开
  _dcId=n.id;_dcT=now;selectNode(n.id);})                                // 单击→选中
.onBackgroundClick(()=>clearSelection());
```
（注：`Date.now()` 在浏览器里可用；CLAUDE.md 里"Date.now 不可用"仅指 Workflow 脚本沙箱，不影响 index.html。）

### 2. 图例浮层挪出 #cy（结构性修复，根治 Issue ②）
3d-force-graph 构造时 `init: e.innerHTML=""` 会清空容器 `#cy`。把 `#legend` / `.hint` / `#status` 从 `#cy` 内移到 `#main` 里（与 `#panel` 同级），并给 `#main` 加 `position:relative`。清的是 `#cy`，永远碰不到它们 → 图例从结构上不可能再丢。`.hint` 加 `pointer-events:none`。

### 3. 主题底色三重兜底 + 重启渲染循环（Issue ①）
```js
function applyGraphBg(){
  if(!Graph)return; const c=T().graphBg;
  Graph.backgroundColor(c);
  try{const r=Graph.renderer&&Graph.renderer();if(r){r.setClearColor(new THREE.Color(c),1);if(r.domElement)r.domElement.style.backgroundColor=c;}}catch(e){}
  try{const sc=Graph.scene();if(sc)sc.background=new THREE.Color(c);}catch(e){}
}
function refreshGraph(){if(!Graph)return;applyGraphBg();Graph.nodeColor(...).nodeThreeObject(...).linkColor(...).linkWidth(...).linkDirectionalParticleColor(()=>T().flow);try{Graph.resumeAnimation&&Graph.resumeAnimation();}catch(e){}Graph.refresh();}
```
- 直接 `renderer().setClearColor()` 写死清除色（不依赖 prop 刷新时机）；
- `scene.background` 每帧由渲染器绘制；
- `resumeAnimation()` 引擎停后渲染循环可能停了，重启它确保有帧重画新底色（已在跑则空操作）。
- **关键前提**：这些只有 `Graph` 非 null 才执行 → 所以必须先修好 Issue ① 的真因（链断裂）。

### 4. 数据流更醒目（Issue ③，前两轮已生效）
- `THEMES.dark.flow`: `#9a7426` → `#ffc107`（亮金）；
- `linkWidth`：transforms=3 / produces·consumes=1.8 / calls=1.2 / contains=0.7；
- `arrowLen`：transforms=6.5 / produces·consumes=4.5 / calls=3.2 / contains=0；
- `particles`：transforms=5 / produces·consumes=3 / else=0；
- `linkDirectionalParticleWidth` 0.5→1，新增 `linkDirectionalParticleSpeed(0.01)`。
- AudioChunk→Transcript→LLMMessage→TTSAudio 管道主线最醒目。

---

## 当前状态 / 待办

**待用户确认**：硬刷新（Ctrl+Shift+R）后 ①主题切底色变 ②左下角图例在 ③双击展开/收起恢复。用户是视觉优先（阅读障碍），请其截图后用 **vision skill** 核对。

**确认通过后**（wayfinder 工单流转，见 `F:\FlowSight\.scratch\flowsight\map.md`）：
- **结单 07（可视化）**：更新 worklog、append Answer、Status: resolved、map.md 加 Decisions 行；注明 03 的 Cytoscape→3D 分歧。工单：`F:\FlowSight\.scratch\flowsight\issues\07-visualization-ia.md`。
- **结单 01**：landscape.md 研究已做，缺正式 Answer + map.md 行。
- **做 06**（runtime 轨迹叠加静态骨架）。
- **做 08**（形态：web vs 浏览器扩展，中等优先）。

---

## 关键技术事实（非显然，下个 agent 必读）

1. **3d-force-graph v1.80**（非最新）。方法名以 `lib/3d-force-graph.min.js` dist 为准。无 `onNodeDblClick`。
2. **构造会清空容器**：`ForceGraph3D()(el)` 执行 `el.innerHTML=""`。任何浮层 div 必须放在容器**外**（这里是 `#main`，不是 `#cy`）。
3. **ESM 单实例**：`<script type="importmap">` 把 `three`/`three/` 映射到 `esm.sh/three@0.183.0`；3d-force-graph / three-spritetext 用 `?external=three` 走 importmap 共享同一个 three 实例（消除"Multiple instances of Three.js"）。esm.sh 不可达时回退 `bootLoader`（本地 UMD：`lib/three.min.js` r160 + `lib/3d-force-graph.min.js`）。
4. **r160 vs r183 版本差**：UMD 回退路径用 three r160（最新 UMD），3d-force-graph 内部打包 r183；标签精灵用 SpriteText 或手写 canvas 纹理（API 跨版本稳定）。ESM 路径同版本 r183，无此问题。
5. **Graph 为 null 会让 refreshGraph 静默 no-op**——任何"主题/选中/维度切换没反应"先查 `Graph` 是否赋值成功（看 F12 有无链中抛错）。
6. **数据模型**：module>file>class>function；struct(dataclass)>fields；flow 边 = produces/consumes/transforms；默认 'dep' 维度所有边都 lit。struct 永远可见，transforms 链（管道主线）默认就显示。

---

## 文件清单

- `F:\FlowSight\.scratch\flowsight\prototype\index.html` — 活跃产物（本轮所有改动在此）
- `F:\FlowSight\.scratch\flowsight\prototype\lib\three.min.js` — three r160 UMD（仅回退用）
- `F:\FlowSight\.scratch\flowsight\prototype\lib\3d-force-graph.min.js` — v1.80 UMD（查方法名用这个）
- `F:\FlowSight\.scratch\flowsight\map.md` — wayfinder 追踪
- `F:\FlowSight\.scratch\flowsight\issues\07-visualization-ia.md` — 可视化工单
- `F:\FlowSight\doc\handoff\handoff-2026-08-06-prototype-v4-labels-esm.md` — 上一份 handoff

---

## Suggested skills

- **`/wayfinder`** — 确认修复后流转工单（结 07/01，做 06/08），更新 map.md。
- **vision skill** — `node "C:/Users/Administrator/.claude/skills/vision/vision.js" "<截图路径>" "用中文描述..."`。当前模型无原生识图；用户视觉优先，验证截图必用此脚本。
- **`/handoff`** — 若需再次交接。

---

## 用户画像 / 约束

- 阅读障碍，视觉优先：图 > 逐行文字；验证请用截图 + vision skill。
- 中文交流，回复用中文。
- CLAUDE.md 约束：git push 走 V2Ray 代理 `http://127.0.0.1:10808`（push 前确认 V2Ray 在跑）；FlowSight 无 `.codegraph/`，不用 CodeGraph。
