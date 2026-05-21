# Acceptance checklist

Mirrors the requirements in the Mobileye DevOps-IT home assignment brief.
Each row is ticked only after being verified. **All functional rows have been
live-verified against `gitlab/gitlab-ee:18.10.5-ee.0` running locally per
the brief's playground instructions.**

## Functional requirements

- [x] Read-only — `GitLabClient` exposes only `list_*` (GET) methods; the FastAPI app has no POST/PUT/PATCH/DELETE routes
- [x] `GET /health` returns `{"status":"ok"}` with HTTP 200 (live-verified)
- [x] `GET /issues?year=YYYY` (instance scope) returns issues created in that year — live-verified: 7 issues across 2 projects in 2026, 0 in 2024
- [x] `GET /issues?year=YYYY&project=<id>` (project scope by numeric ID) — live-verified: project 1 → 5 issues, project 2 → 2 issues
- [x] `GET /issues?year=YYYY&project=group%2Fproject` (project scope by encoded path) — live-verified: `playground%2Fissues-mrs-test` → 5 issues
- [x] `GET /merge-requests?year=YYYY` (instance scope) — live-verified: 4 MRs in 2026
- [x] `GET /merge-requests?year=YYYY&project=<id>` — live-verified: project 1 → 3, project 2 → 1
- [x] `GET /merge-requests?year=YYYY&project=group%2Fproject` — live-verified: encoded path → 3

## Error mapping (from the brief)

- [x] Missing `year` parameter → 400 (live-verified)
- [x] Non-integer `year` → 400 (live-verified)
- [x] Out-of-range `year` → 400 (live-verified)
- [x] GitLab returns 401 → service returns 401 (live-verified earlier against gitlab.com with a bad token)
- [x] GitLab returns 403 → service returns 403 (live-verified: PAT with `read_repository` scope only → GitLab returns `insufficient_scope` 403 → service translates to 403)
- [x] GitLab returns 404 (project not found) → service returns 404 (live-verified: `?project=does%2Fnot-exist`)
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

## Live playground verification log

GitLab Enterprise Edition 18.10.5 booted from the brief's image
(`gitlab/gitlab-ee:18.10.5-ee.0`) and bootstrapped via the GitLab REST API:

| Project              | ID | Visibility | Issues | MRs |
|----------------------|----|------------|-------:|----:|
| `playground/issues-mrs-test` | 1  | public     |      5 |   3 |
| `playground/secret`          | 2  | private    |      2 |   1 |
| **Instance totals**          |    |            |  **7** | **4** |

Probe results (16/16 PASS):

```
=== 1. /health ===
  [PASS] 200  /health
=== 2. Error mapping ===
  [PASS] 400  missing year
  [PASS] 400  non-integer year
  [PASS] 400  out-of-range year
  [PASS] 404  bogus project -> 404
=== 3. Issues - instance scope ===
  [PASS] 200  all issues year=2026         (count == 7)
  [PASS] 200  issues year=2024 empty       (count == 0)
=== 4. Issues - project scope (numeric id) ===
  [PASS] 200  issues project=1             (count == 5)
  [PASS] 200  issues project=2             (count == 2)
=== 5. Issues - project scope (URL-encoded path) ===
  [PASS] 200  issues encoded path          (count == 5)
=== 6. Merge requests - instance scope ===
  [PASS] 200  all MRs year=2026            (count == 4)
  [PASS] 200  MRs year=2025 empty          (count == 0)
=== 7. Merge requests - project scope ===
  [PASS] 200  MRs project=1                (count == 3)
  [PASS] 200  MRs project=2                (count == 1)
  [PASS] 200  MRs encoded path             (count == 3)
=== 8. 403 translation ===
  [PASS] 403  GitLab 403 (read_repository scope) -> service 403
```
