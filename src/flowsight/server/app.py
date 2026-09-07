"""Local web server (decision 08) - serves the 3D graph view in the browser.

stdlib ``http.server`` only (no Flask/FastAPI dep): serves the static web assets
plus ``GET /api/graph`` (the indexed graph JSON) and ``GET /api/enrich`` (lazy
per-function LLM enrichment, ticket 03). Single user, local files, no auth.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from flowsight import schema as S
from flowsight.enrich.attacher import enrich_eager, enrich_function
from flowsight.enrich.cache import EnrichCache
from flowsight.enrich.llm import from_env
from flowsight.reading_subjects import ReadingSubjectCatalog, apply_catalog, load_catalog
from flowsight.refinement.dossier import ContextPolicy, build_dossier
from flowsight.refinement.jobs import JobStore
from flowsight.skeleton.extractor import extract

WEB_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "web"))


class GraphState:
    """Holds the indexed graph; rebuilt on re-index.

    Module purposes are enriched eagerly at index time (LLM if configured, else
    docstring fallback); per-function detail is enriched lazily via /api/enrich.
    """

    def __init__(self, project_path: str, trace_path: str | None = None):
        self.project_path = project_path
        self.trace_path = trace_path
        self.trace_id = os.path.basename(trace_path) if trace_path else ""
        self.cache = EnrichCache(os.path.join(project_path, ".flowsight", "enrich-cache.json"))
        self.llm = from_env()
        self.catalog = ReadingSubjectCatalog()
        self.refinements = JobStore(project_path)
        self.doc: S.GraphDocument = None  # set by _build
        self.divergence: dict = {}
        self._payload: dict = {}
        self._build()

    def _build(self) -> None:
        self.doc = extract(self.project_path)
        self.catalog = load_catalog(self.project_path, previous=self.catalog)
        apply_catalog(self.doc, self.catalog)
        enrich_eager(self.doc, self.llm, self.cache)
        self.cache.save()
        self.divergence = {}
        if self.trace_path:  # ticket 05: overlay runtime trace onto the skeleton
            from flowsight.overlay.correlator import apply_overlay, correlate
            from flowsight.overlay.trace import load_trace

            trace = load_trace(self.trace_path)
            result = correlate(self.doc, trace, project_root=self.project_path, trace_id=self.trace_id)
            apply_overlay(self.doc, result)
            self.divergence = result.divergence
        self._payload = S.doc_to_dict(self.doc)
        self.refinements.refresh_freshness(self._refinement_fingerprint)

    def _refinement_fingerprint(self, request: dict) -> str:
        dossier = request["dossier"]
        context = dossier.get("context") or {}
        extensions = dossier.get("critical_path_extensions", {
            node["id"]: node["context"]["justification"]
            for node in dossier["nodes"].get("boundary", [])
            if (node.get("context") or {}).get("hop", 1) > 1
        })
        return build_dossier(
            self.doc, self.catalog, request["subject_id"], self.project_path,
            context_policy=ContextPolicy(**context.get("policy", {})),
            critical_path_extensions=extensions,
        )["fingerprint"]

    def reindex(self) -> None:
        self._build()

    def refresh_payload(self) -> None:
        """Re-serialize the doc after an in-place mutation (lazy enrichment)."""
        self._payload = S.doc_to_dict(self.doc)

    def payload(self) -> dict:
        return self._payload

    def request_refinement(
        self,
        subject_id: str,
        *,
        event_stream=None,
        critical_path_extensions: dict[str, str] | None = None,
    ) -> dict:
        dossier = build_dossier(
            self.doc,
            self.catalog,
            subject_id,
            self.project_path,
            critical_path_extensions=critical_path_extensions,
        )
        status, _created = self.refinements.create_request(dossier, event_stream=event_stream)
        return status


def make_handler(state: GraphState, *, event_stream=None):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=WEB_DIR, **kwargs)

        def log_message(self, *args):  # silence default logging
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path.rstrip("/") == "/api/refinements/current":
                subject_id = parse_qs(parsed.query).get("subject_id", [""])[0]
                if not subject_id:
                    self._json({"ok": False, "error": "subject_id is required"}, 400)
                    return
                try:
                    if not any(subject.id == subject_id for subject in state.catalog.subjects):
                        raise KeyError(f"unknown reading subject: {subject_id}")
                    self._json(state.refinements.latest_status(subject_id))
                except KeyError as exc:
                    self._json({"ok": False, "error": str(exc)}, 404)
                return
            if self.path == "/api/graph":
                self._json(state.payload())
                return
            if self.path == "/api/divergence":
                # ticket 05: actual-on-expected divergence report (not_fired/unexpected/role)
                self._json({"ok": True, "divergence": state.divergence,
                            "trace_id": state.trace_id})
                return
            if self.path.startswith("/api/reindex"):
                state.reindex()
                self._json({"ok": True, "nodes": len(state.doc.nodes), "edges": len(state.doc.edges)})
                return
            if self.path.startswith("/api/enrich-all"):
                from flowsight.server.enrich_api import enrich_all
                enrich_all(self, state)
                return
            if self.path.startswith("/api/enrich"):
                # ticket 03 wires the LLM enricher here
                from flowsight.server.enrich_api import handle_enrich
                handle_enrich(self, state)
                return
            clean_path = self.path.split("?", 1)[0]
            refinement_parts = clean_path.strip("/").split("/")
            if len(refinement_parts) == 4 and refinement_parts[:2] == ["api", "refinements"] and refinement_parts[3] == "artifact":
                job_id = refinement_parts[2]
                try:
                    artifact = state.refinements.artifact_path(job_id)
                    self._serve_path(artifact, "text/html; charset=utf-8")
                except KeyError as exc:
                    self._json({"ok": False, "error": str(exc)}, 404)
                return
            if len(refinement_parts) == 3 and refinement_parts[:2] == ["api", "refinements"]:
                job_id = refinement_parts[2]
                try:
                    self._json(state.refinements.get_status(job_id))
                except KeyError as exc:
                    self._json({"ok": False, "error": str(exc)}, 404)
                return
            # static: strip query string
            path = self.path.split("?", 1)[0].lstrip("/")
            if path == "" or path == "index.html":
                self._serve_file("index.html", "text/html; charset=utf-8")
                return
            return super().do_GET()

        def do_POST(self):
            if self.path.split("?", 1)[0].rstrip("/") != "/api/refinements":
                self._json({"ok": False, "error": "Not found"}, 404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 65536:
                    raise ValueError("invalid request body length")
                body = json.loads(self.rfile.read(length))
                subject_id = body.get("subject_id") if isinstance(body, dict) else None
                if not isinstance(subject_id, str) or not subject_id:
                    raise ValueError("subject_id is required")
                extensions = body.get("critical_path_extensions", {})
                if not isinstance(extensions, dict) or not all(
                    isinstance(key, str) and isinstance(value, str)
                    for key, value in extensions.items()
                ):
                    raise ValueError("critical_path_extensions must be a string map")
                status = state.request_refinement(
                    subject_id,
                    event_stream=event_stream,
                    critical_path_extensions=extensions,
                )
                self._json(status, 202)
            except (ValueError, json.JSONDecodeError) as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            except KeyError as exc:
                self._json({"ok": False, "error": str(exc)}, 404)

        def do_DELETE(self):
            if not self.path.startswith("/api/refinements/"):
                self._json({"ok": False, "error": "Not found"}, 404)
                return
            job_id = self.path.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
            try:
                self._json(state.refinements.cancel(job_id))
            except KeyError as exc:
                self._json({"ok": False, "error": str(exc)}, 404)
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 409)

        def _serve_file(self, name: str, ctype: str):
            full = os.path.join(WEB_DIR, name)
            self._serve_path(full, ctype)

        def _serve_path(self, path, ctype: str):
            full = os.fspath(path)
            if not os.path.isfile(full):
                self.send_error(404, "Not found")
                return
            with open(full, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(project_path: str, port: int = 8000, open_browser: bool = True,
          trace_path: str | None = None) -> None:
    state = GraphState(project_path, trace_path=trace_path)
    handler = make_handler(state)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"FlowSight serving {project_path}", file=sys.stderr)
    print(f"  {len(state.doc.nodes)} nodes, {len(state.doc.edges)} edges", file=sys.stderr)
    if trace_path:
        n_df = sum(1 for e in state.doc.edges if e.type == S.DATA_FLOW)
        print(f"  runtime overlay: {trace_path} ({n_df} data_flow edges)", file=sys.stderr)
    print(f"  open {url}", file=sys.stderr)
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye", file=sys.stderr)
    finally:
        httpd.server_close()
