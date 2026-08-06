"""Shared pytest fixtures."""

import os
import sys

import pytest

FIXTURE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "fixtures"))


@pytest.fixture(scope="session")
def fixture_root() -> str:
    """Dir whose contents form the project-under-index (contains the voice_agent package)."""
    return FIXTURE_ROOT


@pytest.fixture(scope="session")
def voice_agent_pkg() -> str:
    return os.path.join(FIXTURE_ROOT, "voice_agent")
