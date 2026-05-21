"""FastAPI surface for the reporting service.

Endpoint table (matches the assignment brief):
    GET /health                               -> {"status": "ok"}
    GET /issues?year=YYYY&project=...         -> trimmed issue records
    GET /merge-requests?year=YYYY&project=... -> trimmed MR records

Error mapping (matches the assignment brief):
    missing/invalid year         -> 400
    GitLab authentication failed -> 401
    GitLab permission denied     -> 403
    GitLab project not found     -> 404
    missing token / startup fail -> startup failure (process exits non-zero)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import __version__
from .config import ConfigError, get_settings
from .errors import (
    GitLabAuthError,
    GitLabError,
    GitLabForbidden,
    GitLabNotFound,
    GitLabUpstreamError,
    InvalidYearError,
)
from .reports import get_issues_by_year, get_merge_requests_by_year

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Fail fast: if config is invalid we want the container to exit, not
    # serve 500s on every request.
    settings = get_settings()
    logger.info(
        "starting gitlab-yearly-report version=%s gitlab_url=%s",
        __version__,
        settings.gitlab_url,
    )
    yield


def _problem(status: int, title: str, detail: str | None = None) -> JSONResponse:
    body: dict[str, object] = {"error": title, "status": status}
    if detail:
        body["detail"] = detail
    return JSONResponse(status_code=status, content=body)


def create_app() -> FastAPI:
    app = FastAPI(
        title="GitLab Yearly Report Service",
        description="Read-only reporting over GitLab REST API v4.",
        version=__version__,
        lifespan=lifespan,
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/issues", tags=["reports"])
    async def issues(
        year: int = Query(..., description="4-digit calendar year, e.g. 2025"),
        project: str | None = Query(
            None,
            description="GitLab project numeric ID or URL-encoded path",
        ),
    ) -> list[dict[str, Any]]:
        return await get_issues_by_year(year, project)

    @app.get("/merge-requests", tags=["reports"])
    async def merge_requests(
        year: int = Query(..., description="4-digit calendar year, e.g. 2025"),
        project: str | None = Query(
            None,
            description="GitLab project numeric ID or URL-encoded path",
        ),
    ) -> list[dict[str, Any]]:
        return await get_merge_requests_by_year(year, project)

    # ----- exception handlers -----

    @app.exception_handler(RequestValidationError)
    async def _on_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI raises this for missing ?year=, non-int year, etc.
        # Brief requires 400 (FastAPI's default is 422).
        return _problem(400, "Bad Request", detail=str(exc.errors()))

    @app.exception_handler(InvalidYearError)
    async def _on_invalid_year(_: Request, exc: InvalidYearError) -> JSONResponse:
        return _problem(400, "Bad Request", detail=str(exc))

    @app.exception_handler(GitLabAuthError)
    async def _on_auth(_: Request, exc: GitLabAuthError) -> JSONResponse:
        return _problem(401, "Unauthorized", detail=str(exc))

    @app.exception_handler(GitLabForbidden)
    async def _on_forbidden(_: Request, exc: GitLabForbidden) -> JSONResponse:
        return _problem(403, "Forbidden", detail=str(exc))

    @app.exception_handler(GitLabNotFound)
    async def _on_not_found(_: Request, exc: GitLabNotFound) -> JSONResponse:
        return _problem(404, "Not Found", detail=str(exc))

    @app.exception_handler(GitLabUpstreamError)
    async def _on_upstream(_: Request, exc: GitLabUpstreamError) -> JSONResponse:
        return _problem(502, "Bad Gateway", detail=str(exc))

    @app.exception_handler(GitLabError)
    async def _on_gitlab_other(_: Request, exc: GitLabError) -> JSONResponse:
        return _problem(exc.status_code, "GitLab Error", detail=str(exc))

    @app.exception_handler(ConfigError)
    async def _on_config(_: Request, exc: ConfigError) -> JSONResponse:
        return _problem(500, "Internal Server Error", detail=str(exc))

    return app


app = create_app()
