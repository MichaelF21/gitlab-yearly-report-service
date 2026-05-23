# Acceptance checklist

Requirement-to-evidence map for the assignment brief. Each row points
to where the verification is implemented or how to reproduce it.

For end-to-end live verification steps see [TESTING.md](TESTING.md);
the live corpus is created by `scripts/bootstrap-test-data.sh`.

## Functional requirements

- [x] Read-only — `GitLabClient` exposes only `list_*` (GET) methods; the FastAPI app has no POST/PUT/PATCH/DELETE routes
- [x] `GET /health` returns `{"status":"ok"}` with HTTP 200 — [TESTING §1](TESTING.md#1-sanity----health)
- [x] `GET /issues?year=YYYY` (instance scope) — [TESTING §2.1](TESTING.md#21--issues-entire-instance), unit-tested in `tests/test_api.py::test_happy_path_returns_trimmed_issues`
- [x] `GET /issues?year=YYYY&project=<id>` (project scope by numeric ID) — [TESTING §2.2](TESTING.md#22--issues-project-by-numeric-id)
- [x] `GET /issues?year=YYYY&project=group%2Fproject` (project scope by encoded path) — [TESTING §2.3](TESTING.md#23--issues-project-by-url-encoded-path), `tests/test_reports.py::test_project_scope_hits_project_endpoint`
- [x] `GET /merge-requests?year=YYYY` (instance scope) — [TESTING §2.5](TESTING.md#25--same-four-shapes-for-merge-requests)
- [x] `GET /merge-requests?year=YYYY&project=<id>` — [TESTING §2.5](TESTING.md#25--same-four-shapes-for-merge-requests)
- [x] `GET /merge-requests?year=YYYY&project=group%2Fproject` — [TESTING §2.5](TESTING.md#25--same-four-shapes-for-merge-requests)

## Error mapping (from the brief)

- [x] Missing `year` → 400 — [TESTING §3](TESTING.md#3-error-mapping-rows-from-the-brief), `tests/test_api.py::test_missing_year_returns_400`
- [x] Non-integer `year` → 400 — [TESTING §3](TESTING.md#3-error-mapping-rows-from-the-brief), `tests/test_api.py::test_non_integer_year_returns_400`
- [x] Out-of-range `year` → 400 — [TESTING §3](TESTING.md#3-error-mapping-rows-from-the-brief), `tests/test_api.py::test_out_of_range_year_returns_400`
- [x] GitLab returns 401 → service returns 401 — [TESTING §3.1](TESTING.md#31--401-gitlab-authentication-failed), `tests/test_api.py::test_gitlab_401_maps_to_401`
- [x] GitLab returns 403 → service returns 403 — [TESTING §3.2](TESTING.md#32--403-gitlab-permission-denied), `tests/test_api.py::test_gitlab_403_maps_to_403`
- [x] GitLab returns 404 (project not found) → service returns 404 — [TESTING §3](TESTING.md#3-error-mapping-rows-from-the-brief), `tests/test_api.py::test_gitlab_project_404_maps_to_404`
- [x] Missing `GITLAB_TOKEN` → clear startup failure, non-zero exit code — [TESTING §3.3](TESTING.md#33--missing-gitlab_token-clear-startup-failure)

## Containerization

- [x] `docker build` succeeds — verified in CI's `docker` job
- [x] `docker run --rm -p 8080:8080 -e GITLAB_URL=... -e GITLAB_TOKEN=...` works as in the brief — [README quick start](README.md#quick-start)
- [x] Service is reachable on `http://localhost:8080`
- [x] Image built FROM `python:3.12-slim` (multi-stage) — see `Dockerfile`
- [x] Container runs as non-root user (uid 1001) — see `Dockerfile`
- [x] `HEALTHCHECK` shows `(healthy)` within 30s — see `Dockerfile`
- [x] Image size is reasonable for the stack (~300MB; the python:3.12-slim base + FastAPI + uvicorn[standard] + mcp accounts for almost all of it)

## Code quality

- [x] `ruff check .` clean — CI `lint` job
- [x] `ruff format --check .` clean — CI `lint` job
- [x] `mypy` clean under strict settings (0 issues across 8 source files) — CI `lint` job
- [x] `bandit -r src` clean — CI `lint` job; `B113` and `B104` suppressed inline with comment-justified rationale
- [x] `pytest` — 30/30 tests pass — CI `test` job
- [x] Test coverage ≥ 80% — CI `test` job fails below 80%
- [x] `hadolint Dockerfile` clean — CI `docker` job; `DL3008` suppressed inline (unpinned apt versions in a discarded builder layer)
- [x] `trivy image` clean of HIGH/CRITICAL fixable CVEs — CI `docker` job

## Bonus — MCP server

- [x] `gitlab-report-mcp` exposes `get_issues_by_year` — [TESTING §4.1](TESTING.md#41--stdio-handshake-protocol-smoke)
- [x] `gitlab-report-mcp` exposes `get_merge_requests_by_year` — [TESTING §4.1](TESTING.md#41--stdio-handshake-protocol-smoke)
- [x] MCP initialize handshake succeeds — [TESTING §4.1](TESTING.md#41--stdio-handshake-protocol-smoke)
- [x] MCP `tools/call` returns the same data as the HTTP API — [TESTING §4.2](TESTING.md#42--stdio-toolscall-functional-smoke)
- [x] README documents how to wire the MCP server into Claude Desktop and Docker — [README MCP section](README.md#claude-desktop)
- [x] Project-scope MCP config shipped — [`.mcp.json`](.mcp.json)

## Submission

- [x] README has quick start, env-var table, endpoint reference, curl examples — [README](README.md)
- [x] README documents the MCP server setup — [README](README.md#mcp-server-bonus)
- [x] README documents the local GitLab playground (per brief) — [README](README.md#local-gitlab-playground)
- [x] Repository is public: https://github.com/MichaelF21/gitlab-yearly-report-service
- [x] CI is green on `main` — see [Actions tab](https://github.com/MichaelF21/gitlab-yearly-report-service/actions)
