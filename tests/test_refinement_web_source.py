"""Static regression checks for exact exploration-state restoration."""

from pathlib import Path


def test_close_deep_read_refreshes_theme_without_resuming_layout():
    source = (
        Path(__file__).parents[1] / "src" / "flowsight" / "web" / "app.js"
    ).read_text(encoding="utf-8")

    close_body = source.split("function closeDeepRead()", 1)[1].split(
        'document.getElementById("deep-read-back")', 1
    )[0]
    assert "applyTheme({ preserveCamera: true })" in close_body
    assert "refreshGraph({ resume: !preserveCamera })" in source


def test_browser_restores_current_jobs_can_cancel_and_polls_until_terminal():
    source = (
        Path(__file__).parents[1] / "src" / "flowsight" / "web" / "app.js"
    ).read_text(encoding="utf-8")

    assert "/api/refinements/current?subject_id=" in source
    assert 'method: "DELETE"' in source
    assert "Open previous deep read" in source
    assert "Retry deep read" in source
    poll_body = source.split("async function pollRefinement", 1)[1].split(
        "// ---- runtime overlay card", 1
    )[0]
    assert "attempt >=" not in poll_body
    assert "Math.min(1000 + attempt * 100, 5000)" in poll_body
    assert "presentation && presentation.busy" in poll_body.split("catch (error)", 1)[1]
