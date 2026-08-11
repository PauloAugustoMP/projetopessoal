import pytest

from backend.domain import ClockSkewError, compute_missing_snapshot_dates


def test_returns_nothing_on_the_very_first_run() -> None:
    assert compute_missing_snapshot_dates(None, "2026-08-11") == []


def test_returns_nothing_if_the_app_was_already_opened_today() -> None:
    assert compute_missing_snapshot_dates("2026-08-11", "2026-08-11") == []


def test_fills_every_day_between_last_snapshot_and_today() -> None:
    result = compute_missing_snapshot_dates("2026-08-05", "2026-08-08")
    assert result == ["2026-08-06", "2026-08-07", "2026-08-08"]


def test_fills_correctly_across_a_month_boundary() -> None:
    result = compute_missing_snapshot_dates("2026-07-30", "2026-08-02")
    assert result == ["2026-07-31", "2026-08-01", "2026-08-02"]


def test_still_returns_full_list_after_several_weeks_offline() -> None:
    result = compute_missing_snapshot_dates("2026-07-01", "2026-07-15")
    assert len(result) == 14
    assert result[0] == "2026-07-02"
    assert result[-1] == "2026-07-15"


def test_raises_if_last_snapshot_is_in_the_future() -> None:
    with pytest.raises(ClockSkewError):
        compute_missing_snapshot_dates("2026-08-15", "2026-08-11")
