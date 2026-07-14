from src.config import Settings
from src.integrations.garmin.config import GarminIntegrationSettings
from src.scripts import garmin_auth


def test_authentication_saves_tokens_with_private_permissions(tmp_path, monkeypatch):
    class FakeGarmin:
        def __init__(self, email, password):
            assert email == "athlete@example.test"
            assert password == "secret"

        def login(self):
            return None

    monkeypatch.setattr(garmin_auth, "Garmin", FakeGarmin)
    monkeypatch.setattr(
        garmin_auth.garth,
        "save",
        lambda path: (tmp_path / "tokens" / "token").write_text(path),
    )
    integration = GarminIntegrationSettings.from_app_settings(
        Settings(garmin_tokenstore_path=str(tmp_path / "tokens"))
    )

    path = garmin_auth.authenticate("athlete@example.test", "secret", integration)

    assert path == tmp_path / "tokens"
    assert path.stat().st_mode & 0o777 == 0o700
    assert (path / "token").stat().st_mode & 0o777 == 0o600
