"""FlowSight CLI: ``flowsight index <path>`` / ``flowsight serve <path>``.

- index: walk a Python project and emit a graph JSON document (ticket 01)
- serve: build the graph and serve the 3D view locally (ticket 02)
- trace: capture a runtime trace with viztracer and overlay it (ticket 05)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Sequence

from flowsight import schema as S
from flowsight.skeleton.extractor import extract


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flowsight", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="extract a project's skeleton to a graph JSON document")
    p_index.add_argument("path", help="path to the Python project (its source root)")
    p_index.add_argument("-o", "--output", default="-", help="output file (default: stdout)")

    p_serve = sub.add_parser("serve", help="serve the 3D graph view locally (ticket 02)")
    p_serve.add_argument("path", help="path to the Python project")
    p_serve.add_argument("-p", "--port", type=int, default=8000)
    p_serve.add_argument("--no-browser", action="store_true")
    p_serve.add_argument("--trace", default=None,
                         help="overlay a viztracer trace (Chrome JSON) onto the served graph (ticket 05)")

    p_trace = sub.add_parser("trace", help="capture a runtime trace and overlay it (ticket 05)")
    p_trace.add_argument("cmd", nargs=argparse.REMAINDER,
                         help="entrypoint to trace, e.g. script.py args...  (use `--` before `-m module`)")
    p_trace.add_argument("--from", dest="from_file", default=None,
                         help="ingest an existing trace instead of running a command")
    p_trace.add_argument("--out", default=None, help="trace output path (default: .flowsight/trace.json)")
    p_trace.add_argument("--project", default=None,
                         help="correlate the trace against this project's skeleton; writes an overlay graph")
    p_trace.add_argument("--overlay-out", default=None,
                         help="overlay-augmented graph output path (default: graph-overlay.json)")
    p_trace.add_argument("--log-args", action="store_true",
                         help="capture argument and return values (off by default for privacy)")
    p_trace.add_argument("--max-stack-depth", type=int, default=None)

    args = parser.parse_args(argv)

    if args.command == "index":
        return _cmd_index(args)
    if args.command == "serve":
        return _cmd_serve(args)
    if args.command == "trace":
        return _cmd_trace(args)
    return 1


def _cmd_index(args) -> int:
    doc = extract(args.path)
    # eager module purposes (LLM if configured, else docstring fallback) - ticket 03
    from flowsight.enrich.attacher import enrich_eager
    from flowsight.enrich.cache import EnrichCache
    from flowsight.enrich.llm import from_env

    cache = EnrichCache(os.path.join(args.path, ".flowsight", "enrich-cache.json"))
    enrich_eager(doc, from_env(), cache)
    cache.save()

    payload = S.doc_to_dict(doc)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output == "-":
        sys.stdout.write(text + "\n")
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"indexed {len(doc.nodes)} nodes, {len(doc.edges)} edges -> {args.output}", file=sys.stderr)
    return 0


def _cmd_serve(args) -> int:
    # implemented in ticket 02 (server.app); imported lazily to keep 01 standalone.
    from flowsight.server.app import serve

    serve(args.path, port=args.port, open_browser=not args.no_browser, trace_path=args.trace)
    return 0


def _cmd_trace(args) -> int:
    """ticket 05: capture a viztracer trace and optionally overlay it on a skeleton."""
    from flowsight.overlay import trace as OT

    out = args.out or os.path.join(".flowsight", "trace.json")

    if args.from_file:
        OT.ingest_trace(args.from_file, out)
        print(f"trace: ingested {args.from_file} -> {out}", file=sys.stderr)
    else:
        cmd = list(args.cmd or [])
        if cmd and cmd[0] == "--":  # argparse REMAINDER keeps a leading `--`
            cmd = cmd[1:]
        if not cmd:
            print("trace: no command given. Pass a script, `-m module` (after `--`), or use --from <file>.",
                  file=sys.stderr)
            return 2
        try:
            OT.run_trace(cmd, out, log_args=args.log_args, max_stack_depth=args.max_stack_depth)
        except (RuntimeError, ValueError) as e:
            print(f"trace: {e}", file=sys.stderr)
            return 3
        print(f"trace: ran {' '.join(cmd)} -> {out}", file=sys.stderr)

    if args.project:
        trace = OT.load_trace(out)
        overlay_out = args.overlay_out or "graph-overlay.json"
        payload = OT.overlay_graph_dict(args.project, trace, trace_id=os.path.basename(out))
        with open(overlay_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        n_df = sum(1 for e in payload["edges"] if e["type"] == S.DATA_FLOW)
        print(f"trace: correlated against {args.project} -> {overlay_out} ({n_df} runtime data_flow edges)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
