"""FlowSight CLI: ``flowsight index <path>`` / ``flowsight serve <path>``.

- index: walk a Python project and emit a graph JSON document (ticket 01)
- serve: build the graph and serve the 3D view locally (ticket 02)
- trace: capture a runtime trace with viztracer (ticket 05, not in this slice)
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

    sub.add_parser("trace", help="capture a runtime trace (ticket 05, not in this slice)")

    args = parser.parse_args(argv)

    if args.command == "index":
        return _cmd_index(args)
    if args.command == "serve":
        return _cmd_serve(args)
    if args.command == "trace":
        print("trace: not implemented in this slice (ticket 05).", file=sys.stderr)
        return 2
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

    serve(args.path, port=args.port, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
