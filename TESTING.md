# Testing guide

A walkthrough for verifying the service against a live GitLab instance,
covering every functional and error-mapping requirement from the
assignment brief.

## 0. Environment setup

The minimum setup depends on what state you're in.

### Prerequisites (per machine, one-time)

| Tool | Purpose | Install |
|------|---------|---------|
| Docker Desktop (running) | Hosts the gitlab + api containers | https://www.docker.com/products/docker-desktop |
| Git | Clone this repo | `winget install Git.Git` |
| curl + Python | Run the test commands below | Come bundled with Git Bash on Windows |
| Node.js (optional) | MCP Inspector — section 4.3 | `winget install OpenJS.NodeJS` |

### Cold start (no playground yet)

`docker compose up -d` **alone is not enough** the first time. Compose
enforces that `GITLAB_TOKEN` is set in `.env` before starting the api
service, and a token can only be minted inside a running GitLab. Five
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

# Paste the GITLAB_TOKEN= line over the empty one in .env, then:
docker compose up -d
```

After that, `docker ps` should show both containers as `(healthy)`.

### Resume (volumes preserved)

If you only ran `docker compose down` (no `-v` flag), then **one
command** is enough — the GitLab data and the PAT in `.env` are still
valid:

```bash
docker compose up -d
```

### Full reset

```bash
docker compose down -v          # nukes the gitlab-* volumes (~7GB)
rm .env                          # next bootstrap will need a fresh token
```

Then follow the cold-start steps again.

### Configure MCP clients (only if you want to test sections 4.3-4.4)

| Client | Action |
|--------|--------|
| MCP Inspector | Just needs Node.js installed; the `npx` command in §4.3 handles everything else. |
| Claude Code (project-scope) | The committed [`.mcp.json`](.mcp.json) auto-registers when you launch `claude` from this directory. Set `GITLAB_TOKEN` in your shell first. |
| Claude Code (user-scope, works anywhere) | Add an entry to `~/.claude.json` under top-level `mcpServers`. See README's MCP section. |
| Claude Desktop | Edit `%APPDATA%\Claude\claude_desktop_config.json` per the README's MCP section. Restart Claude Desktop. |

---

## What's running once setup is done

| Service              | URL                     | Purpose                             |
|----------------------|-------------------------|-------------------------------------|
| GitLab 18.10.5 EE    | http://localhost:8929   | Test data lives here                |
| Report service       | http://localhost:8080   | The thing under test                |
| Swagger / OpenAPI    | http://localhost:8080/docs | Interactive request builder      |

GitLab web UI: open http://localhost:8929 in a browser. Login is `root`
plus the initial password (one-liner below).

```bash
docker exec gitlab cat /etc/gitlab/initial_root_password | grep '^Password:'
```

## Test data

| Project (id)               | Visibility | Issues | MRs |
|----------------------------|-----------:|-------:|----:|
| `playground/issues-mrs-test` (1) | public     |      5 |   3 |
| `playground/secret` (2)          | private    |      2 |   1 |
| **Instance totals**              |            |  **7** | **4** |

All issues and MRs were created on 2026-05-21, so they all fall in
`year=2026`. Other years should return zero results.

## Tokens

```bash
# Admin PAT — has 'api' scope. Use this for the normal happy-path tests.
ADMIN_PAT=glpat-_KoddDtFd4HSybNhcVdGZm86MQp1OjEH.01.0w0t1zvre

# Limited PAT — only 'read_repository' scope. Use this to trigger a 403.
LIMITED_PAT=glpat-6ZPWZnXih51qeDg5tz9DSG86MQp1OjEH.01.0w05rtrut
```

The report container is already running with `ADMIN_PAT`. To test 403 you
swap to `LIMITED_PAT` (one command, shown in the 403 row below).

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

### 2.1 — Issues, entire instance

```bash
curl -s "http://localhost:8080/issues?year=2026" | python -c "import sys,json; d=json.load(sys.stdin); print('count =', len(d))"
```
**Expected:** `count = 7`

### 2.2 — Issues, project by numeric ID

```bash
curl -s "http://localhost:8080/issues?year=2026&project=1" | python -c "import sys,json; d=json.load(sys.stdin); print('count =', len(d))"
curl -s "http://localhost:8080/issues?year=2026&project=2" | python -c "import sys,json; d=json.load(sys.stdin); print('count =', len(d))"
```
**Expected:** `count = 5` and `count = 2`

### 2.3 — Issues, project by URL-encoded path

```bash
curl -s "http://localhost:8080/issues?year=2026&project=playground%2Fissues-mrs-test" \
  | python -c "import sys,json; d=json.load(sys.stdin); print('count =', len(d))"
```
**Expected:** `count = 5`

### 2.4 — Year boundary — empty year

```bash
curl -s "http://localhost:8080/issues?year=2024" | python -c "import sys,json; print('count =', len(json.load(sys.stdin)))"
```
**Expected:** `count = 0`

### 2.5 — Same four rows for `/merge-requests`

```bash
# Instance
curl -s "http://localhost:8080/merge-requests?year=2026" \
  | python -c "import sys,json; print('MRs instance:', len(json.load(sys.stdin)))"
# By ID
curl -s "http://localhost:8080/merge-requests?year=2026&project=1" \
  | python -c "import sys,json; print('MRs project 1:', len(json.load(sys.stdin)))"
curl -s "http://localhost:8080/merge-requests?year=2026&project=2" \
  | python -c "import sys,json; print('MRs project 2:', len(json.load(sys.stdin)))"
# By encoded path
curl -s "http://localhost:8080/merge-requests?year=2026&project=playground%2Fissues-mrs-test" \
  | python -c "import sys,json; print('MRs by path:', len(json.load(sys.stdin)))"
# Year boundary
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

### 2.6 — Response shape inspection

```bash
curl -s "http://localhost:8080/issues?year=2026&project=1" | python -m json.tool | head -20
```
**Expected:** Trimmed shape — only `id`, `iid`, `project_id`, `title`,
`state`, `created_at`, `updated_at`, `closed_at`, `author`, `labels`,
`web_url`. No `description`, no `_links`, no GitLab internals.

```bash
curl -s "http://localhost:8080/merge-requests?year=2026&project=1" | python -m json.tool | head -25
```
**Expected:** MR shape — adds `draft`, `merged_at`, `source_branch`,
`target_branch` to the above.

---

## 3. Error mapping rows from the brief

| Brief row | Expected | Command |
|-----------|---------:|---------|
| Missing `year` | 400 | `curl -s -w '%{http_code}\n' -o /dev/null http://localhost:8080/issues` |
| Non-integer `year` | 400 | `curl -s -w '%{http_code}\n' -o /dev/null "http://localhost:8080/issues?year=bad"` |
| Out-of-range `year` | 400 | `curl -s -w '%{http_code}\n' -o /dev/null "http://localhost:8080/issues?year=1500"` |
| GitLab project not found | 404 | `curl -s -w '%{http_code}\n' -o /dev/null "http://localhost:8080/issues?year=2026&project=does%2Fnot-exist"` |

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
**Expected:** `400 400 400 404` (each on its own line)

### 3.1 — 401 (GitLab authentication failed)

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
**Expected:** `status: 401` with an error body explaining "GitLab returned 401".

### 3.2 — 403 (GitLab permission denied)

```bash
# Swap the report container's token to the limited-scope PAT
docker rm -f report > /dev/null
docker run -d --rm --name report -p 8080:8080 \
  --add-host host.docker.internal:host-gateway \
  -e GITLAB_URL=http://host.docker.internal:8929 \
  -e GITLAB_TOKEN=glpat-6ZPWZnXih51qeDg5tz9DSG86MQp1OjEH.01.0w05rtrut \
  gitlab-yearly-report-service:dev > /dev/null
sleep 3

curl -s -w '\nstatus: %{http_code}\n' "http://localhost:8080/issues?year=2026"
```
**Expected:** `status: 403`. The body includes GitLab's `insufficient_scope` error.

**Restore the admin token** before continuing with other tests:

```bash
docker rm -f report > /dev/null
docker run -d --rm --name report -p 8080:8080 \
  --add-host host.docker.internal:host-gateway \
  -e GITLAB_URL=http://host.docker.internal:8929 \
  -e GITLAB_TOKEN=glpat-_KoddDtFd4HSybNhcVdGZm86MQp1OjEH.01.0w0t1zvre \
  gitlab-yearly-report-service:dev > /dev/null
sleep 3
curl -fsS http://localhost:8080/health
```

### 3.3 — Missing `GITLAB_TOKEN` (clear startup failure)

```bash
docker run --rm -e GITLAB_URL=http://host.docker.internal:8929 \
  gitlab-yearly-report-service:dev
echo "exit code: $?"
```
**Expected:** A `FATAL: ...` message naming `GITLAB_TOKEN` as the missing
variable, and `exit code: 2`.

---

## 4. Bonus — MCP server

The MCP server is the bonus deliverable. Five practical ways to test it,
ordered from cheapest smoke check to fullest end-to-end.

### 4.1 — Stdio handshake (protocol smoke)

Confirms the server speaks JSON-RPC 2.0 and exposes both required tools.

```bash
{ printf '%s\n%s\n%s\n' \
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
    '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}' \
    '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
  sleep 2
} | docker run --rm -i \
    --add-host host.docker.internal:host-gateway \
    -e GITLAB_URL=http://host.docker.internal:8929 \
    -e GITLAB_TOKEN="$(grep ^GITLAB_TOKEN .env | cut -d= -f2)" \
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

Goes the rest of the way: actually invoke each tool and confirm it
returns the same data the HTTP API would. The list is in
`result.structuredContent.result` (FastMCP also mirrors each element
into `result.content[]` as separate TextContent blocks).

Save the responses to a file, then parse:

```bash
PAT="$(grep ^GITLAB_TOKEN .env | cut -d= -f2)"
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
    -e GITLAB_TOKEN="$PAT" \
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
        print("get_issues_by_year(2026, 'playground/issues-mrs-test')")
        print("  ->", len(items), "issues")
    elif rid == 3:
        items = obj["result"]["structuredContent"]["result"]
        print("get_merge_requests_by_year(2026)")
        print("  ->", len(items), "MRs")
PY
```
**Expected** (matches the HTTP API counts):
```
get_issues_by_year(2026, 'playground/issues-mrs-test')
  -> 5 issues
get_merge_requests_by_year(2026)
  -> 4 MRs
```

### 4.3 — MCP Inspector (interactive browser UI)

The official Anthropic tool. Lists tools, lets you fill in arguments
through a form, displays the JSON response inline. No setup beyond `npx`.

```bash
npx @modelcontextprotocol/inspector \
  docker run --rm -i \
  --add-host host.docker.internal:host-gateway \
  -e GITLAB_URL=http://host.docker.internal:8929 \
  -e GITLAB_TOKEN="$(grep ^GITLAB_TOKEN .env | cut -d= -f2)" \
  gitlab-yearly-report-service:dev gitlab-report-mcp
```

The inspector prints a `http://localhost:<port>/?MCP_PROXY_AUTH_TOKEN=...`
URL — open that. Click "Tools" in the left sidebar, then either tool, fill
in `year` (and optionally `project_id_or_path`), and click "Run Tool".
Same data shape as section 4.2 comes back, formatted nicely.

### 4.4 — Claude Desktop / Claude Code (real end-to-end)

The point of an MCP server is to let an AI model use it. Wire it up and
ask Claude natural-language questions; verify it picks the right tool
with the right arguments.

**Claude Desktop**: edit
`%APPDATA%\Claude\claude_desktop_config.json` (Windows) and add:

```json
{
  "mcpServers": {
    "gitlab-yearly-report": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--add-host", "host.docker.internal:host-gateway",
        "-e", "GITLAB_URL=http://host.docker.internal:8929",
        "-e", "GITLAB_TOKEN",
        "gitlab-yearly-report-service:dev",
        "gitlab-report-mcp"
      ],
      "env": {
        "GITLAB_TOKEN": "glpat-..."
      }
    }
  }
}
```

Restart Claude Desktop, then in a new chat ask things like:

- *"List the issues created in 2026 in `playground/issues-mrs-test`."*
- *"How many merge requests were opened across all projects in 2026?"*
- *"What was the title of the third MR in project 1 in 2026?"*

Watch for Claude announcing the tool call (it'll show "using
`get_issues_by_year`..." with the arguments) and verify the answer
matches the data you can see in the GitLab UI.

**Claude Code**: same JSON, but in
`%APPDATA%\Claude Code\settings.json` under `"mcpServers"`. Or use the
`/mcp` slash command to manage MCP servers without editing the file
directly.

### 4.5 — Python MCP client (programmatic, for CI regression)

If you want MCP coverage in CI alongside the existing pytest suite:

```python
# tests/test_mcp.py — sketch, not yet checked in
import asyncio, json
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
            items = json.loads(result.content[0].text) if isinstance(result.content[0].text, str) else result.structuredContent["result"]
            assert len(items) == 5
```

Not currently checked into `tests/` — the existing pytest suite covers
the domain layer (`reports.py`) that the MCP server thinly wraps, so MCP
coverage would be largely redundant. Add this if you ever change the MCP
adapter beyond the current thin wrapper.

---

## 5. Test data — observe in the GitLab UI

Browse to http://localhost:8929 and login as `root`. The two
playground projects are at:

- http://localhost:8929/playground/issues-mrs-test
- http://localhost:8929/playground/secret

Add or close issues/MRs through the UI and re-run the count queries
in section 2 — the numbers should update accordingly.

---

## 6. Stop everything when you're done

```bash
docker stop report gitlab
```

Volumes (`gitlab-config`, `gitlab-data`, `gitlab-logs`) and the GitLab
image are preserved so the next start is fast.

To wipe everything (frees ~7GB):

```bash
docker rm gitlab report
docker volume rm gitlab-config gitlab-data gitlab-logs
docker rmi gitlab/gitlab-ee:18.10.5-ee.0
```

---

## Resuming the playground

If both containers have been stopped, the fastest way to bring them back is
via compose (the same `gitlab-config`/`-logs`/`-data` volumes back the
playground regardless of whether you started them via `docker run` or
`docker compose`):

```bash
# Compose path — uses .env for GITLAB_TOKEN
docker compose up -d
# wait until 'docker compose ps' shows both services healthy
curl -fsS http://localhost:8080/health && echo " report OK"
```

Manual path (no compose) — equivalent:

```bash
docker start gitlab
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8929/api/v4/version)
  [ "$code" = "401" ] && echo "GitLab ready" && break
  sleep 5
done

docker run -d --rm --name report -p 8080:8080 \
  --add-host host.docker.internal:host-gateway \
  -e GITLAB_URL=http://host.docker.internal:8929 \
  -e GITLAB_TOKEN=glpat-_KoddDtFd4HSybNhcVdGZm86MQp1OjEH.01.0w0t1zvre \
  gitlab-yearly-report-service:dev

curl -fsS http://localhost:8080/health && echo " report OK"
```

## Starting fresh on a different machine

If you've never run the playground before:

```bash
git clone https://github.com/MichaelF21/gitlab-yearly-report-service
cd gitlab-yearly-report-service
cp .env.example .env

docker compose up -d gitlab           # ~3-5 min cold boot
./scripts/bootstrap-playground.sh     # mints a PAT, prints GITLAB_TOKEN=...

# Paste the GITLAB_TOKEN=... line into .env, then:
docker compose up -d
```

Then come back here and work through sections 1-4 above — note that on a
fresh playground you won't have the bootstrapped issues and MRs yet, so
section 2 will return zero counts until you create some test data via the
GitLab UI or API.

## Regenerating PATs

If the PATs above ever expire (the admin one is 365 days, the limited one
30 days), mint fresh ones with the bootstrap script:

```bash
./scripts/bootstrap-playground.sh
# Or, for the limited-scope variant used in the 403 test:
TOKEN_SCOPE=read_repository TOKEN_TTL_DAYS=30 ./scripts/bootstrap-playground.sh
```
