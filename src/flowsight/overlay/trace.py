"""viztracer wrapper (ticket 05 / decision 06).

- ``run_trace(cmd, output)`` wraps an entrypoint with viztracer to capture a
  Chrome Trace JSON. viztracer is run as a subprocess (``python -m viztracer``)
  so the target program runs in its own process, not FlowSight's.
- ``load_trace`` / ``ingest_trace`` read (and re-dump) an existing trace for the
  ``flowsight trace --from <file>`` path.

viztracer is imported lazily (and only to probe availability); this module - and
the correlator - import fine without the runtime dependency installed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from typing import Sequence

from flowsight import schema as S
from flowsight.overlay.correlator import apply_overlay, correlate
from flowsight.skeleton.extractor import extract


def _viztracer_available() -> bool:
    return importlib.util.find_spec("viztracer") is not None


def _ensure_parent_dir(path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)


def run_trace(
    cmd: Sequence[str],
    output: str,
    *,
    log_args: bool = False,
    max_stack_depth: int | None = None,
) -> str:
    """Run ``cmd`` under viztracer, writing a Chrome Trace JSON to ``output``.

    ``cmd`` is the target entrypoint, the same form you'd hand to python:
    ``["script.py", "--flag"]`` or ``["-m", "pkg.main", "arg"]``. Returns the
    output path. Raises RuntimeError if viztracer is not installed.
    """
    if not cmd:
        raise ValueError("trace: no command given (pass a script or `-m module`)")
    if not _viztracer_available():
        raise RuntimeError(
            "viztracer is not installed in this interpreter. Install it with "
            "`pip install viztracer` (pyproject [runtime]) and re-run."
        )
    _ensure_parent_dir(output)
    args: list[str] = [sys.executable, "-m", "viztracer", "--quiet", "-o", output]
    if log_args:
        args += ["--log_func_args", "--log_func_retval"]
    if max_stack_depth is not None:
        args += ["--max_stack_depth", str(max_stack_depth)]
    if cmd[0] == "-m":
        if len(cmd) < 2:
            raise ValueError("trace: `-m` requires a module name")
        args += ["--module", cmd[1], *cmd[2:]]  # viztracer passes trailing args to the module
    else:
        args += list(cmd)  # script + its args
    completed = subprocess.run(args)
    if completed.returncode != 0:
        raise RuntimeError(
            f"trace: viztracer exited with code {completed.returncode} for command: {' '.join(cmd)}"
        )
    if not os.path.isfile(output):
        raise RuntimeError(f"trace: viztracer did not produce a trace at {output}")
    return output


def load_trace(path: str) -> dict:
    """Load and validate a Chrome Trace JSON file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "traceEvents" not in data:
        raise ValueError(f"trace: {path} is not a Chrome Trace JSON (missing 'traceEvents')")
    return data


def ingest_trace(src_path: str, dest_path: str) -> str:
    """Validate an existing trace (via :func:`load_trace`) and stage a local copy
    at ``dest_path`` for the server / CLI to read. No normalization is applied -
    the bytes are re-dumped unchanged so the served trace matches the source."""
    data = load_trace(src_path)
    _ensure_parent_dir(dest_path)
    with open(dest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return dest_path


def overlay_graph_dict(
    project_path: str,
    trace: dict,
    *,
    trace_id: str = "trace",
) -> dict:
    """Extract a project's skeleton, correlate ``trace`` onto it, and return the
    overlay-augmented graph as a JSON-ready dict (skeleton + runtime data_flow
    edges + per-node runtime). Used by ``flowsight trace --project``."""
    doc = extract(project_path)
    result = correlate(doc, trace, project_root=project_path, trace_id=trace_id)
    apply_overlay(doc, result)
    return S.doc_to_dict(doc)
