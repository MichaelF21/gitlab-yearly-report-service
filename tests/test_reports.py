"""Tests for the reports domain layer."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from gitlab_report.errors import InvalidYearError
from gitlab_report.reports import (
    get_issues_by_year,
    get_merge_requests_by_year,
)

API_BASE = "https://gitlab.example.com/api/v4"


@pytest.mark.asyncio
async def test_year_must_be_int() -> None:
    with pytest.raises(InvalidYearError):
        await get_issues_by_year("2025")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_year_rejects_bool() -> None:
    # bool is a subclass of int — easy gotcha.
    with pytest.raises(InvalidYearError):
        await get_issues_by_year(True)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_year_must_be_in_range() -> None:
    with pytest.raises(InvalidYearError):
        await get_issues_by_year(1900)


@pytest.mark.asyncio
async def test_year_future_rejected() -> None:
    current = datetime.now(tz=UTC).year
    with pytest.raises(InvalidYearError):
        await get_issues_by_year(current + 5)


@pytest.mark.asyncio
@respx.mock
async def test_issues_response_is_trimmed() -> None:
    raw_issue = {
        "id": 101,
        "iid": 7,
        "project_id": 5,
        "title": "Something broke",
        "state": "opened",
        "created_at": "2025-04-01T12:00:00Z",
        "updated_at": "2025-04-02T09:00:00Z",
        "closed_at": None,
        "author": {"username": "alice", "id": 1},
        "labels": ["bug"],
        "web_url": "https://gitlab.example.com/g/p/-/issues/7",
        "description": "internal details we do not want to leak",  # should be dropped
        "_links": {"self": "..."},  # should be dropped
    }
    respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(200, json=[raw_issue]))
    result = await get_issues_by_year(2025)
    assert len(result) == 1
    item = result[0]
    assert item == {
        "id": 101,
        "iid": 7,
        "project_id": 5,
        "title": "Something broke",
        "state": "opened",
        "created_at": "2025-04-01T12:00:00Z",
        "updated_at": "2025-04-02T09:00:00Z",
        "closed_at": None,
        "author": "alice",
        "labels": ["bug"],
        "web_url": "https://gitlab.example.com/g/p/-/issues/7",
    }


@pytest.mark.asyncio
@respx.mock
async def test_merge_requests_response_is_trimmed() -> None:
    raw_mr = {
        "id": 9001,
        "iid": 12,
        "project_id": 5,
        "title": "Add foo",
        "state": "merged",
        "draft": False,
        "created_at": "2025-06-01T00:00:00Z",
        "merged_at": "2025-06-02T00:00:00Z",
        "source_branch": "feature/foo",
        "target_branch": "main",
        "author": {"username": "bob"},
        "labels": [],
        "web_url": "https://gitlab.example.com/g/p/-/merge_requests/12",
        "diff_refs": {"base_sha": "..."},
    }
    respx.get(f"{API_BASE}/merge_requests").mock(return_value=httpx.Response(200, json=[raw_mr]))
    result = await get_merge_requests_by_year(2025)
    assert len(result) == 1
    assert result[0]["author"] == "bob"
    assert result[0]["source_branch"] == "feature/foo"
    assert "diff_refs" not in result[0]


@pytest.mark.asyncio
@respx.mock
async def test_project_scope_hits_project_endpoint() -> None:
    route = respx.get(f"{API_BASE}/projects/mygroup%2Fmy-project/issues").mock(
        return_value=httpx.Response(200, json=[])
    )
    await get_issues_by_year(2025, "mygroup/my-project")
    assert route.called
