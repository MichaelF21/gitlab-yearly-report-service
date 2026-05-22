#!/usr/bin/env bash
#
# Bootstrap the local GitLab playground:
#   1. Wait until the GitLab API is responding
#   2. Mint a PAT for root with `api` scope via gitlab-rails runner
#   3. Print a GITLAB_TOKEN=... line ready to paste into .env
#
# This is the one piece of the playground that can't be expressed
# declaratively in docker-compose.yml — GitLab tokens have to be created
# *inside* a running GitLab process. Everything else is in compose.
#
# Usage:
#   docker compose up -d gitlab
#   ./scripts/bootstrap-playground.sh

set -euo pipefail

GITLAB_URL="${GITLAB_URL_HOST:-http://localhost:8929}"
CONTAINER="${GITLAB_CONTAINER:-gitlab}"
TOKEN_NAME="${TOKEN_NAME:-playground-$(date +%s)}"
TOKEN_SCOPE="${TOKEN_SCOPE:-api}"
TOKEN_TTL_DAYS="${TOKEN_TTL_DAYS:-365}"

log() { printf '%s\n' "$*" >&2; }

# 1. Wait for the API to be responsive. We check for 200 or 401 — both
#    mean the API is up; 401 just means we haven't authenticated.
log "Waiting for GitLab at $GITLAB_URL/api/v4/version ..."
for i in $(seq 1 120); do
    code=$(curl -s -o /dev/null -w '%{http_code}' "$GITLAB_URL/api/v4/version" || true)
    case "$code" in
        200|401)
            log "GitLab API ready after ${i}x5s (HTTP $code)"
            break
            ;;
    esac
    if [ "$i" = "120" ]; then
        log "ERROR: GitLab never became ready after 10 minutes."
        log "Check 'docker compose logs gitlab' for details."
        exit 1
    fi
    sleep 5
done

# 2. Mint a PAT via gitlab-rails runner. This is the official non-UI path
#    documented by GitLab for bootstrapping; it bypasses the web sign-in.
log "Minting PAT (name=$TOKEN_NAME, scope=$TOKEN_SCOPE, ttl=${TOKEN_TTL_DAYS}d) ..."
token=$(docker exec "$CONTAINER" gitlab-rails runner "
user = User.find_by_username('root')
pat = user.personal_access_tokens.create(
  name: '${TOKEN_NAME}',
  scopes: [:${TOKEN_SCOPE}],
  expires_at: ${TOKEN_TTL_DAYS}.days.from_now
)
pat.save!
puts pat.token
" 2>/dev/null | tail -1)

if [ -z "$token" ] || [ "${token#glpat-}" = "$token" ]; then
    log "ERROR: rails runner returned an unexpected value: '$token'"
    log "Run 'docker exec $CONTAINER gitlab-rails runner ...' manually to debug."
    exit 1
fi

# 3. Emit the env line on stdout so the user can pipe/append it to .env.
log "PAT minted."
log ""
log "Append this to .env (or copy it manually):"
log ""
echo "GITLAB_TOKEN=$token"
log ""
log "Then run: docker compose up -d"
