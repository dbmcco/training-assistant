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
  - `http://127.0.0.1:8001/health`
  - `http://127.0.0.1:8001/health/ready` (DB + warmup)
  - `http://127.0.0.1:8001/api/v1/dashboard/today`
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

## Tailnet access

The durable Tailnet URL is:

`https://braydons-macbook-pro.tail277a09.ts.net:3572/`

Tailscale Serve keeps port `3572` on the Tailnet mapped to the persistent web
service on `127.0.0.1:4100`. If the mapping is lost after a rebuild, restore it
with:

```bash
tailscale serve --https=3572 --bg 4100
```

Verify the mapping with `tailscale serve status`. The Training Assistant API
remains behind the web proxy on local port `8001`.
