"""Shared pytest fixtures.

Sets minimum env vars so ``get_settings()`` does not fail. Tests that
need different values monkeypatch within the test itself.
"""

from __future__ import annotations

import os

import pytest

# Set env vars before any gitlab_report module is imported.
os.environ.setdefault("GITLAB_URL", "https://gitlab.example.com")
os.environ.setdefault("GITLAB_TOKEN", "test-token-not-real")


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from gitlab_report.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
