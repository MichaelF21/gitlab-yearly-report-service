# Testing guide

A walkthrough for verifying the service against a live GitLab instance,
covering every functional and error-mapping requirement from the
assignment brief.

The playground is already running on this machine. If you stopped it,
see [Resuming the playground](#resuming-the-playground) at the end.

## What's running

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

Drive the MCP server over stdio and confirm both required tools are present:

```bash
{ printf '%s\n%s\n%s\n' \
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
    '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}' \
    '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
  sleep 2
} | docker run --rm -i \
    --add-host host.docker.internal:host-gateway \
    -e GITLAB_URL=http://host.docker.internal:8929 \
    -e GITLAB_TOKEN=glpat-_KoddDtFd4HSybNhcVdGZm86MQp1OjEH.01.0w0t1zvre \
    gitlab-yearly-report-service:dev gitlab-report-mcp 2>/dev/null \
  | python -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line: continue
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

For interactive MCP exploration:

```bash
npx @modelcontextprotocol/inspector \
  docker run --rm -i \
  --add-host host.docker.internal:host-gateway \
  -e GITLAB_URL=http://host.docker.internal:8929 \
  -e GITLAB_TOKEN=glpat-_KoddDtFd4HSybNhcVdGZm86MQp1OjEH.01.0w0t1zvre \
  gitlab-yearly-report-service:dev gitlab-report-mcp
```

Then open the URL the inspector prints. Click each tool, set
`year=2026`, optionally a `project_id_or_path`, and `Call`. Same numbers
you saw via the HTTP API should come back.

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
