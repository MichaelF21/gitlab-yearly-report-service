"""Async GitLab REST API v4 client.

Scope of this module:
    - Encapsulates authentication, pagination, retries, and error translation.
    - Exposes only GET operations (the service is read-only by design).
    - Never logs the token; logs the redacted upstream URL and status only.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .errors import (
    GitLabAuthError,
    GitLabError,
    GitLabForbidden,
    GitLabNotFound,
    GitLabUpstreamError,
)

logger = logging.getLogger(__name__)

# A single decoded JSON object from GitLab (a row in the response array).
JsonDict = dict[str, Any]

# rel="next" link header parser — keyset pagination uses this rather than X-Next-Page.
_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


def _encode_project(project_id_or_path: str) -> str:
    """All-digit values are passed through as IDs; paths are URL-encoded."""
    if project_id_or_path.isdigit():
        return project_id_or_path
    return quote(project_id_or_path, safe="")


def _parse_next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    match = _LINK_NEXT_RE.search(link_header)
    return match.group(1) if match else None


class GitLabClient:
    """Thin async wrapper around the GitLab REST API."""

    def __init__(
        self,
        api_base: str,
        token: str,
        *,
        timeout_seconds: float = 30.0,
        per_page: int = 100,
        max_retries: int = 3,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._per_page = per_page
        self._max_retries = max_retries
        # Timeout is set explicitly below via httpx.Timeout(); bandit's B113
        # check matches on the function name only and cannot see through the
        # Timeout() construction, hence the inline suppression.
        self._client = httpx.AsyncClient(  # nosec B113
            headers={
                "PRIVATE-TOKEN": token,
                "Accept": "application/json",
                "User-Agent": "gitlab-yearly-report/0.1",
            },
            timeout=httpx.Timeout(connect=5.0, read=timeout_seconds, write=10.0, pool=5.0),
            follow_redirects=True,
        )

    async def __aenter__(self) -> GitLabClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_issues(
        self,
        *,
        year: int,
        project_id_or_path: str | None,
    ) -> list[JsonDict]:
        path = self._issues_path(project_id_or_path)
        params = self._year_params(year)
        params["scope"] = "all"  # required for instance-wide queries; harmless for project scope
        return [item async for item in self._paginate(path, params)]

    async def list_merge_requests(
        self,
        *,
        year: int,
        project_id_or_path: str | None,
    ) -> list[JsonDict]:
        path = self._merge_requests_path(project_id_or_path)
        params = self._year_params(year)
        params["scope"] = "all"
        return [item async for item in self._paginate(path, params)]

    def _issues_path(self, project_id_or_path: str | None) -> str:
        if project_id_or_path is None:
            return "/issues"
        return f"/projects/{_encode_project(project_id_or_path)}/issues"

    def _merge_requests_path(self, project_id_or_path: str | None) -> str:
        if project_id_or_path is None:
            return "/merge_requests"
        return f"/projects/{_encode_project(project_id_or_path)}/merge_requests"

    @staticmethod
    def _year_params(year: int) -> dict[str, str]:
        # Inclusive lower bound, inclusive upper bound matching GitLab semantics.
        # Using next-year midnight as the upper bound would include items
        # created exactly at 00:00:00Z on Jan 1 of the following year.
        return {
            "created_after": f"{year:04d}-01-01T00:00:00Z",
            "created_before": f"{year:04d}-12-31T23:59:59Z",
        }

    async def _paginate(
        self,
        path: str,
        params: dict[str, str],
    ) -> AsyncIterator[JsonDict]:
        """Yield items across keyset-paginated pages.

        We start with keyset pagination on /issues and /merge_requests
        (both support it). The next page URL is provided in the Link
        header; we follow it verbatim until exhausted.
        """
        url: str | None = f"{self._api_base}{path}"
        query: dict[str, str] | None = {
            **params,
            "pagination": "keyset",
            "per_page": str(self._per_page),
            "order_by": "created_at",
            "sort": "asc",
        }

        while url is not None:
            response = await self._request_with_retries("GET", url, params=query)
            payload = response.json()
            if not isinstance(payload, list):
                raise GitLabUpstreamError(
                    f"Unexpected payload shape from GitLab at {self._redact(url)}: "
                    f"expected list, got {type(payload).__name__}",
                    upstream_status=response.status_code,
                )
            for item in payload:
                yield item
            # Subsequent pages: follow Link header verbatim, drop our params
            url = _parse_next_link(response.headers.get("link"))
            query = None

    async def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Send a request, retrying transient failures (429, 5xx, network errors)."""
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._max_retries),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
                retry=retry_if_exception_type((GitLabUpstreamError, httpx.TransportError)),
                reraise=True,
            ):
                with attempt:
                    response = await self._client.request(method, url, params=params)
                    self._raise_for_status(response, url)
                    return response
        except RetryError as exc:  # pragma: no cover — reraise=True keeps this unreachable
            raise GitLabUpstreamError("Retries exhausted") from exc
        raise GitLabUpstreamError("Retry loop exited without a response")  # pragma: no cover

    def _raise_for_status(self, response: httpx.Response, url: str) -> None:
        status = response.status_code
        if status < 400:
            return
        redacted = self._redact(url)
        body_snippet = response.text[:200].replace("\n", " ")
        message = (
            f"GitLab returned {status} for {redacted}: {body_snippet}"
            if body_snippet
            else f"GitLab returned {status} for {redacted}"
        )
        logger.warning("gitlab_request_failed status=%s url=%s", status, redacted)
        if status == 401:
            raise GitLabAuthError(message, upstream_status=status)
        if status == 403:
            raise GitLabForbidden(message, upstream_status=status)
        if status == 404:
            raise GitLabNotFound(message, upstream_status=status)
        if status == 429 or status >= 500:
            raise GitLabUpstreamError(message, upstream_status=status)
        raise GitLabError(message, upstream_status=status)

    @staticmethod
    def _redact(url: str) -> str:
        """Return URL stripped of query string in case secrets leaked in.

        We never send the token via query string, but defensive logging
        avoids accidental leakage if that ever changes.
        """
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}{parts.path}"
