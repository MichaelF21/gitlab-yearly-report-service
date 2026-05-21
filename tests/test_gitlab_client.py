"""Unit tests for the GitLab REST client."""

from __future__ import annotations

import httpx
import pytest
import respx

from gitlab_report.errors import (
    GitLabAuthError,
    GitLabForbidden,
    GitLabNotFound,
    GitLabUpstreamError,
)
from gitlab_report.gitlab_client import (
    GitLabClient,
    _encode_project,
    _parse_next_link,
)

API_BASE = "https://gitlab.example.com/api/v4"


def test_encode_project_numeric_id_passthrough() -> None:
    assert _encode_project("12345") == "12345"


def test_encode_project_path_url_encoded() -> None:
    assert _encode_project("mygroup/my-project") == "mygroup%2Fmy-project"


def test_encode_project_nested_path() -> None:
    assert _encode_project("a/b/c") == "a%2Fb%2Fc"


def test_parse_next_link_returns_url() -> None:
    header = (
        '<https://gitlab.example.com/api/v4/issues?page=2>; rel="next", '
        '<https://gitlab.example.com/api/v4/issues?page=1>; rel="first"'
    )
    assert _parse_next_link(header) == "https://gitlab.example.com/api/v4/issues?page=2"


def test_parse_next_link_no_next() -> None:
    assert _parse_next_link('<https://x/api/v4/issues?page=1>; rel="prev"') is None
    assert _parse_next_link(None) is None
    assert _parse_next_link("") is None


@pytest.mark.asyncio
@respx.mock
async def test_list_issues_instance_scope_uses_correct_path() -> None:
    route = respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(200, json=[{"id": 1}]))
    async with GitLabClient(API_BASE, "tok", max_retries=1) as client:
        result = await client.list_issues(year=2025, project_id_or_path=None)
    assert result == [{"id": 1}]
    assert route.called
    params = dict(route.calls.last.request.url.params)
    assert params["created_after"] == "2025-01-01T00:00:00Z"
    assert params["created_before"] == "2025-12-31T23:59:59Z"
    assert params["scope"] == "all"
    assert params["pagination"] == "keyset"
    assert params["per_page"] == "100"


@pytest.mark.asyncio
@respx.mock
async def test_list_issues_project_scope_url_encoded() -> None:
    route = respx.get(f"{API_BASE}/projects/mygroup%2Fmy-project/issues").mock(
        return_value=httpx.Response(200, json=[])
    )
    async with GitLabClient(API_BASE, "tok", max_retries=1) as client:
        await client.list_issues(year=2025, project_id_or_path="mygroup/my-project")
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_list_merge_requests_numeric_id() -> None:
    route = respx.get(f"{API_BASE}/projects/42/merge_requests").mock(
        return_value=httpx.Response(200, json=[{"iid": 7}])
    )
    async with GitLabClient(API_BASE, "tok", max_retries=1) as client:
        result = await client.list_merge_requests(year=2024, project_id_or_path="42")
    assert result == [{"iid": 7}]
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_pagination_follows_link_header() -> None:
    page1 = httpx.Response(
        200,
        json=[{"id": 1}, {"id": 2}],
        headers={"link": f'<{API_BASE}/issues?cursor=abc>; rel="next"'},
    )
    page2 = httpx.Response(200, json=[{"id": 3}])

    # side_effect chains responses so each call to /issues gets the next page.
    # (A second respx.get() without strict URL matching would shadow the first.)
    respx.get(f"{API_BASE}/issues").mock(side_effect=[page1, page2])

    async with GitLabClient(API_BASE, "tok", max_retries=1) as client:
        result = await client.list_issues(year=2025, project_id_or_path=None)
    assert [item["id"] for item in result] == [1, 2, 3]


@pytest.mark.asyncio
@respx.mock
async def test_401_translates_to_auth_error() -> None:
    respx.get(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(401, json={"message": "401 Unauthorized"})
    )
    async with GitLabClient(API_BASE, "tok", max_retries=1) as client:
        with pytest.raises(GitLabAuthError):
            await client.list_issues(year=2025, project_id_or_path=None)


@pytest.mark.asyncio
@respx.mock
async def test_403_translates_to_forbidden() -> None:
    respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(403))
    async with GitLabClient(API_BASE, "tok", max_retries=1) as client:
        with pytest.raises(GitLabForbidden):
            await client.list_issues(year=2025, project_id_or_path=None)


@pytest.mark.asyncio
@respx.mock
async def test_404_translates_to_not_found() -> None:
    respx.get(f"{API_BASE}/projects/missing/issues").mock(return_value=httpx.Response(404))
    async with GitLabClient(API_BASE, "tok", max_retries=1) as client:
        with pytest.raises(GitLabNotFound):
            await client.list_issues(year=2025, project_id_or_path="missing")


@pytest.mark.asyncio
@respx.mock
async def test_500_translates_to_upstream_error_after_retries() -> None:
    route = respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(500))
    async with GitLabClient(API_BASE, "tok", max_retries=2) as client:
        with pytest.raises(GitLabUpstreamError):
            await client.list_issues(year=2025, project_id_or_path=None)
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_token_sent_as_private_token_header() -> None:
    route = respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(200, json=[]))
    async with GitLabClient(API_BASE, "secret-token-xyz", max_retries=1) as client:
        await client.list_issues(year=2025, project_id_or_path=None)
    assert route.calls.last.request.headers["PRIVATE-TOKEN"] == "secret-token-xyz"
