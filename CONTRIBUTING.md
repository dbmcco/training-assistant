# Contributing

## Development Setup

1. Follow the root `README.md` quick start.
2. Use `api/.env.example` as your baseline env file.
3. Run changes locally before opening a PR.

## Validation

- API smoke tests:

```bash
cd api
uv run pytest -q tests/test_health.py tests/test_dashboard_routes.py::test_dashboard_refresh
```

- Web build:

```bash
cd web
npm run build
```

Run broader API tests when your change affects DB-backed behavior:

```bash
cd api
uv run pytest -q
```

## Pull Requests

- Keep PRs scoped and explain behavior changes.
- Include screenshots for UI changes.
- Mention any DB migration or Garmin-sync dependency in the PR description.
