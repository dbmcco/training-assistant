#!/usr/bin/env python3
from __future__ import annotations

import getpass
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import garth
from garminconnect import Garmin

from src.integrations.garmin.config import GarminIntegrationSettings


def authenticate(email: str, password: str, integration: GarminIntegrationSettings) -> Path:
    client = Garmin(email, password)
    client.login()
    integration.tokenstore_path.mkdir(parents=True, exist_ok=True)
    garth.save(str(integration.tokenstore_path))
    integration.tokenstore_path.chmod(0o700)
    for token_file in integration.tokenstore_path.iterdir():
        token_file.chmod(0o600)
    return integration.tokenstore_path


def main() -> int:
    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password: ")
    if not email or not password:
        print("Email and password are required.", file=sys.stderr)
        return 1
    try:
        path = authenticate(email, password, GarminIntegrationSettings.from_app_settings())
    except Exception as exc:
        print(f"Authentication failed: {exc}", file=sys.stderr)
        return 1
    print(f"Tokens saved to: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
