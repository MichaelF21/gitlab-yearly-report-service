"""Domain functions exposed by both the HTTP API and the MCP server.

These are the deliverables named in the assignment:
    - get_issues_by_year(year, project_id_or_path=None)
    - get_merge_requests_by_year(year, project_id_or_path=None)

The functions own input validation and response shaping. Anything that
needs the GitLab REST API goes through GitLabClient; anything that needs
configuration reads it from get_settings().
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .config import Settings, get_settings
from .errors import InvalidYearError
from .gitlab_client import GitLabClient, JsonDict

_MIN_YEAR = 2000
# Upper bound is "current calendar year + 1" so reports can be generated
# for the current year without false-positive validation errors.


def _validate_year(year: Any) -> int:
    if isinstance(year, bool) or not isinstance(year, int):
        raise InvalidYearError(f"year must be an integer, got {type(year).__name__}")
    # After the isinstance check mypy still treats `year` as Any (it widens on
    # the not-isinstance branch); rebind to a typed local so the return type
    # is honoured without an explicit cast.
    year_int: int = year
    if year_int < 1000 or year_int > 9999:
        raise InvalidYearError(f"year must be a 4-digit integer, got {year_int}")
    current_year = datetime.now(tz=UTC).year
    if year_int < _MIN_YEAR or year_int > current_year + 1:
        raise InvalidYearError(
            f"year must be between {_MIN_YEAR} and {current_year + 1}, got {year_int}"
        )
    return year_int


def _issue_view(raw: JsonDict) -> JsonDict:
    """Trim GitLab's issue payload to a stable subset.

    We deliberately do not pass GitLab's response through unchanged so the
    HTTP contract is not coupled to upstream schema drift.
    """
    return {
        "id": raw.get("id"),
        "iid": raw.get("iid"),
        "project_id": raw.get("project_id"),
        "title": raw.get("title"),
        "state": raw.get("state"),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "closed_at": raw.get("closed_at"),
        "author": (raw.get("author") or {}).get("username"),
        "labels": raw.get("labels") or [],
        "web_url": raw.get("web_url"),
    }


def _merge_request_view(raw: JsonDict) -> JsonDict:
    return {
        "id": raw.get("id"),
        "iid": raw.get("iid"),
        "project_id": raw.get("project_id"),
        "title": raw.get("title"),
        "state": raw.get("state"),
        "draft": raw.get("draft", raw.get("work_in_progress", False)),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "merged_at": raw.get("merged_at"),
        "closed_at": raw.get("closed_at"),
        "source_branch": raw.get("source_branch"),
        "target_branch": raw.get("target_branch"),
        "author": (raw.get("author") or {}).get("username"),
        "labels": raw.get("labels") or [],
        "web_url": raw.get("web_url"),
    }


def _build_client(settings: Settings) -> GitLabClient:
    return GitLabClient(
        api_base=settings.gitlab_api_base,
        token=settings.gitlab_token,
        timeout_seconds=settings.request_timeout_seconds,
        per_page=settings.per_page,
    )


async def get_issues_by_year(
    year: int,
    project_id_or_path: str | None = None,
) -> list[JsonDict]:
    """Return GitLab issues created during ``year``.

    Args:
        year: 4-digit calendar year (e.g. 2025).
        project_id_or_path: GitLab project numeric ID or URL-encoded path.
            When ``None``, results span the entire GitLab instance scoped
            to the token's permissions.

    Raises:
        InvalidYearError: ``year`` is missing, wrong type, or out of range.
        GitLabError (subclasses): upstream GitLab failures map to HTTP
            status codes; see errors.py.
    """
    validated_year = _validate_year(year)
    settings = get_settings()
    async with _build_client(settings) as client:
        raw_items = await client.list_issues(
            year=validated_year,
            project_id_or_path=project_id_or_path,
        )
    return [_issue_view(item) for item in raw_items]


async def get_merge_requests_by_year(
    year: int,
    project_id_or_path: str | None = None,
) -> list[JsonDict]:
    """Return GitLab merge requests created during ``year``.

    Args:
        year: 4-digit calendar year (e.g. 2025).
        project_id_or_path: GitLab project numeric ID or URL-encoded path.
            When ``None``, results span the entire GitLab instance scoped
            to the token's permissions.

    Raises:
        InvalidYearError: ``year`` is missing, wrong type, or out of range.
        GitLabError (subclasses): upstream GitLab failures map to HTTP
            status codes; see errors.py.
    """
    validated_year = _validate_year(year)
    settings = get_settings()
    async with _build_client(settings) as client:
        raw_items = await client.list_merge_requests(
            year=validated_year,
            project_id_or_path=project_id_or_path,
        )
    return [_merge_request_view(item) for item in raw_items]
