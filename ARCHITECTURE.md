# Architecture and code walkthrough

A deep-dive guide to how this service is built, organised, and why each
piece exists. Read top to bottom for a guided tour; or jump to a section
to look up a specific file or concept.

The MCP section ([§7](#7-mcp-deep-dive)) is the longest because it's the
least-familiar piece to most readers and it's the bonus deliverable.

---

## 1. Big picture

The service is a small **read-only adapter** between two things:

- **GitLab's REST API v4** (the source of truth)
- Two **consumer surfaces**: an HTTP API and an MCP server

Both surfaces ask the same question — *"give me the issues/MRs created
in year N, optionally for one project"* — and both call into the same
two domain functions. That symmetry is the central design choice; once
you see it, everything else falls out.

```
                                 ┌────────────────────────┐
   HTTP client ──── GET ───────▶ │  api.py (FastAPI)      │ ┐
                                 │  routes + validation   │ │
                                 └───────────┬────────────┘ │
                                             ▼              │ both adapters
                                 ┌────────────────────────┐ │ call into the
                                 │  reports.py            │ │ same domain
                                 │  get_issues_by_year    │ │ functions
                                 │  get_merge_requests_by │ │
                                 │  _year + view shaping  │ │
                                 └───────────┬────────────┘ │
                                             ▼              │
                                 ┌────────────────────────┐ │
                                 │  gitlab_client.py      │ │
                                 │  async httpx wrapper   │ │
                                 │  pagination + retries  │ │
                                 │  status → exception    │ │
                                 └───────────┬────────────┘ │
                                             ▼              │
                                       GitLab REST API      │
                                                            │
   MCP client ──── tool call ──▶ ┌────────────────────────┐ │
   (Claude / Inspector)          │  mcp_server.py         │ ┘
                                 │  FastMCP @mcp.tool()   │
                                 │  decorators            │
                                 └────────────────────────┘
```

**Key invariant:** every byte that reaches a GitLab endpoint goes through
`gitlab_client.py`. Every JSON record returned to a consumer is shaped by
`reports.py`. There is one path through the system, not two.

---

## 2. Top-level files

```
gitlab-yearly-report-service/
├── pyproject.toml          # Project manifest: deps, entry points, tool config
├── Dockerfile              # Multi-stage container build
├── docker-compose.yml      # GitLab playground + api (shared network)
├── .mcp.json               # Claude Code MCP server config (project-scope)
├── .env.example            # Template for runtime secrets (gitignored)
├── .gitignore / .dockerignore / .gitattributes
├── README.md               # User-facing intro and quick start
├── TESTING.md              # Verification walkthrough
├── CHECKLIST.md            # Brief-requirement traceability matrix
├── ARCHITECTURE.md         # ← you are here
├── scripts/
│   └── bootstrap-playground.sh   # Mint a PAT inside the GitLab container
├── src/gitlab_report/      # All application code lives here
│   ├── __init__.py
│   ├── config.py
│   ├── errors.py
│   ├── gitlab_client.py
│   ├── reports.py
│   ├── api.py
│   ├── main.py
│   └── mcp_server.py
├── tests/
│   ├── conftest.py
│   ├── test_gitlab_client.py
│   ├── test_reports.py
│   └── test_api.py
└── .github/workflows/ci.yml      # GitHub Actions CI
```

### `pyproject.toml`

Modern Python project manifest (PEP 518/621). One file holds:

- **`[project]`** — package metadata: name, version, Python version, deps.
- **`[project.optional-dependencies.dev]`** — pytest, ruff, mypy, bandit,
  respx, pytest-cov, pip-audit.
- **`[project.scripts]`** — installs two console entry points (`pip install`
  generates wrapper executables in the venv's `bin/` for each):
  - `gitlab-report-api` → `gitlab_report.main:run` (uvicorn)
  - `gitlab-report-mcp` → `gitlab_report.mcp_server:run` (stdio MCP server)
- **`[tool.*]`** — configuration for pytest, coverage, ruff, mypy, bandit.

The Dockerfile installs this with `pip install .`, which both pulls deps
and creates those entry points. That's why `CMD ["gitlab-report-api"]`
works in the runtime stage.

### `Dockerfile`

Multi-stage build:

1. **builder** stage on `python:3.12-slim` installs build tools, creates
   a venv in `/opt/venv`, installs the project (including its
   dependencies) into the venv via `pip install .`.
2. **runtime** stage starts fresh from `python:3.12-slim`, adds only
   `ca-certificates` (for TLS) and `curl` (for HEALTHCHECK), creates a
   non-root user (`app`, uid 1001), and copies `/opt/venv` from the
   builder.

Why multi-stage: the runtime image doesn't carry `build-essential`,
`pip`'s cache, or the source-tarball staging area, keeping it slim
(~300MB).

`HEALTHCHECK` curls `/health` so `docker ps` shows `(healthy)`.

### `docker-compose.yml`

Defines the local playground — GitLab 18.10.5 EE alongside our service
on a shared compose network. The `api` service `depends_on` the `gitlab`
service being healthy (compose only starts api once GitLab's built-in
healthcheck passes). Volumes are pinned with `name:` so they're shared
with the `docker run`-style playground in the README.

### `.mcp.json`

Project-scope MCP config that Claude Code reads automatically when you
open this directory. Tells Claude Code to launch `docker run ...
gitlab-report-mcp` as a stdio MCP server. Env vars are interpolated from
the shell at Claude Code launch time (`${GITLAB_TOKEN}`).

### `scripts/bootstrap-playground.sh`

The one piece of the playground that can't be declared in compose —
GitLab tokens have to be minted inside a running GitLab process. The
script polls until the GitLab API responds, then uses `docker exec
gitlab gitlab-rails runner` to create a PAT and print a
`GITLAB_TOKEN=...` line ready to paste into `.env`.

---

## 3. The application code, file by file

### `src/gitlab_report/__init__.py`

Exists so `gitlab_report` is a package. Holds `__version__` so the
FastAPI app and logs can self-identify.

### `src/gitlab_report/config.py`

Configuration loaded from environment variables, with fail-fast
validation.

**Libraries used:**
- **`pydantic-settings.BaseSettings`** — a pydantic-based settings class
  that reads from env vars (or a `.env` file in dev), with type coercion
  and validation. Used because we want type-safe access to env vars
  without writing manual `os.environ.get(...)` boilerplate.
- **`pydantic.HttpUrl`** — string subtype that rejects malformed URLs at
  construction time.
- **`functools.lru_cache`** — memoises the `Settings` instance so
  `get_settings()` is effectively a singleton without a module-level
  global.

**Behaviour:**

- Reads `GITLAB_URL`, `GITLAB_TOKEN`, plus optional `REQUEST_TIMEOUT_SECONDS`,
  `GITLAB_PER_PAGE`, `LOG_LEVEL`.
- `gitlab_api_base` is a derived property that turns `https://gitlab.com`
  into `https://gitlab.com/api/v4` so the client doesn't need to know
  the path convention.
- If validation fails, raises `ConfigError` (defined in this file too).
  `main.py` catches that and exits with code 2.

### `src/gitlab_report/errors.py`

A small exception hierarchy. Each concrete exception maps 1:1 to an HTTP
status code in `api.py`'s exception handlers.

```python
class GitLabError(Exception):           # base; defaults to 502
    status_code: int = 502

class GitLabAuthError(GitLabError):     # 401
class GitLabForbidden(GitLabError):     # 403
class GitLabNotFound(GitLabError):      # 404
class GitLabUpstreamError(GitLabError): # 502 (5xx or transport failure)

class InvalidYearError(ValueError):     # 400 — domain-layer validation
```

**Why have these:** without them, `api.py` would be full of
`if status == 401: ...` ladders, or the GitLab client would have to know
about HTTP framework concepts. Custom exceptions let each layer speak
its own language.

### `src/gitlab_report/gitlab_client.py`

The async GitLab REST API client. All network I/O lives here.

**Libraries used:**
- **`httpx`** — async HTTP client (similar role to `requests` but works
  with `await`). We use it instead of `requests` because the rest of the
  app is async and we want connection pool reuse across calls.
- **`tenacity`** — retry library; we use `AsyncRetrying` with exponential
  backoff for transient failures (429, 5xx, network errors).
- **`urllib.parse.quote`** — URL-encodes project paths like
  `mygroup/my-project` → `mygroup%2Fmy-project`.

**Key methods:**

- **`__init__`** — constructs the `httpx.AsyncClient` with the
  `PRIVATE-TOKEN: <token>` header (GitLab's auth scheme for PATs and
  project access tokens) and explicit timeouts. Never log the token.
- **`list_issues` / `list_merge_requests`** — public async methods. Each
  returns a `list[JsonDict]` of every record across all pages.
- **`_paginate`** — the heart of the client. Uses GitLab's keyset
  pagination (`pagination=keyset&order_by=created_at&sort=asc`) on the
  first request, then follows the `rel="next"` URL from the `Link`
  header until exhausted. This is async-generator-shaped (`yield item`)
  so callers don't have to hold the whole result list in memory.
- **`_request_with_retries`** — wraps a single HTTP call with
  exponential-backoff retry for upstream transient failures. Only
  retries on `GitLabUpstreamError` and `httpx.TransportError`; hard
  failures (401/403/404) propagate immediately so we don't burn retries
  on permission problems.
- **`_raise_for_status`** — central status-code → exception translator.
  This is the one place that knows "401 means auth, 403 means
  permission..." — adding a new status mapping happens here and nowhere
  else.

**Why keyset pagination:** GitLab's docs explicitly warn that
offset-based pagination (`?page=N`) degrades on large result sets, and
keyset is required for instance-wide endpoints (`/issues`,
`/merge_requests`) on big instances.

### `src/gitlab_report/reports.py`

The two domain functions named in the assignment brief. This is also the
**single source of truth** that both the HTTP API and the MCP server
call into.

**Key functions:**

- **`get_issues_by_year(year, project_id_or_path=None)`** and
  **`get_merge_requests_by_year(...)`** — exposed publicly. Each:
  1. Validates `year` (`_validate_year` rejects non-int, out-of-range)
  2. Builds a `GitLabClient` from settings
  3. Calls `list_issues` or `list_merge_requests`
  4. Maps each record through `_issue_view` or `_merge_request_view`

- **`_validate_year`** — rejects strings, booleans (`bool` is a Python
  int subclass — easy to forget), and values outside `[2000, current+1]`.

- **`_issue_view` / `_merge_request_view`** — trim GitLab's full record
  to a stable subset. This is deliberate: GitLab's response is large and
  internal-detail-heavy. Passing it through unchanged would mean our
  HTTP contract is *implicitly* whatever GitLab returns today. Trimming
  decouples us from upstream schema drift.

### `src/gitlab_report/api.py`

The FastAPI surface. Three routes, mapped 1:1 to the brief.

**Libraries used:**
- **`fastapi.FastAPI` / `Query`** — FastAPI's declarative routing and
  query-parameter parsing.
- **`fastapi.exceptions.RequestValidationError`** — raised by FastAPI
  when query-param parsing/validation fails (e.g. `year` is not an int).
  We catch it and re-emit as 400 instead of FastAPI's default 422.
- **`contextlib.asynccontextmanager`** — used to define a FastAPI
  `lifespan` handler that runs once at startup (and shutdown). Used to
  call `get_settings()` early so the app exits fast on bad config.

**Endpoints:**
```python
GET /health             -> {"status": "ok"}
GET /issues             -> reports.get_issues_by_year(year, project)
GET /merge-requests     -> reports.get_merge_requests_by_year(year, project)
```

**Exception handlers:** the file ends with `@app.exception_handler(...)`
decorators that translate the custom exception hierarchy from
`errors.py` into the exact HTTP status codes the brief asks for. This is
the *only* place HTTP framework concepts live — the domain layer
(`reports.py`) and the GitLab layer (`gitlab_client.py`) raise abstract
exceptions, and this file alone knows how to render them.

### `src/gitlab_report/main.py`

The uvicorn entry point — what the `gitlab-report-api` console script
runs.

Does three things:
1. `get_settings()` — fail fast if env is wrong (prints `FATAL:` and
   exits 2).
2. Configures stdlib logging from `LOG_LEVEL`.
3. `uvicorn.run("gitlab_report.api:app", host=..., port=...)`.

Bind defaults to `0.0.0.0:8080` (container scoping handles network
isolation; `# nosec B104` justifies the choice to bandit).

### `src/gitlab_report/mcp_server.py`

See [§7](#7-mcp-deep-dive) for the deep dive — this is short and works
by re-exporting the same two domain functions as MCP tools.

---

## 4. Tests

### `tests/conftest.py`

Sets `GITLAB_URL` and `GITLAB_TOKEN` env vars *before* any
`gitlab_report` module is imported, so `get_settings()` doesn't fail at
import time. Also provides an `autouse` fixture that clears the cached
settings between tests so a test that monkeypatches env vars sees the
change.

### `tests/test_gitlab_client.py`

Unit-tests the client in isolation using **`respx`**, which intercepts
`httpx` calls and lets you assert exact request URLs/params and return
canned responses without any real network calls. Tests cover:

- URL-encoding behaviour of `_encode_project`
- Year → `created_after` / `created_before` translation
- Project-scope vs instance-scope path construction
- Keyset pagination (verifies the `Link`-header follow)
- Status-code → exception mapping (401/403/404/500)
- Token sent in `PRIVATE-TOKEN` header

The pagination test was a hidden trap during development — see
`tests/test_gitlab_client.py::test_pagination_follows_link_header` and
its inline comment. `respx.get(url).mock(side_effect=[...])` chains
responses; without `side_effect` the route would shadow itself and loop
forever.

### `tests/test_reports.py`

Tests the domain layer with mocked GitLab responses. Key cases:

- Year validation (string, bool, out-of-range)
- Response trimming (asserts internal fields like `description` and
  `_links` are dropped)
- Project scope hits the right endpoint URL

### `tests/test_api.py`

Tests the FastAPI surface using `FastAPI.TestClient` + `respx`. Asserts
every row of the brief's error-mapping table — missing year → 400,
GitLab 401 → 401, project 404 → 404, etc.

### `.github/workflows/ci.yml`

Three jobs run in parallel on every push and PR:

1. **lint** — `ruff check`, `ruff format --check`, `mypy`, `bandit`
2. **test** — `pytest` with coverage; fails under 80%
3. **docker** — `hadolint Dockerfile`, build the image, fail-fast and
   `/health` smoke tests against the image, `trivy` scan for HIGH/CRITICAL
   CVEs

The badge in the README's top reflects the latest run.

---

## 5. The data flow, step by step

Walk through `curl http://localhost:8080/issues?year=2026&project=playground%2Fissues-mrs-test`:

1. **uvicorn** receives the TCP connection, parses HTTP, hands the
   parsed request to FastAPI.
2. **FastAPI** routes the path `/issues` to the `issues()` coroutine in
   `api.py`. The `Query(...)` declarations cause it to:
   - Coerce `year` to `int` (raises `RequestValidationError` if it
     can't, which our exception handler converts to 400).
   - Pass `project` as `str | None`.
3. The route awaits `reports.get_issues_by_year(year=2026,
   project_id_or_path="playground/issues-mrs-test")`.
4. **`reports._validate_year`** checks the year is in range; returns
   `2026`.
5. **`reports._build_client(settings)`** constructs a `GitLabClient` with
   the configured base URL and token, then opens it as an async context
   manager (so the underlying `httpx.AsyncClient` is closed when done).
6. **`GitLabClient.list_issues`** computes the path
   `/projects/playground%2Fissues-mrs-test/issues`, the year-window
   query params, and starts paginating.
7. **`GitLabClient._paginate`** issues the first GET with
   `pagination=keyset&per_page=100&...`. Response comes back with the
   first batch of issues and a `Link: <...>; rel="next"` header if
   there's more.
8. **`GitLabClient._request_with_retries`** wraps each call in
   `tenacity.AsyncRetrying`. If GitLab returns 5xx, it retries with
   exponential backoff up to 3 times. If it returns 401/403/404, it
   raises the matching custom exception immediately.
9. Each page's items are yielded; the loop collects all pages until the
   `Link` header has no `next`.
10. Back in `reports.get_issues_by_year`, each raw record is shaped by
    `_issue_view` (drops `description`, `_links`, etc.).
11. The list returns up the call stack to the route, which returns it
    as the FastAPI response body. FastAPI JSON-encodes the list and
    sends `200 OK`.
12. **uvicorn** writes the response to the socket.

If anything raises a `GitLabError` subclass anywhere in that stack, the
matching `@app.exception_handler` in `api.py` catches it and returns the
right HTTP status code with a JSON error body. No `try/except` ladders
in the route — that's the value of the exception hierarchy.

---

## 6. The libraries we depend on, in plain English

| Library | What it does | Where we use it |
|---|---|---|
| **fastapi** | Web framework. Route declaration, request validation, exception handlers, automatic OpenAPI docs. | `api.py` |
| **uvicorn** | ASGI server. The thing that actually listens on a port and runs the FastAPI app. | `main.py` |
| **httpx** | Async HTTP client. Like `requests` but supports `await` and connection pools. | `gitlab_client.py` |
| **pydantic** | Type-validated data classes. FastAPI uses it under the hood; we use `HttpUrl`. | `config.py` |
| **pydantic-settings** | Env-var loader on top of pydantic. Reads env into a `BaseSettings` subclass with validation. | `config.py` |
| **tenacity** | Retry library. We use `AsyncRetrying` with exponential backoff. | `gitlab_client.py` |
| **mcp** | The Model Context Protocol Python SDK. Provides `FastMCP`, server runtime, transport. | `mcp_server.py` |
| **pytest** + **pytest-asyncio** | Test runner; the asyncio plugin lets us write `async def test_...`. | `tests/` |
| **respx** | Mocks `httpx`. Intercepts requests at the transport layer; lets you assert call shape and return canned responses. | `tests/` |
| **pytest-cov** | Coverage measurement plugin for pytest. | `tests/` + CI |
| **ruff** | All-in-one linter + formatter (replaces flake8 + isort + black). | dev + CI |
| **mypy** | Static type checker. | dev + CI |
| **bandit** | Python security linter. | dev + CI |

---

## 7. MCP deep dive

This is the longest section because MCP is the least-familiar piece.
Skip the conceptual half if you only care about how `mcp_server.py`
works.

### 7.1 — What MCP actually is

**Model Context Protocol (MCP)** is a JSON-RPC 2.0 protocol that lets
AI agents (Claude, etc.) discover and invoke external **tools** in a
standardised way. It's "USB-C for AI" — instead of every model+tool
combination needing custom integration code, the model speaks MCP, the
tool exposes MCP, and they negotiate at runtime.

The protocol defines a handshake (`initialize`), a discovery mechanism
(`tools/list`, `resources/list`, `prompts/list`), and an invocation
mechanism (`tools/call`, `resources/read`, `prompts/get`). For our
service we only implement tools.

### 7.2 — Transports

MCP messages can flow over three transports:

- **stdio** — the server reads JSON-RPC messages from stdin and writes
  responses to stdout. The client launches the server as a subprocess.
  Most desktop AI clients (Claude Desktop, Claude Code) use stdio
  because they can launch a binary themselves.
- **SSE (Server-Sent Events) / Streamable HTTP** — the server is a long-
  running HTTP daemon; the client connects over HTTPS. Useful when the
  MCP server is hosted somewhere remote.
- **WebSocket** — bidirectional, real-time. Less common.

**Our server uses stdio.** That's what `mcp.run()` defaults to in
FastMCP, and what `gitlab-report-mcp` runs.

### 7.3 — The protocol lifecycle

A typical session looks like:

```
client          server
  │ ── initialize ──▶ │   {"protocolVersion": ..., "clientInfo": ...}
  │                   │
  │ ◀── result ─────  │   {"serverInfo": ..., "capabilities": {tools: {}}}
  │                   │
  │ ─ initialized ──▶ │   (notification — no response expected)
  │                   │
  │ ── tools/list ──▶ │
  │ ◀── result ─────  │   [{"name": "get_issues_by_year", "inputSchema": ...}, ...]
  │                   │
  │ ── tools/call ──▶ │   {"name": "...", "arguments": {"year": 2026}}
  │ ◀── result ─────  │   {"content": [...], "structuredContent": {...}}
```

Every message is JSON-RPC 2.0: a `jsonrpc: "2.0"` envelope, a method
name, params, and an `id` for request/response pairing. Notifications
omit `id`.

### 7.4 — FastMCP — what it does for us

The `mcp` Python SDK ships two server APIs:

- **Low-level** (`mcp.server.Server`) — you write request handlers
  manually and emit responses. More flexibility, more boilerplate.
- **FastMCP** (`mcp.server.fastmcp.FastMCP`) — decorator-driven, like
  FastAPI. You write a plain Python function, decorate it with
  `@mcp.tool()`, and FastMCP:
  - Inspects the function's signature (Python's `inspect` + type hints)
  - Generates the **input schema** (JSON Schema) from the annotations
  - Generates the **tool description** from the docstring
  - Registers a handler for `tools/list` and `tools/call` that finds and
    invokes your function
  - Wraps the return value in MCP's content envelope

The naming is intentional: FastMCP is to MCP what FastAPI is to HTTP.

### 7.5 — Our MCP server, line by line

`src/gitlab_report/mcp_server.py`:

```python
import logging
import sys
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from .config import ConfigError, get_settings
from .reports import (
    get_issues_by_year as _get_issues_by_year,
    get_merge_requests_by_year as _get_merge_requests_by_year,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("gitlab-yearly-report")  # ← name advertised in serverInfo
```

`FastMCP("gitlab-yearly-report")` creates a server instance. The string
is what shows up in the `initialize` response's `serverInfo.name`.

```python
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
```

This is the *whole* MCP tool. The decorator inspects the function:

- **Name** → `"get_issues_by_year"` (from the function name)
- **Description** → the docstring summary line (shown to the AI agent
  when it's deciding whether to use this tool)
- **Input schema** → JSON Schema generated from type hints:
  ```json
  {
    "type": "object",
    "properties": {
      "year": {"type": "integer"},
      "project_id_or_path": {"type": ["string", "null"]}
    },
    "required": ["year"]
  }
  ```
- **Output schema** → from the return annotation `list[dict[str, Any]]`

When the server receives `tools/call` with arguments, FastMCP validates
them against the schema, then calls the function with kwargs.

`get_merge_requests_by_year` is the same pattern.

```python
def run() -> None:
    try:
        get_settings()           # fail-fast on missing GITLAB_TOKEN
    except ConfigError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(2)
    mcp.run()                    # blocks; reads from stdin, writes to stdout
```

`mcp.run()` blocks the process, runs the stdio loop, and serialises every
tool call to JSON.

### 7.6 — Two non-obvious gotchas

#### `Optional[str]`, not `str | None`

FastMCP introspects parameter annotations with `issubclass(annotation,
SomeClass)` to detect special types. `str | None` (PEP 604 union syntax)
produces a `types.UnionType` object — not a class — so `issubclass`
raises `TypeError: issubclass() arg 1 must be a class` and tool
registration crashes at import time.

**Fix:** use `Optional[str]` from `typing` in MCP tool parameter
annotations. This is the only place in the codebase we don't use
`str | None`. The other modules can use either freely.

This bit us during development on `mcp==1.12.4` and `mcp==1.27.1`. The
fix is a one-line difference.

#### `result.structuredContent.result`, not `result.content[0].text`

When a FastMCP tool returns a list, the response looks like:

```json
{
  "jsonrpc": "2.0", "id": 2,
  "result": {
    "content": [                                         // ← mirrored
      {"type": "text", "text": "{\"id\": 1, ...}"},     //   per-element
      {"type": "text", "text": "{\"id\": 2, ...}"}      //   as text blocks
    ],
    "structuredContent": {
      "result": [                                        // ← real list,
        {"id": 1, ...},                                  //   parsed
        {"id": 2, ...}
      ]
    },
    "isError": false
  }
}
```

`content[]` is for *display* — every list element is mirrored into a
TextContent block. Reading `content[0].text` gives you only the first
element. The canonical structured shape lives in `structuredContent.result`.

This is documented in the MCP spec as "structured content", but it's a
subtle point. The TESTING.md MCP parsing examples use the right path.

### 7.7 — How `.mcp.json` (Claude Code) and `claude_desktop_config.json` (Claude Desktop) connect

Both clients support stdio MCP servers via the same shape of JSON:

```json
{
  "mcpServers": {
    "name-the-client-sees": {
      "command": "executable",
      "args": ["arg1", "arg2"],
      "env": {"OPTIONAL_VAR": "value"}
    }
  }
}
```

When the client starts, for each entry it:
1. Spawns `executable args...` as a subprocess
2. Pipes its stdin/stdout to that subprocess
3. Sends `initialize`, expects a response
4. Sends `tools/list`, learns what's available
5. Exposes those tools to the AI model

The model sees `get_issues_by_year` and `get_merge_requests_by_year`
alongside its built-in tools. When the user asks something like *"how
many issues were created in 2026?"*, the model can decide to call those
tools, the client routes the call to our server, our server queries
GitLab, results flow back up, the model formats them in its response.

For our project:

- **Claude Code** uses [`.mcp.json`](.mcp.json) in this directory — it's
  the recommended project-scope config and gets committed (the actual
  token comes from `${GITLAB_TOKEN}` in the shell env, not the file).
- **Claude Desktop** uses `claude_desktop_config.json` in the user's
  `%APPDATA%\Claude\` folder — that one isn't committed because it's per-user.

The README has copy-pasteable snippets for both.

### 7.8 — Why MCP is worth the bonus

It's not just an extra deliverable — having the same domain layer expose
two surfaces (HTTP + MCP) is a tiny code change with two big upsides:

1. **Validates the design.** If a totally different protocol can wrap
   `reports.py` in 30 lines, the domain layer is well-factored. If it
   needed restructuring to fit MCP, the design was leaky.
2. **Real-world use.** An LLM with these two tools can do things a
   plain HTTP API can't, like *"compare 2024 vs 2025 issue counts per
   project and tell me where the biggest jump was"* — the LLM combines
   the tools, our service just provides the primitives.

---

## 8. Suggested reading order

If you want to map this back to the brief and see how every requirement
is met:

1. Read the assignment PDF.
2. Open [CHECKLIST.md](CHECKLIST.md) — every requirement is mapped here.
3. Open [README.md](README.md#api-reference) for the public surface.
4. Walk through this file (§1–§7).
5. Pick a route in `api.py` and trace it down to `gitlab_client.py`
   step by step.
6. Then read `mcp_server.py` — it should look obvious after the rest.

The whole thing is ~700 lines of Python + ~150 lines of config across
the Dockerfile and compose. It should fit in your head in an afternoon.
