# 02 - Local serve + 3D static-skeleton render (visual spine)

**What to build:** Serve the graph document locally and render it in the browser as a floating, click-to-expand 3D graph - the first demoable slice. Adapts the verified prototype to consume real served graph JSON instead of inline fake data, with a renderer-agnostic data adapter as the tested seam.

**Blocked by:** 01 (needs the graph JSON).

**Status:** ready-for-agent

- [ ] `flowsight serve` runs a local web server and opens the browser
- [ ] 3d-force-graph renders the skeleton: modules/files/functions/classes expand and collapse on click/double-click
- [ ] calls/imports/contains edges render per the spec's edge-encoding decision (width/arrow/particles by type)
- [ ] Node legend and light/dark theme toggle work
- [ ] Consumes served graph JSON, not inline fake data
- [ ] Renderer-agnostic data adapter (graph JSON -> render model) is a pure module with unit tests
- [ ] Respects v1.80 constraints: pin 3d-force-graph v1.80, double-click detected in onNodeClick, overlays outside the graph container, triple-set theme background
