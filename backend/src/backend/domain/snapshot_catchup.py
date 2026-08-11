from datetime import date, timedelta


class ClockSkewError(Exception):
    def __init__(self, last_snapshot_date: str, today: str) -> None:
        super().__init__(
            f"Last snapshot date ({last_snapshot_date}) is later than today ({today}) "
            "-- inconsistent state, review before recalculating."
        )


def compute_missing_snapshot_dates(last_snapshot_date: str | None, today: str) -> list[str]:
    """On app startup, computes which days were left without a snapshot while the app was
    closed (docs/business-rules.md sections 8 and 2 -- same recalculation engine, now
    triggered by startup instead of a manual edit). `last_snapshot_date` comes from
    persisted state (the date of the last successfully processed snapshot). Returns the
    dates (ISO, ascending order) that need to be recalculated, including today.
    """
    if last_snapshot_date is None:
        # First ever run: there's no baseline date to know what was missed.
        # Today's snapshot is the normal job's responsibility, not a catch-up's.
        return []

    start = date.fromisoformat(last_snapshot_date)
    end = date.fromisoformat(today)

    if start > end:
        raise ClockSkewError(last_snapshot_date, today)

    missing_dates: list[str] = []
    cursor = start + timedelta(days=1)
    while cursor <= end:
        missing_dates.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return missing_dates
