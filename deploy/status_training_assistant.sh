#!/usr/bin/env bash
set -euo pipefail

UID_NUM="$(id -u)"
API_LABEL="com.training.api"
WEB_LABEL="com.training.web"

status_probe() {
  local url="$1"
  local attempts="${2:-3}"
  local code="000"
  local time_total="0.000"
  local out=""

  for ((i=1; i<=attempts; i++)); do
    out="$(curl -sS -m 6 -o /dev/null -w '%{http_code} %{time_total}' "$url" || echo '000 6.000')"
    code="${out%% *}"
    time_total="${out##* }"
    if [[ "$code" == "200" ]]; then
      break
    fi
    sleep 1
  done

  printf '%s (%ss)' "$code" "$time_total"
}

printf '[status] launchctl\n'
launchctl list | rg 'com\.training\.(api|web)' || true

printf '\n[status] launchctl detail\n'
launchctl print "gui/$UID_NUM/$API_LABEL" 2>/dev/null | rg 'state =|pid =|last exit code' || true
launchctl print "gui/$UID_NUM/$WEB_LABEL" 2>/dev/null | rg 'state =|pid =|last exit code' || true

printf '\n[status] listeners\n'
lsof -nP -iTCP:8000 -sTCP:LISTEN || true
lsof -nP -iTCP:4100 -sTCP:LISTEN || true

printf '\n[status] health checks\n'
printf '8000 /health -> %s\n' "$(status_probe 'http://127.0.0.1:8000/health')"
printf '8000 /health/ready -> %s\n' "$(status_probe 'http://127.0.0.1:8000/health/ready')"
printf '8000 /api/v1/dashboard/today -> %s\n' "$(status_probe 'http://127.0.0.1:8000/api/v1/dashboard/today')"
printf '8000 /api/v1/dashboard/weekly -> %s\n' "$(status_probe 'http://127.0.0.1:8000/api/v1/dashboard/weekly')"
printf '4100 / -> %s\n' "$(status_probe 'http://127.0.0.1:4100/')"
printf '4100 /api/v1/dashboard/today -> %s\n' "$(status_probe 'http://127.0.0.1:4100/api/v1/dashboard/today')"
printf '4100 /api/v1/dashboard/weekly -> %s\n' "$(status_probe 'http://127.0.0.1:4100/api/v1/dashboard/weekly')"
