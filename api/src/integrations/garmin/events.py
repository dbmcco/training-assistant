from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen
from typing import Any

logger = logging.getLogger(__name__)
EVENTS_URL = os.environ.get("PAIA_EVENTS_URL", "http://localhost:3511/v1/events")


def publish_event(
    event_type: str,
    source_event_id: str,
    dedupe_key: str,
    payload: dict[str, Any],
) -> None:
    """Publish a non-blocking event without allowing the sync to fail."""
    try:
        envelope = {
            "event_type": event_type,
            "source_app": "training-assistant",
            "source_event_id": source_event_id,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "dedupe_key": dedupe_key,
            "payload": payload,
        }
        request = Request(
            EVENTS_URL,
            data=json.dumps(envelope).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urlopen(request, timeout=3)
    except (URLError, OSError, Exception):
        logger.debug("Garmin event publish failed; continuing sync")
