"""MCP server (bonus deliverable).

Exposes the same domain functions as the HTTP API. Transport is stdio,
which is what Claude Desktop and Claude Code use to launch MCP servers.

Run with:
    gitlab-report-mcp
or:
    python -m gitlab_report.mcp_server

Requires the same GITLAB_URL and GITLAB_TOKEN env vars as the HTTP service.
"""

import logging
import sys
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from .config import ConfigError, get_settings
from .reports import (
    get_issues_by_year as _get_issues_by_year,
)
from .reports import (
    get_merge_requests_by_year as _get_merge_requests_by_year,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("gitlab-yearly-report")


# Note: we use Optional[str] (not `str | None`) for tool parameter annotations
# because FastMCP's tool registration inspects annotations with issubclass(),
# which fails on PEP 604 union types.
@mcp.tool()
async def get_issues_by_year(
    year: int,
    project_id_or_path: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return GitLab issues created during the given year.

    Args:
        year: 4-digit calendar year (e.g. 2025).
        project_id_or_path: GitLab project numeric ID or URL-encoded path.
            Omit to query the entire instance.
    """
    return await _get_issues_by_year(year, project_id_or_path)


@mcp.tool()
async def get_merge_requests_by_year(
    year: int,
    project_id_or_path: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return GitLab merge requests created during the given year.

    Args:
        year: 4-digit calendar year (e.g. 2025).
        project_id_or_path: GitLab project numeric ID or URL-encoded path.
            Omit to query the entire instance.
    """
    return await _get_merge_requests_by_year(year, project_id_or_path)


def run() -> None:
    # Validate config up front so the MCP client gets a clean error if
    # the server is misconfigured.
    try:
        get_settings()
    except ConfigError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(2)
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    run()
