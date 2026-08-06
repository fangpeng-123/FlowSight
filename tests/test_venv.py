"""venv / import classification (decision 02/04)."""

import sys

from flowsight.skeleton import venv as V


def test_stdlib_detected():
    info = V.detect(".")
    assert info.is_stdlib("os")
    assert info.is_stdlib("json")
    assert info.is_stdlib("asyncio")
    assert not info.is_stdlib("requests")
    assert not info.is_stdlib("some_third_party")


def test_classify_project_vs_stdlib_vs_external():
    info = V.detect(".")
    project_modules = {"voice_agent", "voice_agent.models", "voice_agent.audio_in"}
    assert V.classify("voice_agent", project_modules, info) == "project"
    assert V.classify("voice_agent.models", project_modules, info) == "project"
    assert V.classify("os", project_modules, info) == "stdlib"
    assert V.classify("os.path", project_modules, info) == "stdlib"
    assert V.classify("requests", project_modules, info) == "external"
    assert V.classify("some_unknown_pkg", project_modules, info) == "external"


def test_installed_third_party_is_site_packages():
    """jedi is a real installed third-party package in the test env."""
    info = V.detect(".")
    path = info.find_installed_path("jedi")
    assert path is not None, "jedi must be installed in the test env"
    assert info.is_site_packages(path), f"{path} should be under site-packages"


def test_uninstalled_third_party_has_no_path():
    info = V.detect(".")
    assert info.find_installed_path("requests") is None or info.is_site_packages(info.find_installed_path("requests"))
