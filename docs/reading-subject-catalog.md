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
      "rationale": "Owns graph delivery and browser-facing APIs.",
      "locked": false
    }
  ]
}
```

Paths use forward slashes and are relative to the project path passed to
`flowsight serve`. The stable `id` is the normalized `root`, so changing an
Agent-generated label does not change subject identity. Every root must map to
an existing Python package module; every member must be an existing parser
source file; and a file may have only one primary subject owner.

A human-corrected subject can set `locked` to `true`. On reindex, FlowSight
keeps the last loaded locked definition even if a refreshed Agent catalog
changes or omits it. Reading-subject metadata is advisory: module and file nodes
remain parser-origin nodes.
