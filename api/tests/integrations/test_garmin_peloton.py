from src.config import Settings
from src.integrations.garmin.config import GarminIntegrationSettings
from src.integrations.garmin.peloton import GarminPelotonImporter, build_tcx


def test_peloton_importer_skips_without_enabled_credentials(tmp_path):
    integration = GarminIntegrationSettings.from_app_settings(
        Settings(
            peloton_enabled=False,
            garmin_tokenstore_path=str(tmp_path / "tokens"),
        )
    )

    result = GarminPelotonImporter(integration).sync(days_back=7)

    assert result == {"status": "skipped", "reason": "peloton_disabled", "synced": 0}


def test_peloton_importer_requires_credentials_when_enabled(tmp_path):
    integration = GarminIntegrationSettings.from_app_settings(
        Settings(
            peloton_enabled=True,
            garmin_tokenstore_path=str(tmp_path / "tokens"),
        )
    )

    result = GarminPelotonImporter(integration).sync(days_back=7)

    assert result["status"] == "failed"
    assert result["reason"] == "peloton_credentials_missing"


def test_peloton_tcx_builder_returns_activity_xml():
    xml = build_tcx(
        {
            "fitness_discipline": "cycling",
            "start_time": 0,
            "created_at": 0,
            "ride": {"title": "Easy Ride", "duration": 600},
        },
        {},
    )

    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "Peloton: Easy Ride" in xml
