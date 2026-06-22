#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/kbqa}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-develop}"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
BACKEND_SERVICE="${BACKEND_SERVICE:-kbqa-backend}"
NGINX_SERVICE="${NGINX_SERVICE:-nginx}"
WEB_ROOT="${WEB_ROOT:-/var/www/kbqa}"
FRONTEND_DIR="${FRONTEND_DIR:-$APP_DIR/frontend}"

log() {
  printf '[deploy] %s\n' "$*"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf '[deploy] missing required command: %s\n' "$1" >&2
    exit 1
  fi
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts="${3:-30}"
  local delay="${4:-2}"

  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS --max-time 10 "$url" >/dev/null; then
      log "$label is reachable"
      return 0
    fi
    sleep "$delay"
  done

  printf '[deploy] %s did not become reachable: %s\n' "$label" "$url" >&2
  return 1
}

require_command git
require_command curl
require_command npm
require_command sudo
require_command "$PYTHON_BIN"

if [ ! -d "$APP_DIR/.git" ]; then
  printf '[deploy] app directory is not a git repository: %s\n' "$APP_DIR" >&2
  exit 1
fi

cd "$APP_DIR"

log "syncing $DEPLOY_BRANCH from origin"
git fetch origin "$DEPLOY_BRANCH"
git checkout -B "$DEPLOY_BRANCH" "origin/$DEPLOY_BRANCH"
git reset --hard "origin/$DEPLOY_BRANCH"

log "preparing Python environment"
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$APP_DIR/.venv"
fi

"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -e "$APP_DIR"

log "building frontend"
cd "$FRONTEND_DIR"
if [ -f package-lock.json ]; then
  npm ci
else
  npm install
fi
npm run build

log "publishing frontend to $WEB_ROOT"
sudo mkdir -p "$WEB_ROOT"
sudo find "$WEB_ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
sudo cp -a "$FRONTEND_DIR/dist/." "$WEB_ROOT/"
sudo chown -R www-data:www-data "$WEB_ROOT"

log "restarting backend service"
sudo systemctl restart "$BACKEND_SERVICE"

log "reloading nginx"
sudo systemctl reload "$NGINX_SERVICE" || sudo systemctl restart "$NGINX_SERVICE"

wait_for_url "http://127.0.0.1:8000/" "backend"
wait_for_url "http://127.0.0.1/" "frontend"

log "deployment finished"
