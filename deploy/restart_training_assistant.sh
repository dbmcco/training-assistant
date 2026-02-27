#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="$ROOT_DIR/deploy"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
CURL_TIMEOUT=6
LOCK_DIR="/tmp/training-assistant-restart.lock"

API_LABEL="com.training.api"
WEB_LABEL="com.training.web"

API_PLIST_SRC="$DEPLOY_DIR/$API_LABEL.plist"
WEB_PLIST_SRC="$DEPLOY_DIR/$WEB_LABEL.plist"
API_PLIST_DST="$LAUNCH_AGENTS_DIR/$API_LABEL.plist"
WEB_PLIST_DST="$LAUNCH_AGENTS_DIR/$WEB_LABEL.plist"

log() {
  printf '[restart] %s\n' "$*"
}

quiet() {
  "$@" >/dev/null 2>&1
}

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "another restart is already running (lock: $LOCK_DIR)"
  exit 1
fi
trap 'rmdir "$LOCK_DIR" >/dev/null 2>&1 || true' EXIT

kickstart_label() {
  local label="$1"
  quiet launchctl kickstart -k "gui/$UID_NUM/$label" || quiet launchctl start "$label" || true
}

start_api_fallback() {
  log "starting API fallback process"
  quiet pkill -f '/training-assistant/api/.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 2' || true
  (
    cd "$ROOT_DIR/api"
    nohup ./.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 2 >/tmp/training-api.log 2>/tmp/training-api.err &
  )
}

start_web_fallback() {
  log "starting web fallback process"
  quiet pkill -f '/training-assistant/web/node_modules/.bin/vite --host 0.0.0.0 --port 4100 --strictPort' || true
  (
    cd "$ROOT_DIR/web"
    nohup ./node_modules/.bin/vite --host 0.0.0.0 --port 4100 --strictPort >/tmp/training-web.log 2>/tmp/training-web.err &
  )
}

http_ok() {
  local url="$1"
  local code
  code="$(curl -sS -m "$CURL_TIMEOUT" -o /dev/null -w '%{http_code}' "$url" || true)"
  [[ "$code" == "200" ]]
}

wait_http_ok() {
  local url="$1"
  local timeout_secs="$2"
  local elapsed=0

  while (( elapsed < timeout_secs )); do
    if http_ok "$url"; then
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  return 1
}

wait_http_stable() {
  local url="$1"
  local timeout_secs="$2"
  local required_successes="$3"
  local elapsed=0
  local streak=0

  while (( elapsed < timeout_secs )); do
    if http_ok "$url"; then
      streak=$((streak + 1))
      if (( streak >= required_successes )); then
        return 0
      fi
    else
      streak=0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  return 1
}

bootout_label() {
  local label="$1"
  local plist_path="$2"

  quiet launchctl bootout "gui/$UID_NUM/$label" || true
  quiet launchctl unload "$plist_path" || true
}

stop_orphans() {
  quiet pkill -f '/training-assistant/api/.venv/bin/uvicorn src.main:app' || true
  quiet pkill -f '/training-assistant/web/node_modules/.bin/vite --host 0.0.0.0 --port 4100 --strictPort' || true
}

load_label() {
  local label="$1"
  local plist_path="$2"

  # Prefer bootstrap; fallback to load for shells where bootstrap is restricted.
  if ! quiet launchctl bootstrap "gui/$UID_NUM" "$plist_path"; then
    quiet launchctl load -w "$plist_path" || true
  fi

  kickstart_label "$label"
}

show_diag() {
  log "launchctl status"
  launchctl list | rg 'com\\.training\\.(api|web)' || true
  log "listening ports"
  lsof -nP -iTCP:8000 -sTCP:LISTEN || true
  lsof -nP -iTCP:4100 -sTCP:LISTEN || true
  log "recent logs"
  tail -n 40 /tmp/training-api.err || true
  tail -n 40 /tmp/training-web.err || true
}

log "syncing launch agent plists"
mkdir -p "$LAUNCH_AGENTS_DIR"
cp "$API_PLIST_SRC" "$API_PLIST_DST"
cp "$WEB_PLIST_SRC" "$WEB_PLIST_DST"
chmod 644 "$API_PLIST_DST" "$WEB_PLIST_DST"

log "restarting launch agents"
bootout_label "$API_LABEL" "$API_PLIST_DST"
bootout_label "$WEB_LABEL" "$WEB_PLIST_DST"
stop_orphans
sleep 1
load_label "$API_LABEL" "$API_PLIST_DST"
load_label "$WEB_LABEL" "$WEB_PLIST_DST"

log "waiting for API liveness"
if ! wait_http_ok "http://127.0.0.1:8000/health" 40; then
  log "API liveness failed first check, kickstarting once more"
  kickstart_label "$API_LABEL"
  sleep 2
  if ! wait_http_ok "http://127.0.0.1:8000/health" 40; then
    start_api_fallback
    sleep 2
    if ! wait_http_ok "http://127.0.0.1:8000/health" 30; then
      log "API failed liveness check"
      show_diag
      exit 1
    fi
  fi
fi

log "waiting for API readiness (DB + warmup)"
if ! wait_http_stable "http://127.0.0.1:8000/health/ready" 60 2; then
  log "API readiness failed first check, kickstarting once more"
  kickstart_label "$API_LABEL"
  sleep 2
  if ! wait_http_stable "http://127.0.0.1:8000/health/ready" 60 2; then
    start_api_fallback
    sleep 2
    if ! wait_http_stable "http://127.0.0.1:8000/health/ready" 45 2; then
      log "API readiness still failing"
      show_diag
      exit 1
    fi
  fi
fi

log "warming API data routes"
curl -sS -m "$CURL_TIMEOUT" -o /dev/null "http://127.0.0.1:8000/api/v1/dashboard/today" || true
curl -sS -m "$CURL_TIMEOUT" -o /dev/null "http://127.0.0.1:8000/api/v1/dashboard/weekly" || true
curl -sS -m "$CURL_TIMEOUT" -o /dev/null "http://127.0.0.1:8000/api/v1/dashboard/trends?metric=readiness" || true

log "waiting for API dashboard payload"
if ! wait_http_stable "http://127.0.0.1:8000/api/v1/dashboard/today" 60 2; then
  log "API dashboard endpoint still unstable after warmup"
  show_diag
  exit 1
fi

log "waiting for web root"
if ! wait_http_stable "http://127.0.0.1:4100/" 40 2; then
  log "Web root failed first check, kickstarting once more"
  kickstart_label "$WEB_LABEL"
  sleep 2
  if ! wait_http_stable "http://127.0.0.1:4100/" 40 2; then
    start_web_fallback
    sleep 2
    if ! wait_http_stable "http://127.0.0.1:4100/" 30 2; then
      log "Web failed root check"
      show_diag
      exit 1
    fi
  fi
fi

log "waiting for web proxy -> API"
if ! wait_http_stable "http://127.0.0.1:4100/api/v1/dashboard/today" 45 2; then
  log "Proxy check failed on first pass, kickstarting web once"
  kickstart_label "$WEB_LABEL"
  sleep 2
  if ! wait_http_stable "http://127.0.0.1:4100/api/v1/dashboard/today" 45 2; then
    log "Web proxy still failing"
    show_diag
    exit 1
  fi
fi

log "waiting for web proxy weekly payload"
if ! wait_http_stable "http://127.0.0.1:4100/api/v1/dashboard/weekly" 45 2; then
  log "Web proxy weekly endpoint still failing"
  show_diag
  exit 1
fi

log "services healthy"
show_diag
