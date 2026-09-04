# Reading Subject Catalog

FlowSight loads an optional Agent-authored catalog from
`.flowsight/reading-subjects.json` before serving the interactive graph. A
missing catalog preserves the ordinary project overview; an invalid catalog
stops indexing instead of silently exposing incorrect ownership.

```json
{
  "version": 1,
  "subjects": [
    {
      "id": "flowsight/server",
      "label": "Local HTTP server",
      "root": "flowsight/server",
      "member_files": [
        "flowsight/server/__init__.py",
        "flowsight/server/app.py"
      ],
      "exclusions": [],
      "rationale": "Owns graph delivery and browser-facing APIs.",
      "locked": false
    }
  ]
}
```

Paths use forward slashes and are relative to the project path passed to
`flowsight serve`. The stable `id` is the normalized `root`, so changing an
Agent-generated label does not change subject identity. Every member must be an
existing parser source file, a file may have only one primary subject owner,
and roots under parser-excluded directories such as `.git`, `node_modules`, or
build caches are rejected. Optional `exclusions` must stay inside the subject
root and cannot exclude a listed member.

When the root is also a parser-created Python package, FlowSight attaches the
reading subject to that module node. Otherwise it attaches the action metadata
to the subject's explicit member-file nodes. This keeps an Agent-defined
functional module distinct from parser package structure.

A human-corrected subject can set `locked` to `true`. FlowSight persists locked
definitions in `.flowsight/reading-subject-locks.json`; reindex and process
restart keep that definition even if a refreshed Agent catalog changes or omits
it. Reading-subject metadata is advisory: module and file nodes remain
parser-origin nodes.
