# Testing guide

A walkthrough for verifying every functional and error-mapping
requirement from the assignment brief against a live GitLab instance.

All commands assume a Bash-compatible shell (Git Bash on Windows, any
POSIX shell elsewhere). PowerShell equivalents are noted where they
differ meaningfully.

## 0. Environment setup

The minimum setup depends on what state you're in.

### Prerequisites (one-time, per machine)

| Tool | Purpose | Install |
|------|---------|---------|
| Docker Desktop (running) | Hosts the gitlab + api containers | https://www.docker.com/products/docker-desktop |
| Git | Clone this repo | `winget install Git.Git` on Windows |
| curl + Python 3 | Run the test commands below | Come bundled with Git Bash on Windows |
| Node.js (optional) | MCP Inspector — section 4.3 | `winget install OpenJS.NodeJS` on Windows |

### Cold start (no playground yet)

`docker compose up -d` **alone is not enough** the first time. Compose
enforces that `GITLAB_TOKEN` is set in `.env` before starting the api
service, and a token can only be minted inside a running GitLab. Six
steps:

```bash
git clone https://github.com/MichaelF21/gitlab-yearly-report-service
cd gitlab-yearly-report-service
cp .env.example .env

# Start GitLab first (3-5 min cold boot).
docker compose up -d gitlab

# Mint a PAT once GitLab's API responds. The script polls and prints
# a GITLAB_TOKEN=glpat-... line ready to paste into .env.
./scripts/bootstrap-playground.sh

# Paste the GITLAB_TOKEN= line into .env, then:
docker compose up -d

# Populate the test corpus (idempotent).
./scripts/bootstrap-test-data.sh
```

After that, `docker ps` should show both containers as `(healthy)` and
the GitLab instance has the test corpus described below.

### Resume (volumes preserved)

`docker compose down` (no `-v`) preserves data. To resume:

```bash
docker compose up -d
```

### Full reset

```bash
docker compose down -v
docker volume rm gitlab-config gitlab-logs gitlab-data
rm -f .env
```

Then follow the cold-start steps again.

### Configure MCP clients (only if you want to test sections 4.3–4.4)

| Client | Action |
|--------|--------|
| MCP Inspector | Node.js installed; the `npx` command in §4.3 handles the rest. |
| Claude Code (project scope) | The committed [`.mcp.json`](.mcp.json) auto-registers when you `cd` here and run `claude`. Export `GITLAB_TOKEN` first. |
| Claude Code (user scope) | Add the same JSON to `~/.claude.json` under top-level `mcpServers`. See README's MCP section. |
| Claude Desktop | Edit `%APPDATA%\Claude\claude_desktop_config.json` (Win) or `~/Library/Application Support/Claude/claude_desktop_config.json` (mac). Restart Claude Desktop. |

---

## What's running once setup is done

| Service           | URL                          | Purpose                          |
|-------------------|------------------------------|----------------------------------|
| GitLab 18.10.5 EE | http://localhost:8929        | Holds the test corpus            |
| Report service    | http://localhost:8080        | The thing under test             |
| Swagger / OpenAPI | http://localhost:8080/docs   | Interactive request builder      |

GitLab login: `root` and the password from
`docker exec gitlab cat /etc/gitlab/initial_root_password | grep '^Password:'`.

## Test corpus

`scripts/bootstrap-test-data.sh` creates a known dataset so the count
assertions below are deterministic:

| Project                        | ID | Visibility | Issues | MRs |
|--------------------------------|----|------------|-------:|----:|
| `playground/issues-mrs-test`   | 1  | public     |      5 |   3 |
| `playground/secret`            | 2  | private    |      2 |   1 |
| **Instance totals**            |    |            |  **7** | **4** |

All records are stamped at script-run time, so query them with the
current calendar year. Examples below use `2026` — replace as needed.

> **In the commands below**, `$ADMIN_PAT` refers to the value of
> `GITLAB_TOKEN` in your `.env`. Set it for your shell with:
>
> ```bash
> export ADMIN_PAT="$(grep ^GITLAB_TOKEN .env | cut -d= -f2)"
> ```

---

## 1. Sanity — `/health`

```bash
curl -s -w "\nstatus: %{http_code}\n" http://localhost:8080/health
```
**Expected:**
```
{"status":"ok"}
status: 200
```

---

## 2. Functional rows from the brief

`YEAR` below is the year the corpus was created in (the current
calendar year if you just ran the bootstrap).

### 2.1 — Issues, entire instance

```bash
curl -s "http://localhost:8080/issues?year=2026" \
  | python -c "import sys,json; print('count =', len(json.load(sys.stdin)))"
```
**Expected:** `count = 7`

### 2.2 — Issues, project by numeric ID

```bash
curl -s "http://localhost:8080/issues?year=2026&project=1" \
  | python -c "import sys,json; print('count =', len(json.load(sys.stdin)))"
curl -s "http://localhost:8080/issues?year=2026&project=2" \
  | python -c "import sys,json; print('count =', len(json.load(sys.stdin)))"
```
**Expected:** `count = 5` and `count = 2`

### 2.3 — Issues, project by URL-encoded path

```bash
curl -s "http://localhost:8080/issues?year=2026&project=playground%2Fissues-mrs-test" \
  | python -c "import sys,json; print('count =', len(json.load(sys.stdin)))"
```
**Expected:** `count = 5`

### 2.4 — Year boundary

```bash
curl -s "http://localhost:8080/issues?year=2024" \
  | python -c "import sys,json; print('count =', len(json.load(sys.stdin)))"
```
**Expected:** `count = 0` (the corpus was created in `YEAR`, not 2024).

### 2.5 — Same four shapes for `/merge-requests`

```bash
# Instance scope
curl -s "http://localhost:8080/merge-requests?year=2026" \
  | python -c "import sys,json; print('MRs instance:', len(json.load(sys.stdin)))"
# Project by ID
curl -s "http://localhost:8080/merge-requests?year=2026&project=1" \
  | python -c "import sys,json; print('MRs project 1:', len(json.load(sys.stdin)))"
curl -s "http://localhost:8080/merge-requests?year=2026&project=2" \
  | python -c "import sys,json; print('MRs project 2:', len(json.load(sys.stdin)))"
# Project by encoded path
curl -s "http://localhost:8080/merge-requests?year=2026&project=playground%2Fissues-mrs-test" \
  | python -c "import sys,json; print('MRs by path:', len(json.load(sys.stdin)))"
# Empty year
curl -s "http://localhost:8080/merge-requests?year=2025" \
  | python -c "import sys,json; print('MRs 2025:', len(json.load(sys.stdin)))"
```
**Expected:**
```
MRs instance: 4
MRs project 1: 3
MRs project 2: 1
MRs by path: 3
MRs 2025: 0
```

### 2.6 — Response shape

```bash
curl -s "http://localhost:8080/issues?year=2026&project=1" \
  | python -m json.tool | head -20
```
**Expected:** Trimmed shape — `id`, `iid`, `project_id`, `title`, `state`,
`created_at`, `updated_at`, `closed_at`, `author`, `labels`, `web_url`.
No `description`, `_links`, or other GitLab internals.

```bash
curl -s "http://localhost:8080/merge-requests?year=2026&project=1" \
  | python -m json.tool | head -25
```
**Expected:** MR shape — adds `draft`, `merged_at`, `source_branch`,
`target_branch` to the above.

---

## 3. Error mapping rows from the brief

| Brief row                       | Expected | Command (one-liner) |
|---------------------------------|---------:|---------------------|
| Missing `year`                  |      400 | `curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/issues` |
| Non-integer `year`              |      400 | `curl -s -o /dev/null -w '%{http_code}\n' "http://localhost:8080/issues?year=bad"` |
| Out-of-range `year`             |      400 | `curl -s -o /dev/null -w '%{http_code}\n' "http://localhost:8080/issues?year=1500"` |
| GitLab project not found        |      404 | `curl -s -o /dev/null -w '%{http_code}\n' "http://localhost:8080/issues?year=2026&project=does%2Fnot-exist"` |

Run them as a batch:

```bash
for url in \
  "http://localhost:8080/issues" \
  "http://localhost:8080/issues?year=bad" \
  "http://localhost:8080/issues?year=1500" \
  "http://localhost:8080/issues?year=2026&project=does%2Fnot-exist"
do
  printf "%-65s %s\n" "$url" "$(curl -s -o /dev/null -w '%{http_code}' "$url")"
done
```
**Expected:** `400 400 400 404` (each on its own line).

### 3.1 — 401 (GitLab authentication failed)

Start a second report container with a bogus token:

```bash
docker run --rm -d --name report-bad-token -p 8081:8080 \
  --add-host host.docker.internal:host-gateway \
  -e GITLAB_URL=http://host.docker.internal:8929 \
  -e GITLAB_TOKEN=glpat-this-token-does-not-exist \
  gitlab-yearly-report-service:dev > /dev/null
sleep 3
curl -s -w '\nstatus: %{http_code}\n' "http://localhost:8081/issues?year=2026"
docker stop report-bad-token > /dev/null
```
**Expected:** `status: 401` and a body whose `detail` mentions
"GitLab returned 401".

### 3.2 — 403 (GitLab permission denied)

Mint a PAT with insufficient scope and restart the report container
against it:

```bash
LIMITED_PAT=$(docker exec gitlab gitlab-rails runner '
user = User.find_by_username("root")
t = user.personal_access_tokens.create(name: "limited-test", scopes: [:read_repository], expires_at: 30.days.from_now)
t.save!; puts t.token' 2>/dev/null | tail -1)
echo "limited PAT: ${LIMITED_PAT:0:25}..."

docker rm -f report > /dev/null
docker run -d --rm --name report -p 8080:8080 \
  --add-host host.docker.internal:host-gateway \
  -e GITLAB_URL=http://host.docker.internal:8929 \
  -e GITLAB_TOKEN="$LIMITED_PAT" \
  gitlab-yearly-report-service:dev > /dev/null
sleep 3

curl -s -w '\nstatus: %{http_code}\n' "http://localhost:8080/issues?year=2026"
```
**Expected:** `status: 403` and a body referencing `insufficient_scope`.

**Restore the admin token** for subsequent tests:

```bash
docker rm -f report > /dev/null
docker compose up -d
```

### 3.3 — Missing `GITLAB_TOKEN` (clear startup failure)

```bash
docker run --rm -e GITLAB_URL=http://host.docker.internal:8929 \
  gitlab-yearly-report-service:dev
echo "exit code: $?"
```
**Expected:** A `FATAL:` message naming `GITLAB_TOKEN`, and `exit code: 2`.

---

## 4. Bonus — MCP server

The MCP server is the bonus deliverable. Five practical ways to test it,
ordered from cheapest smoke check to fullest end-to-end.

### 4.1 — Stdio handshake (protocol smoke)

Confirms the server speaks JSON-RPC 2.0 and exposes both required tools.

```bash
ADMIN_PAT="$(grep ^GITLAB_TOKEN .env | cut -d= -f2)"

{ printf '%s\n%s\n%s\n' \
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
    '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}' \
    '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
  sleep 2
} | docker run --rm -i \
    --add-host host.docker.internal:host-gateway \
    -e GITLAB_URL=http://host.docker.internal:8929 \
    -e GITLAB_TOKEN="$ADMIN_PAT" \
    gitlab-yearly-report-service:dev gitlab-report-mcp 2>/dev/null \
  | python -c "
import sys, json
for line in sys.stdin:
    if not line.strip(): continue
    obj = json.loads(line)
    if obj.get('id') == 1:
        print('init OK, server:', obj['result']['serverInfo']['name'])
    elif obj.get('id') == 2:
        print('tools:', [t['name'] for t in obj['result']['tools']])
"
```
**Expected:**
```
init OK, server: gitlab-yearly-report
tools: ['get_issues_by_year', 'get_merge_requests_by_year']
```

### 4.2 — Stdio `tools/call` (functional smoke)

Actually invoke each tool and confirm it returns the same data the HTTP
API would. The list lives in `result.structuredContent.result` (FastMCP
also mirrors each element into `result.content[]` as TextContent blocks).

```bash
ADMIN_PAT="$(grep ^GITLAB_TOKEN .env | cut -d= -f2)"
OUT="${TMPDIR:-/tmp}/mcp.jsonl"

{ printf '%s\n%s\n%s\n%s\n' \
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"demo","version":"0"}}}' \
    '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}' \
    '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_issues_by_year","arguments":{"year":2026,"project_id_or_path":"playground/issues-mrs-test"}}}' \
    '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_merge_requests_by_year","arguments":{"year":2026}}}'
  sleep 4
} | docker run --rm -i \
    --add-host host.docker.internal:host-gateway \
    -e GITLAB_URL=http://host.docker.internal:8929 \
    -e GITLAB_TOKEN="$ADMIN_PAT" \
    gitlab-yearly-report-service:dev gitlab-report-mcp 2>/dev/null \
  > "$OUT"

python <<PY
import json
for line in open("$OUT"):
    if not line.strip(): continue
    obj = json.loads(line)
    rid = obj.get("id")
    if rid == 2:
        items = obj["result"]["structuredContent"]["result"]
        print("get_issues_by_year(2026, 'playground/issues-mrs-test') ->", len(items), "issues")
    elif rid == 3:
        items = obj["result"]["structuredContent"]["result"]
        print("get_merge_requests_by_year(2026) ->", len(items), "MRs")
PY
```
**Expected:**
```
get_issues_by_year(2026, 'playground/issues-mrs-test') -> 5 issues
get_merge_requests_by_year(2026) -> 4 MRs
```

### 4.3 — MCP Inspector (interactive browser UI)

The official Anthropic tool. Browser UI lists tools, lets you fill in
arguments through a form, displays the response inline.

```bash
ADMIN_PAT="$(grep ^GITLAB_TOKEN .env | cut -d= -f2)"

npx -y "@modelcontextprotocol/inspector" \
  -e "GITLAB_URL=http://host.docker.internal:8929" \
  -e "GITLAB_TOKEN=$ADMIN_PAT" \
  -- docker run --rm -i \
       --add-host host.docker.internal:host-gateway \
       -e GITLAB_URL -e GITLAB_TOKEN \
       gitlab-yearly-report-service:dev gitlab-report-mcp
```

The inspector prints a `http://localhost:<port>/?MCP_PROXY_AUTH_TOKEN=...`
URL — open it. Click "Tools" → either tool → fill `year` (and optionally
`project_id_or_path`) → "Run Tool". Same counts as section 4.2.

The `--` separator is required so the second set of `-e` flags reaches
docker (the inspector parses `-e` as its own option for setting env vars
on the spawned process).

### 4.4 — Claude Desktop / Claude Code (real end-to-end)

The point of an MCP server is to let an AI model use it. Wire it up and
ask the model natural-language questions; verify it picks the right
tool with the right arguments.

Both clients accept the same shape under `mcpServers`. See the README
section for ready-to-paste JSON.

Try prompts like:

- *"List the issues created in 2026 in `playground/issues-mrs-test`."*
- *"How many merge requests were opened across all projects in 2026?"*
- *"What was the title of the third MR in project 1 in 2026?"*

Watch for the client announcing the tool call (the model emits `using
get_issues_by_year` with the arguments) and verify the answer matches
the corpus.

### 4.5 — Python MCP client (programmatic, for CI regression)

Sketch for a regression test, if you ever expand MCP coverage:

```python
import asyncio, json, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_mcp_tools_list_and_call():
    params = StdioServerParameters(
        command="docker",
        args=[
            "run", "--rm", "-i",
            "--add-host", "host.docker.internal:host-gateway",
            "-e", "GITLAB_URL=http://host.docker.internal:8929",
            "-e", f"GITLAB_TOKEN={os.environ['GITLAB_TOKEN']}",
            "gitlab-yearly-report-service:dev",
            "gitlab-report-mcp",
        ],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {t.name for t in tools.tools} == {
                "get_issues_by_year",
                "get_merge_requests_by_year",
            }
            result = await session.call_tool(
                "get_issues_by_year",
                arguments={"year": 2026, "project_id_or_path": "playground/issues-mrs-test"},
            )
            items = result.structuredContent["result"]
            assert len(items) == 5
```

Not currently included — the existing pytest suite covers `reports.py`,
which the MCP server thinly wraps, so MCP coverage would be largely
redundant. Add this if you change the MCP adapter beyond the current
thin wrapper.

---

## 5. Observe in the GitLab UI

Browse to http://localhost:8929 and login as `root`. The playground
projects are at:

- http://localhost:8929/playground/issues-mrs-test
- http://localhost:8929/playground/secret

Add or close issues/MRs through the UI and re-run the count queries
in section 2 — the numbers should update accordingly.

---

## 6. Stop and clean up

Graceful stop (preserves data):

```bash
docker compose down
```

Full reset (frees ~7GB):

```bash
docker compose down -v
docker volume rm gitlab-config gitlab-logs gitlab-data
docker rmi gitlab/gitlab-ee:18.10.5-ee.0
```

---

## Troubleshooting

### `dependency failed to start: container gitlab is unhealthy`

GitLab's PostgreSQL is stuck on a stale lock file from a previous
unclean shutdown. Symptoms in `docker logs gitlab`:

```
FATAL: lock file "/var/opt/gitlab/postgresql/.s.PGSQL.5432.lock" already exists
```

Fix:

```bash
docker exec gitlab gitlab-ctl stop postgresql
docker exec gitlab sh -c 'rm -f /var/opt/gitlab/postgresql/data/postmaster.pid /var/opt/gitlab/postgresql/.s.PGSQL.5432.lock'
docker exec gitlab gitlab-ctl start postgresql
docker inspect gitlab --format '{{.State.Health.Status}}'    # should be healthy
docker compose up -d
```

Avoid by always shutting down with `docker compose down` (not `docker
kill` or letting the OS shut down ungracefully).

### Warning: `volume "gitlab-data" already exists but was not created by Docker Compose`

Cosmetic. Compose noting that the volume was created outside it (via
the README's docker-run flow, or by a previous compose run with
different settings). It adopts the volume and uses it normally.

### `error: required variable GITLAB_TOKEN is missing a value`

You're running `docker compose up` without a `GITLAB_TOKEN` in `.env`.
This is intentional — the `${GITLAB_TOKEN:?...}` enforcement prevents
starting the api with an empty token. See the cold-start steps in
section 0.

### `/mcp` in Claude Code doesn't show `gitlab-yearly-report`

Claude Code only reads `.mcp.json` from the directory you launched
`claude` in. Either restart `claude` from this repo's directory, or
add the same server entry to `~/.claude.json` under top-level
`mcpServers` (see README's MCP section for the JSON).

---

## Resuming the playground

```bash
docker compose up -d                                   # both services come back healthy
curl -fsS http://localhost:8080/health && echo " OK"
```

If the PAT in `.env` ever expires, mint a fresh one:

```bash
./scripts/bootstrap-playground.sh
# replace the GITLAB_TOKEN= line in .env, then restart api
docker compose up -d --force-recreate api
```
