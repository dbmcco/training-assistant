# ABOUTME: Garmin Connect sync daemon — fetches activities and daily health summaries.
# ABOUTME: Upserts data to PostgreSQL garmin_activities and garmin_daily_summary tables.

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import garth
import psycopg2
from garminconnect import Garmin

from src.config import settings
from src.integrations.garmin.config import GarminIntegrationSettings
from src.integrations.garmin.events import publish_event


API_DELAY_SECONDS = 1.0


def _calendar_workout_record(
    item: Dict[str, Any], *, today: date | None = None
) -> Optional[Dict[str, Any]]:
    """Normalize Garmin calendar workouts, including assistant-created ones."""
    if item.get("itemType") not in {"workout", "fbtAdaptiveWorkout"}:
        return None

    item_date = item.get("date")
    workout_id = item.get("workoutId") or item.get("id")
    workout_uuid = item.get("workoutUuid")
    if not item_date or (workout_id is None and not workout_uuid):
        return None

    try:
        workout_date = date.fromisoformat(str(item_date))
    except ValueError:
        return None

    today = today or date.today()
    title = str(item.get("title") or "Garmin workout")
    title_without_date = title.rsplit(" (", 1)[0] if title.endswith(")") else title
    title_parts = title_without_date.split(maxsplit=1)
    workout_type = title_parts[1] if len(title_parts) == 2 else title_without_date
    workout_uuid = workout_uuid or (
        f"calendar-workout-{workout_id}-{workout_date.isoformat()}"
    )

    return {
        "workout_uuid": str(workout_uuid),
        "workout_id": str(workout_id),
        "date": workout_date,
        "discipline": item.get("sportTypeKey") or "other",
        "workout_type": workout_type,
        "title": title,
        "status": "upcoming" if workout_date >= today else "missed",
        "training_plan_id": str(item.get("trainingPlanId") or "0"),
    }


class GarminSyncError(Exception):
    """Raised when Garmin sync operations fail."""
    pass


class GarminSyncClient:
    """Syncs Garmin Connect data to PostgreSQL."""

    def __init__(
        self,
        integration_settings: GarminIntegrationSettings | None = None,
    ) -> None:
        self._integration_settings = integration_settings or GarminIntegrationSettings.from_app_settings()
        self._client: Optional[Garmin] = None
        self._conn: Optional[Any] = None

    @property
    def client(self) -> Garmin:
        if self._client is None:
            tokenstore_path = self._integration_settings.tokenstore_path
            if not tokenstore_path.exists():
                raise GarminSyncError(
                    f"Garmin tokens not found at {tokenstore_path}. "
                    "Authenticate the Training Assistant-owned token store first."
                )
            try:
                self._client = Garmin()
                self._client.login(tokenstore=str(tokenstore_path))
                # Save refreshed tokens back to disk so they stay fresh.
                self._client.garth.dump(str(tokenstore_path))
            except Exception as e:
                raise GarminSyncError(
                    f"Failed to authenticate with Garmin: {e}\n"
                    "If tokens expired, re-run: python auth.py"
                )
        return self._client

    @property
    def conn(self) -> Any:
        if self._conn is None or self._conn.closed:
            database_url = settings.database_url_sync
            if not database_url:
                raise GarminSyncError("DATABASE_URL_SYNC environment variable not set")
            self._conn = psycopg2.connect(database_url)
        return self._conn

    def _delay(self) -> None:
        """Rate-limit safety delay between API calls."""
        time.sleep(API_DELAY_SECONDS)

    def _safe_get(self, method_name: str, *args: Any, **kwargs: Any) -> Optional[Any]:
        """Call a Garmin client method, returning None on failure."""
        try:
            method = getattr(self.client, method_name)
            result = method(*args, **kwargs)
            self._delay()
            return result
        except Exception as e:
            print(f"  [warn] {method_name} failed: {e}")
            return None

    def ensure_schema(self) -> None:
        """Apply schema.sql if tables don't exist yet."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'garmin_activities'
            )
        """)
        exists = cur.fetchone()[0]
        if exists:
            return

        raise GarminSyncError(
            "Garmin-backed tables are missing. Run the Training Assistant Alembic migrations first."
        )

    def sync_activities(self, days_back: int = 14) -> int:
        """Fetch recent activities and upsert to garmin_activities."""
        start_date = (date.today() - timedelta(days=days_back)).isoformat()
        end_date = date.today().isoformat()

        print(f"Fetching activities from {start_date} to {end_date}...")
        activities = self._safe_get("get_activities_by_date", start_date, end_date)

        if not activities:
            print("  No activities found.")
            return 0

        print(f"  Found {len(activities)} activities.")
        synced = 0
        cur = self.conn.cursor()

        for activity in activities:
            try:
                garmin_id = activity.get("activityId")
                if not garmin_id:
                    continue

                cur.execute("""
                    INSERT INTO garmin_activities (
                        garmin_activity_id, name, activity_type, sport_type,
                        start_time, distance_meters, duration_seconds,
                        elapsed_duration_seconds, elevation_gain_meters, calories,
                        average_hr, max_hr,
                        aerobic_training_effect, anaerobic_training_effect,
                        avg_stroke_count, avg_swolf, pool_length_meters,
                        average_power, normalized_power, max_power,
                        raw_data
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb
                    )
                    ON CONFLICT (garmin_activity_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        activity_type = EXCLUDED.activity_type,
                        sport_type = EXCLUDED.sport_type,
                        start_time = EXCLUDED.start_time,
                        distance_meters = EXCLUDED.distance_meters,
                        duration_seconds = EXCLUDED.duration_seconds,
                        elapsed_duration_seconds = EXCLUDED.elapsed_duration_seconds,
                        elevation_gain_meters = EXCLUDED.elevation_gain_meters,
                        calories = EXCLUDED.calories,
                        average_hr = EXCLUDED.average_hr,
                        max_hr = EXCLUDED.max_hr,
                        aerobic_training_effect = EXCLUDED.aerobic_training_effect,
                        anaerobic_training_effect = EXCLUDED.anaerobic_training_effect,
                        avg_stroke_count = EXCLUDED.avg_stroke_count,
                        avg_swolf = EXCLUDED.avg_swolf,
                        pool_length_meters = EXCLUDED.pool_length_meters,
                        average_power = EXCLUDED.average_power,
                        normalized_power = EXCLUDED.normalized_power,
                        max_power = EXCLUDED.max_power,
                        raw_data = EXCLUDED.raw_data,
                        synced_at = NOW()
                """, (
                    garmin_id,
                    activity.get("activityName"),
                    activity.get("activityType", {}).get("typeKey"),
                    activity.get("sportType"),
                    activity.get("startTimeLocal"),
                    activity.get("distance"),
                    activity.get("duration"),
                    activity.get("elapsedDuration"),
                    activity.get("elevationGain"),
                    activity.get("calories"),
                    activity.get("averageHR"),
                    activity.get("maxHR"),
                    activity.get("aerobicTrainingEffect"),
                    activity.get("anaerobicTrainingEffect"),
                    activity.get("avgStrokeCount"),
                    activity.get("avgSwolf"),
                    activity.get("poolLength"),
                    activity.get("avgPower"),
                    activity.get("normPower"),
                    activity.get("maxPower"),
                    json.dumps(activity),
                ))
                synced += 1
                publish_event(
                    "garmin.activity.synced",
                    str(activity["activityId"]),
                    f"garmin:activity:{activity['activityId']}:synced",
                    {
                        "activity_id": activity["activityId"],
                        "name": activity.get("activityName", ""),
                        "sport": activity.get("sportTypeId", ""),
                    },
                )
            except Exception as e:
                print(f"  [warn] Activity {activity.get('activityId')} failed: {e}")
                self.conn.rollback()
                continue

        self.conn.commit()
        print(f"  Synced {synced}/{len(activities)} activities.")
        return synced

    def sync_daily_summary(self, target_date: date) -> bool:
        """Fetch all daily metrics for a single date and upsert to garmin_daily_summary."""
        date_str = target_date.isoformat()
        print(f"  Fetching daily summary for {date_str}...")

        # Gather metrics from multiple API endpoints
        training_status = self._safe_get("get_training_status", date_str)
        training_readiness = self._safe_get("get_training_readiness", date_str)
        body_battery = self._safe_get("get_body_battery", date_str)
        hrv_data = self._safe_get("get_hrv_data", date_str)
        sleep_data = self._safe_get("get_sleep_data", date_str)
        race_predictions = self._safe_get("get_race_predictions")
        endurance_score = self._safe_get("get_endurance_score", date_str)
        stress_data = self._safe_get("get_all_day_stress", date_str)
        rhr_data = self._safe_get("get_rhr_day", date_str)
        hill_score = self._safe_get("get_hill_score", date_str)

        # Tier 2: Expanded wellness data
        user_summary = self._safe_get("get_user_summary", date_str)
        respiration = self._safe_get("get_respiration_data", date_str)
        spo2 = self._safe_get("get_spo2_data", date_str)
        intensity = self._safe_get("get_intensity_minutes_data", date_str)
        heart_rates = self._safe_get("get_heart_rates", date_str)
        bb_events = self._safe_get("get_body_battery_events", date_str)
        morning_readiness = self._safe_get("get_morning_training_readiness", date_str)

        def _dig(data: Any, *keys: str) -> Any:
            """Safely navigate nested dicts. Returns None if any key missing."""
            current = data
            for key in keys:
                if not isinstance(current, dict):
                    return None
                current = current.get(key)
                if current is None:
                    return None
            return current

        def _first_device_data(container: Any, *path: str) -> Optional[Dict]:
            """Get data for the first (primary) device from nested device maps."""
            sub = _dig(container, *path)
            if isinstance(sub, dict) and sub:
                return next(iter(sub.values()))
            return None

        # Training status — deeply nested under device IDs
        ts_device = _first_device_data(training_status,
                                        "mostRecentTrainingStatus", "latestTrainingStatusData")
        ts_status = None
        ts_load_7d = None
        ts_load_28d = None
        recovery_hours = None
        if ts_device:
            ts_phrase = ts_device.get("trainingStatusFeedbackPhrase", "")
            ts_status = ts_phrase.split("_")[0] if ts_phrase else None
            acute = ts_device.get("acuteTrainingLoadDTO") or {}
            ts_load_7d = acute.get("dailyTrainingLoadAcute")
            ts_load_28d = acute.get("dailyTrainingLoadChronic")

        ts_vo2_run = _dig(training_status, "mostRecentVO2Max", "generic", "vo2MaxPreciseValue")
        ts_vo2_cycling = _dig(training_status, "mostRecentVO2Max", "cycling", "vo2MaxPreciseValue")

        # Training readiness — returns a list
        readiness_score = None
        if isinstance(training_readiness, list) and training_readiness:
            readiness_score = training_readiness[0].get("score")
            if recovery_hours is None:
                rt = training_readiness[0].get("recoveryTime")
                # Garmin recoveryTime is minute-scale; DB column stores hours.
                if isinstance(rt, int):
                    recovery_hours = int(round(rt / 60.0))
                else:
                    recovery_hours = None

        # Body battery — list with bodyBatteryValuesArray
        bb_high = None
        bb_low = None
        bb_wake = None
        if isinstance(body_battery, list) and body_battery:
            entry = body_battery[0] if isinstance(body_battery[0], dict) else {}
            values_arr = entry.get("bodyBatteryValuesArray") or []
            bb_values = [v[1] for v in values_arr if isinstance(v, list) and len(v) >= 2 and v[1] is not None]
            if bb_values:
                bb_high = max(bb_values)
                bb_low = min(bb_values)

        # Derive wake value from sleep event (last BB reading when sleep ended)
        if isinstance(bb_events, list):
            for evt in bb_events:
                event_info = evt.get("event") or {}
                if event_info.get("eventType") == "SLEEP":
                    sleep_bb_arr = evt.get("bodyBatteryValuesArray") or []
                    # bodyBatteryLevel is at index 2 per the descriptor
                    sleep_bb_vals = [
                        v[2] for v in sleep_bb_arr
                        if isinstance(v, list) and len(v) >= 3 and v[2] is not None
                    ]
                    if sleep_bb_vals:
                        bb_wake = sleep_bb_vals[-1]
                    break
        # Fallback: if no sleep event found, use body_battery_high (peak is typically at wake)
        if bb_wake is None and bb_high is not None:
            bb_wake = bb_high

        # HRV
        hrv_status_val = _dig(hrv_data, "hrvSummary", "status")
        hrv_7d = _dig(hrv_data, "hrvSummary", "weeklyAvg")
        hrv_last = _dig(hrv_data, "hrvSummary", "lastNightAvg")

        # Sleep
        sleep_score_val = _dig(sleep_data, "dailySleepDTO", "sleepScores", "overall", "value")
        sleep_dur = _dig(sleep_data, "dailySleepDTO", "sleepTimeSeconds")
        sleep_qual = _dig(sleep_data, "dailySleepDTO", "sleepScores", "overall", "qualifierKey")

        # Race predictions — flat dict with time fields
        rp_5k = _dig(race_predictions, "time5K")
        rp_10k = _dig(race_predictions, "time10K")
        rp_half = _dig(race_predictions, "timeHalfMarathon")
        rp_marathon = _dig(race_predictions, "timeMarathon")

        # Endurance score
        endurance_val = _dig(endurance_score, "overallScore")

        # Stress
        avg_stress = _dig(stress_data, "avgStressLevel")

        # RHR — deeply nested
        rhr_metrics = _dig(rhr_data, "allMetrics", "metricsMap", "WELLNESS_RESTING_HEART_RATE")
        rhr = None
        if isinstance(rhr_metrics, list) and rhr_metrics:
            rhr = rhr_metrics[0].get("value")

        # Hill score
        hill_val = _dig(hill_score, "overallScore")

        # Tier 2: Expanded wellness extraction
        steps_val = _dig(user_summary, "totalSteps")
        total_calories_val = _dig(user_summary, "totalKilocalories")
        active_calories_val = _dig(user_summary, "activeKilocalories")
        daily_distance_val = _dig(user_summary, "totalDistanceMeters")
        active_min_mod = _dig(intensity, "moderateIntensityMinutes")
        active_min_vig = _dig(intensity, "vigorousIntensityMinutes")
        respiration_avg_val = _dig(respiration, "avgWakingRespirationValue")
        spo2_avg_val = _dig(spo2, "averageSpO2")
        spo2_low_val = _dig(spo2, "lowestSpO2")
        morning_readiness_val = _dig(morning_readiness, "score")
        bb_events_json = bb_events if bb_events else None
        hr_zones_json = _dig(heart_rates, "heartRateZones") if heart_rates else None

        # Build raw_data blob
        raw: Dict[str, Any] = {}
        if training_status:
            raw["training_status"] = training_status
        if training_readiness:
            raw["training_readiness"] = training_readiness
        if body_battery:
            raw["body_battery"] = body_battery
        if hrv_data:
            raw["hrv"] = hrv_data
        if sleep_data:
            raw["sleep"] = sleep_data
        if race_predictions:
            raw["race_predictions"] = race_predictions
        if endurance_score:
            raw["endurance_score"] = endurance_score
        if stress_data:
            raw["stress"] = stress_data
        if rhr_data:
            raw["rhr"] = rhr_data
        if hill_score:
            raw["hill_score"] = hill_score
        if user_summary:
            raw["user_summary"] = user_summary
        if respiration:
            raw["respiration"] = respiration
        if spo2:
            raw["spo2"] = spo2
        if intensity:
            raw["intensity"] = intensity
        if heart_rates:
            raw["heart_rates"] = heart_rates
        if bb_events:
            raw["body_battery_events"] = bb_events
        if morning_readiness:
            raw["morning_readiness"] = morning_readiness

        try:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO garmin_daily_summary (
                    calendar_date,
                    training_status, training_load_7d, training_load_28d,
                    vo2_max_run, vo2_max_cycling, recovery_time_hours,
                    training_readiness_score,
                    body_battery_high, body_battery_low, body_battery_at_wake,
                    hrv_status, hrv_7d_avg, hrv_last_night,
                    sleep_score, sleep_duration_seconds, sleep_quality,
                    race_prediction_5k_seconds, race_prediction_10k_seconds,
                    race_prediction_half_seconds, race_prediction_marathon_seconds,
                    endurance_score,
                    average_stress, resting_heart_rate, hill_score,
                    steps, total_calories, active_calories,
                    active_minutes_moderate, active_minutes_vigorous,
                    respiration_avg, spo2_avg, spo2_low,
                    morning_readiness_score, daily_distance_meters,
                    body_battery_events, heart_rate_zones,
                    raw_data
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
                    %s::jsonb
                )
                ON CONFLICT (calendar_date) DO UPDATE SET
                    training_status = COALESCE(EXCLUDED.training_status, garmin_daily_summary.training_status),
                    training_load_7d = COALESCE(EXCLUDED.training_load_7d, garmin_daily_summary.training_load_7d),
                    training_load_28d = COALESCE(EXCLUDED.training_load_28d, garmin_daily_summary.training_load_28d),
                    vo2_max_run = COALESCE(EXCLUDED.vo2_max_run, garmin_daily_summary.vo2_max_run),
                    vo2_max_cycling = COALESCE(EXCLUDED.vo2_max_cycling, garmin_daily_summary.vo2_max_cycling),
                    recovery_time_hours = COALESCE(EXCLUDED.recovery_time_hours, garmin_daily_summary.recovery_time_hours),
                    training_readiness_score = COALESCE(EXCLUDED.training_readiness_score, garmin_daily_summary.training_readiness_score),
                    body_battery_high = COALESCE(EXCLUDED.body_battery_high, garmin_daily_summary.body_battery_high),
                    body_battery_low = COALESCE(EXCLUDED.body_battery_low, garmin_daily_summary.body_battery_low),
                    body_battery_at_wake = COALESCE(EXCLUDED.body_battery_at_wake, garmin_daily_summary.body_battery_at_wake),
                    hrv_status = COALESCE(EXCLUDED.hrv_status, garmin_daily_summary.hrv_status),
                    hrv_7d_avg = COALESCE(EXCLUDED.hrv_7d_avg, garmin_daily_summary.hrv_7d_avg),
                    hrv_last_night = COALESCE(EXCLUDED.hrv_last_night, garmin_daily_summary.hrv_last_night),
                    sleep_score = COALESCE(EXCLUDED.sleep_score, garmin_daily_summary.sleep_score),
                    sleep_duration_seconds = COALESCE(EXCLUDED.sleep_duration_seconds, garmin_daily_summary.sleep_duration_seconds),
                    sleep_quality = COALESCE(EXCLUDED.sleep_quality, garmin_daily_summary.sleep_quality),
                    race_prediction_5k_seconds = COALESCE(EXCLUDED.race_prediction_5k_seconds, garmin_daily_summary.race_prediction_5k_seconds),
                    race_prediction_10k_seconds = COALESCE(EXCLUDED.race_prediction_10k_seconds, garmin_daily_summary.race_prediction_10k_seconds),
                    race_prediction_half_seconds = COALESCE(EXCLUDED.race_prediction_half_seconds, garmin_daily_summary.race_prediction_half_seconds),
                    race_prediction_marathon_seconds = COALESCE(EXCLUDED.race_prediction_marathon_seconds, garmin_daily_summary.race_prediction_marathon_seconds),
                    endurance_score = COALESCE(EXCLUDED.endurance_score, garmin_daily_summary.endurance_score),
                    average_stress = COALESCE(EXCLUDED.average_stress, garmin_daily_summary.average_stress),
                    resting_heart_rate = COALESCE(EXCLUDED.resting_heart_rate, garmin_daily_summary.resting_heart_rate),
                    hill_score = COALESCE(EXCLUDED.hill_score, garmin_daily_summary.hill_score),
                    steps = COALESCE(EXCLUDED.steps, garmin_daily_summary.steps),
                    total_calories = COALESCE(EXCLUDED.total_calories, garmin_daily_summary.total_calories),
                    active_calories = COALESCE(EXCLUDED.active_calories, garmin_daily_summary.active_calories),
                    active_minutes_moderate = COALESCE(EXCLUDED.active_minutes_moderate, garmin_daily_summary.active_minutes_moderate),
                    active_minutes_vigorous = COALESCE(EXCLUDED.active_minutes_vigorous, garmin_daily_summary.active_minutes_vigorous),
                    respiration_avg = COALESCE(EXCLUDED.respiration_avg, garmin_daily_summary.respiration_avg),
                    spo2_avg = COALESCE(EXCLUDED.spo2_avg, garmin_daily_summary.spo2_avg),
                    spo2_low = COALESCE(EXCLUDED.spo2_low, garmin_daily_summary.spo2_low),
                    morning_readiness_score = COALESCE(EXCLUDED.morning_readiness_score, garmin_daily_summary.morning_readiness_score),
                    daily_distance_meters = COALESCE(EXCLUDED.daily_distance_meters, garmin_daily_summary.daily_distance_meters),
                    body_battery_events = COALESCE(EXCLUDED.body_battery_events, garmin_daily_summary.body_battery_events),
                    heart_rate_zones = COALESCE(EXCLUDED.heart_rate_zones, garmin_daily_summary.heart_rate_zones),
                    raw_data = EXCLUDED.raw_data,
                    synced_at = NOW()
            """, (
                target_date,
                ts_status, ts_load_7d, ts_load_28d,
                ts_vo2_run, ts_vo2_cycling, recovery_hours,
                readiness_score,
                bb_high, bb_low, bb_wake,
                hrv_status_val, hrv_7d, hrv_last,
                sleep_score_val, sleep_dur, sleep_qual,
                rp_5k, rp_10k, rp_half, rp_marathon,
                endurance_val,
                avg_stress, rhr, hill_val,
                steps_val, total_calories_val, active_calories_val,
                active_min_mod, active_min_vig,
                respiration_avg_val, spo2_avg_val, spo2_low_val,
                morning_readiness_val, daily_distance_val,
                json.dumps(bb_events_json),
                json.dumps(hr_zones_json),
                json.dumps(raw),
            ))
            self.conn.commit()
            print(f"    Saved daily summary for {date_str}.")
            publish_event(
                "garmin.daily_summary.synced",
                f"daily-{target_date}",
                f"garmin:daily:{target_date}:synced",
                {
                    "date": str(target_date),
                    "training_readiness": readiness_score,
                },
            )
            return True
        except Exception as e:
            print(f"    [error] Failed to save daily summary for {date_str}: {e}")
            self.conn.rollback()
            return False

    def sync_daily_range(self, start: date, end: date) -> int:
        """Sync daily summaries for a date range."""
        synced = 0
        current = start
        while current <= end:
            if self.sync_daily_summary(current):
                synced += 1
            current += timedelta(days=1)
        return synced

    def sync_biometrics(self, target_date: date) -> bool:
        """Fetch athlete biometrics and upsert to athlete_biometrics."""
        date_str = target_date.isoformat()
        print(f"\n  Fetching biometrics for {date_str}...")

        # Gather data from multiple API endpoints
        user_profile = self._safe_get("get_user_profile")
        body_comp = self._safe_get("get_body_composition", date_str)
        fitness_age = self._safe_get("get_fitnessage_data", date_str)
        max_metrics = self._safe_get("get_max_metrics", date_str)
        lactate_threshold = self._safe_get("get_lactate_threshold", latest=True)
        cycling_ftp = self._safe_get("get_cycling_ftp")
        personal_records = self._safe_get("get_personal_record")
        goals = self._safe_get("get_goals", status="active")

        def _dig(data: Any, *keys: str) -> Any:
            """Safely navigate nested dicts. Returns None if any key missing."""
            current = data
            for key in keys:
                if not isinstance(current, dict):
                    return None
                current = current.get(key)
                if current is None:
                    return None
            return current

        # Weight / body composition
        weight_kg = _dig(body_comp, "weight")
        # Garmin API returns weight in grams — convert to kg
        if weight_kg is not None and weight_kg > 500:
            weight_kg = weight_kg / 1000.0
        body_fat_pct = _dig(body_comp, "bodyFat")
        muscle_mass_kg = _dig(body_comp, "muscleMass")
        if muscle_mass_kg is not None and muscle_mass_kg > 500:
            muscle_mass_kg = muscle_mass_kg / 1000.0
        bmi_val = _dig(body_comp, "bmi")

        # Fitness age
        fitness_age_val = _dig(fitness_age, "fitnessAge")
        actual_age_val = _dig(fitness_age, "chronologicalAge")

        # Lactate threshold
        lt_hr = _dig(lactate_threshold, "lactateThreshold", "heartRateValue")
        lt_pace = _dig(lactate_threshold, "lactateThreshold", "paceValue")

        # Cycling FTP
        ftp_val = _dig(cycling_ftp, "ftpValue") if isinstance(cycling_ftp, dict) else None
        if ftp_val is None and isinstance(cycling_ftp, (int, float)):
            ftp_val = cycling_ftp

        # VO2 max detailed — store entire max_metrics response as JSONB
        vo2_detailed = None
        if max_metrics:
            vo2_detailed = max_metrics

        # Build raw_data blob
        raw: Dict[str, Any] = {}
        if user_profile:
            raw["user_profile"] = user_profile
        if body_comp:
            raw["body_composition"] = body_comp
        if fitness_age:
            raw["fitness_age"] = fitness_age
        if max_metrics:
            raw["max_metrics"] = max_metrics
        if lactate_threshold:
            raw["lactate_threshold"] = lactate_threshold
        if cycling_ftp:
            raw["cycling_ftp"] = cycling_ftp
        if personal_records:
            raw["personal_records"] = personal_records
        if goals:
            raw["goals"] = goals

        try:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO athlete_biometrics (
                    date, weight_kg, body_fat_pct, muscle_mass_kg, bmi,
                    fitness_age, actual_age,
                    lactate_threshold_hr, lactate_threshold_pace,
                    cycling_ftp, vo2_max_detailed,
                    raw_data
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb
                )
                ON CONFLICT (date) DO UPDATE SET
                    weight_kg = EXCLUDED.weight_kg,
                    body_fat_pct = EXCLUDED.body_fat_pct,
                    muscle_mass_kg = EXCLUDED.muscle_mass_kg,
                    bmi = EXCLUDED.bmi,
                    fitness_age = EXCLUDED.fitness_age,
                    actual_age = EXCLUDED.actual_age,
                    lactate_threshold_hr = EXCLUDED.lactate_threshold_hr,
                    lactate_threshold_pace = EXCLUDED.lactate_threshold_pace,
                    cycling_ftp = EXCLUDED.cycling_ftp,
                    vo2_max_detailed = EXCLUDED.vo2_max_detailed,
                    raw_data = EXCLUDED.raw_data,
                    synced_at = NOW()
            """, (
                target_date,
                weight_kg, body_fat_pct, muscle_mass_kg, bmi_val,
                fitness_age_val, actual_age_val,
                lt_hr, lt_pace,
                ftp_val,
                json.dumps(vo2_detailed),
                json.dumps(raw),
            ))
            self.conn.commit()
            print(f"    Saved biometrics for {date_str}.")
            publish_event(
                "garmin.biometrics.synced",
                f"bio-{target_date}",
                f"garmin:biometrics:{target_date}:synced",
                {
                    "date": str(target_date),
                    "weight_kg": weight_kg,
                },
            )
            return True
        except Exception as e:
            print(f"    [error] Failed to save biometrics for {date_str}: {e}")
            self.conn.rollback()
            return False

    def sync_training_plans(self) -> int:
        """Fetch training plans and planned workouts, upsert to DB."""
        print("\n  Fetching training plans...")
        plans = self._safe_get("get_training_plans")

        if not plans:
            print("    No training plans found.")
            return 0

        if not isinstance(plans, list):
            plans = [plans]

        synced = 0
        cur = self.conn.cursor()

        for plan in plans:
            try:
                plan_id = str(plan.get("trainingPlanId") or plan.get("id", ""))
                if not plan_id:
                    continue

                cur.execute("""
                    INSERT INTO garmin_training_plans (
                        garmin_plan_id, name, plan_type,
                        start_date, end_date, raw_data
                    ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (garmin_plan_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        plan_type = EXCLUDED.plan_type,
                        start_date = EXCLUDED.start_date,
                        end_date = EXCLUDED.end_date,
                        raw_data = EXCLUDED.raw_data,
                        synced_at = NOW()
                """, (
                    plan_id,
                    plan.get("name") or plan.get("trainingPlanName"),
                    plan.get("type") or plan.get("trainingPlanType"),
                    plan.get("startDate"),
                    plan.get("endDate"),
                    json.dumps(plan),
                ))
                synced += 1
            except Exception as e:
                print(f"    [warn] Training plan {plan_id} failed: {e}")
                self.conn.rollback()
                continue

        # Fetch planned workouts
        print("  Fetching planned workouts...")
        workouts = self._safe_get("get_workouts", 0, 200)
        workout_count = 0

        if workouts and isinstance(workouts, list):
            for workout in workouts:
                try:
                    workout_id = str(workout.get("workoutId") or workout.get("id", ""))
                    if not workout_id:
                        continue

                    cur.execute("""
                        INSERT INTO garmin_planned_workouts (
                            garmin_workout_id, plan_id, date,
                            discipline, workout_type, description,
                            target_data, raw_data
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                        ON CONFLICT (garmin_workout_id) DO UPDATE SET
                            plan_id = EXCLUDED.plan_id,
                            date = EXCLUDED.date,
                            discipline = EXCLUDED.discipline,
                            workout_type = EXCLUDED.workout_type,
                            description = EXCLUDED.description,
                            target_data = EXCLUDED.target_data,
                            raw_data = EXCLUDED.raw_data,
                            synced_at = NOW()
                    """, (
                        workout_id,
                        str(workout.get("trainingPlanId", "")) or None,
                        workout.get("scheduledDate") or workout.get("date"),
                        str(workout.get("sportType") or workout.get("discipline") or ""),
                        str(workout.get("workoutType") or workout.get("subSportType") or ""),
                        str(workout.get("description") or workout.get("workoutName") or ""),
                        json.dumps(workout.get("targetData") or workout.get("steps"), default=str),
                        json.dumps(workout, default=str),
                    ))
                    workout_count += 1
                except Exception as e:
                    print(f"    [warn] Workout {workout_id} failed: {e}")
                    self.conn.rollback()
                    continue

        self.conn.commit()
        print(f"    Synced {synced} plans, {workout_count} workouts.")
        return synced

    def sync_activity_details(self, days_back: int = 14) -> int:
        """Fetch detail enrichment for recent activities missing details."""
        print(f"\n  Fetching activity details (last {days_back} days)...")

        cur = self.conn.cursor()
        cur.execute("""
            SELECT ga.garmin_activity_id
            FROM garmin_activities ga
            LEFT JOIN activity_details ad ON ga.garmin_activity_id = ad.garmin_activity_id
            WHERE ga.start_time >= NOW() - INTERVAL '%s days'
              AND ad.id IS NULL
            ORDER BY ga.start_time DESC
        """, (days_back,))
        rows = cur.fetchall()

        if not rows:
            print("    No activities need detail enrichment.")
            return 0

        print(f"    Found {len(rows)} activities needing details.")
        synced = 0

        for (aid,) in rows:
            try:
                aid_str = str(aid)
                splits = self._safe_get("get_activity_splits", aid_str)
                hr_zones = self._safe_get("get_activity_hr_in_timezones", aid_str)
                weather = self._safe_get("get_activity_weather", aid_str)
                gear = self._safe_get("get_activity_gear", aid_str)

                gear_uuid = None
                if isinstance(gear, list) and gear:
                    gear_uuid = gear[0].get("uuid") or gear[0].get("gearUuid")

                raw: Dict[str, Any] = {}
                if splits:
                    raw["splits"] = splits
                if hr_zones:
                    raw["hr_zones"] = hr_zones
                if weather:
                    raw["weather"] = weather
                if gear:
                    raw["gear"] = gear

                cur.execute("""
                    INSERT INTO activity_details (
                        id, garmin_activity_id, splits, hr_zones,
                        weather, gear_uuid, raw_data
                    ) VALUES (gen_random_uuid(), %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::jsonb)
                    ON CONFLICT (garmin_activity_id) DO UPDATE SET
                        splits = EXCLUDED.splits,
                        hr_zones = EXCLUDED.hr_zones,
                        weather = EXCLUDED.weather,
                        gear_uuid = EXCLUDED.gear_uuid,
                        raw_data = EXCLUDED.raw_data,
                        synced_at = NOW()
                """, (
                    aid,
                    json.dumps(splits),
                    json.dumps(hr_zones),
                    json.dumps(weather),
                    gear_uuid,
                    json.dumps(raw),
                ))
                synced += 1
            except Exception as e:
                print(f"    [warn] Activity detail {aid} failed: {e}")
                self.conn.rollback()
                continue

        self.conn.commit()
        print(f"    Enriched {synced}/{len(rows)} activities.")
        return synced

    def sync_gear(self) -> int:
        """Fetch gear inventory and stats, upsert to gear table."""
        print("\n  Fetching gear...")

        # Get profile number from garth profile (most reliable source)
        profile_number = None
        try:
            garth_profile = self.client.garth.profile
            if garth_profile:
                profile_number = garth_profile.get("profileId") or garth_profile.get("displayName")
        except Exception:
            pass

        if not profile_number:
            profile = self._safe_get("get_user_profile")
            if profile:
                profile_number = profile.get("profileNumber") or profile.get("displayName")

        if not profile_number:
            print("    [warn] No profile number found.")
            return 0

        gear_list = self._safe_get("get_gear", profile_number)
        if not gear_list:
            print("    No gear found.")
            return 0

        if not isinstance(gear_list, list):
            gear_list = [gear_list]

        synced = 0
        cur = self.conn.cursor()

        for item in gear_list:
            try:
                gear_uuid = str(item.get("uuid") or item.get("gearUuid", ""))
                if not gear_uuid:
                    continue

                # Fetch stats for this gear item
                stats = self._safe_get("get_gear_stats", gear_uuid)
                total_distance = None
                total_acts = None
                if isinstance(stats, dict):
                    total_distance = stats.get("totalDistance")
                    if total_distance is not None:
                        total_distance = total_distance / 1000.0  # meters to km
                    total_acts = stats.get("totalActivities")
                elif isinstance(stats, list) and stats:
                    s = stats[0] if isinstance(stats[0], dict) else {}
                    total_distance = s.get("totalDistance")
                    if total_distance is not None:
                        total_distance = total_distance / 1000.0
                    total_acts = s.get("totalActivities")

                max_dist = item.get("maximumMeters")
                if max_dist is not None:
                    max_dist = max_dist / 1000.0

                raw: Dict[str, Any] = {"gear": item}
                if stats:
                    raw["stats"] = stats

                cur.execute("""
                    INSERT INTO gear (
                        id, garmin_gear_uuid, name, gear_type, brand, model,
                        date_begin, max_distance_km,
                        total_distance_km, total_activities, raw_data
                    ) VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (garmin_gear_uuid) DO UPDATE SET
                        name = EXCLUDED.name,
                        gear_type = EXCLUDED.gear_type,
                        brand = EXCLUDED.brand,
                        model = EXCLUDED.model,
                        date_begin = EXCLUDED.date_begin,
                        max_distance_km = EXCLUDED.max_distance_km,
                        total_distance_km = EXCLUDED.total_distance_km,
                        total_activities = EXCLUDED.total_activities,
                        raw_data = EXCLUDED.raw_data,
                        synced_at = NOW()
                """, (
                    gear_uuid,
                    item.get("displayName") or item.get("name"),
                    item.get("gearTypeName") or item.get("gearType"),
                    item.get("customMakeModel") or item.get("brand"),
                    item.get("gearModelName") or item.get("model"),
                    item.get("dateBegin"),
                    max_dist,
                    total_distance,
                    total_acts,
                    json.dumps(raw),
                ))
                synced += 1
            except Exception as e:
                print(f"    [warn] Gear {gear_uuid} failed: {e}")
                self.conn.rollback()
                continue

        self.conn.commit()
        print(f"    Synced {synced}/{len(gear_list)} gear items.")
        return synced

    def sync_calendar(self, months_ahead: int = 5) -> Dict[str, int]:
        """Fetch Garmin calendar items and sync races + planned workouts to app tables."""
        print(f"\n  Syncing calendar (next {months_ahead} months)...")

        cur = self.conn.cursor()

        # Ensure app tables have garmin linking columns (idempotent)
        cur.execute("""
            ALTER TABLE planned_workouts ADD COLUMN IF NOT EXISTS target_duration INTEGER;
            ALTER TABLE planned_workouts ADD COLUMN IF NOT EXISTS target_distance DOUBLE PRECISION;
            ALTER TABLE planned_workouts ADD COLUMN IF NOT EXISTS target_hr_zone INTEGER;
            ALTER TABLE planned_workouts ADD COLUMN IF NOT EXISTS garmin_detail_json JSONB;
            ALTER TABLE planned_workouts ADD COLUMN IF NOT EXISTS garmin_workout_uuid TEXT UNIQUE;
            ALTER TABLE planned_workouts ADD COLUMN IF NOT EXISTS garmin_workout_id TEXT;
            CREATE UNIQUE INDEX IF NOT EXISTS idx_planned_workouts_garmin_wid
                ON planned_workouts(garmin_workout_id) WHERE garmin_workout_id IS NOT NULL;
            ALTER TABLE races ADD COLUMN IF NOT EXISTS garmin_event_uuid TEXT UNIQUE;
            ALTER TABLE training_plan ADD COLUMN IF NOT EXISTS garmin_plan_id TEXT UNIQUE;
        """)
        self.conn.commit()

        # Fetch calendar items across months
        today = date.today()
        assistant_owned_mode = self._integration_settings.plan_ownership_mode == "assistant"
        fetched_window_end = today
        all_items: List[Dict] = []
        for offset in range(months_ahead + 1):
            m = today.month + offset
            y = today.year + (m - 1) // 12
            m = ((m - 1) % 12) + 1
            if m == 12:
                month_end = date(y + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(y, m + 1, 1) - timedelta(days=1)
            if month_end > fetched_window_end:
                fetched_window_end = month_end
            try:
                resp = self.client.garth.connectapi(
                    f'/calendar-service/year/{y}/month/{m - 1}'
                )
                self._delay()
                items = resp.get('calendarItems', []) if isinstance(resp, dict) else []
                all_items.extend(items)
            except Exception as e:
                print(f"    [warn] Calendar fetch for {y}-{m:02d} failed: {e}")

        print(f"    Fetched {len(all_items)} total calendar items.")

        # Discipline mapping from Garmin sportTypeKey
        discipline_map = {
            'running': 'running',
            'cycling': 'cycling',
            'swimming': 'swimming',
            'strength_training': 'strength',
            'yoga': 'flexibility',
        }

        races_synced = 0
        workouts_synced = 0
        plans_synced = 0
        plan_uuid_map: Dict[str, str] = {}  # garmin_plan_id -> app training_plan.id
        adaptive_task_workouts: Dict[str, Dict[str, Dict[str, Any]]] = {}
        active_future_workout_uuids: Set[str] = set()
        details_horizon = today + timedelta(days=2)

        def _as_float(value: Any) -> Optional[float]:
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def _as_int(value: Any) -> Optional[int]:
            as_float = _as_float(value)
            if as_float is None:
                return None
            return int(round(as_float))

        def _extract_target_fields(item: Dict[str, Any]) -> Tuple[Optional[int], Optional[float], Optional[int]]:
            target_duration = _as_int(item.get("duration"))
            target_distance = _as_float(item.get("distance"))
            completion_target = item.get("completionTarget")

            if isinstance(completion_target, dict):
                if target_duration is None:
                    target_duration = _as_int(
                        completion_target.get("duration")
                        or completion_target.get("targetDuration")
                        or completion_target.get("durationSeconds")
                    )
                if target_distance is None:
                    target_distance = _as_float(
                        completion_target.get("distance")
                        or completion_target.get("targetDistance")
                        or completion_target.get("distanceMeters")
                    )

            if target_duration is not None and target_duration > 100_000:
                # Some Garmin payloads use milliseconds; normalize to seconds.
                target_duration = int(round(target_duration / 1000.0))

            target_hr_zone = None
            if isinstance(completion_target, dict):
                target_hr_zone = _as_int(
                    completion_target.get("targetHrZone")
                    or completion_target.get("hrZone")
                    or completion_target.get("zoneNumber")
                )

            return target_duration, target_distance, target_hr_zone

        def _safe_connectapi(path: str) -> Optional[Any]:
            try:
                response = self.client.garth.connectapi(path)
                self._delay()
                return response
            except Exception as e:
                print(f"    [warn] Garmin endpoint failed ({path}): {e}")
                return None

        def _has_payload(data: Any) -> bool:
            if data is None:
                return False
            if isinstance(data, (list, dict)):
                return len(data) > 0
            return True

        # Pass 1: Sync race events
        for item in all_items:
            if not item.get('isRace'):
                continue
            title = item.get('title')
            item_date = item.get('date')
            event_uuid = item.get('shareableEventUuid') or f"race-{item_date}-{title}"
            if not title or not item_date:
                continue

            # Determine distance_type from title or completionTarget
            distance_type = 'other'
            title_lower = title.lower()
            if '70.3' in title_lower or 'half ironman' in title_lower:
                distance_type = '70.3'
            elif 'ironman' in title_lower or '140.6' in title_lower:
                distance_type = '140.6'
            elif 'marathon' in title_lower and 'half' not in title_lower:
                distance_type = 'marathon'
            elif 'half marathon' in title_lower:
                distance_type = 'half_marathon'
            elif 'olympic' in title_lower:
                distance_type = 'olympic'
            elif 'sprint' in title_lower and 'triathlon' in title_lower:
                distance_type = 'sprint_tri'

            location = item.get('location')
            notes = location if location else None

            try:
                cur.execute("""
                    INSERT INTO races (id, name, date, distance_type, notes, garmin_event_uuid, created_at)
                    VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (garmin_event_uuid) DO UPDATE SET
                        name = EXCLUDED.name,
                        date = EXCLUDED.date,
                        distance_type = EXCLUDED.distance_type,
                        notes = EXCLUDED.notes
                """, (title, item_date, distance_type, notes, event_uuid))
                races_synced += 1
            except Exception as e:
                print(f"    [warn] Race '{title}' failed: {e}")
                self.conn.rollback()

        self.conn.commit()

        # Pass 2: Ensure training_plan rows exist for referenced plans
        plan_ids_seen = set()
        for item in all_items:
            tp_id = item.get('trainingPlanId')
            if tp_id and tp_id not in plan_ids_seen:
                plan_ids_seen.add(tp_id)

        generic_workout_records = [
            record
            for item in all_items
            if (record := _calendar_workout_record(item, today=today)) is not None
            and item.get("itemType") == "workout"
            and not assistant_owned_mode
        ]
        if generic_workout_records:
            # These ordinary Garmin workouts are the assistant's plan after
            # writeback, but Garmin does not attach an assistant plan ID.
            cur.execute(
                """
                SELECT id FROM training_plan
                WHERE source = 'assistant'
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            assistant_plan_row = cur.fetchone()
            if assistant_plan_row:
                plan_uuid_map["0"] = str(assistant_plan_row[0])
            else:
                plan_start = min(record["date"] for record in generic_workout_records)
                plan_end = max(record["date"] for record in generic_workout_records)
                cur.execute(
                    """
                    INSERT INTO training_plan (
                        id, name, source, race_id, start_date, end_date, created_at
                    )
                    VALUES (
                        gen_random_uuid(), 'Recovered Assistant Plan', 'assistant',
                        (SELECT id FROM races ORDER BY date LIMIT 1), %s, %s, NOW()
                    )
                    RETURNING id
                    """,
                    (plan_start, plan_end),
                )
                recovered_plan_row = cur.fetchone()
                if recovered_plan_row:
                    plan_uuid_map["0"] = str(recovered_plan_row[0])
                    plans_synced += 1
            self.conn.commit()

        # Find training plan names from trainingPlan-type calendar items
        plan_names: Dict[int, str] = {}
        for item in all_items:
            if item.get('itemType') == 'trainingPlan' and item.get('title'):
                # Attempt to associate with a trainingPlanId
                # The trainingPlan calendar item doesn't always have trainingPlanId,
                # but we can match by proximity
                plan_names[item.get('trainingPlanId') or 0] = item.get('title', '')

        for tp_id in plan_ids_seen:
            tp_id_str = str(tp_id)
            plan_name = plan_names.get(tp_id, f"Garmin Plan {tp_id}")
            # Also check if there's a matching trainingPlan item title
            if not plan_names.get(tp_id):
                for item in all_items:
                    if item.get('itemType') == 'trainingPlan':
                        plan_name = item.get('title', plan_name)
                        break

            # Link to race if we have one
            cur.execute("SELECT id FROM races ORDER BY date LIMIT 1")
            race_row = cur.fetchone()
            race_id = race_row[0] if race_row else None

            try:
                cur.execute("""
                    INSERT INTO training_plan (id, name, source, race_id, garmin_plan_id, created_at)
                    VALUES (gen_random_uuid(), %s, 'garmin', %s, %s, NOW())
                    ON CONFLICT (garmin_plan_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        race_id = EXCLUDED.race_id
                    RETURNING id
                """, (plan_name, race_id, tp_id_str))
                row = cur.fetchone()
                if row:
                    plan_uuid_map[tp_id_str] = str(row[0])
                plans_synced += 1
            except Exception as e:
                print(f"    [warn] Training plan {tp_id} failed: {e}")
                self.conn.rollback()

        self.conn.commit()

        # Pass 2b: Fetch adaptive task metadata (duration/distance/description)
        for tp_id in sorted(plan_ids_seen):
            tp_id_str = str(tp_id)
            adaptive_plan = self._safe_get("get_adaptive_training_plan_by_id", tp_id)
            if not isinstance(adaptive_plan, dict):
                continue
            task_list = adaptive_plan.get("taskList")
            if not isinstance(task_list, list):
                continue

            by_workout_uuid: Dict[str, Dict[str, Any]] = {}
            for task in task_list:
                if not isinstance(task, dict):
                    continue
                task_workout = task.get("taskWorkout")
                if not isinstance(task_workout, dict):
                    continue
                task_workout_uuid = task_workout.get("workoutUuid")
                if not task_workout_uuid:
                    continue

                by_workout_uuid[str(task_workout_uuid)] = {
                    "task_workout": task_workout,
                    "task_meta": {
                        "calendarDate": task.get("calendarDate"),
                        "weekId": task.get("weekId"),
                        "dayOfWeekId": task.get("dayOfWeekId"),
                        "workoutOrder": task.get("workoutOrder"),
                        "priority": task.get("priority"),
                    },
                }

            if by_workout_uuid:
                adaptive_task_workouts[tp_id_str] = by_workout_uuid

        # Pass 3: Sync planned workouts, including ordinary workouts written
        # by the assistant into Garmin's calendar.
        for item in all_items:
            record = _calendar_workout_record(item, today=today)
            if record is None:
                continue
            if item.get("itemType") == "workout" and assistant_owned_mode:
                continue

            workout_uuid = record["workout_uuid"]
            item_date = record["date"].isoformat()
            title = record["title"]
            workout_type = (
                record["workout_type"]
                if item.get("itemType") == "workout"
                else title
            )
            sport_key = record["discipline"]
            discipline = discipline_map.get(sport_key, sport_key or 'other')
            tp_id_str = record["training_plan_id"]
            plan_id = plan_uuid_map.get(tp_id_str)
            adaptive_task_row = adaptive_task_workouts.get(tp_id_str, {}).get(workout_uuid, {})
            adaptive_task_workout = (
                adaptive_task_row.get("task_workout")
                if isinstance(adaptive_task_row, dict)
                else None
            )
            workout_id = item.get("workoutId")
            if workout_id is None and isinstance(adaptive_task_workout, dict):
                workout_id = adaptive_task_workout.get("workoutId")
            workout_schedule_id = None
            if isinstance(adaptive_task_workout, dict):
                workout_schedule_id = adaptive_task_workout.get("workoutScheduleId")

            # Determine status based on date
            try:
                workout_date = date.fromisoformat(item_date) if item_date else None
            except ValueError:
                workout_date = None

            status = 'upcoming'
            if workout_date and workout_date < today:
                status = 'missed'  # Past workouts not matched to activity

            if workout_date and workout_date >= today:
                active_future_workout_uuids.add(workout_uuid)

            target_duration, target_distance, target_hr_zone = _extract_target_fields(item)
            if isinstance(adaptive_task_workout, dict):
                if target_duration is None:
                    target_duration = _as_int(adaptive_task_workout.get("estimatedDurationInSecs"))
                if target_distance is None:
                    target_distance = _as_float(adaptive_task_workout.get("estimatedDistanceInMeters"))

            detail_payload: Dict[str, Any] = {"calendar_item": item}
            if isinstance(adaptive_task_workout, dict):
                detail_payload["adaptive_task_workout"] = adaptive_task_workout
                task_meta = adaptive_task_row.get("task_meta")
                if isinstance(task_meta, dict):
                    detail_payload["adaptive_task_meta"] = task_meta
            if workout_date and today <= workout_date <= details_horizon:
                if workout_id:
                    workout_definition = self._safe_get("get_workout_by_id", workout_id)
                    if _has_payload(workout_definition):
                        detail_payload["workout_definition"] = workout_definition
                if workout_schedule_id:
                    schedule_payload = _safe_connectapi(
                        f"/workout-service/schedule/{workout_schedule_id}"
                    )
                    if _has_payload(schedule_payload):
                        detail_payload["workout_schedule"] = schedule_payload
                        if isinstance(schedule_payload, dict):
                            schedule_workout_id = schedule_payload.get("workoutId")
                            if schedule_workout_id and not detail_payload.get("workout_definition"):
                                workout_definition = self._safe_get(
                                    "get_workout_by_id", schedule_workout_id
                                )
                                if _has_payload(workout_definition):
                                    detail_payload["workout_definition"] = workout_definition
                for endpoint_name in ("details", "steps", "segments"):
                    endpoint_payload = _safe_connectapi(
                        f"/workout-service/workout/{workout_uuid}/{endpoint_name}"
                    )
                    if _has_payload(endpoint_payload):
                        detail_payload[f"workout_{endpoint_name}"] = endpoint_payload

            description_text = title
            if isinstance(adaptive_task_workout, dict):
                description_text = (
                    adaptive_task_workout.get("workoutDescription")
                    or adaptive_task_workout.get("workoutPhrase")
                    or title
                )

            workout_id_str = str(workout_id) if workout_id else None

            try:
                detail_json = json.dumps(detail_payload, default=str)
                cur.execute("""
                    UPDATE planned_workouts
                    SET plan_id = %s,
                        target_duration = %s,
                        target_distance = %s,
                        target_hr_zone = %s,
                        description = %s,
                        status = %s,
                        garmin_workout_uuid = %s,
                        garmin_workout_id = %s,
                        garmin_detail_json = %s::jsonb,
                        created_at = NOW()
                    WHERE id = (
                        SELECT id
                        FROM planned_workouts
                        WHERE date = %s
                          AND discipline = %s
                          AND workout_type = %s
                          AND status = 'upcoming'
                          AND garmin_workout_uuid IS NULL
                          AND (garmin_workout_id IS NULL OR garmin_workout_id = %s OR %s IS NULL)
                          AND NOT EXISTS (
                              SELECT 1
                              FROM planned_workouts existing
                              WHERE existing.garmin_workout_uuid = %s
                          )
                        ORDER BY
                          (garmin_workout_id IS NOT NULL) DESC,
                          created_at DESC
                        LIMIT 1
                    )
                """, (
                    plan_id,
                    target_duration,
                    target_distance,
                    target_hr_zone,
                    description_text,
                    status,
                    workout_uuid,
                    workout_id_str,
                    detail_json,
                    item_date,
                    discipline,
                    workout_type,
                    workout_id_str,
                    workout_id_str,
                    workout_uuid,
                ))
                if cur.rowcount == 0:
                    cur.execute("""
                        INSERT INTO planned_workouts (
                            id, plan_id, date, discipline, workout_type,
                            target_duration, target_distance, target_hr_zone,
                            description, status, garmin_workout_uuid,
                            garmin_workout_id, garmin_detail_json, created_at
                        ) VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                        ON CONFLICT (garmin_workout_uuid) DO UPDATE SET
                            plan_id = EXCLUDED.plan_id,
                            date = EXCLUDED.date,
                            discipline = EXCLUDED.discipline,
                            workout_type = EXCLUDED.workout_type,
                            target_duration = EXCLUDED.target_duration,
                            target_distance = EXCLUDED.target_distance,
                            target_hr_zone = EXCLUDED.target_hr_zone,
                            description = EXCLUDED.description,
                            status = EXCLUDED.status,
                            garmin_workout_id = EXCLUDED.garmin_workout_id,
                            garmin_detail_json = EXCLUDED.garmin_detail_json
                    """, (
                        plan_id,
                        item_date,
                        discipline,
                        workout_type,
                        target_duration,
                        target_distance,
                        target_hr_zone,
                        description_text,
                        status,
                        workout_uuid,
                        workout_id_str,
                        detail_json,
                    ))
                if item.get("itemType") == "workout":
                    cur.execute(
                        """
                        INSERT INTO assistant_plan_entries (
                            id, planned_workout_id, garmin_workout_id,
                            garmin_sync_status, created_at, updated_at
                        )
                        SELECT
                            gen_random_uuid(), id, %s, 'recovered', NOW(), NOW()
                        FROM planned_workouts
                        WHERE garmin_workout_uuid = %s
                        ON CONFLICT (planned_workout_id) DO NOTHING
                        """,
                        (workout_id_str, workout_uuid),
                    )
                workouts_synced += 1
            except Exception as e:
                print(f"    [warn] Workout '{title}' on {item_date} failed: {e}")
                self.conn.rollback()

        # Remove Garmin-linked future workouts that no longer exist in Garmin's
        # current calendar response for the fetched window.
        stale_removed = 0
        if active_future_workout_uuids:
            cur.execute("""
                DELETE FROM planned_workouts
                WHERE date >= %s
                  AND date <= %s
                  AND status = 'upcoming'
                  AND garmin_workout_uuid IS NOT NULL
                  AND NOT (garmin_workout_uuid = ANY(%s))
            """, (today, fetched_window_end, sorted(active_future_workout_uuids)))
            stale_removed = cur.rowcount
        else:
            cur.execute("""
                DELETE FROM planned_workouts
                WHERE date >= %s
                  AND date <= %s
                  AND status = 'upcoming'
                  AND garmin_workout_uuid IS NOT NULL
            """, (today, fetched_window_end))
            stale_removed = cur.rowcount

        self.conn.commit()
        if stale_removed:
            print(f"    Removed {stale_removed} stale upcoming workout rows.")
        print(f"    Synced {races_synced} races, {plans_synced} plans, {workouts_synced} workouts.")
        return {
            "races": races_synced,
            "plans": plans_synced,
            "workouts": workouts_synced,
            "stale_removed": stale_removed,
        }

    def full_sync(
        self,
        days_back: int = 3,
        comprehensive: bool = False,
        include_calendar: bool = False,
    ) -> Dict[str, Any]:
        """Run full sync: activities + daily summaries + optional biometrics."""
        print(f"\n=== Garmin Sync (last {days_back} days) ===\n")

        self.ensure_schema()

        activities_synced = self.sync_activities(days_back)

        print(f"\nSyncing daily summaries...")
        end_date = date.today()
        start_date = end_date - timedelta(days=days_back)
        days_synced = self.sync_daily_range(start_date, end_date)

        results: Dict[str, Any] = {
            "activities_synced": activities_synced,
            "days_synced": days_synced,
            "days_back": days_back,
        }

        if comprehensive:
            print(f"\nSyncing biometrics...")
            biometrics_ok = self.sync_biometrics(date.today())
            results["biometrics_synced"] = biometrics_ok

            print(f"\nSyncing training plans...")
            plans_synced = self.sync_training_plans()
            results["training_plans_synced"] = plans_synced

            print(f"\nSyncing activity details...")
            details_synced = self.sync_activity_details(days_back)
            results["activity_details_synced"] = details_synced

            print(f"\nSyncing gear...")
            gear_synced = self.sync_gear()
            results["gear_synced"] = gear_synced

        if comprehensive or include_calendar:
            print(f"\nSyncing calendar to app tables...")
            cal_results = self.sync_calendar(
                months_ahead=self._integration_settings.calendar_months_ahead
            )
            results["calendar_synced"] = cal_results

        summary = f"\n=== Done: {activities_synced} activities, {days_synced} daily summaries"
        if comprehensive:
            summary += f", biometrics={'OK' if results.get('biometrics_synced') else 'FAILED'}"
            summary += f", plans={plans_synced}, details={details_synced}, gear={gear_synced}"
        if comprehensive or include_calendar:
            cal = results.get("calendar_synced", {})
            summary += f", calendar={cal.get('races', 0)}R/{cal.get('workouts', 0)}W"
        summary += " ==="
        print(summary)
        return results

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Garmin Connect data to PostgreSQL")
    parser.add_argument(
        "--days-back", type=int, default=3,
        help="Number of days to sync (default: 3)"
    )
    parser.add_argument(
        "--activities-only", action="store_true",
        help="Only sync activities, skip daily summaries"
    )
    parser.add_argument(
        "--daily-only", action="store_true",
        help="Only sync daily summaries, skip activities"
    )
    parser.add_argument(
        "--calendar-only", action="store_true",
        help="Only sync Garmin calendar (planned workouts + races)"
    )
    parser.add_argument(
        "--comprehensive", action="store_true",
        help="Include all extended sync tasks (biometrics, plans, details, gear, calendar)"
    )
    parser.add_argument(
        "--calendar", action="store_true",
        help="Include Garmin calendar sync (races and planned workouts)"
    )
    parser.add_argument(
        "--loop", action="store_true",
        help="Run continuously, syncing every --interval hours"
    )
    parser.add_argument(
        "--interval", type=float, default=6.0,
        help="Hours between syncs when using --loop (default: 6)"
    )
    args = parser.parse_args()

    if args.loop:
        print(f"Starting Garmin sync loop (every {args.interval}h)...")
        while True:
            sync = GarminSyncClient()
            try:
                if args.calendar_only:
                    sync.ensure_schema()
                    sync.sync_calendar(
                        months_ahead=sync._integration_settings.calendar_months_ahead
                    )
                else:
                    sync.full_sync(
                        args.days_back,
                        comprehensive=args.comprehensive,
                        include_calendar=args.calendar,
                    )
            except GarminSyncError as e:
                print(f"\nSync error: {e}")
            except Exception as e:
                print(f"\nUnexpected error: {e}")
            finally:
                sync.close()

            sleep_seconds = args.interval * 3600
            print(f"\nSleeping {args.interval}h until next sync...")
            time.sleep(sleep_seconds)
    else:
        sync = GarminSyncClient()
        try:
            if args.calendar_only:
                sync.ensure_schema()
                sync.sync_calendar(
                    months_ahead=sync._integration_settings.calendar_months_ahead
                )
            elif args.activities_only:
                sync.ensure_schema()
                sync.sync_activities(args.days_back)
            elif args.daily_only:
                sync.ensure_schema()
                end_date = date.today()
                start_date = end_date - timedelta(days=args.days_back)
                sync.sync_daily_range(start_date, end_date)
            else:
                sync.full_sync(
                    args.days_back,
                    comprehensive=args.comprehensive,
                    include_calendar=args.calendar,
                )
        except GarminSyncError as e:
            print(f"\nError: {e}")
            sys.exit(1)
        finally:
            sync.close()


if __name__ == "__main__":
    main()
