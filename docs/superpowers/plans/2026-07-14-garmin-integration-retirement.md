# Garmin Integration Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use speedrift with the seeded Workgraph graph. Every task must run its pre-task and post-task drift checks before completion.

**Goal:** Move every runtime Garmin and Peloton responsibility into Training Assistant, cut over safely, and retire the sibling `garmin-connect-sync` repository without changing user-facing behavior or losing data.

**Architecture:** Training Assistant will contain a standalone Garmin integration package and worker command. The FastAPI process will retain lightweight application adapters, while long-running Garmin and Peloton operations remain in a separate Training Assistant-owned process. The migration uses schema verification, shadow comparison, canary writes, scheduler cutover, soak validation, and rollback before the old repository is removed from runtime.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL, Garmin Connect client, Peloton client, pytest, macOS LaunchAgents, `uv`.

## Global Constraints

- The Training Assistant public API and frontend behavior remain backward compatible.
- `PLAN_OWNERSHIP_MODE=assistant` remains authoritative for future workouts.
- No two Garmin writers may run simultaneously.
- Existing Garmin identifiers, completed history, races, plan rows, and assistant plan-entry rows must be preserved.
- The FastAPI request process must not perform long-running Garmin network work synchronously.
- The old `garmin-connect-sync` repository remains available for rollback until soak validation passes.
- No credentials, token files, FIT files, TCX files, GPX files, or personal activity exports may be committed.

---

### Task 1: Freeze the current Garmin contract

**Files:**
- Create: `docs/superpowers/contracts/garmin-sync-contract.md`
- Create: `api/tests/test_garmin_contract.py`
- Modify: `README.md`

**Interfaces:**
- Produces a documented `SyncReport` shape with `status`, `domains`, `counts`, `created_ids`, `updated_ids`, `deleted_ids`, `skipped`, and `failures`.
- Produces a documented `WritebackResult` shape with `status`, `workout_id`, `workout_date`, `discipline`, `deleted_existing_ids`, and `delete_failed_ids`.
- Establishes the compatibility contract for `refresh_garmin_data`, assistant plan generation, approved workout changes, calendar ownership, and Peloton import.

- [ ] **Step 1: Write the contract tests.**

```python

def test_sync_report_has_stable_top_level_fields():
    assert set(make_sync_report().keys()) == {
        "status", "domains", "counts", "created_ids", "updated_ids",
        "deleted_ids", "skipped", "failures",
    }


def test_writeback_result_preserves_existing_success_shape():
    result = make_writeback_result(workout_id="123")
    assert result["status"] == "success"
    assert result["workout_id"] == "123"
    assert "workout_date" in result
    assert "discipline" in result
```

- [ ] **Step 2: Run the focused tests and confirm they fail because the contract helpers do not exist.**

Run: `cd api && uv run pytest -q tests/test_garmin_contract.py`

Expected: collection or assertion failure identifying the missing contract implementation.

- [ ] **Step 3: Document the existing observable behavior.**

Record the current command flags from `garmin-connect-sync/sync.py`, current environment keys from both `.env.example` files, current LaunchAgent cadence, and current API adapter behavior. Do not copy secrets or personal exports.

- [ ] **Step 4: Add contract fixtures and compatibility assertions.**

Implement test-only `make_sync_report()` and `make_writeback_result()` fixtures, then assert that the existing refresh and writeback service tests continue to expose the documented fields.

- [ ] **Step 5: Run the focused tests.**

Run: `cd api && uv run pytest -q tests/test_garmin_contract.py tests/test_garmin_refresh_service.py tests/test_garmin_writeback.py`

Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add docs/superpowers/contracts/garmin-sync-contract.md api/tests/test_garmin_contract.py README.md
git commit -m "test: freeze Garmin integration contracts"
```

---

### Task 2: Add Training Assistant-owned Garmin dependencies and configuration

**Files:**
- Modify: `api/pyproject.toml`
- Modify: `api/.env.example`
- Modify: `api/src/config.py`
- Create: `api/src/integrations/garmin/config.py`
- Create: `api/tests/test_garmin_config.py`

**Interfaces:**
- `GarminIntegrationSettings.from_app_settings() -> GarminIntegrationSettings`.
- Settings include `enabled`, `tokenstore_path`, `days_back`, `calendar_months_ahead`, `timeout_seconds`, `lock_path`, `plan_ownership_mode`, and `peloton_enabled`.
- The configuration must resolve relative paths from the Training Assistant repository, never from `garmin-connect-sync`.

- [ ] **Step 1: Write failing configuration tests.**

```python

def test_garmin_settings_default_to_training_assistant_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_TOKENSTORE_PATH", str(tmp_path / "garmin-tokenstore"))
    settings = GarminIntegrationSettings.from_app_settings()
    assert settings.tokenstore_path == tmp_path / "garmin-tokenstore"
    assert "garmin-connect-sync" not in str(settings.tokenstore_path)


def test_assistant_plan_mode_is_preserved(monkeypatch):
    monkeypatch.setenv("PLAN_OWNERSHIP_MODE", "assistant")
    assert GarminIntegrationSettings.from_app_settings().plan_ownership_mode == "assistant"
```

- [ ] **Step 2: Run the focused tests and confirm failure.**

Run: `cd api && uv run pytest -q tests/test_garmin_config.py`

Expected: FAIL because the internal settings class does not exist.

- [ ] **Step 3: Add dependencies and settings.**

Move the pinned Garmin and Peloton runtime dependencies from `garmin-connect-sync/requirements.txt` into `api/pyproject.toml`. Add explicit Training Assistant configuration keys to `api/.env.example`, including a token-store path, sync lock path, refresh windows, timeouts, and feature toggles. Do not add secret values.

- [ ] **Step 4: Implement `GarminIntegrationSettings`.**

Keep environment parsing in `api/src/integrations/garmin/config.py`; expose only typed values to the integration modules. Preserve `PLAN_OWNERSHIP_MODE=assistant` and reject a configured legacy repository path during the final cutover configuration.

- [ ] **Step 5: Run tests and dependency validation.**

Run: `cd api && uv lock --check && uv run pytest -q tests/test_garmin_config.py`

Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add api/pyproject.toml api/uv.lock api/.env.example api/src/config.py api/src/integrations/garmin/config.py api/tests/test_garmin_config.py
git commit -m "feat: configure Training Assistant-owned Garmin integration"
```

---

### Task 3: Extract the Garmin client and ingestion worker

**Files:**
- Create: `api/src/integrations/garmin/client.py`
- Create: `api/src/integrations/garmin/ingest.py`
- Create: `api/src/integrations/garmin/report.py`
- Create: `api/src/integrations/garmin/locks.py`
- Create: `api/scripts/garmin_sync.py`
- Create: `api/tests/integrations/test_garmin_ingest.py`
- Create: `api/tests/test_garmin_worker.py`

**Interfaces:**
- `GarminClient.connect() -> GarminApiClient` owns token-store authentication.
- `GarminIngestion.sync_activities(days_back: int) -> DomainSyncResult`.
- `GarminIngestion.sync_daily_summary(target_date: date) -> DomainSyncResult`.
- `GarminIngestion.sync_biometrics(target_date: date) -> DomainSyncResult`.
- `GarminIngestion.sync_activity_details(days_back: int) -> DomainSyncResult`.
- `GarminIngestion.sync_gear() -> DomainSyncResult`.
- `GarminWorker.run(args: GarminWorkerArgs) -> SyncReport`.
- CLI: `python -m scripts.garmin_sync --days-back 2 --calendar --report-json /path/report.json`.

- [ ] **Step 1: Write failing ingestion tests using fake Garmin responses.**

```python

def test_activity_ingestion_is_idempotent_by_garmin_activity_id(fake_client, db):
    first = GarminIngestion(fake_client, db).sync_activities(days_back=2)
    second = GarminIngestion(fake_client, db).sync_activities(days_back=2)
    assert first.created == 1
    assert second.created == 0
    assert second.updated == 1


def test_worker_releases_lock_after_failure(tmp_path, fake_client, db):
    with pytest.raises(GarminSyncError):
        GarminWorker(...).run(GarminWorkerArgs(days_back=2, fail_after="daily_summary"))
    assert not (tmp_path / "garmin-sync.lock").exists()
```

- [ ] **Step 2: Run focused tests and confirm failure.**

Run: `cd api && uv run pytest -q tests/integrations/test_garmin_ingest.py tests/test_garmin_worker.py`

Expected: FAIL because the internal client, ingestion modules, and worker do not exist.

- [ ] **Step 3: Move the existing ingestion behavior with minimal changes.**

Port the corresponding logic from `garmin-connect-sync/sync.py` into the internal modules. Preserve the existing database columns, Garmin ID handling, date windows, retry behavior, and summary counts. Replace direct environment reads with `GarminIntegrationSettings`.

- [ ] **Step 4: Implement process locking and structured reporting.**

Use an atomic lock file or PostgreSQL advisory lock so scheduled and on-demand workers cannot overlap. Ensure all failure paths release the lock and return a report that identifies the failed domain without credentials.

- [ ] **Step 5: Implement the worker CLI.**

Support the existing operational modes: daily-only, calendar-only, comprehensive, days-back, calendar inclusion, and JSON report output. The CLI must exit nonzero on a failed domain and zero on a successful or intentionally skipped domain.

- [ ] **Step 6: Run the internal worker tests.**

Run: `cd api && uv run pytest -q tests/integrations/test_garmin_ingest.py tests/test_garmin_worker.py`

Expected: PASS.

- [ ] **Step 7: Commit.**

```bash
git add api/src/integrations/garmin api/scripts/garmin_sync.py api/tests/integrations/test_garmin_ingest.py api/tests/test_garmin_worker.py
git commit -m "feat: add Training Assistant Garmin ingestion worker"
```

---

### Task 4: Bring Garmin-backed schema ownership into Alembic

**Files:**
- Modify: `api/src/db/migrations/env.py`
- Create: `api/src/db/migrations/versions/<revision>_own_garmin_tables.py`
- Create: `api/scripts/verify_garmin_schema.py`
- Create: `api/tests/test_garmin_schema_migration.py`

**Interfaces:**
- `verify_garmin_schema(database_url: str) -> SchemaVerificationReport`.
- The report contains table names, row counts, identifier counts, missing indexes, and constraint mismatches.

- [ ] **Step 1: Write migration verification tests.**

```python

def test_clean_database_creates_all_garmin_tables(alembic_runner):
    alembic_runner.upgrade("head")
    assert alembic_runner.has_table("garmin_activities")
    assert alembic_runner.has_table("garmin_daily_summary")
    assert alembic_runner.has_table("athlete_biometrics")


def test_verification_reports_preserved_identifiers(before_snapshot, after_snapshot):
    assert after_snapshot.garmin_activity_ids == before_snapshot.garmin_activity_ids
    assert after_snapshot.daily_summary_dates == before_snapshot.daily_summary_dates
```

- [ ] **Step 2: Run migration tests and confirm failure.**

Run: `cd api && uv run pytest -q tests/test_garmin_schema_migration.py`

Expected: FAIL because the external tables are excluded from repository migration ownership.

- [ ] **Step 3: Capture the live schema before changing it.**

Run the verification script against the current database and save its JSON report outside git. Compare columns, indexes, constraints, row counts, and Garmin identifiers with `garmin-connect-sync/schema.sql` and `api/src/db/models.py`.

- [ ] **Step 4: Add a non-destructive ownership migration.**

Remove these tables from the Alembic exclusion set and add a migration that creates the required structure only when absent. Add missing indexes and constraints only after comparing the live report. Never drop populated tables or rewrite Garmin IDs.

- [ ] **Step 5: Implement verification.**

Make `verify_garmin_schema.py` return nonzero when a required table, column, identifier, or index is missing. Make it safe to run before and after migration.

- [ ] **Step 6: Run clean and populated database validation.**

Run:

```bash
cd api
uv run alembic upgrade head
uv run pytest -q tests/test_garmin_schema_migration.py tests/test_db.py
uv run python scripts/verify_garmin_schema.py
```

Expected: PASS, with unchanged Garmin identifier sets in the populated database.

- [ ] **Step 7: Commit.**

```bash
git add api/src/db/migrations/env.py api/src/db/migrations/versions api/scripts/verify_garmin_schema.py api/tests/test_garmin_schema_migration.py
git commit -m "feat: own Garmin tables through Training Assistant migrations"
```

---

### Task 5: Replace subprocess refresh and writeback adapters

**Files:**
- Create: `api/src/integrations/garmin/calendar.py`
- Create: `api/src/integrations/garmin/workouts.py`
- Create: `api/src/integrations/garmin/peloton.py`
- Modify: `api/src/services/garmin_refresh.py`
- Modify: `api/src/services/garmin_writeback.py`
- Modify: `api/src/services/plan_intelligence.py`
- Modify: `api/src/services/recommendations.py`
- Create: `api/tests/integrations/test_garmin_calendar.py`
- Modify: `api/tests/test_garmin_refresh_service.py`
- Modify: `api/tests/test_garmin_writeback.py`
- Modify: `api/tests/test_recommendations_service.py`

**Interfaces:**
- `GarminCalendar.sync(months_ahead: int, plan_ownership_mode: str) -> DomainSyncResult`.
- `GarminWorkoutWriter.apply_change(payload: dict[str, Any]) -> WritebackResult`.
- `GarminWorkoutWriter.delete(workout_id: str) -> WritebackResult`.
- `GarminPelotonImporter.sync(days_back: int) -> DomainSyncResult`.
- Existing service entrypoints retain their current public signatures so API routes and agent tools do not change.

- [ ] **Step 1: Add failing adapter tests.**

```python

def test_assistant_mode_skips_generic_calendar_workouts(fake_calendar, db):
    result = GarminCalendar(fake_calendar, db).sync(5, "assistant")
    assert result.workouts == 0
    assert result.races == 1


def test_writeback_updates_assistant_entry_atomically(fake_garmin, db, assistant_entry):
    result = GarminWorkoutWriter(fake_garmin, db).apply_change(payload)
    db.refresh(assistant_entry)
    assert result["status"] == "success"
    assert assistant_entry.garmin_workout_id == result["workout_id"]
    assert assistant_entry.garmin_sync_status == "success"
```

- [ ] **Step 2: Run focused tests and confirm failure.**

Run: `cd api && uv run pytest -q tests/integrations/test_garmin_calendar.py tests/test_garmin_refresh_service.py tests/test_garmin_writeback.py tests/test_recommendations_service.py`

Expected: FAIL because the internal calendar and writer are not yet wired into the services.

- [ ] **Step 3: Port calendar and workout behavior.**

Move `_calendar_workout_record`, calendar race handling, assistant ownership filtering, stale-workout deletion, Garmin workout step conversion, deduplication, and replacement behavior into the internal integration modules. Preserve existing IDs and status values.

- [ ] **Step 4: Make writeback atomic at the application boundary.**

The application must update `planned_workouts` and `assistant_plan_entries` only after Garmin returns a verified ID. On failure, preserve the prior ID and record failure details. On replacement, delete the old Garmin ID and update the linked assistant entry in one database transaction.

- [ ] **Step 5: Replace filesystem-path subprocess resolution.**

Change `garmin_refresh.py` and `garmin_writeback.py` to call the internal worker boundary. Remove default paths pointing at `experiments/garmin-connect-sync`. Preserve timeout and structured error behavior at the API boundary.

- [ ] **Step 6: Port Peloton import.**

Move the existing Peloton-to-Garmin behavior into `GarminPelotonImporter`, preserving source IDs, idempotency, date windows, and activity mapping.

- [ ] **Step 7: Run all integration and recommendation tests.**

Run: `cd api && uv run pytest -q tests/integrations tests/test_garmin_refresh_service.py tests/test_garmin_writeback.py tests/test_recommendations_service.py tests/test_plan_intelligence.py`

Expected: PASS.

- [ ] **Step 8: Commit.**

```bash
git add api/src/integrations/garmin api/src/services/garmin_refresh.py api/src/services/garmin_writeback.py api/src/services/plan_intelligence.py api/src/services/recommendations.py api/tests
git commit -m "feat: route Training Assistant refresh and writeback through internal Garmin"
```

---

### Task 6: Move scheduled operations into Training Assistant

**Files:**
- Create: `api/scripts/run_garmin_sync.sh`
- Create: `deploy/com.training.garmin-sync.plist`
- Modify: `deploy/README.md`
- Modify: `README.md`
- Create: `api/tests/test_garmin_scheduler.py`

**Interfaces:**
- `api/scripts/run_garmin_sync.sh` runs the Training Assistant worker with the configured lock, environment, report path, and failure exit behavior.
- `deploy/com.training.garmin-sync.plist` is the only active Garmin scheduler after cutover.

- [ ] **Step 1: Write scheduler tests.**

```python

def test_scheduler_points_only_at_training_assistant_worker():
    plist = Path("deploy/com.training.garmin-sync.plist").read_text()
    assert "garmin-connect-sync" not in plist
    assert "api/scripts/run_garmin_sync.sh" in plist


def test_runner_uses_training_assistant_python_and_lock(tmp_path):
    result = run_runner(env={"GARMIN_SYNC_LOCK_PATH": str(tmp_path / "lock")})
    assert result.returncode == 0
    assert "garmin-connect-sync" not in result.stdout
```

- [ ] **Step 2: Run scheduler tests and confirm failure.**

Run: `cd api && uv run pytest -q tests/test_garmin_scheduler.py`

Expected: FAIL because the new Training Assistant-owned scheduler does not exist.

- [ ] **Step 3: Implement the runner and LaunchAgent.**

Preserve the existing cadence, daily backfill window, calendar refresh, alert/report behavior, and lock semantics. Make the runner fail visibly and write a structured report. Do not enable the new LaunchAgent yet.

- [ ] **Step 4: Validate launch configuration.**

Run:

```bash
plutil -lint deploy/com.training.garmin-sync.plist
bash -n api/scripts/run_garmin_sync.sh
cd api && uv run pytest -q tests/test_garmin_scheduler.py
```

Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add api/scripts/run_garmin_sync.sh deploy/com.training.garmin-sync.plist deploy/README.md README.md api/tests/test_garmin_scheduler.py
git commit -m "feat: add Training Assistant-owned Garmin scheduler"
```

---

### Task 7: Run shadow and canary validation against the populated system

**Files:**
- Create: `api/scripts/compare_garmin_sync.py`
- Create: `api/tests/test_garmin_sync_comparison.py`
- Create: `docs/superpowers/runbooks/garmin-cutover.md`

**Interfaces:**
- `compare_garmin_sync --days-back 2 --months-ahead 5` returns a JSON comparison report with domain-level differences and duplicate candidates.
- The runbook records exact commands for shadow mode, canary writes, rollback, and evidence capture.

- [ ] **Step 1: Write comparison tests.**

```python

def test_comparison_ignores_order_but_detects_id_differences():
    report = compare_reports(old_report, new_report)
    assert report["differences"] == []


def test_comparison_flags_duplicate_workout_ids():
    report = compare_reports(old_report_with_duplicate, new_report)
    assert report["duplicate_candidates"] == ["workout-123"]
```

- [ ] **Step 2: Run the focused tests and confirm failure.**

Run: `cd api && uv run pytest -q tests/test_garmin_sync_comparison.py`

Expected: FAIL because the comparison tool does not exist.

- [ ] **Step 3: Implement comparison and evidence capture.**

Compare Garmin activity IDs, summary dates, biometrics dates, race IDs, calendar workout IDs, assistant plan-entry IDs, and writeback status. Never compare titles alone. Write reports outside git unless they contain no personal data.

- [ ] **Step 4: Execute shadow validation.**

Run the new worker in dry-run mode and compare its report with the current known-good behavior. Resolve every difference or record it as an explicit follow-up before canary writes.

- [ ] **Step 5: Execute canary writes.**

Enable one domain at a time in the order documented by the design. After each domain, verify database counts, identifiers, API responses, and Garmin calendar state. Do not enable the old and new schedulers together.

- [ ] **Step 6: Run the full application suite.**

Run:

```bash
cd api
uv run pytest -q
cd ../web && npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit the validation tooling and runbook.**

```bash
git add api/scripts/compare_garmin_sync.py api/tests/test_garmin_sync_comparison.py docs/superpowers/runbooks/garmin-cutover.md
git commit -m "test: add Garmin shadow and canary validation"
```

---

### Task 8: Cut over runtime ownership and remove old-repository references

**Files:**
- Modify: `api/.env.example`
- Modify: `api/src/services/garmin_refresh.py`
- Modify: `api/src/services/garmin_writeback.py`
- Modify: `README.md`
- Modify: `deploy/README.md`
- Modify: `docs/superpowers/runbooks/garmin-cutover.md`
- Create: `api/tests/test_no_legacy_garmin_reference.py`

**Interfaces:**
- Training Assistant is the only runtime Garmin provider.
- `test_no_legacy_garmin_reference.py` fails if active code, config, deploy files, or documentation references `garmin-connect-sync`.

- [ ] **Step 1: Write the final reference-removal test.**

```python

def test_active_training_assistant_files_do_not_reference_legacy_repo():
    forbidden = "garmin-connect-sync"
    roots = [Path("api/src"), Path("api/scripts"), Path("deploy"), Path("README.md")]
    hits = [str(path) for root in roots for path in files(root) if forbidden in path.read_text(errors="ignore")]
    assert hits == []
```

- [ ] **Step 2: Run the test and confirm it finds the legacy references.**

Run: `cd api && uv run pytest -q tests/test_no_legacy_garmin_reference.py`

Expected: FAIL with the current sibling-repository references.

- [ ] **Step 3: Remove runtime and documentation references.**

Replace sibling paths, commands, environment keys, setup instructions, and scheduler references with Training Assistant-owned paths. Keep historical migration notes outside active runtime documentation only if they do not create an operational dependency.

- [ ] **Step 4: Disable the old jobs and enable the new job.**

Unload the old Garmin LaunchAgents, install the Training Assistant-owned LaunchAgent, and verify that exactly one Garmin worker process is active. Capture the command output in the runbook without committing personal logs.

- [ ] **Step 5: Run final end-to-end verification.**

Run:

```bash
cd api
uv run pytest -q
uv run pytest -q tests/test_no_legacy_garmin_reference.py
uv run python scripts/verify_garmin_schema.py
cd ..
plutil -lint deploy/com.training.garmin-sync.plist
bash -n api/scripts/run_garmin_sync.sh
curl -k -fsS https://braydons-macbook-pro.tail277a09.ts.net:3572/api/v1/plan/current
curl -k -fsS https://braydons-macbook-pro.tail277a09.ts.net:3572/api/v1/plan/workouts
```

Expected: all commands succeed; the plan endpoint remains assistant-owned; six current Garmin-linked workouts remain intact; no old repository reference is found in active files.

- [ ] **Step 6: Commit and push the cutover.**

```bash
git add api/.env.example api/src api/scripts deploy README.md docs/superpowers/runbooks/garmin-cutover.md
git commit -m "feat: retire legacy Garmin repository runtime dependency"
git push origin main
```

- [ ] **Step 7: Retire only after soak.**

After the documented soak window passes, archive the sibling repository outside the active workspace or tag its final known-good commit. Do not delete personal activity exports or token stores as part of repository retirement.
