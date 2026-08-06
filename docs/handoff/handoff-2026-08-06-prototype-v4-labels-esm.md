# FlowSight · Handoff v4 — 可视化原型：标签渲染根因与 ESM 单实例修复

> 承接 [handoff-2026-08-06-prototype-v3.md](handoff-2026-08-06-prototype-v3.md)（项目背景、wayfinder 概览、用户画像、ticket 全表）。本文只记录 v3 之后的进展与本次新发现的关键根因，不重复已有内容。

## 一句话现状

可视化原型 `prototype/index.html` 已迭代到 **v5b**：3D 图谱（3d-force-graph）能渲染、侧栏详情正常、顶栏已改为实心栏（搜索/维度/主题可见）。**正在等待用户硬刷新确认节点文字标签是否终于显示**——这是本会话的核心未决项。

## 本次会话解决了什么（v3 → v5b 的关键故事）

用户连续反馈"图谱有了但没标签""顶栏看不见""总觉得代码实现了但界面没展示"。通过截图（vision skill）+ 直接扒库源码，定位到**三个真实根因**（非显示微调）：

### 根因 1：节点标签从来没法渲染（three.js 实例问题）
- **3d-force-graph v1.80** 把 `three` 作为**依赖打包进 UMD dist**（`dependencies: {three: ">=0.179 <1"}`），UMD 包装器只暴露 `ForceGraph3D`，**不暴露 `window.THREE`**（已从 dist 源码验证：`(e=...).ForceGraph3D=t()`，three 全在闭包内）。
- **three-spritetext v1.10** 把 `three` 作为 **peerDependency**（不打包），UMD 加载时执行 `class SpriteText extends THREE.Sprite` —— 因全局 `THREE` 未定义而**抛错**，`SpriteText` 永远 undefined，`labelObj` 返回 null → 无标签。
- **npmmirror 白名单挡死 three-spritetext**：`registry.npmmirror.com/three-spritetext/.../files/` 返回 `FORBIDDEN`，`cdn.npmmirror.com/npm/...` 返回 `NoSuchKey`。国内 CDN 根本拉不到它。
- 早期 v5/v5.1 的 `labelObj` 在 `SpriteText` 未定义时直接 `return null`，无兜底 → 标签全无。

### 根因 2：跨实例警告（"Multiple instances of Three.js"）
- 尝试用本地 `lib/three.min.js`（r160 UMD，仍提供 `build/three.min.js` 的最新版；r170 起移除 UMD）提供全局 `THREE`，再加载 3d-force-graph（内置 r183）→ **两个 three 实例**。
- 控制台出现 `THREE.WARNING: Multiple instances of Three.js being imported`。3d-force-graph 内置 r183，全局是 r160，跨 23 版本 + 跨实例 → 标签精灵（属 r160 实例）无法被 r183 渲染器可靠渲染。
- 用户把这条警告贴给我，确认了跨实例问题。

### 根因 3：顶栏被画布压住
- v5 顶栏用绝对定位飘在 3D 画布上，与画布层叠（z-index）打架；暗色半透明（`rgba(16,22,30,.9)`）在纯黑画布上几乎隐形 → 搜索框/维度标签/主题按钮"看不见"。

## v5b 的修复（已写入 `prototype/index.html`）

### 顶栏（根因 3）
- 布局改为 **flex 列**：`#app > #topbar（实心、正常文档流、flex:0 0 52px）+ #main > (#cy 画布 + #panel 侧栏)`。
- 顶栏与画布在**不同布局行**，物理上不可能被画布盖住。顶栏元素坐在实心 `var(--tb-bg)` 背景上，明暗主题都清晰。

### 标签（根因 1+2）—— ESM 单实例方案
- **主路径**：`<script type="importmap">` 把 `three` / `three/` 映射到 `https://esm.sh/three@0.183.0`；`<script type="module">` 顶级 await 依次 `import('three')`、`import('https://esm.sh/3d-force-graph@1.80.0?external=three')`、`import('https://esm.sh/three-spritetext@1.10.0?external=three')`。
- **已逐一验证**：esm.sh 可达且 `Access-Control-Allow-Origin: *`（file:// origin=null 可 import）；`?external=three` 让 3d-force-graph 用 bare `import from "three"`；三个库最终都汇聚到同一个 `/three@0.183.0/es2022/three.mjs`，浏览器去重为**单实例** → 无跨实例警告，标签必渲染。
- `labelObj` 优先用 `SpriteText`（esm.sh 加载，清晰），失败则用手写 canvas 纹理精灵（`makeCanvasSprite`，用 `window.THREE`）兜底；另加 `Graph.nodeLabel(n=>...)` hover 提示作第二道保底。
- **兜底路径**：esm.sh 不可达时（catch / 15s 超时），`window.__esmOK` 为假 → 回退 `bootLoader()` 加载本地 UMD（`lib/three.min.js` r160 + `lib/3d-force-graph.min.js`），跨实例（标签可能不显示，但图能跑 + hover 提示）。
- 时序：经典 `<script>`（定义全部函数、末尾挂 `engines-ready` 监听）先执行 → 延迟的 module 脚本拉完模块后 `dispatchEvent('engines-ready')` → 触发 `initGraph()` 或 `bootLoader()`。

### 顺手改进
- 默认展开模块（`expanded = new Set(modules.map(m=>m.id))`）→ 露出文件层，图谱不再只有 9 个光秃秃的点。
- `initGraph` 仍遵守 **graphData 先于 d3Force** 的顺序（v5.1 修复的崩溃点）。

## 关键文件

- `F:\FlowSight\.scratch\flowsight\prototype\index.html` —— 单文件原型（v5b），活跃工件。数据模型/侧栏/搜索/主题/维度逻辑见文件内（模块>文件>类/函数；结构体>字段；函数>参数+契约+风险；折叠式 3D 层级）。
- `F:\FlowSight\.scratch\flowsight\prototype\lib\three.min.js` —— three r160 UMD（仅兜底用；首行有 r150+ 弃用警告，不影响设 `window.THREE`）。
- `F:\FlowSight\.scratch\flowsight\prototype\lib\3d-force-graph.min.js` —— 3d-force-graph v1.80 UMD（内置 three r183）。
- `.scratch/flowsight/map.md` —— wayfinder 跟踪。Decisions-so-far 列 02/03/04/05；**01 未正式 resolve**（landscape.md 研究已做但无 Answer 行）；**06/08 pending**；**07 claimed**（worklog 仍写 Cytoscape，已过时——见下）。
- `.scratch/flowsight/issues/07-visualization-ia.md` —— 可视化 ticket，状态 claimed。

## ⚠️ 需要注意的偏离

- **ticket 03 决策是 Cytoscape.js，但原型已迁到 3d-force-graph（3D）**。这是用户明确要 3D 效果后的转向。07 resolve 时应同步修正 03/05 的措辞，或在 07 的 Answer 里说明"3D 优先于 Cytoscape 的理由 + 2D 降级路径"。
- **07 的 worklog 还写着 "single-file Cytoscape.js mock"**，已过时，resolve 时更新。

## 立即下一步（按优先级）

1. **等用户硬刷新（Ctrl+Shift+R）确认**：节点标签是否显示？控制台是否还有 `Multiple instances` 警告？顶栏是否可见？
   - 若标签显示 + 控制台干净 → 07 可 resolve（更新 worklog、append Answer、Status: resolved、map.md 加 Decisions 行；并修正 03 的 Cytoscape→3D 偏离说明）。
   - 若标签仍不显示 → esm.sh 在用户网络下可能不通（走了 UMD 兜底）。诊断：让用户报 F12 控制台是否有 `[FlowSight] ESM(esm.sh) 加载失败，回退到本地 UMD 引擎`。若是，需改用国内能直连的单实例方案（见下"备选"）。
   - 若 ESM 成功但标签仍不显示（少数）→ 检查 `SpriteText` 是否加载、`nodeThreeObject` 是否生效。
2. **关闭 ticket 01**：研究已在 `research/landscape.md` 完成，只缺正式 Answer 行 + map.md Decisions 行。
3. **ticket 06（运行时叠加技术）与 08（medium：web vs 扩展）**：pending，已 unblocked，可开工。

## 若 esm.sh 在国内不通的备选方案（已调研，按推荐度）

- **手动 importmap 映射整棵依赖树到 npmmirror**：3d-force-graph.mjs 有 6 个 bare import（three / three-forcegraph / three-render-objects / accessor-fn / kapsule / three/examples/jsm/controls/DragControls.js），且 three-forcegraph/three-render-objects 还有传递依赖（three-blobs-utils 等）。需逐个映射到 `registry.npmmirror.com/<pkg>/<ver>/files/<path>`，且要逐个验证白名单（three-spritetext 已被 FORBIDDEN，其他未必都放行）。**繁琐且脆**，仅作最后手段。
- **让用户起本地 http server**（`python -m http.server`）+ 用 importmap：同上但避免 file:// 的 CORS 不确定性。
- **放弃持久 3D 标签，仅用 `nodeLabel` hover 提示 + 侧栏**：最稳，但用户体验下降（用户明确想要持久标签）。

## CLAUDE.md 约束（必须遵守）

- **git push 走 V2Ray 代理** `http://127.0.0.1:10808`（已全局配置 `http.proxy`/`https.proxy`）。push 前确认 V2Ray 在运行；报 `Recv failure`/`Failed to connect to github.com port 443` = V2Ray 没开，提醒用户启动并检查 `git config --global http.proxy`。`gh` CLI 偶尔能通**不代表** `git push` 能通。
- **无原生识图能力**：遇到图片（路径/URL/"Saved attachments:"）用 vision skill 脚本，不要用 Read：
  `node "C:/Users/Administrator/.claude/skills/vision/vision.js" "<图片路径>" "用中文描述这张图片"`
- **CodeGraph**：仓库根若有 `.codegraph/` 目录，优先用 CodeGraph（MCP `codegraph_explore`/`codegraph_node` 或 shell `codegraph explore/node`）再 grep/find。FlowSight 目前**没有** `.codegraph/`，跳过。

## 用户画像（关键，影响所有交互）

- **阅读障碍**：视觉优先，图谱优于逐行阅读。回复要**短、结构化、视觉化**；少长段落。
- 国内网络：jsdelivr/unpkg 常被墙，优先 npmmirror；esm.sh 待验证可达性。
- 迭代式工作风格：会反复给截图/控制台反馈，快速试错。

## Suggested skills（下个会话应调用）

- `/wayfinder` —— 跟踪 ticket 状态（07 resolve、01 关闭、06/08 开工、map.md Decisions 维护）。
- `/prototype` —— 继续可视化迭代（标签确认后的下一步：真实数据接入、运行时叠加层等）。
- `/grilling` + `/domain-modeling` —— 处理 06（运行时叠加技术）、08（medium 决策）等需要权衡的决策。
- `/research` —— 06/08 涉及的外部技术事实（viztracer/sys.monitoring、webview vs extension）。
- `vision` skill —— 用户给截图时识图（路径见上）。
