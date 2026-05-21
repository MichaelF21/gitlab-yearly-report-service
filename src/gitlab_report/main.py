"""Uvicorn entrypoint.

Running ``python -m gitlab_report.main`` or ``gitlab-report-api`` starts
the HTTP service on 0.0.0.0:8080.
"""

from __future__ import annotations

import logging
import os
import sys

import uvicorn

from .config import ConfigError, get_settings


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def run() -> None:
    try:
        settings = get_settings()
    except ConfigError as exc:
        # Print, not log, so the operator sees it even when stdlib logging
        # is not configured yet.
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(2)

    _configure_logging(settings.log_level)

    # Binding to 0.0.0.0 is intentional — the service is designed to run
    # inside a container where the network is scoped by Docker's port
    # mapping. Override with the HOST env var if you need a tighter bind.
    host = os.environ.get("HOST", "0.0.0.0")  # nosec B104
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        "gitlab_report.api:app",
        host=host,
        port=port,
        log_level=settings.log_level.lower(),
        access_log=True,
    )


if __name__ == "__main__":  # pragma: no cover
    run()
