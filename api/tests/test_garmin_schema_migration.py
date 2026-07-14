from pathlib import Path

from src.scripts.verify_garmin_schema import verify_garmin_schema


MIGRATIONS = Path(__file__).parents[1] / "src/db/migrations/versions"


def test_current_database_contains_required_garmin_tables_and_identifiers():
    report = verify_garmin_schema()

    assert report["status"] == "success"
    assert report["missing_tables"] == []
    assert report["missing_columns"] == {}
    assert report["row_counts"]["garmin_activities"] > 0
    assert report["row_counts"]["garmin_daily_summary"] > 0
    assert report["identifier_counts"]["garmin_activity_id"] > 0


def test_foundational_migration_creates_garmin_tables_before_foreign_keys():
    migration = (MIGRATIONS / "f59ae60687df_add_training_assistant_tables.py").read_text()

    assert migration.index("CREATE TABLE IF NOT EXISTS garmin_activities") < migration.index(
        "op.create_table('activity_details'"
    )


def test_ownership_migration_is_non_destructive():
    migration = (MIGRATIONS / "a1b2c3d4e5f6_own_garmin_tables.py").read_text()

    assert "DROP TABLE" not in migration
    assert "ADD COLUMN IF NOT EXISTS" in migration
    assert "CREATE INDEX IF NOT EXISTS" in migration
