"""Exception hierarchy for upstream GitLab failures.

Each concrete subclass maps 1:1 to an HTTP status code in the API layer
(see api.py exception handlers). Keeping the mapping in one place avoids
status-code ladders inside the client and route code.
"""

from __future__ import annotations


class GitLabError(Exception):
    """Base class for all GitLab upstream failures."""

    status_code: int = 502

    def __init__(self, message: str, *, upstream_status: int | None = None) -> None:
        super().__init__(message)
        self.upstream_status = upstream_status


class GitLabAuthError(GitLabError):
    """GitLab returned 401 — token is invalid or expired."""

    status_code = 401


class GitLabForbidden(GitLabError):
    """GitLab returned 403 — token lacks permission for the resource."""

    status_code = 403


class GitLabNotFound(GitLabError):
    """GitLab returned 404 — project (or other resource) does not exist."""

    status_code = 404


class GitLabUpstreamError(GitLabError):
    """GitLab returned 5xx or a transport-level failure after retries."""

    status_code = 502


class InvalidYearError(ValueError):
    """Year argument failed validation (not 4 digits, out of range, etc)."""
