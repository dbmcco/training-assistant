# Service Ops

Scripts for managing the local Training Assistant services.

## Restart (hardened)

```bash
./deploy/restart_training_assistant.sh
```

What it does:
- Syncs LaunchAgent plists from `deploy/` to `~/Library/LaunchAgents`
- Restarts `com.training.api` and `com.training.web`
- Waits for:
  - `http://127.0.0.1:8000/health`
  - `http://127.0.0.1:8000/health/ready` (DB + warmup)
  - `http://127.0.0.1:8000/api/v1/dashboard/today`
  - `http://127.0.0.1:4100/`
  - `http://127.0.0.1:4100/api/v1/dashboard/today`
- `http://127.0.0.1:4100/api/v1/dashboard/weekly`
- Uses stability checks (multiple consecutive successful probes)
- If checks fail, it kickstarts services and falls back to direct process start
- Prints service diagnostics and logs

## Status

```bash
./deploy/status_training_assistant.sh
```

Shows LaunchAgent state/details, listening ports, and key HTTP checks
with per-endpoint response time.
