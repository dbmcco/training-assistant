from datetime import date

import pytest

from src.db.models import GarminDailySummary
from src.routers.dashboard import _has_recovery_metrics, _select_latest_dashboard_summary


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, values):
        self._values = list(values)
        self.calls = 0

    async def execute(self, _query):
        self.calls += 1
        value = self._values.pop(0) if self._values else None
        return _FakeResult(value)


def test_has_recovery_metrics_detects_any_signal():
    empty = GarminDailySummary(calendar_date=date(2026, 3, 2))
    assert _has_recovery_metrics(empty) is False

    with_sleep = GarminDailySummary(calendar_date=date(2026, 3, 1), sleep_score=78)
    assert _has_recovery_metrics(with_sleep) is True


@pytest.mark.asyncio
async def test_select_latest_summary_uses_latest_when_metrics_present():
    latest = GarminDailySummary(calendar_date=date(2026, 3, 2), body_battery_at_wake=65)
    fake_db = _FakeDB([latest])

    latest_summary, summary_for_metrics = await _select_latest_dashboard_summary(fake_db)

    assert latest_summary is latest
    assert summary_for_metrics is latest
    assert fake_db.calls == 1


@pytest.mark.asyncio
async def test_select_latest_summary_falls_back_when_latest_is_sparse():
    latest_sparse = GarminDailySummary(calendar_date=date(2026, 3, 2))
    fallback = GarminDailySummary(calendar_date=date(2026, 3, 1), sleep_score=72)
    fake_db = _FakeDB([latest_sparse, fallback])

    latest_summary, summary_for_metrics = await _select_latest_dashboard_summary(fake_db)

    assert latest_summary is latest_sparse
    assert summary_for_metrics is fallback
    assert fake_db.calls == 2


@pytest.mark.asyncio
async def test_select_latest_summary_keeps_latest_when_no_fallback_exists():
    latest_sparse = GarminDailySummary(calendar_date=date(2026, 3, 2))
    fake_db = _FakeDB([latest_sparse, None])

    latest_summary, summary_for_metrics = await _select_latest_dashboard_summary(fake_db)

    assert latest_summary is latest_sparse
    assert summary_for_metrics is latest_sparse
    assert fake_db.calls == 2
