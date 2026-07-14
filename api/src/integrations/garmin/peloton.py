# ABOUTME: Syncs Peloton workouts to Garmin Connect via Auth0 OAuth + TCX upload.
# ABOUTME: Authenticates with Peloton's Auth0 PKCE flow, converts workouts to TCX, uploads to Garmin.

import argparse
import hashlib
import html
import json
import os
import re
import secrets
import sys
import time
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree.ElementTree import Element, SubElement, tostring

import requests
import psycopg2
from garminconnect import Garmin

from src.config import settings
from src.integrations.garmin.config import GarminIntegrationSettings


PELOTON_TOKEN_FILE = Path.home() / ".config" / "training-assistant" / "peloton_token.json"

# Peloton Auth0 config (from peloton-to-garmin project)
AUTH_DOMAIN = "auth.onepeloton.com"
AUTH_CLIENT_ID = "WVoJxVDdPoFx4RNewvvg6ch2mZ7bwnsM"
AUTH_AUDIENCE = "https://api.onepeloton.com/"
AUTH_SCOPE = "offline_access openid peloton-api.members:default"
AUTH_REDIRECT_URI = "https://members.onepeloton.com/callback"
AUTH0_CLIENT_PAYLOAD = "eyJuYW1lIjoiYXV0aDAuanMtdWxwIiwidmVyc2lvbiI6IjkuMTQuMyJ9"
PELOTON_API = "https://api.onepeloton.com/"


def _random_string(length: int) -> str:
    raw = secrets.token_bytes(length)
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return encoded[:length]


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


class PelotonAuth:
    """Handles Peloton Auth0 PKCE authentication flow."""

    def __init__(self, token_file: Path | None = None) -> None:
        self.token_file = token_file or PELOTON_TOKEN_FILE
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        })
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.expires_at: Optional[float] = None
        self.user_id: Optional[str] = None

    def login(self, email: str, password: str) -> str:
        """Full Auth0 PKCE login flow. Returns bearer token."""
        code_verifier = _random_string(64)
        challenge = _code_challenge(code_verifier)
        state = _random_string(32)
        nonce = _random_string(32)

        # Step 1: Initiate authorize flow
        authorize_url = (
            f"https://{AUTH_DOMAIN}/authorize?"
            f"client_id={AUTH_CLIENT_ID}&"
            f"audience={AUTH_AUDIENCE}&"
            f"scope={AUTH_SCOPE.replace(' ', '+')}&"
            f"response_type=code&"
            f"response_mode=query&"
            f"redirect_uri={AUTH_REDIRECT_URI}&"
            f"state={state}&"
            f"nonce={nonce}&"
            f"code_challenge={challenge}&"
            f"code_challenge_method=S256&"
            f"auth0Client={AUTH0_CLIENT_PAYLOAD}"
        )

        resp = self.session.get(authorize_url, allow_redirects=True)
        resp.raise_for_status()
        login_url = resp.url

        # Extract state from final URL if updated
        if "state=" in login_url:
            m = re.search(r"[?&]state=([^&]+)", login_url)
            if m:
                state = m.group(1)

        # Extract CSRF token from cookies
        csrf_token = None
        for cookie in self.session.cookies:
            if cookie.name == "_csrf" and cookie.path == "/usernamepassword/login":
                csrf_token = cookie.value
                break

        if not csrf_token:
            raise RuntimeError("Could not extract CSRF token from Auth0 login flow")

        # Step 2: Submit credentials
        login_payload = {
            "client_id": AUTH_CLIENT_ID,
            "redirect_uri": AUTH_REDIRECT_URI,
            "tenant": "peloton-prod",
            "response_type": "code",
            "scope": AUTH_SCOPE,
            "audience": AUTH_AUDIENCE,
            "_csrf": csrf_token,
            "state": state,
            "_intstate": "deprecated",
            "nonce": nonce,
            "username": email,
            "password": password,
            "connection": "pelo-user-password",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }

        resp = self.session.post(
            f"https://{AUTH_DOMAIN}/usernamepassword/login",
            json=login_payload,
            headers={
                "Content-Type": "application/json",
                "Origin": f"https://{AUTH_DOMAIN}",
                "Referer": login_url,
                "Auth0-Client": AUTH0_CLIENT_PAYLOAD,
            },
            allow_redirects=False,
        )

        if resp.status_code == 302:
            next_url = resp.headers.get("Location", "")
            # Resolve relative URLs from Auth0
            if next_url and not next_url.startswith("http"):
                next_url = f"https://{AUTH_DOMAIN}{next_url}"
        elif resp.status_code == 200:
            # Parse hidden form from response — returns code or URL
            next_url = self._submit_hidden_form(resp.text)
        else:
            raise RuntimeError(f"Login failed with status {resp.status_code}: {resp.text[:300]}")

        # Step 3: Extract auth code — may already be the code, in a URL, or need more redirects
        auth_code = None
        m = re.search(r"[?&]code=([^&]+)", next_url)
        if m:
            auth_code = m.group(1)
        elif not next_url.startswith("http"):
            # _submit_hidden_form returned the code directly
            auth_code = next_url if next_url and len(next_url) > 10 else None
        if not auth_code and next_url.startswith("http"):
            auth_code = self._follow_for_code(next_url)

        if not auth_code:
            raise RuntimeError("Could not extract authorization code from redirect chain")

        # Step 4: Exchange code for tokens
        token_resp = self.session.post(
            f"https://{AUTH_DOMAIN}/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": AUTH_CLIENT_ID,
                "code_verifier": code_verifier,
                "code": auth_code,
                "redirect_uri": AUTH_REDIRECT_URI,
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()

        self.access_token = token_data["access_token"]
        self.refresh_token = token_data.get("refresh_token")
        self.expires_at = time.time() + token_data.get("expires_in", 172800)

        # Get user ID
        self.user_id = self._get_user_id()

        # Save tokens
        self._save_tokens()
        return self.access_token

    def refresh(self) -> str:
        """Refresh the access token using the refresh token."""
        if not self.refresh_token:
            raise RuntimeError("No refresh token available")

        resp = self.session.post(
            f"https://{AUTH_DOMAIN}/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "refresh_token",
                "client_id": AUTH_CLIENT_ID,
                "refresh_token": self.refresh_token,
            },
        )
        resp.raise_for_status()
        token_data = resp.json()

        self.access_token = token_data["access_token"]
        if "refresh_token" in token_data:
            self.refresh_token = token_data["refresh_token"]
        self.expires_at = time.time() + token_data.get("expires_in", 172800)

        self._save_tokens()
        return self.access_token

    def ensure_valid_token(self, email: str = "", password: str = "") -> str:
        """Ensure we have a valid token, refreshing or re-logging in as needed."""
        if self.access_token and self.expires_at and time.time() < self.expires_at - 300:
            return self.access_token

        if self.refresh_token:
            try:
                print("  Refreshing Peloton token...")
                return self.refresh()
            except Exception as e:
                print(f"  Refresh failed: {e}")

        if email and password:
            print("  Performing full Peloton login...")
            return self.login(email, password)

        raise RuntimeError("Peloton token expired and no credentials for re-login")

    def _get_user_id(self) -> str:
        resp = self.session.get(
            f"{PELOTON_API}api/me",
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def _submit_hidden_form(self, html_body: str) -> str:
        """Parse and submit the hidden callback form from Auth0.

        Manually follows redirects to capture the auth code from Location
        headers, since the final callback URL is a client-side SPA route.
        """
        action_match = re.search(r'<form[^>]+action="([^"]+)"', html_body)
        if not action_match:
            raise RuntimeError("Could not find form action in Auth0 response")

        action = html.unescape(action_match.group(1))
        if not action.startswith("http"):
            action = f"https://{AUTH_DOMAIN}{action}"

        fields = {}
        for m in re.finditer(
            r'<input[^>]+type="hidden"[^>]+name="([^"]+)"[^>]+value="([^"]*)"', html_body
        ):
            fields[m.group(1)] = html.unescape(m.group(2))
        # Also match reversed attribute order
        for m in re.finditer(
            r'<input[^>]+name="([^"]+)"[^>]+type="hidden"[^>]+value="([^"]*)"', html_body
        ):
            fields[m.group(1)] = html.unescape(m.group(2))

        # Don't follow redirects — we need to capture the code from Location headers
        resp = self.session.post(
            action,
            data=fields,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self.session.headers["User-Agent"],
            },
            allow_redirects=False,
        )

        # Follow redirect chain manually, looking for code= in Location
        max_redirects = 10
        for _ in range(max_redirects):
            location = resp.headers.get("Location", "")
            if not location:
                break

            # Check for auth code in this redirect
            code_match = re.search(r"[?&]code=([^&]+)", location)
            if code_match:
                return code_match.group(1)

            # Resolve relative URLs
            if not location.startswith("http"):
                from urllib.parse import urljoin
                location = urljoin(resp.url or action, location)

            resp = self.session.get(location, allow_redirects=False)

        # Fallback: check final URL
        final_url = resp.url or ""
        code_match = re.search(r"[?&]code=([^&]+)", final_url)
        if code_match:
            return code_match.group(1)

        return final_url

    def _follow_for_code(self, url: str) -> Optional[str]:
        """Follow redirects to extract the authorization code."""
        # Check if we already have the code
        m = re.search(r"[?&]code=([^&]+)", url)
        if m:
            return m.group(1)

        resp = self.session.get(url, allow_redirects=True)
        final_url = resp.url
        m = re.search(r"[?&]code=([^&]+)", final_url)
        if m:
            return m.group(1)

        for r in resp.history:
            m = re.search(r"[?&]code=([^&]+)", r.headers.get("Location", ""))
            if m:
                return m.group(1)

        return None

    def _save_tokens(self) -> None:
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "user_id": self.user_id,
        }
        with open(self.token_file, "w") as f:
            json.dump(data, f, indent=2)
        os.chmod(self.token_file, 0o600)

    def load_tokens(self) -> bool:
        """Load saved tokens. Returns True if loaded."""
        if not self.token_file.exists():
            return False
        with open(self.token_file) as f:
            data = json.load(f)
        self.access_token = data.get("access_token")
        self.refresh_token = data.get("refresh_token")
        self.expires_at = data.get("expires_at")
        self.user_id = data.get("user_id")
        return bool(self.access_token)


PELOTON_TO_GARMIN_TYPE_KEY = {
    "cycling": "cycling",
    "running": "running",
    "walking": "walking",
    "bike_bootcamp": "cycling",
    "strength": "strength_training",
    "yoga": "yoga",
    "stretching": "flexibility",
    "meditation": "meditation",
    "cardio": "cardio",
}


def _parse_upload_response(resp) -> Dict[str, Any]:
    """Parse Garmin upload response to determine actual success/failure.

    Returns dict with keys:
      - "status": "success" | "silent_reject" | "failure"
      - "activity_id": int or None
      - "failures": list
    """
    try:
        body = resp.json() if hasattr(resp, "json") else {}
    except Exception:
        body = {}
    result = body.get("detailedImportResult", {})
    successes = result.get("successes", [])
    failures = result.get("failures", [])
    if successes:
        activity_id = None
        if isinstance(successes[0], dict):
            activity_id = successes[0].get("internalId")
        return {"status": "success", "activity_id": activity_id, "failures": []}
    if failures:
        return {"status": "failure", "activity_id": None, "failures": failures}
    return {"status": "silent_reject", "activity_id": None, "failures": []}


def _extract_summaries(samples: Dict) -> Dict[str, Any]:
    """Extract summary values from performance graph (replaces dead summary endpoint)."""
    result: Dict[str, Any] = {}
    for s in samples.get("summaries", []):
        result[s["slug"]] = s.get("value")
    for s in samples.get("average_summaries", []):
        result[s["slug"]] = s.get("value")
    return result


def _build_trackpoints(
    track: Element,
    start_dt: datetime,
    sample_interval: List[int],
    start_idx: int,
    end_idx: int,
    hr_samples: List,
    power_samples: List,
    cadence_samples: List,
    speed_samples: List,
    pace_samples: List,
    ns_ext: str,
) -> None:
    """Add trackpoints to a Track element for the given sample range."""
    for i in range(start_idx, end_idx):
        tp = SubElement(track, "Trackpoint")

        if i < len(sample_interval):
            tp_time = start_dt + timedelta(seconds=sample_interval[i])
        else:
            tp_time = start_dt + timedelta(seconds=i * 5)

        time_elem = SubElement(tp, "Time")
        time_elem.text = tp_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        if i < len(hr_samples) and hr_samples[i]:
            hr_elem = SubElement(tp, "HeartRateBpm")
            val = SubElement(hr_elem, "Value")
            val.text = str(int(hr_samples[i]))

        if i < len(cadence_samples) and cadence_samples[i]:
            cad_elem = SubElement(tp, "Cadence")
            cad_elem.text = str(int(cadence_samples[i]))

        # Speed: from speed metric (mph) or derived from pace (min/mi)
        speed_ms = None
        if i < len(speed_samples) and speed_samples[i]:
            speed_ms = round(speed_samples[i] * 0.44704, 2)  # mph to m/s
        elif i < len(pace_samples) and pace_samples[i] and pace_samples[i] > 0:
            speed_ms = round(26.8224 / pace_samples[i], 2)  # min/mi to m/s

        has_ext = (
            speed_ms is not None or
            (i < len(power_samples) and power_samples[i])
        )
        if has_ext:
            ext = SubElement(tp, "Extensions")
            tpx = SubElement(ext, "ns3:TPX")
            if speed_ms is not None:
                spd = SubElement(tpx, "ns3:Speed")
                spd.text = str(speed_ms)
            if i < len(power_samples) and power_samples[i]:
                watts = SubElement(tpx, "ns3:Watts")
                watts.text = str(int(power_samples[i]))


def build_tcx(workout: Dict, samples: Dict) -> str:
    """Build a TCX XML string from Peloton workout data.

    Uses the performance_graph response for both time-series metrics and
    summary values (the old /summary endpoint is deprecated/404).
    Creates separate laps from Peloton segments when available.
    """
    ride = workout.get("ride") or {}
    fitness_discipline = workout.get("fitness_discipline", "cycling")

    sport_map = {
        "cycling": "Biking",
        "running": "Running",
        "walking": "Running",
        "bike_bootcamp": "Biking",
        "strength": "Other",
        "yoga": "Other",
        "stretching": "Other",
        "meditation": "Other",
        "cardio": "Other",
    }
    sport = sport_map.get(fitness_discipline, "Other")

    start_ts = workout.get("start_time", workout.get("created_at", 0))
    start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    duration = ride.get("duration", 0) if isinstance(ride, dict) else 0

    # Extract summaries from performance graph
    sums = _extract_summaries(samples)
    calories = sums.get("calories")
    distance_mi = sums.get("distance")
    distance_m = round(distance_mi * 1609.34, 1) if distance_mi else 0

    # Extract time-series data
    hr_samples: List = []
    power_samples: List = []
    cadence_samples: List = []
    speed_samples: List = []
    pace_samples: List = []

    for metric in samples.get("metrics", []):
        slug = metric.get("slug", "")
        values = metric.get("values", [])
        if slug == "heart_rate":
            hr_samples = values
        elif slug == "output":
            power_samples = values
        elif slug == "cadence":
            cadence_samples = values
        elif slug == "speed":
            speed_samples = values
        elif slug == "pace":
            pace_samples = values

    sample_interval = samples.get("seconds_since_pedaling_start", [])
    num_samples = max(
        len(hr_samples), len(power_samples), len(cadence_samples),
        len(speed_samples), len(pace_samples), 1,
    )
    if not sample_interval:
        interval = duration / num_samples if num_samples > 1 else 5
        sample_interval = [int(i * interval) for i in range(num_samples)]

    # Build TCX XML
    ns = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    ns_ext = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"

    root = Element("TrainingCenterDatabase")
    root.set("xmlns", ns)
    root.set("xmlns:ns3", ns_ext)

    activities_el = SubElement(root, "Activities")
    activity = SubElement(activities_el, "Activity")
    activity.set("Sport", sport)

    id_elem = SubElement(activity, "Id")
    id_elem.text = start_iso

    # Build segments list — use Peloton segments if available, else one lap
    segments = samples.get("segment_list", [])
    if not segments:
        segments = [{"name": "Workout", "start_time_offset": 0, "length": duration}]

    # Create one lap per segment
    for seg_idx, seg in enumerate(segments):
        seg_start_offset = seg.get("start_time_offset", 0)
        seg_length = seg.get("length", duration)
        seg_start_dt = start_dt + timedelta(seconds=seg_start_offset)

        lap = SubElement(activity, "Lap")
        lap.set("StartTime", seg_start_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"))

        total_time = SubElement(lap, "TotalTimeSeconds")
        total_time.text = str(seg_length)

        # Distribute distance proportionally across laps
        if len(segments) == 1:
            lap_distance = distance_m
        else:
            lap_distance = round(distance_m * seg_length / duration, 1) if duration else 0
        dist_elem = SubElement(lap, "DistanceMeters")
        dist_elem.text = str(lap_distance)

        # Calories on first lap only (Garmin sums across laps)
        if seg_idx == 0 and calories is not None:
            cal_elem = SubElement(lap, "Calories")
            cal_elem.text = str(int(calories))
        elif seg_idx > 0:
            cal_elem = SubElement(lap, "Calories")
            cal_elem.text = "0"

        seg_name = seg.get("name", "")
        is_rest = seg_name.lower() in ("warm up", "cool down", "warmup", "cooldown")
        intensity = SubElement(lap, "Intensity")
        intensity.text = "Resting" if is_rest else "Active"

        trigger = SubElement(lap, "TriggerMethod")
        trigger.text = "Manual"

        # Find sample index range for this segment
        seg_end_offset = seg_start_offset + seg_length
        start_idx = 0
        end_idx = num_samples
        for j, t in enumerate(sample_interval):
            if t >= seg_start_offset and start_idx == 0 and j > 0:
                start_idx = j
            if t >= seg_end_offset:
                end_idx = j
                break
        # First segment always starts at 0
        if seg_idx == 0:
            start_idx = 0

        track = SubElement(lap, "Track")
        _build_trackpoints(
            track, start_dt, sample_interval, start_idx, end_idx,
            hr_samples, power_samples, cadence_samples, speed_samples,
            pace_samples, ns_ext,
        )

    # Add workout title as Notes
    title = ride.get("title", workout.get("fitness_discipline", "Peloton Workout"))
    instructor = ride.get("instructor", {})
    instructor_name = instructor.get("name", "") if isinstance(instructor, dict) else ""
    notes_text = f"Peloton: {title}"
    if instructor_name:
        notes_text += f" with {instructor_name}"

    notes = SubElement(activity, "Notes")
    notes.text = notes_text

    xml_str = tostring(root, encoding="unicode", xml_declaration=False)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'


class PelotonToGarminSync:
    """Syncs Peloton workouts to Garmin Connect."""

    def __init__(
        self,
        email: str,
        password: str,
        integration_settings: GarminIntegrationSettings | None = None,
    ) -> None:
        self.integration_settings = integration_settings or GarminIntegrationSettings.from_app_settings()
        self.email = email
        self.password = password
        self.peloton = PelotonAuth(
            self.integration_settings.tokenstore_path.parent / "peloton_token.json"
        )
        self._garmin: Optional[Garmin] = None
        self._conn: Optional[Any] = None

    @property
    def garmin(self) -> Garmin:
        if self._garmin is None:
            self._garmin = Garmin()
            self._garmin.login(tokenstore=str(self.integration_settings.tokenstore_path))
            self._garmin.garth.dump(str(self.integration_settings.tokenstore_path))
        return self._garmin

    @property
    def conn(self) -> Any:
        if self._conn is None or self._conn.closed:
            database_url = settings.database_url_sync
            if not database_url:
                raise RuntimeError("DATABASE_URL_SYNC environment variable not set")
            self._conn = psycopg2.connect(database_url)
        return self._conn

    def ensure_schema(self) -> None:
        """Create tracking table if it doesn't exist."""
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS peloton_synced_workouts (
                peloton_workout_id TEXT PRIMARY KEY,
                workout_title TEXT,
                fitness_discipline TEXT,
                synced_at TIMESTAMPTZ DEFAULT NOW()
            );
            ALTER TABLE peloton_synced_workouts
                ADD COLUMN IF NOT EXISTS sync_method TEXT DEFAULT 'tcx';
        """)
        self.conn.commit()

    def _is_synced(self, workout_id: str) -> bool:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT 1 FROM peloton_synced_workouts WHERE peloton_workout_id = %s",
            (workout_id,)
        )
        return cur.fetchone() is not None

    def _mark_synced(self, workout_id: str, title: str, discipline: str,
                     method: str = "tcx") -> None:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO peloton_synced_workouts "
            "(peloton_workout_id, workout_title, fitness_discipline, sync_method) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (workout_id, title, discipline, method)
        )
        self.conn.commit()

    def _create_manual_fallback(self, w: Dict, perf_data: Dict) -> bool:
        """Create Peloton workout as a manual Garmin activity (fallback when TCX is rejected)."""
        ride = w.get("ride") or {}
        discipline = w.get("fitness_discipline", "cycling")
        type_key = PELOTON_TO_GARMIN_TYPE_KEY.get(discipline, "cycling")

        start_ts = w.get("start_time", w.get("created_at", 0))
        start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
        tz_name = w.get("timezone") or "America/New_York"
        # Peloton stores timezone as "America/New_York" format
        try:
            import zoneinfo
            local_tz = zoneinfo.ZoneInfo(tz_name)
            start_local = start_dt.astimezone(local_tz)
        except Exception:
            start_local = start_dt.astimezone(
                timezone(timedelta(hours=-5))
            )
            tz_name = "America/New_York"

        start_str = start_local.strftime("%Y-%m-%dT%H:%M:%S.000")

        duration_s = ride.get("duration", 0) if isinstance(ride, dict) else 0
        duration_min = max(duration_s // 60, 1)

        sums = _extract_summaries(perf_data)
        distance_mi = sums.get("distance") or 0
        distance_km = distance_mi * 1.60934

        title = ride.get("title", w.get("fitness_discipline", "Peloton Workout"))
        instructor = (ride.get("instructor") or {}).get("name", "")
        activity_name = f"Peloton: {title}"
        if instructor:
            activity_name += f" with {instructor}"

        try:
            self.garmin.create_manual_activity(
                start_datetime=start_str,
                time_zone=tz_name,
                type_key=type_key,
                distance_km=distance_km,
                duration_min=duration_min,
                activity_name=activity_name,
            )
            return True
        except Exception as e:
            print(f"    [error] Manual activity creation failed: {e}")
            return False

    def fetch_workouts(self, days_back: int = 7) -> List[Dict]:
        """Fetch completed Peloton workouts from the last N days."""
        self.peloton.load_tokens()
        token = self.peloton.ensure_valid_token(self.email, self.password)

        headers = {"Authorization": f"Bearer {token}"}
        user_id = self.peloton.user_id

        workouts = []
        page = 0
        cutoff = time.time() - (days_back * 86400)

        while True:
            resp = self.peloton.session.get(
                f"{PELOTON_API}api/user/{user_id}/workouts"
                f"?limit=20&page={page}&joins=ride,ride.instructor",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

            for w in data.get("data", []):
                if w.get("status") != "COMPLETE":
                    continue
                created = w.get("created_at", 0)
                if created < cutoff:
                    return workouts
                workouts.append(w)

            if not data.get("show_next", False):
                break
            page += 1
            time.sleep(0.5)

        return workouts

    def fetch_workout_details(self, workout_id: str) -> Dict:
        """Fetch performance graph for a workout (includes metrics + summaries)."""
        token = self.peloton.access_token
        headers = {"Authorization": f"Bearer {token}"}

        # every_n=1 gives per-second resolution for maximum fidelity
        resp = self.peloton.session.get(
            f"{PELOTON_API}api/workout/{workout_id}/performance_graph?every_n=1",
            headers=headers,
        )
        return resp.json() if resp.status_code == 200 else {}

    def sync(self, days_back: int = 7) -> int:
        """Sync recent Peloton workouts to Garmin Connect."""
        print(f"\n=== Peloton → Garmin Sync (last {days_back} days) ===\n")

        self.ensure_schema()

        print("Fetching Peloton workouts...")
        workouts = self.fetch_workouts(days_back)
        print(f"  Found {len(workouts)} completed workouts.")

        synced = 0
        for w in workouts:
            workout_id = w.get("id")
            ride = w.get("ride") or {}
            title = ride.get("title", w.get("fitness_discipline", "Workout"))
            discipline = w.get("fitness_discipline", "unknown")

            if self._is_synced(workout_id):
                print(f"  [skip] {title} — already synced")
                continue

            print(f"  Syncing: {title} ({discipline})...")

            try:
                perf_data = self.fetch_workout_details(workout_id)
                time.sleep(0.5)

                tcx_xml = build_tcx(w, perf_data)

                # Upload TCX to Garmin, verify it actually landed
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".tcx", mode="w", delete=False) as f:
                    f.write(tcx_xml)
                    tcx_path = f.name

                try:
                    resp = self.garmin.upload_activity(tcx_path)
                    upload_result = _parse_upload_response(resp)

                    if upload_result["status"] == "success":
                        print(f"    Uploaded to Garmin (TCX)")
                        self._mark_synced(workout_id, title, discipline, method="tcx")
                        synced += 1
                    elif upload_result["status"] == "silent_reject":
                        print(f"    TCX silently rejected, creating manual activity...")
                        if self._create_manual_fallback(w, perf_data):
                            print(f"    Created manual activity on Garmin")
                            self._mark_synced(workout_id, title, discipline, method="manual")
                            synced += 1
                        else:
                            print(f"    [error] Manual activity fallback also failed")
                    else:
                        print(f"    [error] Upload rejected: {upload_result['failures']}")
                finally:
                    os.unlink(tcx_path)

                time.sleep(1)

            except Exception as e:
                print(f"    [error] Failed: {e}")
                continue

        print(f"\n=== Done: {synced} workouts synced to Garmin ===")
        return synced

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Peloton workouts to Garmin Connect")
    parser.add_argument("--days-back", type=int, default=7,
                        help="Number of days to look back (default: 7)")
    parser.add_argument("--email", default=os.environ.get("PELOTON_EMAIL", ""),
                        help="Peloton email (or set PELOTON_EMAIL env var)")
    parser.add_argument("--password", default=os.environ.get("PELOTON_PASSWORD", ""),
                        help="Peloton password (or set PELOTON_PASSWORD env var)")
    args = parser.parse_args()

    email = args.email
    password = args.password

    if not email or not password:
        print("Peloton credentials required. Set PELOTON_EMAIL/PELOTON_PASSWORD or use --email/--password")
        sys.exit(1)

    sync = PelotonToGarminSync(email, password)
    try:
        sync.sync(args.days_back)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        sync.close()


class GarminPelotonImporter:
    """Training Assistant-owned Peloton-to-Garmin import boundary."""

    def __init__(self, integration_settings: GarminIntegrationSettings | None = None):
        self.integration_settings = integration_settings or GarminIntegrationSettings.from_app_settings()

    def sync(self, days_back: int = 7) -> dict[str, Any]:
        if not self.integration_settings.peloton_enabled:
            return {"status": "skipped", "reason": "peloton_disabled", "synced": 0}
        if not self.integration_settings.peloton_email or not self.integration_settings.peloton_password:
            return {"status": "failed", "reason": "peloton_credentials_missing", "synced": 0}
        importer = PelotonToGarminSync(
            self.integration_settings.peloton_email,
            self.integration_settings.peloton_password,
            self.integration_settings,
        )
        try:
            return {"status": "success", "synced": importer.sync(days_back)}
        except Exception as exc:
            return {"status": "failed", "reason": str(exc), "synced": 0}
        finally:
            importer.close()


if __name__ == "__main__":
    main()
