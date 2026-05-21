"""HTTP surface tests — verify the error-mapping table from the brief.

Each row of the assignment's error-handling table is asserted here:
    missing year          -> 400
    invalid year format   -> 400
    GitLab 401            -> 401
    GitLab 403            -> 403
    GitLab project 404    -> 404
    /health               -> 200 {"status": "ok"}
"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from gitlab_report.api import create_app

API_BASE = "https://gitlab.example.com/api/v4"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_missing_year_returns_400(client: TestClient) -> None:
    response = client.get("/issues")
    assert response.status_code == 400


def test_non_integer_year_returns_400(client: TestClient) -> None:
    response = client.get("/issues", params={"year": "not-a-year"})
    assert response.status_code == 400


def test_out_of_range_year_returns_400(client: TestClient) -> None:
    response = client.get("/issues", params={"year": 1500})
    assert response.status_code == 400


@respx.mock
def test_gitlab_401_maps_to_401(client: TestClient) -> None:
    respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(401))
    response = client.get("/issues", params={"year": 2025})
    assert response.status_code == 401


@respx.mock
def test_gitlab_403_maps_to_403(client: TestClient) -> None:
    respx.get(f"{API_BASE}/issues").mock(return_value=httpx.Response(403))
    response = client.get("/issues", params={"year": 2025})
    assert response.status_code == 403


@respx.mock
def test_gitlab_project_404_maps_to_404(client: TestClient) -> None:
    respx.get(f"{API_BASE}/projects/no%2Fproject/issues").mock(return_value=httpx.Response(404))
    response = client.get(
        "/issues",
        params={"year": 2025, "project": "no/project"},
    )
    assert response.status_code == 404


@respx.mock
def test_happy_path_returns_trimmed_issues(client: TestClient) -> None:
    respx.get(f"{API_BASE}/issues").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "iid": 1,
                    "project_id": 9,
                    "title": "hello",
                    "state": "opened",
                    "created_at": "2025-01-02T00:00:00Z",
                    "author": {"username": "alice"},
                    "labels": [],
                    "web_url": "https://gitlab.example.com/g/p/-/issues/1",
                }
            ],
        )
    )
    response = client.get("/issues", params={"year": 2025})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["author"] == "alice"


@respx.mock
def test_merge_requests_endpoint(client: TestClient) -> None:
    respx.get(f"{API_BASE}/projects/42/merge_requests").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "iid": 1,
                    "project_id": 42,
                    "title": "feat",
                    "state": "merged",
                    "created_at": "2025-01-02T00:00:00Z",
                    "source_branch": "f",
                    "target_branch": "main",
                    "author": {"username": "bob"},
                    "labels": [],
                    "web_url": "https://gitlab.example.com/g/p/-/merge_requests/1",
                }
            ],
        )
    )
    response = client.get("/merge-requests", params={"year": 2025, "project": "42"})
    assert response.status_code == 200
    assert response.json()[0]["state"] == "merged"
