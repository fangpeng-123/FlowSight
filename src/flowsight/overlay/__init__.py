"""Runtime data-flow overlay (ticket 05 / decision 06).

- ``correlator`` - the pure, unit-tested seam: viztracer Chrome Trace JSON +
  parser skeleton -> runtime ``data_flow`` edges + per-node runtime stats + an
  actual-on-expected divergence report. Never imports viztracer.
- ``trace`` - the viztracer wrapper (``flowsight trace <cmd>`` / ``--from``);
  imports viztracer lazily so this package imports without the runtime dep.
"""

from flowsight.overlay.correlator import (  # noqa: F401
    EdgeRuntime,
    NodeRuntime,
    OverlayResult,
    apply_overlay,
    correlate,
)
from flowsight.overlay.trace import (  # noqa: F401
    ingest_trace,
    load_trace,
    overlay_graph_dict,
    run_trace,
)
