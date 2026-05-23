#!/usr/bin/env bash
#
# Populate the local GitLab playground with a reproducible test corpus
# that the assertions in TESTING.md depend on. Idempotent — re-running
# is safe (existing projects/issues/MRs are skipped, not duplicated).
#
# Corpus:
#   playground/issues-mrs-test  (public)  — 5 issues, 3 MRs
#   playground/secret           (private) — 2 issues, 1 MR
#   Instance totals: 7 issues, 4 MRs
#
# Usage:
#   docker compose up -d gitlab
#   ./scripts/bootstrap-playground.sh     # mint a PAT, save it in .env
#   ./scripts/bootstrap-test-data.sh      # ← creates the corpus
#
# All issues and MRs are timestamped at the moment of creation; query
# them with year=<current calendar year>.

set -euo pipefail

GITLAB_URL="${GITLAB_URL_HOST:-http://localhost:8929}"
PAT="${PAT:-}"

# Read PAT from .env if not provided.
if [ -z "$PAT" ] && [ -f .env ]; then
    PAT="$(grep -E '^GITLAB_TOKEN=' .env | head -1 | cut -d= -f2-)"
fi

if [ -z "$PAT" ] || [ "${PAT#glpat-}" = "$PAT" ]; then
    echo "ERROR: No PAT available. Either set PAT=glpat-... in the env, or" >&2
    echo "       put GITLAB_TOKEN=glpat-... into .env (run bootstrap-playground.sh)." >&2
    exit 2
fi

H="PRIVATE-TOKEN: $PAT"
BASE="$GITLAB_URL/api/v4"

log() { printf '%s\n' "$*" >&2; }
api() { curl -fsS -X "$1" -H "$H" "$BASE$2" "${@:3}"; }
api_quiet() { curl -sS -X "$1" -H "$H" "$BASE$2" "${@:3}" -o /dev/null -w '%{http_code}'; }

# get_or_create_group <path>  -> echoes group id
get_or_create_group() {
    local path="$1"
    local existing
    existing=$(curl -fsS -H "$H" "$BASE/groups?search=$path" | python -c "
import sys,json
for g in json.load(sys.stdin):
    if g['full_path'] == '$path':
        print(g['id']); break
")
    if [ -n "$existing" ]; then
        log "  group '$path' already exists (id=$existing)"
        echo "$existing"
        return
    fi
    log "  creating group '$path'..."
    curl -fsS -X POST -H "$H" "$BASE/groups" \
        -d "name=$path" -d "path=$path" -d 'visibility=public' \
        | python -c "import sys,json; print(json.load(sys.stdin)['id'])"
}

# get_or_create_project <namespace_id> <path> <visibility>  -> echoes project id
get_or_create_project() {
    local ns="$1" path="$2" vis="$3"
    local existing
    existing=$(curl -fsS -H "$H" "$BASE/projects?search=$path" | python -c "
import sys,json
for p in json.load(sys.stdin):
    if p['path'] == '$path':
        print(p['id']); break
")
    if [ -n "$existing" ]; then
        log "  project '$path' already exists (id=$existing)"
        echo "$existing"
        return
    fi
    log "  creating project '$path' (visibility=$vis)..."
    curl -fsS -X POST -H "$H" "$BASE/projects" \
        -d "name=$path" -d "path=$path" \
        -d "namespace_id=$ns" -d "visibility=$vis" \
        -d 'initialize_with_readme=true' -d 'default_branch=main' \
        | python -c "import sys,json; print(json.load(sys.stdin)['id'])"
}

# create_issues_if_missing <project_id> <count> <title_prefix>
create_issues_if_missing() {
    local pid="$1" count="$2" prefix="$3"
    local existing
    existing=$(curl -fsS -H "$H" "$BASE/projects/$pid/issues?per_page=100" \
        | python -c "import sys,json; print(len(json.load(sys.stdin)))")
    if [ "$existing" -ge "$count" ]; then
        log "  project $pid already has $existing issues (target $count) — skipping"
        return
    fi
    log "  creating $((count - existing)) issues in project $pid..."
    for i in $(seq $((existing + 1)) $count); do
        curl -fsS -X POST -H "$H" "$BASE/projects/$pid/issues" \
            -d "title=$prefix $i" -d 'description=test fixture' > /dev/null
    done
}

# create_mrs_if_missing <project_id> <count> <branch_prefix>
create_mrs_if_missing() {
    local pid="$1" count="$2" prefix="$3"
    local existing
    existing=$(curl -fsS -H "$H" "$BASE/projects/$pid/merge_requests?per_page=100" \
        | python -c "import sys,json; print(len(json.load(sys.stdin)))")
    if [ "$existing" -ge "$count" ]; then
        log "  project $pid already has $existing MRs (target $count) — skipping"
        return
    fi
    log "  creating $((count - existing)) MRs in project $pid..."
    for i in $(seq $((existing + 1)) $count); do
        local branch="${prefix}-${i}"
        curl -fsS -X POST -H "$H" "$BASE/projects/$pid/repository/branches?branch=$branch&ref=main" > /dev/null
        curl -fsS -X POST -H "$H" "$BASE/projects/$pid/repository/files/file-$i.txt" \
            -d "branch=$branch" -d "content=fixture $i" -d "commit_message=Add file $i" > /dev/null
        curl -fsS -X POST -H "$H" "$BASE/projects/$pid/merge_requests" \
            -d "source_branch=$branch" -d 'target_branch=main' -d "title=MR $i" > /dev/null
    done
}

log "Using GitLab at $GITLAB_URL"
log ""
log "1/4 Group"
group_id=$(get_or_create_group playground)

log "2/4 Project A (public)"
proj_a=$(get_or_create_project "$group_id" issues-mrs-test public)

log "3/4 Project B (private)"
proj_b=$(get_or_create_project "$group_id" secret private)

log "4/4 Issues and MRs"
create_issues_if_missing "$proj_a" 5 "Issue in A"
create_issues_if_missing "$proj_b" 2 "Issue in B"
create_mrs_if_missing    "$proj_a" 3 "feature/foo"
create_mrs_if_missing    "$proj_b" 1 "feature/bar"

log ""
log "Done. Expected counts (use current calendar year as year query):"
log "  /issues?year=<YYYY>                                           -> 7"
log "  /issues?year=<YYYY>&project=$proj_a                                       -> 5"
log "  /issues?year=<YYYY>&project=playground%2Fissues-mrs-test       -> 5"
log "  /merge-requests?year=<YYYY>                                   -> 4"
log "  /merge-requests?year=<YYYY>&project=$proj_a                                -> 3"
log "  /merge-requests?year=<YYYY>&project=playground%2Fissues-mrs-test          -> 3"
