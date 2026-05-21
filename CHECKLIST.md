# Acceptance checklist

Mirrors the requirements in the Mobileye DevOps-IT home assignment brief.
Each row is ticked only after being verified.

## Functional requirements

- [x] Read-only — `GitLabClient` exposes only `list_*` (GET) methods; the FastAPI app has no POST/PUT/PATCH/DELETE routes
- [x] `GET /health` returns `{"status":"ok"}` with HTTP 200 (smoke-tested)
- [ ] `GET /issues?year=YYYY` (instance scope) returns issues created in that year — *unit-tested with respx; live integration needs a real PAT*
- [ ] `GET /issues?year=YYYY&project=<id>` (project scope by numeric ID) — *unit-tested; live verification pending*
- [ ] `GET /issues?year=YYYY&project=group%2Fproject` (project scope by encoded path) — *unit-tested; live verification pending*
- [ ] `GET /merge-requests?year=YYYY` (instance scope) — *unit-tested; live verification pending*
- [ ] `GET /merge-requests?year=YYYY&project=<id>` — *unit-tested; live verification pending*
- [ ] `GET /merge-requests?year=YYYY&project=group%2Fproject` — *unit-tested; live verification pending*

## Error mapping (from the brief)

- [x] Missing `year` parameter → 400 (live-smoke-tested)
- [x] Non-integer `year` → 400 (live-smoke-tested)
- [x] Out-of-range `year` → 400 (live-smoke-tested)
- [x] GitLab returns 401 → service returns 401 (live-smoke-tested with bad token against gitlab.com)
- [ ] GitLab returns 403 → service returns 403 — *unit-tested only; needs a token without permission on a real project*
- [ ] GitLab returns 404 (project not found) → service returns 404 — *unit-tested; needs live verification against a bogus path*
- [x] Missing `GITLAB_TOKEN` → clear startup failure, non-zero exit code (`docker run` returns exit code 2)

## Containerization

- [x] `docker build -t gitlab-yearly-report-service .` succeeds
- [x] `docker run --rm -p 8080:8080 -e GITLAB_URL=... -e GITLAB_TOKEN=... gitlab-yearly-report-service` works as in the brief
- [x] Service is reachable on `http://localhost:8080`
- [x] Image built FROM `python:3.12-slim` (multi-stage)
- [x] Container runs as non-root user (uid 1001)
- [x] `HEALTHCHECK` shows `(healthy)` within 30s
- [x] Image size is reasonable for the stack (301MB; under 350MB target)

## Code quality

- [x] `ruff check .` clean
- [x] `ruff format --check .` clean
- [x] `mypy` clean under strict settings (0 issues across 8 source files)
- [x] `bandit -r src` clean (B113 and B104 suppressed inline with justification)
- [x] `pytest` — 30/30 tests pass
- [x] Test coverage 81% (≥ 80% gate)
- [x] `hadolint Dockerfile` clean (DL3008 suppressed inline for unpinned apt packages, justified)
- [x] `trivy image` clean of HIGH/CRITICAL fixable CVEs
- [ ] `pip-audit` clean — one disputed advisory (PYSEC-2025-183, pyjwt, no upstream fix); trivy is the authoritative gate

## Bonus — MCP server

- [x] `gitlab-report-mcp` exposes `get_issues_by_year`
- [x] `gitlab-report-mcp` exposes `get_merge_requests_by_year`
- [x] MCP initialize handshake succeeds (verified end-to-end over stdio)
- [x] MCP tools/list returns exactly the two required tools
- [x] README documents how to wire the MCP server into Claude Desktop and Docker

## Submission

- [x] README has quick-start, env-var table, endpoint reference, curl examples
- [x] README documents the MCP server setup
- [x] README documents the local GitLab playground (per brief)
- [x] Repository is public: https://github.com/MichaelF21/gitlab-yearly-report-service
- [x] CI is green on `main` (lint, test, docker — all three jobs passing)
