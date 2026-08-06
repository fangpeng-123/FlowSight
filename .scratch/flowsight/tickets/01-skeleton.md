# 01 - Skeleton extraction -> graph document (data spine)

**What to build:** Point FlowSight at a Python project and extract its structural skeleton into a schema-conformant graph document - the data foundation every later ticket hangs on. The CLI produces the graph JSON; a fixture project and a pipeline end-to-end test prove it correct.

**Blocked by:** None - can start immediately.

**Status:** ready-for-agent

- [ ] `flowsight index <path>` walks a Python project and emits a graph JSON conforming to the 05 schema
- [ ] Node types present: Module, File, Function, Class, External; edge types present: calls, imports, contains, references - each carrying line offsets
- [ ] All node/edge attributes tagged source = parser/trusted (signature, location, args, decorators, is_async)
- [ ] venv detection separates project code from site-packages so External resolves correctly
- [ ] A fixture Python project (mini voice-agent mirroring the prototype's fake data) is checked in
- [ ] Pipeline end-to-end test passes: fixture project in -> expected nodes/edges asserted (the primary test seam)
