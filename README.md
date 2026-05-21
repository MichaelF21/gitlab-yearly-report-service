# GitLab Yearly Report Service

[![CI](https://github.com/MichaelF21/gitlab-yearly-report-service/actions/workflows/ci.yml/badge.svg)](https://github.com/MichaelF21/gitlab-yearly-report-service/actions/workflows/ci.yml)

Read-only HTTP service (and bonus MCP server) that returns GitLab issues and
merge requests created in a given year, either for a specific project or
across the whole instance scoped to the token's permissions.

Built for the Mobileye DevOps-IT home assignment.

---

## Quick start

```bash
docker build -t gitlab-yearly-report-service .

docker run --rm -p 8080:8080 \
  -e GITLAB_URL="https://gitlab.example.com" \
  -e GITLAB_TOKEN="glpat-xxxxxxxxxxxxxxxxxxxx" \
  gitlab-yearly-report-service
```

Then:

```bash
curl -s http://localhost:8080/health
# {"status":"ok"}

curl -s "http://localhost:8080/issues?year=2025"
curl -s "http://localhost:8080/issues?year=2025&project=mygroup%2Fmy-project"
curl -s "http://localhost:8080/issues?year=2025&project=12345"

curl -s "http://localhost:8080/merge-requests?year=2025"
curl -s "http://localhost:8080/merge-requests?year=2025&project=mygroup%2Fmy-project"
```

Interactive OpenAPI docs are served at `http://localhost:8080/docs`.

---

## Configuration

Configuration is taken entirely from environment variables. The service
**fails fast at startup** if anything required is missing or invalid.

| Variable                    | Required | Default | Purpose                                                      |
|-----------------------------|:--------:|---------|--------------------------------------------------------------|
| `GITLAB_URL`                |  Yes     | —       | Base URL of the GitLab instance (e.g. `https://gitlab.com`)  |
| `GITLAB_TOKEN`              |  Yes     | —       | Personal-access or project-access token with read scopes     |
| `REQUEST_TIMEOUT_SECONDS`   |  No      | `30`    | Upstream read timeout for each GitLab call                   |
| `GITLAB_PER_PAGE`           |  No      | `100`   | Page size for keyset pagination (1–100)                      |
| `LOG_LEVEL`                 |  No      | `INFO`  | `DEBUG`, `INFO`, `WARNING`, `ERROR`                          |
| `HOST`                      |  No      | `0.0.0.0` | Bind host                                                  |
| `PORT`                      |  No      | `8080`  | Bind port                                                    |

The token needs `read_api` scope (PAT) or equivalent project-token read scopes.

---

## API reference

| Method | Path                                       | Description                                      |
|--------|--------------------------------------------|--------------------------------------------------|
| GET    | `/health`                                  | Liveness probe — returns `{"status":"ok"}`       |
| GET    | `/issues?year=YYYY`                        | All issues across the instance (token scope)     |
| GET    | `/issues?year=YYYY&project=ID-or-path`     | Issues for a single project                      |
| GET    | `/merge-requests?year=YYYY`                | All MRs across the instance (token scope)        |
| GET    | `/merge-requests?year=YYYY&project=...`    | MRs for a single project                         |

`project` accepts either a numeric project ID or a URL-encoded full path
(e.g. `mygroup%2Fmy-project`). The service URL-encodes paths for you if
you pass an unencoded one.

### Response shape

Each item is a trimmed view of the GitLab record so this service's HTTP
contract is decoupled from upstream schema drift.

Issue:
```json
{
  "id": 101,
  "iid": 7,
  "project_id": 5,
  "title": "Something broke",
  "state": "opened",
  "created_at": "2025-04-01T12:00:00Z",
  "updated_at": "2025-04-02T09:00:00Z",
  "closed_at": null,
  "author": "alice",
  "labels": ["bug"],
  "web_url": "https://gitlab.example.com/g/p/-/issues/7"
}
```

Merge request:
```json
{
  "id": 9001,
  "iid": 12,
  "project_id": 5,
  "title": "Add foo",
  "state": "merged",
  "draft": false,
  "created_at": "2025-06-01T00:00:00Z",
  "updated_at": "2025-06-01T08:00:00Z",
  "merged_at": "2025-06-02T00:00:00Z",
  "closed_at": null,
  "source_branch": "feature/foo",
  "target_branch": "main",
  "author": "bob",
  "labels": [],
  "web_url": "https://gitlab.example.com/g/p/-/merge_requests/12"
}
```

### Error mapping

| Scenario                       | Status |
|--------------------------------|--------|
| Missing `year`                 | 400    |
| `year` not a 4-digit integer   | 400    |
| `year` outside [2000, current+1] | 400    |
| GitLab returned 401            | 401    |
| GitLab returned 403            | 403    |
| GitLab project not found       | 404    |
| GitLab 5xx / network failure   | 502    |
| `GITLAB_TOKEN` missing         | startup failure, exit code 2 |

Error bodies follow `{"error": "...", "status": <int>, "detail": "..."}`.

---

## Local development

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Run the service
export GITLAB_URL=https://gitlab.com
export GITLAB_TOKEN=glpat-xxxx
gitlab-report-api                   # uvicorn on 0.0.0.0:8080

# Quality gate (all four pass in CI)
ruff check .
ruff format --check .
mypy
bandit -r src -q

# Tests + coverage
pytest -v --cov --cov-report=term-missing
```

Tests use `respx` to mock GitLab; no live token is required.

To run the tests inside Docker (no local Python needed):

```bash
docker run --rm -v "$PWD":/src -w /src python:3.12-slim \
  sh -c 'pip install -q -e ".[dev]" && pytest -v'
```

### Continuous integration

`.github/workflows/ci.yml` runs three jobs in parallel on every push and PR:

| Job    | Checks                                                                                |
|--------|---------------------------------------------------------------------------------------|
| lint   | `ruff check`, `ruff format --check`, `mypy`, `bandit`                                 |
| test   | `pytest` with coverage; fails under 80%; uploads `coverage.xml` artifact              |
| docker | `hadolint Dockerfile`, build the image, fail-fast and `/health` smoke tests, `trivy`  |

CI gates the merge to `main`; the badge at the top of this file reflects status.

---

## MCP server (bonus)

The same domain functions are exposed as MCP tools over stdio:

- `get_issues_by_year(year, project_id_or_path?)`
- `get_merge_requests_by_year(year, project_id_or_path?)`

Run the server directly:

```bash
GITLAB_URL=https://gitlab.com GITLAB_TOKEN=glpat-xxxx gitlab-report-mcp
```

### Claude Desktop / Claude Code config

Add to `claude_desktop_config.json` (or equivalent):

```json
{
  "mcpServers": {
    "gitlab-yearly-report": {
      "command": "gitlab-report-mcp",
      "env": {
        "GITLAB_URL": "https://gitlab.com",
        "GITLAB_TOKEN": "glpat-xxxxxxxxxxxx"
      }
    }
  }
}
```

Or with Docker:

```json
{
  "mcpServers": {
    "gitlab-yearly-report": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "GITLAB_URL", "-e", "GITLAB_TOKEN",
        "gitlab-yearly-report-service",
        "gitlab-report-mcp"
      ],
      "env": {
        "GITLAB_URL": "https://gitlab.com",
        "GITLAB_TOKEN": "glpat-xxxxxxxxxxxx"
      }
    }
  }
}
```

Quick smoke test using the MCP inspector:

```bash
npx @modelcontextprotocol/inspector gitlab-report-mcp
```

---

## Local GitLab playground

The brief includes a snippet for running GitLab 18.10+ locally. After the
container is up, sign in with the password from
`/etc/gitlab/initial_root_password` inside the container, create a project
and a few issues/MRs, then mint a personal-access token with `read_api`.

```bash
GITLAB_HOME=/tmp/gitlab
docker run --detach \
  --hostname gitlab.example.com \
  --env GITLAB_OMNIBUS_CONFIG="external_url 'http://gitlab.example.com'" \
  --publish 443:443 --publish 80:80 --publish 22:22 \
  --name gitlab --restart always \
  --volume $GITLAB_HOME/config:/etc/gitlab \
  --volume $GITLAB_HOME/logs:/var/log/gitlab \
  --volume $GITLAB_HOME/data:/var/opt/gitlab \
  --shm-size 256m \
  gitlab/gitlab-ee:18.10.5-ee.0

# Wait until http://gitlab.example.com is reachable (a few minutes on first boot).
docker exec -it gitlab cat /etc/gitlab/initial_root_password

# Then run this service against it:
docker run --rm -p 8080:8080 \
  --add-host gitlab.example.com:host-gateway \
  -e GITLAB_URL=http://gitlab.example.com \
  -e GITLAB_TOKEN=glpat-xxxx \
  gitlab-yearly-report-service
```

---

## Design notes

- **Single source of truth.** `reports.py` defines the two deliverable
  functions; the FastAPI routes and the MCP tools are thin adapters over
  them. No duplicated logic between the two surfaces.
- **Read-only by construction.** `GitLabClient` exposes only `list_*`
  methods. The HTTP service has no POST/PUT/PATCH/DELETE routes.
- **Pagination.** Uses GitLab's keyset pagination (`pagination=keyset`,
  `order_by=created_at`, `sort=asc`) on `/issues` and `/merge_requests`,
  which avoids the deep-page performance cliff GitLab warns about with
  offset pagination. Next-page URLs come from the `Link` header.
- **Year boundaries.** Using inclusive bounds
  `created_after = YYYY-01-01T00:00:00Z`,
  `created_before = YYYY-12-31T23:59:59Z`.
- **Trimmed response shape.** Records pass through `_issue_view` /
  `_merge_request_view` so the HTTP contract is decoupled from GitLab's
  full payload.
- **Resilience.** Transient failures (HTTP 429, 5xx, transport errors)
  are retried with exponential backoff via `tenacity`. Hard failures
  (401/403/404) are not retried — they propagate immediately.
- **Fail fast on bad config.** Missing or invalid env vars cause a
  non-zero exit at startup with a clear message, rather than 500s on
  every request.
- **Container hygiene.** Multi-stage build, non-root user, slim base,
  `HEALTHCHECK` against `/health`, build deps confined to the builder
  stage.
- **No secret leakage.** The token is sent only via the `PRIVATE-TOKEN`
  header, never logged. Outbound URLs are logged with the query string
  stripped defensively.

---

## Repository layout

```
gitlab-yearly-report-service/
├── README.md
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .gitignore
├── .env.example
├── pyproject.toml
├── src/gitlab_report/
│   ├── __init__.py
│   ├── config.py            # env parsing, fail-fast
│   ├── errors.py            # GitLab exception hierarchy
│   ├── gitlab_client.py     # async REST client with keyset pagination
│   ├── reports.py           # deliverable domain functions
│   ├── api.py               # FastAPI app + exception handlers
│   ├── main.py              # uvicorn entrypoint
│   └── mcp_server.py        # MCP server (bonus)
└── tests/
    ├── conftest.py
    ├── test_gitlab_client.py
    ├── test_reports.py
    └── test_api.py
```
